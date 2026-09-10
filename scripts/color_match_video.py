"""Match the color distribution of every video frame to the first frame.

Example:
    .venv\\Scripts\\python.exe scripts\\color_match_video.py \\
        --project ohyes --scene 3
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILENAME = "minimax_h3_i2v_panjang_final.mp4"


def _default_input(project: str, scene: str) -> Path:
    return ROOT / "api_production" / project / f"scene_{scene}" / DEFAULT_FILENAME


def _color_statistics(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB).astype(np.float32)
    mean, std = cv2.meanStdDev(lab)
    return mean.reshape(3), np.maximum(std.reshape(3), 1.0)


def _match_frame(
    frame: np.ndarray,
    reference_mean: np.ndarray,
    reference_std: np.ndarray,
    strength: float,
) -> np.ndarray:
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB).astype(np.float32)
    source_mean, source_std = _color_statistics(frame)
    matched_lab = (lab - source_mean) * (reference_std / source_std) + reference_mean
    matched_lab = np.clip(matched_lab, 0, 255).astype(np.uint8)
    matched = cv2.cvtColor(matched_lab, cv2.COLOR_LAB2BGR)
    if strength < 1.0:
        matched = cv2.addWeighted(frame, 1.0 - strength, matched, strength, 0.0)
    return matched


def color_match_video(input_path: Path, output_path: Path, strength: float = 1.0) -> int:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Input video tidak ditemukan: {input_path}")
    if input_path == output_path:
        raise ValueError("Output harus berbeda dari input agar video asli tetap aman.")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        raise RuntimeError(f"Video tidak dapat dibuka: {input_path}")

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if fps <= 0 or width <= 0 or height <= 0:
        capture.release()
        raise RuntimeError("Metadata video tidak valid: FPS atau resolusi tidak ditemukan.")

    ok, first_frame = capture.read()
    if not ok or first_frame is None:
        capture.release()
        raise RuntimeError("Frame pertama tidak dapat dibaca.")

    reference_mean, reference_std = _color_statistics(first_frame)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    temporary_output = output_path.with_name(output_path.stem + ".__color_match_tmp__.mp4")
    if temporary_output.exists():
        temporary_output.unlink()

    command = [
        ffmpeg,
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", f"{width}x{height}",
        "-r", f"{fps:.12g}",
        "-i", "pipe:0",
        "-i", str(input_path),
        "-map", "0:v:0",
        "-map", "1:a?",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(temporary_output),
    ]

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        # Do not pipe FFmpeg stderr: a long encode can fill the pipe and
        # deadlock while Python is still writing raw frames.
        stderr=subprocess.DEVNULL,
    )
    frame_count = 0
    try:
        assert process.stdin is not None
        process.stdin.write(first_frame.tobytes())
        frame_count = 1
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            process.stdin.write(
                _match_frame(frame, reference_mean, reference_std, strength).tobytes()
            )
            frame_count += 1
            if frame_count % 30 == 0:
                print(f"Processed {frame_count} frames...", flush=True)
        process.stdin.close()
        process.stdin = None
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        return_code = process.wait()
    except BrokenPipeError as exc:
        process.kill()
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        process.wait()
        raise RuntimeError(f"FFmpeg berhenti saat menulis frame: {stderr[-1000:]}") from exc
    finally:
        capture.release()
        if process.stdin is not None:
            process.stdin.close()

    if return_code != 0 or not temporary_output.exists() or temporary_output.stat().st_size == 0:
        if temporary_output.exists():
            temporary_output.unlink()
        raise RuntimeError(f"FFmpeg gagal membuat output:\n{stderr[-2000:]}")
    os.replace(temporary_output, output_path)
    print(f"Selesai: {frame_count} frame diproses")
    print(f"Output: {output_path}")
    return frame_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Color match semua frame video terhadap frame pertama, sambil mempertahankan audio."
    )
    parser.add_argument("--project", default="ohyes", help="Nama folder project di api_production/ (default: ohyes)")
    parser.add_argument("--scene", default="3", help="Nomor scene (default: 3)")
    parser.add_argument("--input", type=Path, help="Path video input; mengesampingkan --project/--scene")
    parser.add_argument("--output", type=Path, help="Path output; default: <input>_color_matched.mp4")
    parser.add_argument(
        "--strength",
        type=float,
        default=1.0,
        help="Kekuatan color match dari 0 sampai 1 (default: 1.0)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0.0 <= args.strength <= 1.0:
        raise ValueError("--strength harus berada di antara 0 dan 1.")
    input_path = args.input.resolve() if args.input else _default_input(args.project, args.scene)
    output_path = args.output.resolve() if args.output else input_path.with_name(input_path.stem + "_color_matched.mp4")
    color_match_video(input_path, output_path, strength=args.strength)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
