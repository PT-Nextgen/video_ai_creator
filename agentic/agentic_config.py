"""Agentic configuration management per-scene."""
import copy
import json
from pathlib import Path


AGENTIC_FILE = "agentic.json"

DEFAULT_AGENERIC_CONFIG = {
    "number_of_variations": 0,
    "special_command": "",
    "create_initial_image": True,
    "image_extra_mode": "image_extra",
}

IMAGE_EXTRA_MODES = [
    ("Image Extra", "image_extra"),
    ("Image Edit", "image_edit"),
    ("Tidak Pakai", "disabled"),
]


def _parse_bool(value, default: bool) -> bool:
    """Parse bool values safely from JSON/editor inputs."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
        return default
    if value is None:
        return default
    return bool(value)


def agentic_config_path(scene_dir: Path) -> Path:
    """Return path to agentic.json inside the given scene directory."""
    return Path(scene_dir) / AGENTIC_FILE


def load_agentic_config(scene_dir: Path) -> dict:
    """Load and normalize agentic config from a scene directory.

    If the file does not exist, returns the default configuration.
    """
    path = agentic_config_path(scene_dir)
    if not path.exists():
        return copy.deepcopy(DEFAULT_AGENERIC_CONFIG)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return _normalize_config(data)
    except Exception:
        return copy.deepcopy(DEFAULT_AGENERIC_CONFIG)


def save_agentic_config(scene_dir: Path, config: dict) -> dict:
    """Save and normalize agentic config to a scene directory."""
    normalized = _normalize_config(config)
    path = agentic_config_path(scene_dir)
    with path.open("w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    return normalized


def _normalize_config(data: dict | None) -> dict:
    """Normalize agentic config data with defaults."""
    merged = copy.deepcopy(DEFAULT_AGENERIC_CONFIG)
    if isinstance(data, dict):
        # number_of_variations
        try:
            val = int(data.get("number_of_variations", 0))
            merged["number_of_variations"] = max(0, val)
        except (TypeError, ValueError):
            merged["number_of_variations"] = 0
        # special_command
        merged["special_command"] = str(data.get("special_command", "")).strip()
        # create_initial_image
        merged["create_initial_image"] = _parse_bool(data.get("create_initial_image", True), True)
        # image_extra_mode
        mode = str(data.get("image_extra_mode", "image_extra")).strip().lower()
        if mode not in ("image_extra", "image_edit", "disabled"):
            mode = "image_extra"
        merged["image_extra_mode"] = mode
    return merged


def get_image_extra_flags(config: dict) -> tuple[bool, bool]:
    """Return (image_extra_enabled, image_edit_enabled) based on config.

    - image_extra_mode == 'image_extra'  → (True, False)
    - image_extra_mode == 'image_edit'   → (False, True)
    - image_extra_mode == 'disabled'     → (False, False)
    """
    mode = config.get("image_extra_mode", "image_extra")
    if mode == "image_extra":
        return (True, False)
    elif mode == "image_edit":
        return (False, True)
    else:
        return (False, False)
