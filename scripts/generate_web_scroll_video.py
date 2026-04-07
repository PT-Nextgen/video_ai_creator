import argparse
from io import BytesIO
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import imageio
import numpy as np
from PIL import Image
from PIL import Image as PILImage

from logging_config import write_log


API_PRODUCTION_ROOT = Path(__file__).resolve().parent.parent / "api_production"
SUPERSAMPLE_FACTOR = 6
INTERNAL_SCROLL_FPS = 30
SPEED_TO_PPS = {
    1: 90.0,
    2: 140.0,
    3: 200.0,
    4: 270.0,
    5: 350.0,
}


def is_valid_http_url(value: str):
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_one_decimal_step(value: float):
    return abs((value * 10.0) - round(value * 10.0)) < 1e-9


def _start_playwright_with_retry(sync_playwright_func, retries=7):
    last_error = None
    for attempt in range(retries + 1):
        manager = sync_playwright_func()
        try:
            return manager.start()
        except Exception as e:
            last_error = e
            try:
                manager.stop()
            except Exception:
                pass
            if attempt < retries:
                time.sleep(min(2.5, 0.6 * (attempt + 1)))
                continue
    raise RuntimeError(f"Gagal inisialisasi Playwright setelah {retries + 1} percobaan: {last_error}")


def _prepare_pan_source_image(
    src_path: Path,
    dst_path: Path,
    width: int,
    height: int,
):
    internal_w = max(1, width * SUPERSAMPLE_FACTOR)
    internal_h = max(1, height * SUPERSAMPLE_FACTOR)
    with Image.open(src_path) as im:
        src = im.convert("RGB")
        src_w, src_h = src.size
        if src_w <= 0 or src_h <= 0:
            raise RuntimeError("Screenshot website tidak valid (ukuran 0).")

        scale = internal_w / float(src_w)
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))
        resized = src.resize((new_w, new_h), resample=Image.LANCZOS)

        canvas_h = max(internal_h, new_h)
        canvas = Image.new("RGB", (internal_w, canvas_h), (0, 0, 0))
        paste_x = (internal_w - new_w) // 2
        canvas.paste(resized, (paste_x, 0))
        canvas.save(dst_path, format="PNG")
    return internal_w, internal_h, canvas_h


def _speed_level_to_pps(speed: int):
    try:
        level = int(speed)
    except Exception:
        level = 1
    return float(SPEED_TO_PPS.get(level, SPEED_TO_PPS[1]))


