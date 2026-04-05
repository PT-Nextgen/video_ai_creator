import base64
import io
import json
import os
import time
from typing import Optional

import requests
from PIL import Image

from logging_config import write_log

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_GEMINI_FLASH_05K = "gemini-3.1-flash-image-preview"
MODEL_GEMINI_FALLBACKS = (
    MODEL_GEMINI_FLASH_05K,
    "gemini-2.5-flash-image-preview",
)


def is_gemini_prompt(z_prompt: dict | None = None) -> bool:
    z_prompt = z_prompt or {}
    model = str(z_prompt.get("image_model", "")).strip().lower()
    json_api = str(z_prompt.get("json_api", "")).strip().lower()
    return model == MODEL_GEMINI_FLASH_05K or json_api == "gemini_flash_05k"


def get_model_key(z_prompt: dict | None = None) -> str:
    return MODEL_GEMINI_FLASH_05K if is_gemini_prompt(z_prompt) else ""


def find_gemini_key() -> Optional[str]:
    cfg_path = os.path.join(ROOT, "keys.cfg")
    if not os.path.exists(cfg_path):
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    wanted = {"GEMINIKEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"}
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip().upper() in wanted:
                    return value.strip()
    except Exception:
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "1:1"
    from math import gcd

    g = gcd(width, height)
    return f"{width // g}:{height // g}"


def _extract_image_bytes(response_json: dict) -> Optional[bytes]:
    candidates = response_json.get("candidates") or []
    for cand in candidates:
        content = cand.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline_data, dict):
                continue
            data = inline_data.get("data")
            if not data:
                continue
            try:
                return base64.b64decode(data)
            except Exception:
                continue
    return None


def _center_cover_resize(src_path: str, dst_path: str, target_width: int, target_height: int):
    with Image.open(src_path) as im:
        im = im.convert("RGB")
        src_w, src_h = im.size
        scale = max(target_width / float(src_w), target_height / float(src_h))
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))
        resized = im.resize((new_w, new_h), resample=Image.LANCZOS)

        left = max(0, (new_w - target_width) // 2)
        top = max(0, (new_h - target_height) // 2)
        right = left + target_width
        bottom = top + target_height
        cropped = resized.crop((left, top, right, bottom))
        cropped.save(dst_path, format="PNG")


def _call_gemini_generate_image(prompt: str, api_key: str, model_name: str, aspect_ratio: str) -> bytes:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
        },
        "imageConfig": {
            "imageSize": "0.5K",
            "aspectRatio": aspect_ratio,
        },
    }

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
    if resp.status_code >= 400:
        # Fallback for APIs that do not accept imageConfig fields yet.
        fallback_payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE", "TEXT"],
            },
        }
        resp = requests.post(url, headers=headers, data=json.dumps(fallback_payload), timeout=120)
    resp.raise_for_status()

    result = resp.json()
    image_bytes = _extract_image_bytes(result)
    if image_bytes:
        return image_bytes
    raise RuntimeError(f"Gemini response has no image data: {json.dumps(result)[:500]}")


def generate_scene_image(scene_dir: str, z_prompt: dict) -> str:
    api_key = find_gemini_key()
    if not api_key:
        raise RuntimeError(
            "Gemini API key tidak ditemukan. Tambahkan GEMINIKEY / GEMINI_API_KEY / GOOGLE_API_KEY di keys.cfg."
        )

    prompt = str(z_prompt.get("positive_prompt", "")).strip()
    if not prompt:
        raise RuntimeError("Prompt positif Gemini wajib diisi.")

    try:
        target_width = int(z_prompt.get("width", 480))
    except (TypeError, ValueError):
        target_width = 480
    try:
        target_height = int(z_prompt.get("height", 848))
    except (TypeError, ValueError):
        target_height = 848

    if target_width <= 0 or target_height <= 0:
        raise RuntimeError("Ukuran target Gemini tidak valid.")

    aspect_ratio = _aspect_ratio(target_width, target_height)
    last_error = None
    image_bytes = None
    used_model = MODEL_GEMINI_FLASH_05K
    for model_name in MODEL_GEMINI_FALLBACKS:
        try:
            image_bytes = _call_gemini_generate_image(prompt, api_key, model_name, aspect_ratio)
            used_model = model_name
            break
        except Exception as e:
            last_error = e

    if not image_bytes:
        raise RuntimeError(f"Gagal generate Gemini image: {last_error}")

    timestamp = int(time.time())
    raw_name = f"Gemini_raw_{timestamp}.png"
    final_name = f"Gemini_{timestamp}.png"
    raw_path = os.path.join(scene_dir, raw_name)
    final_path = os.path.join(scene_dir, final_name)

    with Image.open(io.BytesIO(image_bytes)) as img:
        img.convert("RGB").save(raw_path, format="PNG")

    _center_cover_resize(raw_path, final_path, target_width, target_height)
    try:
        os.remove(raw_path)
    except OSError:
        pass

    write_log(
        f"Gemini image saved to {final_path} (model={used_model}, target={target_width}x{target_height}, mode=scale+crop)"
    )
    return final_path
