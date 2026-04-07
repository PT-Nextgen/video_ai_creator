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

MODEL_GEMINI_IMAGE = "gemini"
MODEL_GEMINI_FLASH_05K = "gemini-3.1-flash-image-preview"
GEMINI_IMAGE_SIZE = "1K"
MODEL_GEMINI_FALLBACKS = (
    MODEL_GEMINI_FLASH_05K,
    "gemini-2.5-flash-image-preview",
)


def is_gemini_prompt(z_prompt: dict | None = None) -> bool:
    z_prompt = z_prompt or {}
    model = str(z_prompt.get("image_model", "")).strip().lower()
    json_api = str(z_prompt.get("json_api", "")).strip().lower()
    return (
        model == MODEL_GEMINI_IMAGE
        or
        model == MODEL_GEMINI_FLASH_05K
        or json_api == "gemini_flash_05k"
        or (model.startswith("gemini-") and "image" in model)
    )


def get_model_key(z_prompt: dict | None = None) -> str:
    return MODEL_GEMINI_IMAGE if is_gemini_prompt(z_prompt) else ""


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
    supported = ("1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9")
    target = width / float(height)
    best = "1:1"
    best_delta = float("inf")
    for ratio in supported:
        a, b = ratio.split(":")
        r = float(a) / float(b)
        delta = abs(target - r)
        if delta < best_delta:
            best = ratio
            best_delta = delta
    return best


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
            "imageConfig": {
                "imageSize": GEMINI_IMAGE_SIZE,
                "aspectRatio": aspect_ratio,
            },
        },
    }

    # Strict fixed-size mode: never retry without imageConfig to avoid unintended higher-cost sizes.
    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
    if resp.status_code >= 400:
        body = resp.text[:1200]
        raise requests.HTTPError(
            f"{resp.status_code} Client Error for model {model_name}: {body}",
            response=resp,
        )

    result = resp.json()
    image_bytes = _extract_image_bytes(result)
    if image_bytes:
        return image_bytes
    raise RuntimeError(f"Gemini response has no image data: {json.dumps(result)[:500]}")


def _list_available_model_ids(api_key: str) -> list[str]:
    """Read model catalog from Gemini API and return model ids without 'models/' prefix."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    out: list[str] = []
    page_token: Optional[str] = None
    for _ in range(10):
        params = {"pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code >= 400:
            break
        data = resp.json()
        for model in data.get("models", []):
            methods = model.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            name = str(model.get("name", "")).strip()
            if not name:
                continue
            if name.startswith("models/"):
                name = name.split("/", 1)[1]
            out.append(name)
        page_token = str(data.get("nextPageToken", "")).strip() or None
        if not page_token:
            break
    # preserve order while removing duplicates
    seen = set()
    unique = []
    for name in out:
        if name in seen:
            continue
        seen.add(name)
        unique.append(name)
    return unique


def _build_gemini_image_candidates(api_key: str) -> list[str]:
    discovered = _list_available_model_ids(api_key)

    def is_image_like(name: str) -> bool:
        n = name.lower()
        return (
            n.startswith("gemini-")
            and ("image" in n or "vision" in n)
            and "embedding" not in n
        )

    def is_halfk_image_model(name: str) -> bool:
        # Practical heuristic requested by user:
        # show only "0.5K-style" image preview models.
        # These are typically published with "image-preview" naming.
        n = name.lower()
        return "image-preview" in n

    discovered_image = [m for m in discovered if is_image_like(m) and is_halfk_image_model(m)]
    preferred_present = [m for m in MODEL_GEMINI_FALLBACKS if m in discovered_image]
    merged = preferred_present + discovered_image
    seen = set()
    result = []
    for name in merged:
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def list_gemini_image_models(api_key: str | None = None) -> list[str]:
    """Return available Gemini image-capable model ids for UI selection."""
    key = api_key or find_gemini_key()
    if not key:
        return list(MODEL_GEMINI_FALLBACKS)
    try:
        models = _build_gemini_image_candidates(key)
    except Exception:
        models = []
    return models or list(MODEL_GEMINI_FALLBACKS)


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
    errors = []
    image_bytes = None
    used_model = MODEL_GEMINI_FLASH_05K
    requested_model = str(z_prompt.get("gemini_model_id", "")).strip()
    candidate_models = _build_gemini_image_candidates(api_key)
    if requested_model:
        candidate_models = [requested_model] + [m for m in candidate_models if m != requested_model]
    for model_name in candidate_models:
        try:
            image_bytes = _call_gemini_generate_image(prompt, api_key, model_name, aspect_ratio)
            used_model = model_name
            break
        except Exception as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code == 429:
                raise RuntimeError(
                    "Gemini API quota/rate limit tercapai (429). "
                    "Tunggu beberapa saat atau gunakan API key/project lain."
                ) from e
            if status_code == 400:
                msg = str(e).lower()
                if "invalid argument" in msg:
                    raise RuntimeError(
                        f"Mode strict {GEMINI_IMAGE_SIZE} tidak didukung oleh model Gemini yang tersedia di API key ini. "
                        "Gunakan model/key lain yang mendukung ukuran ini."
                    ) from e
            last_error = e
            errors.append(f"{model_name}: {e}")

    if not image_bytes:
        short_errors = "; ".join(errors[-4:]) if errors else str(last_error)
        raise RuntimeError(
            "Gagal generate Gemini image. Model image mungkin berubah/tidak aktif untuk API key ini. "
            f"Percobaan terakhir: {short_errors}"
        )

    timestamp = int(time.time())
    raw_name = f"Gemini_raw_{timestamp}.png"
    final_name = f"Gemini_{timestamp}.png"
    raw_dir = os.path.join(scene_dir, "gemini")
    os.makedirs(raw_dir, exist_ok=True)
    raw_path = os.path.join(raw_dir, raw_name)
    final_path = os.path.join(scene_dir, final_name)

    with Image.open(io.BytesIO(image_bytes)) as img:
        img.convert("RGB").save(raw_path, format="PNG")

    _center_cover_resize(raw_path, final_path, target_width, target_height)
    write_log(
        f"Gemini image saved to {final_path} (model={used_model}, request_size={GEMINI_IMAGE_SIZE}, "
        f"target={target_width}x{target_height}, mode=scale+crop, raw={raw_path})"
    )
    return final_path
