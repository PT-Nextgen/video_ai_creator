"""Generate music with Google Gemini API and Lyria 3 Pro."""

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output-music"
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL_ID = "lyria-3-pro-preview"
MAX_IMAGES = 10

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gemini.gemini_image import find_gemini_key


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    stem = re.sub(r"_+", "_", stem).strip("._")
    return stem or "lyria3_music"


def _read_image_input(image_path: str) -> dict:
    path = Path(image_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File gambar tidak ditemukan: {path}")
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise ValueError(f"Format gambar tidak didukung: {path.name}")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image", "mime_type": mime_type, "data": data}


def _extract_result(response_json: dict) -> tuple[bytes | None, str]:
    audio_data = None
    lyrics = []

    output_audio = response_json.get("output_audio")
    if isinstance(output_audio, dict):
        audio_data = output_audio.get("data")

    output_text = response_json.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        lyrics.append(output_text.strip())

    for step in response_json.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if step.get("type") not in {None, "model_output"}:
            continue
        for block in step.get("content") or []:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "audio" and block.get("data"):
                audio_data = block["data"]
            elif block_type == "text" and block.get("text"):
                lyrics.append(str(block["text"]).strip())

    if not audio_data:
        return None, "\n".join(dict.fromkeys(item for item in lyrics if item))
    try:
        return base64.b64decode(audio_data), "\n".join(dict.fromkeys(item for item in lyrics if item))
    except Exception as exc:
        raise RuntimeError(f"Data audio dari Lyria tidak valid: {exc}") from exc


def generate_music(
    prompt: str,
    duration_seconds: float,
    api_key: str,
    output_stem: str,
    image_paths: list[str] | None = None,
    timeout: int = 600,
) -> tuple[Path, Path | None]:
    if not prompt.strip():
        raise ValueError("Prompt wajib diisi.")
    if duration_seconds <= 0 or duration_seconds > 180:
        raise ValueError("Durasi harus lebih besar dari 0 dan maksimal 180 detik.")

    duration_instruction = (
        f"Durasi target musik adalah sekitar {duration_seconds:g} detik. "
        "Pertahankan struktur dan penutup agar sesuai dengan durasi tersebut."
    )
    full_prompt = f"{prompt.strip()}\n\n{duration_instruction}"

    image_paths = image_paths or []
    if len(image_paths) > MAX_IMAGES:
        raise ValueError(f"Maksimal {MAX_IMAGES} gambar referensi.")

    prompt_input: str | list[dict] = full_prompt
    if image_paths:
        prompt_input = [{"type": "text", "text": full_prompt}]
        prompt_input.extend(_read_image_input(path) for path in image_paths)

    payload = {"model": MODEL_ID, "input": prompt_input}
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    response = requests.post(API_URL, headers=headers, json=payload, timeout=timeout)
    if response.status_code >= 400:
        detail = response.text[:2000]
        raise RuntimeError(f"Lyria API error {response.status_code}: {detail}")

    try:
        response_json = response.json()
    except ValueError as exc:
        raise RuntimeError("Response Lyria bukan JSON yang valid.") from exc

    audio_bytes, lyrics = _extract_result(response_json)
    if not audio_bytes:
        raise RuntimeError(
            "Response Lyria tidak berisi audio. "
            f"Response ringkas: {json.dumps(response_json)[:1000]}"
        )

    stem = _safe_stem(output_stem)
    song_dir = OUTPUT_DIR / stem
    song_dir.mkdir(parents=True, exist_ok=True)
    audio_path = song_dir / f"{stem}.mp3"
    audio_path.write_bytes(audio_bytes)

    lyrics_path = None
    if lyrics:
        lyrics_path = song_dir / f"{stem}.lyrics.txt"
        lyrics_path.write_text(lyrics + "\n", encoding="utf-8")
    return audio_path, lyrics_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Membuat musik dengan Gemini API Lyria 3 Pro."
    )
    parser.add_argument(
        "--prompt",
        "-p",
        required=True,
        help="Prompt musik. Disarankan menyebut genre, mood, instrumen, tempo, dan struktur.",
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=float,
        required=True,
        help="Durasi target dalam detik, maksimal 180.",
    )
    parser.add_argument(
        "--output-name",
        "-o",
        default="lyria3_music",
        help="Judul/nama folder dan file output tanpa ekstensi. Default: lyria3_music.",
    )
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        help="Gambar referensi mood/style. Bisa diulang maksimal 10 kali.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout request dalam detik. Default: 600.",
    )
    args = parser.parse_args()

    api_key = find_gemini_key()
    if not api_key:
        print(
            "Gemini API key tidak ditemukan. Isi GEMINIKEY di keys.cfg "
            "atau gunakan environment variable GEMINI_API_KEY.",
            file=sys.stderr,
        )
        return 1

    try:
        audio_path, lyrics_path = generate_music(
            prompt=args.prompt,
            duration_seconds=args.duration,
            api_key=api_key,
            output_stem=args.output_name,
            image_paths=args.image,
            timeout=args.timeout,
        )
    except Exception as exc:
        print(f"Gagal membuat musik: {exc}", file=sys.stderr)
        return 1

    print(f"Musik berhasil dibuat: {audio_path}")
    if lyrics_path:
        print(f"Lirik berhasil disimpan: {lyrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