def _resize_cover_rgb(src: Image.Image, target_w: int, target_h: int):
    src_w, src_h = src.size
    if src_w <= 0 or src_h <= 0:
        raise RuntimeError("Ukuran frame screenshot tidak valid.")
    scale = max(target_w / float(src_w), target_h / float(src_h))
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    resized = src.resize((new_w, new_h), resample=Image.LANCZOS)
    left = max(0, (new_w - target_w) // 2)
    top = max(0, (new_h - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def _build_scroll_positions(frames_total: int, max_y: int, speed: int, fps: int, pps_multiplier: float = 1.0):
    if frames_total <= 1 or max_y <= 0:
        return [0.0] * max(1, frames_total)
    fps_safe = float(max(fps, 1))
    duration_seconds = max(1.0 / fps_safe, frames_total / fps_safe)
    internal_frames = max(2, int(round(duration_seconds * INTERNAL_SCROLL_FPS)))

    internal_values = [0.0]
    pps = _speed_level_to_pps(speed) * float(max(0.0001, pps_multiplier))
    total_scroll = min(float(max_y), pps * duration_seconds)
    internal_step = total_scroll / float(internal_frames - 1)
    acc = 0.0
    for _ in range(1, internal_frames):
        acc += internal_step
        y = min(float(max_y), max(0.0, acc))
        if y < internal_values[-1]:
            y = internal_values[-1]
        internal_values.append(y)

    if frames_total == 1:
        return [internal_values[-1]]
    out = []
    for i in range(frames_total):
        t = i / float(frames_total - 1)
        idx = int(round(t * (internal_frames - 1)))
        idx = max(0, min(idx, internal_frames - 1))
        out.append(internal_values[idx])
    return out


def _render_pan_video_from_image(input_image: Path, out_video: Path, width: int, height: int, duration_seconds: float, speed: int, fps: int, internal_w: int, internal_h: int, canvas_h: int):
    frames_total = max(1, int(round(duration_seconds * fps)))
    max_y = max(0, canvas_h - internal_h)
    y_positions = _build_scroll_positions(
        frames_total,
        max_y,
        speed,
        fps,
        pps_multiplier=float(SUPERSAMPLE_FACTOR),
    )
    writer = imageio.get_writer(
        str(out_video),
        fps=fps,
        codec="libx264",
        ffmpeg_params=["-crf", "18", "-preset", "veryfast"],
        macro_block_size=None,
    )
    try:
        with Image.open(input_image) as im:
            src = im.convert("RGB")
            src_arr = np.asarray(src, dtype=np.uint8)
            for y in y_positions:
                y0 = int(round(y))
                y0 = max(0, min(y0, max_y))
                crop_arr = src_arr[y0:y0 + internal_h, 0:internal_w, :]
                crop_img = Image.fromarray(crop_arr, mode="RGB")
                frame = crop_img.resize((width, height), resample=Image.LANCZOS)
                writer.append_data(np.asarray(frame, dtype=np.uint8))
    finally:
        writer.close()


def _render_live_capture_video(page, out_video: Path, width: int, height: int, duration_seconds: float, speed: int, fps: int):
    frames_total = max(1, int(round(duration_seconds * fps)))
    max_scroll = int(
        page.evaluate(
            "() => Math.max(0, document.documentElement.scrollHeight - window.innerHeight)"
        )
    )
    y_positions = _build_scroll_positions(frames_total, max_scroll, speed, fps)
    writer = imageio.get_writer(
        str(out_video),
        fps=fps,
        codec="libx264",
        ffmpeg_params=["-crf", "18", "-preset", "veryfast"],
        macro_block_size=None,
    )
    try:
        for y in y_positions:
            page.evaluate("(v) => window.scrollTo(0, v)", int(round(y)))
            page.wait_for_timeout(12)
            image_bytes = page.screenshot(full_page=False, type="png")
            # Convert screenshot bytes to RGB frame and fit target canvas without stretching.
            with Image.open(BytesIO(image_bytes)) as shot:
                src = shot.convert("RGB")
                src_w, src_h = src.size
                if src_w != width or src_h != height:
                    # Fill target frame without black bars by cover-resize + center-crop.
                    frame = np.asarray(_resize_cover_rgb(src, width, height), dtype=np.uint8)
                else:
                    frame = np.asarray(src, dtype=np.uint8)
            writer.append_data(frame)
    finally:
        writer.close()


def generate_web_scroll_video(scene_dir, url, width, height, duration_seconds, speed, fps=16, capture_mode="live_capture"):
    scene_dir_path = Path(scene_dir)
    if not is_valid_http_url(str(url).strip()):
        raise ValueError("URL web_scroll tidak valid. Gunakan format http:// atau https://")
    width = int(width)
    height = int(height)
    duration_seconds = float(duration_seconds)
    speed = int(speed)
    fps = int(fps)
    if width <= 0 or height <= 0:
        raise ValueError("Ukuran video web_scroll harus lebih besar dari 0.")
    if duration_seconds < 0 or duration_seconds > 20:
        raise ValueError("Durasi web_scroll harus di antara 0.0 sampai 20.0 detik.")
    if not _is_one_decimal_step(duration_seconds):
        raise ValueError("Durasi web_scroll harus kelipatan 0.1 detik (1 angka di belakang koma).")
    if speed < 1 or speed > 5:
        raise ValueError("Speed web_scroll harus di antara 1 sampai 5.")
    if fps <= 0:
        raise ValueError("FPS web_scroll harus lebih besar dari 0.")
    capture_mode = str(capture_mode or "live_capture").strip()
    if capture_mode not in {"stable_pan", "live_capture"}:
        raise ValueError("Mode capture web_scroll tidak valid. Gunakan `stable_pan` atau `live_capture`.")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError(
            "Playwright belum terpasang di environment aktif. Install dulu dengan: "
            '".\\.venv\\Scripts\\python.exe -m pip install playwright" lalu '
            '".\\.venv\\Scripts\\python.exe -m playwright install chromium"'
        ) from e

    output_name = f"web_scroll_{int(datetime.utcnow().timestamp())}.mp4"
    output_path = scene_dir_path / output_name
    is_portrait_output = height >= width

    write_log(
        f"Generating web_scroll video: url={url}, size={width}x{height}, "
        f"duration={duration_seconds}s, speed={speed}, fps={fps}, mode={capture_mode}"
    )

    pw = None
    browser = None
    context = None
    mobile_viewport_w = width
    mobile_viewport_h = height
    mobile_device_scale = 2
    fullpage_path = None
    pan_source_path = None
    tmpdir_obj = None
    try:
        tmpdir_obj = tempfile.TemporaryDirectory(prefix="webscroll_")
        tmpdir = Path(tmpdir_obj.name)
        fullpage_path = tmpdir / "web_fullpage.png"
        pan_source_path = tmpdir / "web_pan_source.png"

        # Explicit start/stop with retry for transient driver init failures.
        pw = _start_playwright_with_retry(sync_playwright, retries=2)
        browser = pw.chromium.launch(headless=True)
        if is_portrait_output:
            # Portrait output: mobile browser emulation.
            context = browser.new_context(
                viewport={"width": mobile_viewport_w, "height": mobile_viewport_h},
                is_mobile=True,
                has_touch=True,
                device_scale_factor=mobile_device_scale,
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                    "Mobile/15E148 Safari/604.1"
                ),
                ignore_https_errors=True,
            )
        else:
            # Landscape output: desktop browser (non-mobile).
            context = browser.new_context(
                viewport={"width": width, "height": height},
                ignore_https_errors=True,
            )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(1200)
        # Freeze most animations so captured frames look stable.
        page.add_style_tag(
            content=(
                "html, body { scrollbar-gutter: stable both-edges !important; "
                "overscroll-behavior: none !important; } "
                "* { animation: none !important; transition: none !important; "
                "scroll-behavior: auto !important; caret-color: transparent !important; }"
            )
        )
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(250)
        if capture_mode == "stable_pan":
            page.screenshot(path=str(fullpage_path), full_page=True, type="png")
            try:
                internal_w, internal_h, canvas_h = _prepare_pan_source_image(
                    src_path=fullpage_path,
                    dst_path=pan_source_path,
                    width=width,
                    height=height,
                )
                _render_pan_video_from_image(
                    input_image=pan_source_path,
                    out_video=output_path,
                    width=width,
                    height=height,
                    duration_seconds=duration_seconds,
                    speed=speed,
                    fps=fps,
                    internal_w=internal_w,
                    internal_h=internal_h,
                    canvas_h=canvas_h,
                )
            except PILImage.DecompressionBombError:
                write_log(
                    "Stable pan fallback ke live_capture karena full-page screenshot terlalu besar "
                    "(Pillow decompression bomb protection)."
                )
                _render_live_capture_video(
                    page=page,
                    out_video=output_path,
                    width=width,
                    height=height,
                    duration_seconds=duration_seconds,
                    speed=speed,
                    fps=fps,
                )
        else:
            _render_live_capture_video(
                page=page,
                out_video=output_path,
                width=width,
                height=height,
                duration_seconds=duration_seconds,
                speed=speed,
                fps=fps,
            )
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass
        if tmpdir_obj is not None:
            tmpdir_obj.cleanup()

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Gagal membuat video web_scroll: {output_path}")
    write_log(f"Created web_scroll video: {output_path}")
    return str(output_path)


def _main():
    parser = argparse.ArgumentParser(description="Generate web_scroll video for a scene")
    parser.add_argument("--project", "-p", required=True, help="Nama project di api_production")
    parser.add_argument("--scene", "-S", required=True, help="Nama scene, mis. scene_1")
    parser.add_argument("--url", required=True, help="URL website dengan http/https")
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--duration", type=float, default=5.0, help="Durasi detik (0.0-20.0, kelipatan 0.1)")
    parser.add_argument("--speed", type=int, default=1, help="Speed scroll (1-5)")
    parser.add_argument("--fps", type=int, default=16, help="FPS output")
    parser.add_argument("--mode", default="live_capture", help="Mode capture: stable_pan atau live_capture")
    args = parser.parse_args()

    scene_dir = API_PRODUCTION_ROOT / args.project / args.scene
    if not scene_dir.exists():
        raise FileNotFoundError(f"Scene folder tidak ditemukan: {scene_dir}")
    generate_web_scroll_video(
        scene_dir=scene_dir,
        url=args.url,
        width=args.width,
        height=args.height,
        duration_seconds=args.duration,
        speed=args.speed,
        fps=args.fps,
        capture_mode=args.mode,
    )


if __name__ == "__main__":
    _main()
