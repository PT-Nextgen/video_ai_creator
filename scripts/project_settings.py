import copy
import json
from pathlib import Path

from z_image.z_image import DEFAULT_PROMPT as DEFAULT_Z_IMAGE_PROMPT

PROJECT_SETTINGS_FILE = "project_settings.json"
DEFAULT_PROJECT_VOICE_CONFIG = {
    "voice_provider": "gemini",
}
DEFAULT_PROJECT_CAPTION_CONFIG = {
    "generate_caption": True,
}

DEFAULT_PROJECT_SETTINGS = {
    "project_description": "",
    "comfyui_server": "nextgenserver:8188",
    "video_size": {
        "width": 480,
        "height": 848,
    },
    "prompt_generation": {
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite",
    },
    "translate": {
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite",
    },
    "voice": copy.deepcopy(DEFAULT_PROJECT_VOICE_CONFIG),
    "caption": copy.deepcopy(DEFAULT_PROJECT_CAPTION_CONFIG),
    "cover": copy.deepcopy(DEFAULT_Z_IMAGE_PROMPT),
}


def project_settings_path(project_dir: Path) -> Path:
    return project_dir / PROJECT_SETTINGS_FILE


def _normalize_size(value, fallback_w: int, fallback_h: int) -> tuple[int, int]:
    width = fallback_w
    height = fallback_h
    if isinstance(value, dict):
        try:
            width = int(value.get("width", fallback_w))
        except (TypeError, ValueError):
            width = fallback_w
        try:
            height = int(value.get("height", fallback_h))
        except (TypeError, ValueError):
            height = fallback_h
    if width <= 0 or height <= 0:
        return fallback_w, fallback_h
    return width, height


def _normalize_settings(data: dict | None) -> dict:
    merged = copy.deepcopy(DEFAULT_PROJECT_SETTINGS)
    if isinstance(data, dict):
        for key in ("project_description", "comfyui_server"):
            if key in data:
                merged[key] = str(data.get(key, "")).strip()
        for key in ("prompt_generation", "translate", "voice", "caption", "cover"):
            value = data.get(key)
            if isinstance(value, dict):
                merged[key].update(value)
        width, height = _normalize_size(
            data.get("video_size"),
            DEFAULT_PROJECT_SETTINGS["video_size"]["width"],
            DEFAULT_PROJECT_SETTINGS["video_size"]["height"],
        )
        merged["video_size"] = {"width": width, "height": height}

    merged["project_description"] = str(merged.get("project_description", "")).strip()
    merged["comfyui_server"] = str(
        merged.get("comfyui_server", DEFAULT_PROJECT_SETTINGS["comfyui_server"])
    ).strip() or DEFAULT_PROJECT_SETTINGS["comfyui_server"]
    for key in ("prompt_generation", "translate"):
        sub = merged.get(key) if isinstance(merged.get(key), dict) else {}
        provider = str(sub.get("provider", "gemini")).strip().lower()
        sub["provider"] = "gemini" if provider != "gemini" else provider
        model = str(sub.get("model", DEFAULT_PROJECT_SETTINGS[key]["model"])).strip()
        sub["model"] = model or DEFAULT_PROJECT_SETTINGS[key]["model"]
        merged[key] = sub

    voice = merged.get("voice") if isinstance(merged.get("voice"), dict) else {}
    caption = merged.get("caption") if isinstance(merged.get("caption"), dict) else {}
    merged["voice"] = {
        "voice_provider": str(voice.get("voice_provider", DEFAULT_PROJECT_VOICE_CONFIG["voice_provider"])).strip().lower() or DEFAULT_PROJECT_VOICE_CONFIG["voice_provider"]
    }
    merged["caption"] = {
        "generate_caption": bool(caption.get("generate_caption", DEFAULT_PROJECT_CAPTION_CONFIG["generate_caption"]))
    }
    if not isinstance(merged.get("cover"), dict):
        merged["cover"] = copy.deepcopy(DEFAULT_Z_IMAGE_PROMPT)
    return merged


def load_project_settings(project_dir: Path) -> dict:
    path = project_settings_path(project_dir)
    if not path.exists():
        raise FileNotFoundError(f"project_settings.json tidak ditemukan: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return _normalize_settings(data)


def save_project_settings(project_dir: Path, settings: dict) -> dict:
    normalized = _normalize_settings(settings)
    path = project_settings_path(project_dir)
    with path.open("w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    return normalized
