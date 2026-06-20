import argparse
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from logging_config import setup_logging, get_logger
from scripts.generate_compose import upscale_video_with_frames

setup_logging()
logger = get_logger(__name__)


def main(video_path: str, scale_factor: float, output_path: str, frames_dir: str) -> int:
    video_path = os.path.abspath(str(video_path or "").strip())
    output_path = os.path.abspath(str(output_path or "").strip())
    frames_dir = os.path.abspath(str(frames_dir or "").strip())
    if not video_path or not os.path.isfile(video_path):
        print(f"Video tidak ditemukan: {video_path}")
        return 1
    if float(scale_factor) <= 1.0:
        print("Scale factor harus lebih besar dari 1.0")
        return 1
    try:
        upscale_video_with_frames(video_path, output_path, float(scale_factor), frames_dir)
    except Exception as e:
        logger.error("Upscale video gagal: %s", e)
        print(f"Upscale video gagal: {e}")
        return 1
    print(f"Upscale video selesai: {output_path}")
    print(f"Frame output: {frames_dir}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upscale video dan ekstrak frame PNG")
    parser.add_argument("--video", required=True, help="Path video sumber")
    parser.add_argument("--scale-factor", type=float, required=True, help="Scale factor, mis. 1.5 atau 2.0")
    parser.add_argument("--output", required=True, help="Path video output")
    parser.add_argument("--frames-dir", required=True, help="Folder output frame PNG")
    args = parser.parse_args()
    raise SystemExit(
        main(
            video_path=args.video,
            scale_factor=float(args.scale_factor),
            output_path=args.output,
            frames_dir=args.frames_dir,
        )
    )
