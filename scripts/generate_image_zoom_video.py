import argparse
import sys
import time
from pathlib import Path

import imageio
import numpy as np
from PIL import Image, ImageFilter

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from logging_config import write_log


API_PRODUCTION_ROOT = REPO_ROOT / "api_production"
LIVE_SUPERSAMPLE_FACTOR = 2
STABLE_SUPERSAMPLE_FACTOR = 2
MOTION_BLUR_KERNEL = ImageFilter.Kernel(
    (3, 3),
    [
        0.0, 0.0, 0.0,
        0.2, 0.6, 0.2,
        0.0, 0.0, 0.0,
    ],
    scale=1.0,
)

FOCAL_MAP = {
    "top_left": (0.0, 0.0),
    "top_center": (0.5, 0.0),
    "top_right": (1.0, 0.0),
    "center_left": (0.0, 0.5),
    "center": (0.5, 0.5),
    "center_right": (1.0, 0.5),
    "bottom_left": (0.0, 1.0),
    "bottom_center": (0.5, 1.0),
    "bottom_right": (1.0, 1.0),
}


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, t))


def _render_image_zoom_video_from_source(
    input_image: Path,
    out_video: Path,
    width: int,
    height: int,
    duration_seconds: float,
    fps: int,
    zoom_direction: str,
    focal_point: str,
    zoom_strength: float,
    capture_mode: str,
):
    if capture_mode not in {"stable_pan", "live_capture"}:
        raise ValueError("Mode capture image_zoom tidak valid. Gunakan `stable_pan` atau `live_capture`.")

    supersample = STABLE_SUPERSAMPLE_FACTOR if capture_mode == "stable_pan" else LIVE_SUPERSAMPLE_FACTOR
    resize_resample = Image.LANCZOS if capture_mode == "stable_pan" else Image.BICUBIC

    internal_w = max(1, width * supersample)
    internal_h = max(1, height * supersample)

    focal_norm = FOCAL_MAP.get(focal_point, FOCAL_MAP["center"])

    with Image.open(input_image) as im:
        src = im.convert("RGB")
        src_w, src_h = src.size
        if src_w <= 0 or src_h <= 0:
            raise RuntimeError("Gambar sumber image_zoom tidak valid (ukuran 0).")

    # Fit the source to cover the output once, then scale further for each zoom frame.
    base_scale = max(internal_w / float(src_w), internal_h / float(src_h))

    frames_total = max(1, int(round(duration_seconds * fps)))

    if zoom_direction == "in":
        start_scale = 1.0
        end_scale = zoom_strength
    else:
        start_scale = zoom_strength
        end_scale = 1.0

    writer = imageio.get_writer(
        str(out_video),
        fps=fps,
        codec="libx264",
        ffmpeg_params=["-crf", "18", "-preset", "veryfast"],
        macro_block_size=None,
    )
    try:
        for i in range(frames_total):
            t = float(i) / max(1.0, float(frames_total - 1))
            current_scale = _lerp(start_scale, end_scale, t)

            render_scale = base_scale * current_scale
            render_w = max(1, int(round(src_w * render_scale)))
            render_h = max(1, int(round(src_h * render_scale)))
            resized = src.resize((render_w, render_h), resample=resize_resample)

            # Keep the focal point anchored in the same relative position inside the crop.
            crop_w = internal_w
            crop_h = internal_h
            fx = focal_norm[0] * float(render_w)
            fy = focal_norm[1] * float(render_h)
            x0 = fx - (crop_w * focal_norm[0])
            y0 = fy - (crop_h * focal_norm[1])

            max_x = max(0.0, float(render_w - crop_w))
            max_y = max(0.0, float(render_h - crop_h))
            x0 = max(0.0, min(max_x, x0))
            y0 = max(0.0, min(max_y, y0))

            crop_img = resized.crop((x0, y0, x0 + crop_w, y0 + crop_h))
            crop_img = crop_img.filter(MOTION_BLUR_KERNEL)
            frame = crop_img.resize((width, height), resample=Image.LANCZOS)
            writer.append_data(np.asarray(frame, dtype=np.uint8))
    finally:
        writer.close()


