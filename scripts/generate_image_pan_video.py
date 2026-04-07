import argparse
import tempfile
from datetime import datetime
from pathlib import Path

import imageio
import numpy as np
from PIL import Image

from logging_config import write_log


API_PRODUCTION_ROOT = Path(__file__).resolve().parent.parent / "api_production"
SUPERSAMPLE_FACTOR = 6


def _build_pan_positions_full_span(frames_total: int, max_x: int):
    if frames_total <= 1 or max_x <= 0:
        return [0.0] * max(1, frames_total)
    return [(float(i) / float(frames_total - 1)) * float(max_x) for i in range(frames_total)]


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
            raise RuntimeError("Gambar sumber image_pan tidak valid (ukuran 0).")

        # Keep full source height visible in output by fitting to target height.
        scale = internal_h / float(src_h)
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))
        resized = src.resize((new_w, new_h), resample=Image.LANCZOS)

        canvas_w = max(internal_w, new_w)
        canvas = Image.new("RGB", (canvas_w, internal_h), (0, 0, 0))
        canvas.paste(resized, (0, 0))
        canvas.save(dst_path, format="PNG")
    return internal_w, internal_h, canvas_w


def _render_image_pan_video_from_source(
    input_image: Path,
    out_video: Path,
    width: int,
    height: int,
    duration_seconds: float,
    fps: int,
    direction: str,
    capture_mode: str,
):
    if capture_mode not in {"live_capture", "stable_pan"}:
        raise ValueError("Mode capture image_pan tidak valid. Gunakan `stable_pan` atau `live_capture`.")

    if capture_mode == "stable_pan":
        supersample = SUPERSAMPLE_FACTOR
        resample = Image.LANCZOS
    else:
        supersample = 1
        resample = Image.BILINEAR

    internal_w = max(1, width * supersample)
    internal_h = max(1, height * supersample)
    frames_total = max(1, int(round(duration_seconds * fps)))

    with Image.open(input_image) as im:
        src = im.convert("RGB")
        src_w, src_h = src.size
        if src_w <= 0 or src_h <= 0:
            raise RuntimeError("Gambar sumber image_pan tidak valid (ukuran 0).")

        # Keep full source height visible in output by fitting to target height.
        scale = internal_h / float(src_h)
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))
        resized = src.resize((new_w, new_h), resample=resample)
        src_arr = np.asarray(resized, dtype=np.uint8)

    max_x = max(0, new_w - internal_w)
    # Requirement: pan must always complete side-to-side within the given duration.
    x_positions = _build_pan_positions_full_span(frames_total, max_x)
    if direction == "from_right":
        x_positions = [float(max_x) - x for x in x_positions]

    writer = imageio.get_writer(
        str(out_video),
        fps=fps,
        codec="libx264",
        ffmpeg_params=["-crf", "18", "-preset", "veryfast"],
        macro_block_size=None,
    )
    try:
        for x in x_positions:
            x0 = int(round(x))
            x0 = max(0, min(x0, max_x))
            crop_arr = src_arr[0:internal_h, x0:x0 + internal_w, :]
            crop_img = Image.fromarray(crop_arr)
            frame = crop_img.resize((width, height), resample=Image.LANCZOS)
            writer.append_data(np.asarray(frame, dtype=np.uint8))
    finally:
        writer.close()


def generate_image_pan_video(
    scene_dir,
    image_path,
    width,
    height,
    duration_seconds,
    direction="from_right",
    fps=16,
    capture_mode="live_capture",
):
    scene_dir_path = Path(scene_dir)
    image_path = Path(image_path)
    width = int(width)
    height = int(height)
    duration_seconds = float(duration_seconds)
    fps = int(fps)
    direction = str(direction or "from_right").strip()
    capture_mode = str(capture_mode or "live_capture").strip()

    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"Gambar image_pan tidak ditemukan: {image_path}")
    if width <= 0 or height <= 0:
        raise ValueError("Ukuran video image_pan harus lebih besar dari 0.")
    if height <= width:
        raise ValueError("Ukuran image_pan harus portrait (tinggi > lebar).")
    if duration_seconds <= 0:
        raise ValueError("Durasi image_pan harus lebih besar dari 0 detik.")
    if fps <= 0:
        raise ValueError("FPS image_pan harus lebih besar dari 0.")
    if direction not in {"from_right", "from_left"}:
        raise ValueError("Arah image_pan tidak valid. Gunakan `from_right` atau `from_left`.")
    if capture_mode not in {"stable_pan", "live_capture"}:
        raise ValueError("Mode capture image_pan tidak valid. Gunakan `stable_pan` atau `live_capture`.")

    output_name = f"image_pan_{int(datetime.utcnow().timestamp())}.mp4"
    output_path = scene_dir_path / output_name
    write_log(
        f"Generating image_pan video: image={image_path.name}, size={width}x{height}, "
        f"duration={duration_seconds}s, direction={direction}, fps={fps}, mode={capture_mode}"
    )

    tmpdir_obj = None
    pan_source_path = None
    try:
        tmpdir_obj = tempfile.TemporaryDirectory(prefix="imagepan_")
        pan_source_path = Path(tmpdir_obj.name) / "image_pan_source.png"
        if capture_mode == "stable_pan":
            _prepare_pan_source_image(
                src_path=image_path,
                dst_path=pan_source_path,
                width=width,
                height=height,
            )
            source_for_render = pan_source_path
        else:
            source_for_render = image_path
        _render_image_pan_video_from_source(
            input_image=source_for_render,
            out_video=output_path,
            width=width,
            height=height,
            duration_seconds=duration_seconds,
            fps=fps,
            direction=direction,
            capture_mode=capture_mode,
        )
    finally:
        if tmpdir_obj is not None:
            tmpdir_obj.cleanup()

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Gagal membuat video image_pan: {output_path}")
    write_log(f"Created image_pan video: {output_path}")
    return str(output_path)


def _main():
    parser = argparse.ArgumentParser(description="Generate image_pan video for a scene")
    parser.add_argument("--project", "-p", required=True, help="Nama project di api_production")
    parser.add_argument("--scene", "-S", required=True, help="Nama scene, mis. scene_1")
    parser.add_argument("--image", required=True, help="Path file gambar sumber")
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--duration", type=float, default=5.0, help="Durasi detik (0.0-20.0, kelipatan 0.1)")
    parser.add_argument("--direction", default="from_right", help="Arah pan: from_right atau from_left")
    parser.add_argument("--fps", type=int, default=16, help="FPS output")
    parser.add_argument("--mode", default="live_capture", help="Mode capture: stable_pan atau live_capture")
    args = parser.parse_args()

    scene_dir = API_PRODUCTION_ROOT / args.project / args.scene
    if not scene_dir.exists():
        raise FileNotFoundError(f"Scene folder tidak ditemukan: {scene_dir}")
    generate_image_pan_video(
        scene_dir=scene_dir,
        image_path=args.image,
        width=args.width,
        height=args.height,
        duration_seconds=args.duration,
        direction=args.direction,
        fps=args.fps,
        capture_mode=args.mode,
    )


if __name__ == "__main__":
    _main()