def generate_image_zoom_video(
    scene_dir,
    image_path,
    width,
    height,
    duration_seconds,
    zoom_direction="in",
    focal_point="center",
    zoom_strength=1.3,
    fps=16,
    capture_mode="stable_pan",
):
    scene_dir_path = Path(scene_dir)
    image_path = Path(image_path)
    width = int(width)
    height = int(height)
    duration_seconds = float(duration_seconds)
    fps = int(fps)
    zoom_direction = str(zoom_direction or "in").strip()
    focal_point = str(focal_point or "center").strip()
    zoom_strength = float(zoom_strength)
    capture_mode = str(capture_mode or "stable_pan").strip()

    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"Gambar image_zoom tidak ditemukan: {image_path}")
    if width <= 0 or height <= 0:
        raise ValueError("Ukuran video image_zoom harus lebih besar dari 0.")
    if duration_seconds <= 0:
        raise ValueError("Durasi image_zoom harus lebih besar dari 0 detik.")
    if fps <= 0:
        raise ValueError("FPS image_zoom harus lebih besar dari 0.")
    if zoom_direction not in {"in", "out"}:
        raise ValueError("Arah zoom image_zoom tidak valid. Gunakan `in` atau `out`.")
    if focal_point not in FOCAL_MAP:
        raise ValueError(
            f"Titik fokus image_zoom tidak valid. Gunakan salah satu: {', '.join(sorted(FOCAL_MAP.keys()))}"
        )
    if zoom_strength < 1.0 or zoom_strength > 1.5:
        raise ValueError("Kekuatan zoom image_zoom harus di antara 1.0 sampai 1.5.")
    if capture_mode not in {"stable_pan", "live_capture"}:
        raise ValueError("Mode capture image_zoom tidak valid. Gunakan `stable_pan` atau `live_capture`.")

    output_name = f"image_zoom_{int(time.time())}.mp4"
    output_path = scene_dir_path / output_name
    write_log(
        f"Generating image_zoom video: image={image_path.name}, size={width}x{height}, "
        f"duration={duration_seconds}s, zoom={zoom_direction}, focal={focal_point}, "
        f"strength={zoom_strength}, fps={fps}, mode={capture_mode}"
    )

    _render_image_zoom_video_from_source(
        input_image=image_path,
        out_video=output_path,
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        fps=fps,
        zoom_direction=zoom_direction,
        focal_point=focal_point,
        zoom_strength=zoom_strength,
        capture_mode=capture_mode,
    )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Gagal membuat video image_zoom: {output_path}")
    write_log(f"Created image_zoom video: {output_path}")
    return str(output_path)


def _main():
    parser = argparse.ArgumentParser(description="Generate image_zoom video for a scene")
    parser.add_argument("--project", "-p", required=True, help="Nama project di api_production")
    parser.add_argument("--scene", "-S", required=True, help="Nama scene, mis. scene_1")
    parser.add_argument("--image", required=True, help="Path file gambar sumber")
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--duration", type=float, default=5.0, help="Durasi detik")
    parser.add_argument(
        "--zoom-direction", default="in", help="Arah zoom: in atau out"
    )
    parser.add_argument(
        "--focal-point", default="center",
        help="Titik fokus: center, top_left, top_center, top_right, center_left, center_right, bottom_left, bottom_center, bottom_right"
    )
    parser.add_argument("--zoom-strength", type=float, default=1.3, help="Kekuatan zoom (1.0-1.5)")
    parser.add_argument("--fps", type=int, default=16, help="FPS output")
    parser.add_argument("--mode", default="stable_pan", help="Mode capture: stable_pan atau live_capture")
    args = parser.parse_args()

    scene_dir = API_PRODUCTION_ROOT / args.project / args.scene
    if not scene_dir.exists():
        raise FileNotFoundError(f"Scene folder tidak ditemukan: {scene_dir}")
    generate_image_zoom_video(
        scene_dir=scene_dir,
        image_path=args.image,
        width=args.width,
        height=args.height,
        duration_seconds=args.duration,
        zoom_direction=args.zoom_direction,
        focal_point=args.focal_point,
        zoom_strength=args.zoom_strength,
        fps=args.fps,
        capture_mode=args.mode,
    )


if __name__ == "__main__":
    _main()
