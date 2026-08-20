import copy
import datetime
import json
import logging
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from PySide6.QtCore import QProcess, Qt, QUrl, QTimer, QThread, QObject, Signal
from PySide6.QtGui import QAction, QDesktopServices, QDoubleValidator, QIcon, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QInputDialog,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QScrollArea, QSpinBox, QSplitter, QStackedWidget, QTabWidget, QTextEdit, QToolButton,
    QToolBar, QVBoxLayout, QWidget, QStyle, QSizePolicy,
)
from wan22_i2v.wan22_i2v import DEFAULT_PROMPT as DEFAULT_WAN_PROMPT
from wan22_i2v.wan22_i2v import SIZE_OPTIONS as WAN_SIZE_OPTIONS
from wan22_t2v.wan22_t2v import DEFAULT_PROMPT as DEFAULT_WAN22_T2V_PROMPT
from wan22_s2v.wan22_s2v import DEFAULT_PROMPT as DEFAULT_WAN22_S2V_PROMPT
from wan22_s2v.wan22_s2v import MAX_AUDIO_DURATION as WAN22_S2V_MAX_AUDIO_DURATION
from wan22_s2v.wan22_s2v import SIZE_OPTIONS as WAN22_S2V_SIZE_OPTIONS
from wan22_s2v.wan22_s2v import get_audio_duration as get_wan22_s2v_audio_duration
from flux2.flux2 import MODEL_FLUX2, MODEL_FLUX2_K9
from z_image.z_image import IMAGE_MODEL_OPTIONS, MODEL_Z_IMAGE_TURBO
from z_image.z_image import DEFAULT_PROMPT as DEFAULT_Z_IMAGE_PROMPT
from z_image.z_image import SIZE_OPTIONS as Z_IMAGE_SIZES
from z_image.z_image import get_model_key as get_z_image_model_key
from z_image.z_image import supports_negative_prompt as z_image_supports_negative_prompt
from z_image.z_image import get_template_name as get_z_image_template_name
from gemini.gemini_image import MODEL_GEMINI_IMAGE, MODEL_GEMINI_FLASH_05K, list_gemini_image_models
from minimax_h3_t2v.minimax_h3_t2v import (
    DEFAULT_PROMPT as DEFAULT_MINIMAX_H3_T2V_PROMPT,
    SIZE_OPTIONS as MINIMAX_H3_SIZE_OPTIONS,
)
from minimax_h3_i2v.minimax_h3_i2v import (
    DEFAULT_PROMPT as DEFAULT_MINIMAX_H3_I2V_PROMPT,
    I2VA_FIRST_FRAME_PREFIX,
    is_valid_minimax_h3_i2v_prompt,
)
from minimax_h3_r2v.minimax_h3_r2v import (
    DEFAULT_PROMPT as DEFAULT_MINIMAX_H3_S2V_PROMPT,
    DEFAULT_R2V_PROMPT as DEFAULT_MINIMAX_H3_R2V_PROMPT,
    MAX_AUDIO_DURATION as MINIMAX_H3_S2V_MAX_AUDIO_DURATION,
    MAX_DURATION as MINIMAX_H3_R2V_MAX_DURATION,
    SIZE_OPTIONS as MINIMAX_H3_S2V_SIZE_OPTIONS,
    get_audio_duration as get_minimax_h3_s2v_audio_duration,
)
from minimax_h3_prompt import (
    I2VA_FIRST_FRAME_DETAIL_INSTRUCTION,
    enforce_i2va_first_shot_visual,
    REF2VA_SECTION_KEYS,
    normalize_minimax_prompt_payload,
    parse_structured_response,
    serialize_structured_prompt,
    validate_ref2va_prompt,
    validate_ref2va_reference_tokens,
    validate_structured_prompt,
)
from scripts.voice_profiles import (
    DEFAULT_SCENE_VOICE_KEY,
    SCENE_VOICE_OPTIONS,
    VOICE_PROVIDER_GEMINI,
    VOICE_PROVIDER_OPTIONS,
    normalize_provider,
    resolve_scene_voice_key,
)
from scripts.project_settings import (
    DEFAULT_PROJECT_SETTINGS,
    DEFAULT_PROJECT_VOICE_CONFIG,
    DEFAULT_PROJECT_CAPTION_CONFIG,
    load_project_settings as load_project_settings_file,
    save_project_settings as save_project_settings_file,
)
from scripts.server_config import load_server_config
from scripts import comfyui_api
from scripts.runtime_service_controller import (
    RuntimeServiceController,
    ensure_comfyui,
)
from agentic.agentic_config import (
    DEFAULT_AGENERIC_CONFIG,
    IMAGE_EXTRA_MODES,
    load_agentic_config,
    save_agentic_config,
)
from prompt_localization import (
    LORA_TRIGGER_WORDS_FIELD,
    convert_prompt_payload_for_ui,
    _normalize_prompt_entry,
    prepare_prompt_payload_for_save,
    read_json_for_runtime,
)
from prompt_localization import get_prompt_translator, update_generated_prompt_entry
from logging_config import RunIdFilter, setup_logging

ROOT = Path(__file__).resolve().parent
API_PRODUCTION = ROOT / "api_production"
MUSIC_DIR = ROOT / "music"
MAIN_SCRIPT = ROOT / "main.py"
INITIAL_IMAGE_SCRIPT = ROOT / "scripts" / "generate_initial_image.py"
IMAGE_EDIT_SCRIPT = ROOT / "scripts" / "generate_image_edit.py"
VOICE_SCRIPT = ROOT / "scripts" / "generate_voice.py"
SOUND_SCRIPT = ROOT / "scripts" / "generate_sound.py"
CAPTION_SCRIPT = ROOT / "scripts" / "generate_caption.py"
COMPOSE_SCRIPT = ROOT / "scripts" / "generate_compose.py"
UPSCALE_VIDEO_SCRIPT = ROOT / "scripts" / "upscale_video.py"
COVER_IMAGE_SCRIPT = ROOT / "scripts" / "generate_cover_image.py"
AGENTIC_SCRIPT = ROOT / "agentic" / "agentic_cli.py"
BACKUP_SCRIPT = ROOT / "backup_production.py"
KEYS_CFG = ROOT / "keys.cfg"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
ARCHIVE_EXTS = {".zip"}
UPSCALE_OPTIONS = [
    ("Tanpa upscale", 1.0),
    ("1.5x", 1.5),
    ("2x", 2.0),
]
UPSCALE_ACTION_OPTIONS = [
    ("1.5x", 1.5),
    ("2x", 2.0),
]
DEFAULT_SCENE_META = {
    "scene_title": "", "scene_description": "", "duration_seconds": 10, "voice_text": "",
    "voice_character": DEFAULT_SCENE_VOICE_KEY,
    "sound_prompt": "", "sound_volume": "",
    "scene_type": "wan22_i2v",
}
DEFAULT_WEB_SCROLL_PROMPT = {
    "url": "",
    "width": 368,
    "height": 640,
    "duration_seconds": 5.0,
    "speed": 1,
}
DEFAULT_IMAGE_PAN_PROMPT = {
    "width": 480,
    "height": 848,
    "direction": "from_right",
}
DEFAULT_IMAGE_ZOOM_PROMPT = {
    "width": 480,
    "height": 848,
    "zoom_direction": "in",
    "focal_point": "center",
    "zoom_strength": 1.3,
}
DEFAULT_WEB_SEARCH_PROMPT = {
    "width": 480,
    "height": 848,
    "search_term": "",
}
DEFAULT_IMAGE_EDIT_PROMPT = {
    "groups": [
        {"source_image": "", "prompt": ""},
        {"source_image": "", "prompt": ""},
        {"source_image": "", "prompt": ""},
    ],
}
DEFAULT_Z_IMAGE_EXTRA_PROMPTS = {
    "groups": [
        {"positive_prompt": "", "negative_prompt": ""},
        {"positive_prompt": "", "negative_prompt": ""},
        {"positive_prompt": "", "negative_prompt": ""},
    ],
}
DEFAULT_WAN22_T2V_BATCH_EXTRA_PROMPTS = {
    "groups": [
        {"positive_prompt": "", "negative_prompt": ""},
        {"positive_prompt": "", "negative_prompt": ""},
        {"positive_prompt": "", "negative_prompt": ""},
    ],
}

LORA_PREFIX_Z_IMAGE = "Z-IMAGE"
LORA_PREFIX_FLUX2 = "FLUX.2"
LORA_PREFIX_FLUX2_K9 = "FLUX.2.K9"
LORA_PREFIX_WAN_HIGH = "WAN2.2/HIGH"
LORA_PREFIX_WAN_LOW = "WAN2.2/LOW"
LORA_PREFIX_MINIMAX_H3 = "MINIMAX-H3"

_COMFYUI_LORA_OPTIONS_CACHE: dict[str, list[str]] = {}


def _normalize_prompt_provider(value: str) -> str:
    provider = str(value or "").strip().lower()
    if provider == "ollama":
        return "llama.cpp"
    if provider in {"gemini", "llama.cpp"}:
        return provider
    return "gemini"


def _is_local_prompt_provider(value: str) -> bool:
    return _normalize_prompt_provider(value) == "llama.cpp"


def _normalize_server_url(server: str) -> str:
    server = str(server or "").strip()
    if not server:
        return ""
    if not server.startswith(("http://", "https://")):
        server = f"http://{server}"
    return server.rstrip("/")


def _normalize_lora_option_name(value: str) -> str:
    name = str(value or "").strip().replace("\\", "/")
    while "//" in name:
        name = name.replace("//", "/")
    if name.endswith("/"):
        name = name[:-1]
    return name


def _normalize_lora_option_key(value: str) -> str:
    return _normalize_lora_option_name(value).casefold()


def _lora_basename(value: str) -> str:
    name = _normalize_lora_option_name(value)
    if not name:
        return ""
    return name.rsplit("/", 1)[-1].casefold()


def _lora_stem_key(value: str) -> str:
    name = _normalize_lora_option_name(value)
    if not name:
        return ""
    filename = name.rsplit("/", 1)[-1]
    if "." in filename:
        filename = filename.rsplit(".", 1)[0]
    return f"{name.rsplit('/', 1)[0]}/{filename}".casefold() if "/" in name else filename.casefold()


def _dedupe_preserve_order(values) -> list[str]:
    seen = set()
    result = []
    for value in values or []:
        name = _normalize_lora_option_name(value)
        key = _normalize_lora_option_key(name)
        stem_key = _lora_stem_key(name)
        if not name or key in seen or stem_key in seen:
            continue
        seen.add(key)
        seen.add(stem_key)
        result.append(name)
    return result


def _sort_lora_options(values: list[str]) -> list[str]:
    return sorted(_dedupe_preserve_order(values), key=lambda item: item.casefold())


def _extract_lora_options_from_object_info(payload: dict) -> list[str]:
    names: list[str] = []
    if not isinstance(payload, dict):
        return names
    for node in payload.values():
        if not isinstance(node, dict):
            continue
        node_input = node.get("input")
        if not isinstance(node_input, dict):
            continue
        for group_name in ("required", "optional"):
            group = node_input.get(group_name)
            if not isinstance(group, dict):
                continue
            for field_name, field_spec in group.items():
                if not isinstance(field_name, str):
                    continue
                if "lora" not in field_name.lower():
                    continue
                if isinstance(field_spec, (list, tuple)) and field_spec:
                    options = field_spec[0]
                    if isinstance(options, list):
                        names.extend(options)
    return _sort_lora_options(names)


def get_comfyui_lora_options(server: str, force_refresh: bool = False) -> list[str]:
    normalized_server = _normalize_server_url(server)
    if not normalized_server:
        return []
    return list(_COMFYUI_LORA_OPTIONS_CACHE.get(normalized_server, []))


def get_lora_options_by_prefix(server: str, prefix: str, force_refresh: bool = False) -> list[str]:
    prefix = _normalize_lora_option_name(prefix)
    if not prefix:
        return []
    prefix_key = _normalize_lora_option_key(prefix)
    options = get_comfyui_lora_options(server, force_refresh=force_refresh)
    return _sort_lora_options(
        [name for name in options if _normalize_lora_option_key(name).startswith(prefix_key)]
    )


def choose_lora_value(options: list[str], current_value: str = "", template_default: str = "") -> str:
    normalized_options = _dedupe_preserve_order(options)
    current_value = _normalize_lora_option_name(current_value)
    template_default = _normalize_lora_option_name(template_default)
    normalized_map = {_normalize_lora_option_key(option): option for option in normalized_options}
    basename_map = {_lora_basename(option): option for option in normalized_options if _lora_basename(option)}
    stem_map = {_lora_stem_key(option): option for option in normalized_options if _lora_stem_key(option)}

    if current_value:
        mapped_current = normalized_map.get(_normalize_lora_option_key(current_value))
        if mapped_current:
            return mapped_current
        basename_current = _lora_basename(current_value)
        if basename_current:
            mapped_basename = basename_map.get(basename_current)
            if mapped_basename:
                return mapped_basename
        stem_current = _lora_stem_key(current_value)
        if stem_current:
            mapped_stem = stem_map.get(stem_current)
            if mapped_stem:
                return mapped_stem

    if current_value and current_value != template_default:
        return current_value

    if normalized_options:
        return normalized_options[0]

    return current_value


def populate_lora_combo(
    combo: QComboBox,
    options: list[str],
    *,
    current_value: str = "",
    template_default: str = "",
    preserve_missing: bool = False,
) -> str:
    normalized_options = _dedupe_preserve_order(options)
    current_value = _normalize_lora_option_name(current_value)
    template_default = _normalize_lora_option_name(template_default)
    normalized_map = {_normalize_lora_option_key(option): option for option in normalized_options}
    basename_map = {_lora_basename(option): option for option in normalized_options if _lora_basename(option)}
    stem_map = {_lora_stem_key(option): option for option in normalized_options if _lora_stem_key(option)}
    current_key = _normalize_lora_option_key(current_value)
    if current_value and current_key in normalized_map:
        selected_value = normalized_map[current_key]
    elif current_value and _lora_basename(current_value) in basename_map:
        selected_value = basename_map[_lora_basename(current_value)]
    elif current_value and _lora_stem_key(current_value) in stem_map:
        selected_value = stem_map[_lora_stem_key(current_value)]
    elif current_value and preserve_missing and current_value != template_default:
        selected_value = current_value
    elif normalized_options:
        selected_value = normalized_options[0]
    else:
        selected_value = current_value

    combo.blockSignals(True)
    combo.clear()
    for option in normalized_options:
        combo.addItem(option, option)
    selected_key = _normalize_lora_option_key(selected_value)
    selected_stem = _lora_stem_key(selected_value)
    if selected_value and selected_key not in normalized_map and selected_stem not in stem_map:
        combo.addItem(selected_value, selected_value)
    index = combo.findData(selected_value)
    if index >= 0:
        combo.setCurrentIndex(index)
    elif normalized_options:
        combo.setCurrentIndex(0)
        selected_value = str(combo.currentData() or combo.currentText() or "").strip()
    else:
        combo.setCurrentIndex(-1)
    combo.blockSignals(False)
    return selected_value


def _collect_scene_lora_defaults(server: str, z_prompt: dict, wan_t2v_prompt: dict, wan_prompt: dict):
    z_prompt = copy.deepcopy(z_prompt or {})
    wan_t2v_prompt = copy.deepcopy(wan_t2v_prompt or {})
    wan_prompt = copy.deepcopy(wan_prompt or {})

    z_model = str(z_prompt.get("image_model", MODEL_Z_IMAGE_TURBO)).strip().lower()
    if z_model == MODEL_GEMINI_IMAGE:
        z_prompt["lora_name"] = ""
    elif z_model == MODEL_FLUX2_K9:
        z_prompt["lora_name"] = choose_lora_value(
            get_lora_options_by_prefix(server, LORA_PREFIX_FLUX2_K9),
            z_prompt.get("lora_name", ""),
            str(z_prompt.get("lora_name", "")),
        )
    elif z_model == MODEL_FLUX2:
        z_prompt["lora_name"] = choose_lora_value(
            get_lora_options_by_prefix(server, LORA_PREFIX_FLUX2),
            z_prompt.get("lora_name", ""),
            str(z_prompt.get("lora_name", "")),
        )
    else:
        z_prompt["lora_name"] = choose_lora_value(
            get_lora_options_by_prefix(server, LORA_PREFIX_Z_IMAGE),
            z_prompt.get("lora_name", ""),
            str(z_prompt.get("lora_name", "")),
        )

    wan_t2v_prompt["lora_high_name"] = choose_lora_value(
        get_lora_options_by_prefix(server, LORA_PREFIX_WAN_HIGH),
        wan_t2v_prompt.get("lora_high_name", ""),
        DEFAULT_WAN22_T2V_PROMPT["lora_high_name"],
    )
    wan_t2v_prompt["lora_low_name"] = choose_lora_value(
        get_lora_options_by_prefix(server, LORA_PREFIX_WAN_LOW),
        wan_t2v_prompt.get("lora_low_name", ""),
        DEFAULT_WAN22_T2V_PROMPT["lora_low_name"],
    )
    wan_t2v_prompt["lora_high_name_2"] = choose_lora_value(
        get_lora_options_by_prefix(server, LORA_PREFIX_WAN_HIGH),
        wan_t2v_prompt.get("lora_high_name_2", ""),
        DEFAULT_WAN22_T2V_PROMPT["lora_high_name_2"],
    )
    wan_t2v_prompt["lora_low_name_2"] = choose_lora_value(
        get_lora_options_by_prefix(server, LORA_PREFIX_WAN_LOW),
        wan_t2v_prompt.get("lora_low_name_2", ""),
        DEFAULT_WAN22_T2V_PROMPT["lora_low_name_2"],
    )

    wan_prompt["lora_high_name"] = choose_lora_value(
        get_lora_options_by_prefix(server, LORA_PREFIX_WAN_HIGH),
        wan_prompt.get("lora_high_name", ""),
        DEFAULT_WAN_PROMPT["lora_high_name"],
    )
    wan_prompt["lora_low_name"] = choose_lora_value(
        get_lora_options_by_prefix(server, LORA_PREFIX_WAN_LOW),
        wan_prompt.get("lora_low_name", ""),
        DEFAULT_WAN_PROMPT["lora_low_name"],
    )
    wan_prompt["lora_high_name_2"] = choose_lora_value(
        get_lora_options_by_prefix(server, LORA_PREFIX_WAN_HIGH),
        wan_prompt.get("lora_high_name_2", ""),
        DEFAULT_WAN_PROMPT["lora_high_name_2"],
    )
    wan_prompt["lora_low_name_2"] = choose_lora_value(
        get_lora_options_by_prefix(server, LORA_PREFIX_WAN_LOW),
        wan_prompt.get("lora_low_name_2", ""),
        DEFAULT_WAN_PROMPT["lora_low_name_2"],
    )

    return z_prompt, wan_t2v_prompt, wan_prompt

WAN22_T2V_SCENE_TYPE = "wan22_t2v_i2v"
WAN22_T2V_BATCH_SCENE_TYPE = "wan22_t2v_batch"
MINIMAX_H3_T2V_I2V_SCENE_TYPE = "minimax-h3_t2v_i2v"
MINIMAX_H3_I2V_SCENE_TYPE = "minimax-h3_i2v"
MINIMAX_H3_S2V_SCENE_TYPE = "minimax-h3_s2v"
MINIMAX_H3_S2V_PROMPT_FILENAME = "minimax_h3_s2v_prompt.json"
MINIMAX_H3_R2V_SCENE_TYPE = "minimax-h3_r2v"
MINIMAX_H3_R2V_PROMPT_FILENAME = "minimax_h3_r2v_prompt.json"


def s2v_prompt_filename(scene_type: str) -> str:
    return MINIMAX_H3_S2V_PROMPT_FILENAME if str(scene_type or "").strip() == MINIMAX_H3_S2V_SCENE_TYPE else "wan22_s2v_prompt.json"


def s2v_prompt_default(scene_type: str) -> dict:
    return DEFAULT_MINIMAX_H3_S2V_PROMPT if str(scene_type or "").strip() == MINIMAX_H3_S2V_SCENE_TYPE else DEFAULT_WAN22_S2V_PROMPT


def r2v_prompt_default(scene_type: str) -> dict:
    return copy.deepcopy(DEFAULT_MINIMAX_H3_R2V_PROMPT)
DEFAULT_DURATION_OPTIONS = [5, 10]
WAN22_T2V_DURATION_OPTIONS = [5, 10, 15]
MINIMAX_H3_DURATION_OPTIONS = [1, 5, 10, 15, 20, 25, 30]
MINIMAX_H3_I2V_DURATION_OPTIONS = [1, 5, 10, 15]
MINIMAX_H3_DURATION_MIN = 1.0
MINIMAX_H3_DURATION_DECIMALS = 1
MINIMAX_H3_FPS_OPTIONS = [16, 24]
MINIMAX_H3_DEFAULT_FPS = 24
PROMPT_APPEND_OPERATIONS = {
    "wan22_t2v_positive": {
        "title": "Append prompt positive wan22_t2v",
        "targets": [
            {
                "filename": "wan22_t2v_prompt.json",
                "mode": "top_level",
                "keys": ["positive_prompt"],
                "default": DEFAULT_WAN22_T2V_PROMPT,
            },
            {
                "filename": "wan22_t2v_batch_extra_prompts.json",
                "mode": "groups",
                "keys": ["positive_prompt"],
                "default": DEFAULT_WAN22_T2V_BATCH_EXTRA_PROMPTS,
            },
        ],
    },
    "wan22_t2v_negative": {
        "title": "Append prompt negative wan22_t2v",
        "targets": [
            {
                "filename": "wan22_t2v_prompt.json",
                "mode": "top_level",
                "keys": ["negative_prompt"],
                "default": DEFAULT_WAN22_T2V_PROMPT,
            },
            {
                "filename": "wan22_t2v_batch_extra_prompts.json",
                "mode": "groups",
                "keys": ["negative_prompt"],
                "default": DEFAULT_WAN22_T2V_BATCH_EXTRA_PROMPTS,
            },
        ],
    },
    "wan22_i2v_positive": {
        "title": "Append prompt positive wan22_i2v",
        "targets": [
            {
                "filename": "wan22_i2v_prompt.json",
                "mode": "top_level",
                "keys": ["positive_prompt_one", "positive_prompt_two"],
                "default": DEFAULT_WAN_PROMPT,
            },
        ],
    },
    "wan22_i2v_negative": {
        "title": "Append prompt negative wan22_i2v",
        "targets": [
            {
                "filename": "wan22_i2v_prompt.json",
                "mode": "top_level",
                "keys": ["negative_prompt_one", "negative_prompt_two"],
                "default": DEFAULT_WAN_PROMPT,
            },
        ],
    },
    "image_positive": {
        "title": "Append prompt positive image",
        "targets": [
            {
                "filename": "z_image_prompt.json",
                "mode": "top_level",
                "keys": ["positive_prompt"],
                "default": DEFAULT_Z_IMAGE_PROMPT,
            },
            {
                "filename": "z_image_extra_prompts.json",
                "mode": "groups",
                "keys": ["positive_prompt"],
                "default": DEFAULT_Z_IMAGE_EXTRA_PROMPTS,
            },
        ],
    },
}


def duration_options_for_scene_type(scene_type: str) -> list[int]:
    scene_type = str(scene_type or "").strip()
    if scene_type == MINIMAX_H3_T2V_I2V_SCENE_TYPE:
        return list(MINIMAX_H3_DURATION_OPTIONS)
    if scene_type == MINIMAX_H3_I2V_SCENE_TYPE:
        return list(MINIMAX_H3_I2V_DURATION_OPTIONS)
    if scene_type == MINIMAX_H3_R2V_SCENE_TYPE:
        return [1, 5, 10, 15]
    if scene_type == WAN22_T2V_SCENE_TYPE:
        return list(WAN22_T2V_DURATION_OPTIONS)
    if scene_type == WAN22_T2V_BATCH_SCENE_TYPE:
        return [5, 10]
    return list(DEFAULT_DURATION_OPTIONS)


def _prompt_target_dirs_for_scene(scene_dir: Path | None) -> list[Path]:
    if scene_dir is None or not scene_dir.exists() or not scene_dir.is_dir():
        return []
    targets = [scene_dir]
    variations = []
    for child in scene_dir.iterdir():
        if child.is_dir() and child.name.lower().startswith("variasi"):
            variations.append(child)
    targets.extend(
        sorted(variations, key=lambda p: int("".join(ch for ch in p.name if ch.isdigit()) or "999999"))
    )
    return targets


def _prepend_prompt_text(prefix_text: str, base_text: str) -> str:
    prefix_text = str(prefix_text or "").strip()
    base_text = str(base_text or "").strip()
    if not prefix_text:
        return base_text
    if not base_text:
        return prefix_text
    return f"{prefix_text}, {base_text}"


def _prepend_prompt_entry(existing_value, prefix_id: str, prefix_en: str) -> dict:
    existing = _normalize_prompt_entry(existing_value)
    base_id = existing.id_new or existing.id_old
    base_en = existing.en or base_id
    combined_id = _prepend_prompt_text(prefix_id, base_id)
    combined_en = _prepend_prompt_text(prefix_en, base_en)
    return {
        "id_old": combined_id,
        "id_new": combined_id,
        "en": combined_en,
    }


def _load_json_raw(path: Path, default: dict) -> dict:
    if not path.exists():
        return copy.deepcopy(default)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return copy.deepcopy(default)
    return copy.deepcopy(data)


def _append_prompts_in_file(
    path: Path,
    *,
    mode: str,
    keys: list[str],
    default: dict,
    append_id: str,
    append_en: str,
) -> tuple[bool, int]:
    if not path.exists():
        return False, 0
    data = _load_json_raw(path, default)
    changed = False
    updated_prompts = 0

    if mode == "top_level":
        for key in keys:
            existing_value = data.get(key)
            new_value = _prepend_prompt_entry(existing_value, append_id, append_en)
            if new_value != existing_value:
                data[key] = new_value
                changed = True
                updated_prompts += 1
    elif mode == "groups":
        groups = data.get("groups")
        if not isinstance(groups, list):
            groups = []
        new_groups = []
        for item in groups:
            group_item = dict(item) if isinstance(item, dict) else {}
            for key in keys:
                existing_value = group_item.get(key)
                new_value = _prepend_prompt_entry(existing_value, append_id, append_en)
                if new_value != existing_value:
                    group_item[key] = new_value
                    changed = True
                    updated_prompts += 1
            new_groups.append(group_item)
        data["groups"] = new_groups

    if changed:
        write_json(path, data)
    return changed, updated_prompts


def populate_duration_combo(combo: QComboBox, scene_type: str, selected_value: int | None = None):
    desired_value = selected_value
    if desired_value is None:
        current_data = combo.currentData()
        if isinstance(current_data, int):
            desired_value = current_data
        elif current_data is not None:
            try:
                desired_value = int(current_data)
            except (TypeError, ValueError):
                desired_value = None

    options = duration_options_for_scene_type(scene_type)
    if desired_value not in options:
        desired_value = 10 if 10 in options else (options[0] if options else None)

    combo.blockSignals(True)
    combo.clear()
    for value in options:
        combo.addItem(str(value), value)
    if desired_value is not None:
        index = combo.findData(desired_value)
        combo.setCurrentIndex(index if index >= 0 else 0)
    combo.blockSignals(False)


def agentic_create_initial_image_policy(scene_type: str) -> tuple[bool, bool | None]:
    """Return (visible_in_ui, forced_value_or_none) for agentic create_initial_image."""
    scene_type = str(scene_type or "").strip()
    if scene_type in {"wan22", "wan22_i2v", "wan22_s2v", MINIMAX_H3_I2V_SCENE_TYPE, MINIMAX_H3_S2V_SCENE_TYPE}:
        return True, None
    if scene_type in {"i2v", "image_pan", "image_zoom"}:
        return False, True
    if scene_type in {
        "web_scroll",
        WAN22_T2V_SCENE_TYPE,
        WAN22_T2V_BATCH_SCENE_TYPE,
        MINIMAX_H3_T2V_I2V_SCENE_TYPE,
        MINIMAX_H3_R2V_SCENE_TYPE,
    }:
        return False, False
    return False, True


def scene_type_supports_initial_image(scene_type: str) -> bool:
    scene_type = str(scene_type or "").strip()
    return scene_type in {
        "wan22",
        "wan22_i2v",
        "wan22_s2v",
        MINIMAX_H3_I2V_SCENE_TYPE,
        MINIMAX_H3_S2V_SCENE_TYPE,
        MINIMAX_H3_R2V_SCENE_TYPE,
        "i2v",
        "image_pan",
        "image_zoom",
    }


def load_json(path: Path, default: dict):
    if not path.exists():
        return copy.deepcopy(default)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    merged = copy.deepcopy(default)
    merged.update(data)
    return convert_prompt_payload_for_ui(path.name, merged)


def load_json_with_fallback(primary_path: Path, fallback_path: Path | None, default: dict):
    if primary_path.exists():
        return load_json(primary_path, default)
    if fallback_path is not None and fallback_path.exists():
        return load_json(fallback_path, default)
    return copy.deepcopy(default)


def write_json(path: Path, data: dict):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_prompt_json(path: Path, data: dict):
    existing_data = None
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = None
    payload = prepare_prompt_payload_for_save(path.name, data, existing_data=existing_data)
    write_json(path, payload)


def scene_dir_name(index: int) -> str:
    return f"scene_{index}"


def list_scene_dirs_in_project(project_dir: Path | None):
    if project_dir is None:
        return []
    if not project_dir.exists() or not project_dir.is_dir():
        return []
    scenes = []
    for child in project_dir.iterdir():
        if child.is_dir() and child.name.startswith("scene_"):
            try:
                scenes.append((int(child.name.split("_", 1)[1]), child))
            except ValueError:
                pass
    scenes.sort(key=lambda item: item[0])
    return [path for _, path in scenes]


def list_output_files(directory: Path):
    if not directory.exists():
        return {}
    outputs = {}
    for child in directory.iterdir():
        if child.is_file() and child.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS | ARCHIVE_EXTS):
            try:
                outputs[str(child.resolve())] = child.stat().st_mtime
            except OSError:
                continue
    return outputs


def build_scene_templates(title: str, scene_type: str, duration: int | float):
    meta = copy.deepcopy(DEFAULT_SCENE_META)
    meta["scene_title"] = title
    meta["scene_description"] = ""
    meta["scene_type"] = scene_type
    meta["duration_seconds"] = duration
    return (
        meta,
        copy.deepcopy(DEFAULT_Z_IMAGE_PROMPT),
        copy.deepcopy(DEFAULT_WAN22_T2V_PROMPT),
        copy.deepcopy(DEFAULT_WAN_PROMPT),
        copy.deepcopy(DEFAULT_WAN22_S2V_PROMPT),
        copy.deepcopy(DEFAULT_WEB_SCROLL_PROMPT),
        copy.deepcopy(DEFAULT_IMAGE_PAN_PROMPT),
        copy.deepcopy(DEFAULT_IMAGE_ZOOM_PROMPT),
        copy.deepcopy(DEFAULT_WEB_SEARCH_PROMPT),
    )


def create_scene_files(
    scene_dir: Path,
    meta=None,
    z_prompt=None,
    wan_t2v_prompt=None,
    wan_prompt=None,
    wan22_s2v_prompt=None,
    web_scroll_prompt=None,
    image_pan_prompt=None,
    image_zoom_prompt=None,
    web_search_prompt=None,
    image_edit_prompt=None,
    z_image_extra_prompts=None,
    t2v_batch_extra_prompts=None,
    minimax_h3_t2v_prompt=None,
    minimax_h3_i2v_prompt=None,
    minimax_h3_s2v_prompt=None,
    minimax_h3_r2v_prompt=None,
):
    scene_dir.mkdir(parents=True, exist_ok=True)
    resolved_meta = copy.deepcopy(DEFAULT_SCENE_META)
    if isinstance(meta, dict):
        resolved_meta.update(meta)
    scene_type = str(resolved_meta.get("scene_type", "wan22_i2v")).strip()
    write_prompt_json(scene_dir / "scene_meta.json", resolved_meta)
    sync_scene_prompt_files(
        scene_dir,
        scene_type=scene_type,
        z_prompt=z_prompt or DEFAULT_Z_IMAGE_PROMPT,
        wan_t2v_prompt=wan_t2v_prompt or DEFAULT_WAN22_T2V_PROMPT,
        wan_prompt=wan_prompt or DEFAULT_WAN_PROMPT,
        s2v_prompt=wan22_s2v_prompt or DEFAULT_WAN22_S2V_PROMPT,
        web_prompt=web_scroll_prompt or DEFAULT_WEB_SCROLL_PROMPT,
        image_pan_prompt=image_pan_prompt or DEFAULT_IMAGE_PAN_PROMPT,
        image_zoom_prompt=image_zoom_prompt or DEFAULT_IMAGE_ZOOM_PROMPT,
        web_search_prompt=web_search_prompt or DEFAULT_WEB_SEARCH_PROMPT,
        image_edit_prompt=image_edit_prompt or DEFAULT_IMAGE_EDIT_PROMPT,
        z_image_extra_prompts=z_image_extra_prompts or DEFAULT_Z_IMAGE_EXTRA_PROMPTS,
        t2v_batch_extra_prompts=t2v_batch_extra_prompts or DEFAULT_WAN22_T2V_BATCH_EXTRA_PROMPTS,
        minimax_h3_t2v_prompt=minimax_h3_t2v_prompt or DEFAULT_MINIMAX_H3_T2V_PROMPT,
        minimax_h3_i2v_prompt=minimax_h3_i2v_prompt or DEFAULT_MINIMAX_H3_I2V_PROMPT,
        minimax_h3_s2v_prompt=(
            minimax_h3_s2v_prompt
            if scene_type == MINIMAX_H3_S2V_SCENE_TYPE and minimax_h3_s2v_prompt
            else DEFAULT_MINIMAX_H3_S2V_PROMPT
        ),
        minimax_h3_r2v_prompt=(
            minimax_h3_r2v_prompt
            if scene_type == MINIMAX_H3_R2V_SCENE_TYPE and minimax_h3_r2v_prompt
            else DEFAULT_MINIMAX_H3_R2V_PROMPT
        ),
    )


def sync_scene_prompt_files(
    scene_dir: Path,
    scene_type: str,
    z_prompt: dict,
    wan_t2v_prompt: dict,
    wan_prompt: dict,
    s2v_prompt: dict,
    web_prompt: dict,
    image_pan_prompt: dict,
    image_zoom_prompt: dict | None = None,
    web_search_prompt: dict | None = None,
    image_edit_prompt: dict | None = None,
    z_image_extra_prompts: dict | None = None,
    t2v_batch_extra_prompts: dict | None = None,
    minimax_h3_t2v_prompt: dict | None = None,
    minimax_h3_i2v_prompt: dict | None = None,
    minimax_h3_s2v_prompt: dict | None = None,
    minimax_h3_r2v_prompt: dict | None = None,
):
    """Ensure prompt JSON files exist according to selected scene type.

    Rules:
    - z_image_prompt.json: always present
    - wan22_t2v_prompt.json: always present
    - wan22_i2v_prompt.json: always present (used when switching to wan later)
    - wan22_s2v_prompt.json: always present (used when switching to s2v later)
    """
    write_prompt_json(scene_dir / "z_image_prompt.json", z_prompt or DEFAULT_Z_IMAGE_PROMPT)
    write_prompt_json(scene_dir / "wan22_t2v_prompt.json", wan_t2v_prompt or DEFAULT_WAN22_T2V_PROMPT)
    write_prompt_json(scene_dir / "wan22_i2v_prompt.json", wan_prompt or DEFAULT_WAN_PROMPT)
    write_prompt_json(scene_dir / "wan22_s2v_prompt.json", s2v_prompt or DEFAULT_WAN22_S2V_PROMPT)
    write_prompt_json(scene_dir / "web_scroll_prompt.json", web_prompt or DEFAULT_WEB_SCROLL_PROMPT)
    write_prompt_json(scene_dir / "image_pan_prompt.json", image_pan_prompt or DEFAULT_IMAGE_PAN_PROMPT)
    write_prompt_json(scene_dir / "image_zoom_prompt.json", image_zoom_prompt or DEFAULT_IMAGE_ZOOM_PROMPT)
    write_prompt_json(scene_dir / "web_search_prompt.json", web_search_prompt or DEFAULT_WEB_SEARCH_PROMPT)
    write_prompt_json(scene_dir / "image_edit_prompt.json", image_edit_prompt or DEFAULT_IMAGE_EDIT_PROMPT)
    write_prompt_json(scene_dir / "z_image_extra_prompts.json", z_image_extra_prompts or DEFAULT_Z_IMAGE_EXTRA_PROMPTS)
    write_prompt_json(scene_dir / "wan22_t2v_batch_extra_prompts.json", t2v_batch_extra_prompts or DEFAULT_WAN22_T2V_BATCH_EXTRA_PROMPTS)
    write_prompt_json(
        scene_dir / "minimax_h3_t2v_prompt.json",
        minimax_h3_t2v_prompt or DEFAULT_MINIMAX_H3_T2V_PROMPT,
    )
    write_prompt_json(
        scene_dir / "minimax_h3_i2v_prompt.json",
        minimax_h3_i2v_prompt or DEFAULT_MINIMAX_H3_I2V_PROMPT,
    )
    write_prompt_json(
        scene_dir / MINIMAX_H3_S2V_PROMPT_FILENAME,
        prepare_prompt_payload_for_save(
            MINIMAX_H3_S2V_PROMPT_FILENAME,
            minimax_h3_s2v_prompt or DEFAULT_MINIMAX_H3_S2V_PROMPT,
        ),
    )
    r2v_path = scene_dir / MINIMAX_H3_R2V_PROMPT_FILENAME
    r2v_payload = minimax_h3_r2v_prompt
    if r2v_payload is None:
        r2v_payload = load_json(r2v_path, DEFAULT_MINIMAX_H3_R2V_PROMPT) if r2v_path.exists() else DEFAULT_MINIMAX_H3_R2V_PROMPT
    # Repair files created by the earlier R2V implementation, whose default
    # six fields were empty. Do this only for an entirely empty payload so a
    # user's partially edited prompt is never silently overwritten.
    r2v_entry = r2v_payload.get("positive_prompt") if isinstance(r2v_payload, dict) else None
    r2v_id_new = r2v_entry.get("id_new") if isinstance(r2v_entry, dict) else None
    if isinstance(r2v_id_new, dict) and r2v_id_new and not any(str(value or "").strip() for value in r2v_id_new.values()):
        r2v_payload = copy.deepcopy(DEFAULT_MINIMAX_H3_R2V_PROMPT)
    write_prompt_json(
        r2v_path,
        prepare_prompt_payload_for_save(MINIMAX_H3_R2V_PROMPT_FILENAME, r2v_payload),
    )


def validate_project_name(project_name: str) -> str:
    normalized = str(project_name or "").strip()
    if not normalized:
        raise ValueError("Nama project tidak boleh kosong.")
    if any(ch in normalized for ch in '\\/:*?"<>|'):
        raise ValueError("Nama project mengandung karakter yang tidak valid.")
    return normalized


def sync_project_size_to_scene_files(project_dir: Path, project_settings: dict | None = None):
    if project_settings is None:
        project_settings = load_project_settings_file(project_dir)
    video_size = project_settings.get("video_size", {}) if isinstance(project_settings, dict) else {}
    try:
        width = int(video_size.get("width", DEFAULT_PROJECT_SETTINGS["video_size"]["width"]))
    except (TypeError, ValueError):
        width = DEFAULT_PROJECT_SETTINGS["video_size"]["width"]
    try:
        height = int(video_size.get("height", DEFAULT_PROJECT_SETTINGS["video_size"]["height"]))
    except (TypeError, ValueError):
        height = DEFAULT_PROJECT_SETTINGS["video_size"]["height"]

    for scene_dir in list_scene_dirs_in_project(project_dir):
        meta = load_json(scene_dir / "scene_meta.json", DEFAULT_SCENE_META)
        scene_type = str(meta.get("scene_type", "wan22_i2v")).strip()
        prompt_files = [
            "wan22_t2v_prompt.json",
            "wan22_i2v_prompt.json",
            "minimax_h3_t2v_prompt.json",
            "minimax_h3_i2v_prompt.json",
            MINIMAX_H3_S2V_PROMPT_FILENAME,
            "wan22_s2v_prompt.json",
            "web_scroll_prompt.json",
            "image_pan_prompt.json",
            "image_zoom_prompt.json",
        ]
        if scene_type in {"wan22_i2v", "wan22_s2v", MINIMAX_H3_I2V_SCENE_TYPE, "i2v"}:
            prompt_files.insert(0, "z_image_prompt.json")
        for filename in prompt_files:
            path = scene_dir / filename
            if not path.exists():
                continue
            try:
                data = load_json(path, {})
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            data["width"] = width
            data["height"] = height
            write_prompt_json(path, data)


def create_project_on_disk(
    project_name: str,
    *,
    create_default_scene: bool = True,
    project_settings: dict | None = None,
) -> tuple[Path, dict]:
    project_name = validate_project_name(project_name)
    API_PRODUCTION.mkdir(parents=True, exist_ok=True)
    project_dir = API_PRODUCTION / project_name
    if project_dir.exists():
        raise FileExistsError(f"Project `{project_name}` sudah ada.")

    project_dir.mkdir(parents=True, exist_ok=False)
    initial_project_settings = copy.deepcopy(project_settings or DEFAULT_PROJECT_SETTINGS)
    if not isinstance(initial_project_settings.get("cover"), dict):
        initial_project_settings["cover"] = copy.deepcopy(DEFAULT_Z_IMAGE_PROMPT)
    cover_data = initial_project_settings.get("cover") if isinstance(initial_project_settings.get("cover"), dict) else {}
    if isinstance(cover_data, dict):
        comfyui_server = str(initial_project_settings.get("comfyui_server", DEFAULT_PROJECT_SETTINGS["comfyui_server"])).strip()
        cover_model = str(cover_data.get("image_model", MODEL_Z_IMAGE_TURBO)).strip().lower()
        if cover_model == MODEL_GEMINI_IMAGE:
            cover_data["lora_name"] = ""
        elif cover_model == MODEL_FLUX2_K9:
            cover_data["lora_name"] = choose_lora_value(
                get_lora_options_by_prefix(comfyui_server, LORA_PREFIX_FLUX2_K9),
                cover_data.get("lora_name", ""),
                str(cover_data.get("lora_name", "")),
            )
        elif cover_model == MODEL_FLUX2:
            cover_data["lora_name"] = choose_lora_value(
                get_lora_options_by_prefix(comfyui_server, LORA_PREFIX_FLUX2),
                cover_data.get("lora_name", ""),
                str(cover_data.get("lora_name", "")),
            )
        else:
            cover_data["lora_name"] = choose_lora_value(
                get_lora_options_by_prefix(comfyui_server, LORA_PREFIX_Z_IMAGE),
                cover_data.get("lora_name", ""),
                str(cover_data.get("lora_name", "")),
            )
    saved_settings = save_project_settings_file(project_dir, initial_project_settings)

    if create_default_scene:
        create_scene_in_project(project_dir, scene_type="wan22_i2v", scene_title="", duration=10)
    sync_project_size_to_scene_files(project_dir, saved_settings)
    return project_dir, saved_settings


def create_scene_in_project(
    project_dir: Path,
    *,
    scene_type: str,
    scene_title: str = "",
    scene_description: str = "",
    voice_text: str = "",
    duration: int | float = 10,
) -> Path:
    if not project_dir.exists() or not project_dir.is_dir():
        raise FileNotFoundError(f"Project tidak ditemukan: {project_dir}")
    scene_type = str(scene_type or "").strip()
    try:
        raw_duration = float(duration)
    except (TypeError, ValueError) as exc:
        raise ValueError("Durasi harus berupa angka.") from exc
    if scene_type in {MINIMAX_H3_T2V_I2V_SCENE_TYPE, MINIMAX_H3_I2V_SCENE_TYPE, MINIMAX_H3_R2V_SCENE_TYPE}:
        if raw_duration != round(raw_duration, MINIMAX_H3_DURATION_DECIMALS):
            raise ValueError("Durasi MiniMax maksimal memiliki 1 angka desimal.")
        duration = round(raw_duration, MINIMAX_H3_DURATION_DECIMALS)
    else:
        duration = int(raw_duration)
    if scene_type == MINIMAX_H3_T2V_I2V_SCENE_TYPE and not (
        MINIMAX_H3_DURATION_MIN <= duration <= 30.0
        and duration == round(duration, MINIMAX_H3_DURATION_DECIMALS)
    ):
        raise ValueError(
            "Durasi untuk scene minimax-h3_t2v_i2v harus antara 1.0 dan 30.0 detik dengan maksimal 1 angka desimal."
        )
    if scene_type == MINIMAX_H3_I2V_SCENE_TYPE and not (
        MINIMAX_H3_DURATION_MIN <= duration <= 15.0
        and duration == round(duration, MINIMAX_H3_DURATION_DECIMALS)
    ):
        raise ValueError(
            "Durasi untuk scene minimax-h3_i2v harus antara 1.0 dan 15.0 detik dengan maksimal 1 angka desimal."
        )
    if scene_type == MINIMAX_H3_R2V_SCENE_TYPE and not (
        MINIMAX_H3_DURATION_MIN <= duration <= 15.0
        and duration == round(duration, MINIMAX_H3_DURATION_DECIMALS)
    ):
        raise ValueError(
            "Durasi untuk scene minimax-h3_r2v harus antara 1.0 dan 15.0 detik dengan maksimal 1 angka desimal."
        )
    if scene_type == WAN22_T2V_SCENE_TYPE and duration not in WAN22_T2V_DURATION_OPTIONS:
        raise ValueError("Durasi untuk scene wan22_t2v_i2v hanya boleh 5, 10, atau 15 detik.")
    if scene_type == WAN22_T2V_BATCH_SCENE_TYPE and duration not in (5, 10):
        raise ValueError("Durasi untuk scene wan22_t2v_batch hanya boleh 5 atau 10 detik.")
    new_dir = project_dir / scene_dir_name(len(list_scene_dirs_in_project(project_dir)) + 1)
    meta, z_prompt, wan_t2v_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt, image_zoom_prompt, web_search_prompt = build_scene_templates(
        scene_title,
        scene_type,
        duration,
    )
    meta["scene_description"] = str(scene_description or "").strip()
    meta["voice_text"] = str(voice_text or "").strip()
    try:
        project_settings = load_project_settings_file(project_dir)
        comfyui_server = str(project_settings.get("comfyui_server", DEFAULT_PROJECT_SETTINGS["comfyui_server"])).strip()
    except Exception:
        comfyui_server = DEFAULT_PROJECT_SETTINGS["comfyui_server"]
    z_prompt, wan_t2v_prompt, wan_prompt = _collect_scene_lora_defaults(
        comfyui_server,
        z_prompt,
        wan_t2v_prompt,
        wan_prompt,
    )
    create_scene_files(
        new_dir,
        meta=meta,
        z_prompt=z_prompt,
        wan_t2v_prompt=wan_t2v_prompt,
        wan_prompt=wan_prompt,
        wan22_s2v_prompt=s2v_prompt,
        web_scroll_prompt=web_prompt,
        image_pan_prompt=image_pan_prompt,
        image_zoom_prompt=image_zoom_prompt,
        web_search_prompt=web_search_prompt,
        t2v_batch_extra_prompts=DEFAULT_WAN22_T2V_BATCH_EXTRA_PROMPTS,
        minimax_h3_r2v_prompt=DEFAULT_MINIMAX_H3_R2V_PROMPT,
    )
    sync_project_size_to_scene_files(project_dir)
    return new_dir


def duplicate_directory(src: Path, dst: Path):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("variasi*", "__pycache__", "*.pyc"),
    )


def clear_scene_root_contents(scene_dir: Path):
    if not scene_dir.exists():
        return
    for item in scene_dir.iterdir():
        if item.is_dir() and item.name.lower().startswith("variasi"):
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def copy_scene_contents_to_root(src: Path, dst: Path):
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.is_dir() and item.name.lower().startswith("variasi"):
            continue
        if item.is_file() and item.name == "status.done":
            continue
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def copy_latest_video_to_root(src: Path, dst: Path):
    dst.mkdir(parents=True, exist_ok=True)
    videos = [
        item for item in src.iterdir()
        if item.is_file() and item.suffix.lower() in VIDEO_EXTS
    ]
    if not videos:
        raise FileNotFoundError(f"Tidak ada file video di folder variasi: {src.name}")
    videos.sort(key=lambda p: (p.stat().st_mtime, p.name.lower()))
    latest_video = videos[-1]

    for item in list(dst.iterdir()):
        if item.is_file() and item.suffix.lower() in VIDEO_EXTS:
            item.unlink()

    shutil.copy2(latest_video, dst / latest_video.name)
    return latest_video


def find_latest_asset(scene_dir: Path, exts: set[str]):
    if not scene_dir.exists():
        return None
    items = [p for p in scene_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]
    if not items:
        return None
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return items[0]


def find_latest_speech_asset(scene_dir: Path):
    audio_exts = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
    if not scene_dir.exists():
        return None
    items = [
        p for p in scene_dir.iterdir()
        if p.is_file() and p.suffix.lower() in audio_exts and p.name.startswith("speech_")
    ]
    if not items:
        return None
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return items[0]


def read_key_from_cfg(key_name: str) -> str:
    if not KEYS_CFG.exists():
        return ""
    try:
        with KEYS_CFG.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip().upper() == key_name.strip().upper():
                    return v.strip()
    except OSError:
        return ""
    return ""


def _is_valid_web_url(value: str):
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_one_decimal_step(value: float):
    return abs((value * 10.0) - round(value * 10.0)) < 1e-9


def _prompt_text_for_validation(value) -> str:
    """Return user-facing text from legacy or bilingual prompt data."""
    if isinstance(value, dict):
        return str(value.get("id_new", "") or value.get("en", "") or "").strip()
    return str(value or "").strip()


def validate_scene_data(
    meta: dict,
    z_prompt: dict,
    wan_t2v_prompt: dict,
    wan_prompt: dict,
    s2v_prompt: dict | None = None,
    web_prompt: dict | None = None,
    image_pan_prompt: dict | None = None,
    image_zoom_prompt: dict | None = None,
    scene_dir: Path | None = None,
    minimax_h3_t2v_prompt: dict | None = None,
    minimax_h3_i2v_prompt: dict | None = None,
    minimax_h3_r2v_prompt: dict | None = None,
):
    issues = []
    scene_type = str(meta.get("scene_type", "wan22_i2v")).strip()
    wan_t2v_prompt = wan_t2v_prompt or DEFAULT_WAN22_T2V_PROMPT
    s2v_prompt = s2v_prompt or DEFAULT_WAN22_S2V_PROMPT
    web_prompt = web_prompt or DEFAULT_WEB_SCROLL_PROMPT
    image_pan_prompt = image_pan_prompt or DEFAULT_IMAGE_PAN_PROMPT
    image_zoom_prompt = image_zoom_prompt or DEFAULT_IMAGE_ZOOM_PROMPT
    minimax_h3_t2v_prompt = minimax_h3_t2v_prompt or DEFAULT_MINIMAX_H3_T2V_PROMPT
    minimax_h3_i2v_prompt = minimax_h3_i2v_prompt or DEFAULT_MINIMAX_H3_I2V_PROMPT
    if scene_type == MINIMAX_H3_R2V_SCENE_TYPE and minimax_h3_r2v_prompt is None and scene_dir:
        minimax_h3_r2v_prompt = load_json(scene_dir / MINIMAX_H3_R2V_PROMPT_FILENAME, DEFAULT_MINIMAX_H3_R2V_PROMPT)
    minimax_h3_r2v_prompt = minimax_h3_r2v_prompt or DEFAULT_MINIMAX_H3_R2V_PROMPT
    if not str(meta.get("scene_title", "")).strip():
        issues.append("Judul adegan wajib diisi.")
    if not str(meta.get("scene_description", "")).strip():
        issues.append("Deskripsi adegan wajib diisi.")
    try:
        if scene_type not in {"wan22_s2v", "web_scroll"} and int(meta.get("duration_seconds", 0)) <= 0:
            issues.append("Durasi harus lebih besar dari 0.")
    except Exception:
        if scene_type not in {"wan22_s2v", "web_scroll"}:
            issues.append("Durasi harus berupa angka.")
    if scene_type == WAN22_T2V_SCENE_TYPE:
        try:
            duration_value = int(meta.get("duration_seconds", 0))
        except Exception:
            duration_value = 0
        if duration_value not in WAN22_T2V_DURATION_OPTIONS:
            issues.append("Durasi scene wan22_t2v_i2v hanya boleh 5, 10, atau 15 detik.")
        if not str(wan_t2v_prompt.get("positive_prompt", "")).strip():
            issues.append("Prompt positif WAN22 T2V wajib diisi.")
    if scene_type == MINIMAX_H3_T2V_I2V_SCENE_TYPE:
        try:
            duration_value = float(meta.get("duration_seconds", 0))
        except Exception:
            duration_value = 0
        if not (MINIMAX_H3_DURATION_MIN <= duration_value <= 30.0 and duration_value == round(duration_value, 1)):
            issues.append(
                "Durasi scene minimax-h3_t2v_i2v harus antara 1.0 dan 30.0 detik dengan maksimal 1 angka desimal."
            )
        if not _prompt_text_for_validation(minimax_h3_t2v_prompt.get("positive_prompt")):
            issues.append("Prompt positif MiniMax H3 T2V wajib diisi.")
        if duration_value > 15 and not _prompt_text_for_validation(minimax_h3_i2v_prompt.get("positive_prompt")):
            issues.append("Prompt positif MiniMax H3 I2V wajib diisi untuk durasi di atas 15 detik.")
    if scene_type == MINIMAX_H3_I2V_SCENE_TYPE:
        try:
            duration_value = float(meta.get("duration_seconds", 0))
        except Exception:
            duration_value = 0
        if not (MINIMAX_H3_DURATION_MIN <= duration_value <= 15.0 and duration_value == round(duration_value, 1)):
            issues.append(
                "Durasi scene minimax-h3_i2v harus antara 1.0 dan 15.0 detik dengan maksimal 1 angka desimal."
            )
        if not _prompt_text_for_validation(minimax_h3_i2v_prompt.get("positive_prompt")):
            issues.append("Prompt positif MiniMax H3 I2V wajib diisi.")
        if scene_dir and not find_latest_asset(scene_dir, IMAGE_EXTS):
            issues.append("Adegan MiniMax H3 I2V membutuhkan minimal satu gambar lokal di folder scene.")
    if scene_type == MINIMAX_H3_R2V_SCENE_TYPE:
        try:
            duration_value = float(meta.get("duration_seconds", 0))
        except Exception:
            duration_value = 0
        if not (MINIMAX_H3_DURATION_MIN <= duration_value <= 15.0 and duration_value == round(duration_value, 1)):
            issues.append(
                "Durasi scene minimax-h3_r2v harus antara 1.0 dan 15.0 detik dengan maksimal 1 angka desimal."
            )
        r2v_entry = minimax_h3_r2v_prompt.get("positive_prompt", {})
        r2v_id_new = r2v_entry.get("id_new") if isinstance(r2v_entry, dict) else None
        if not isinstance(r2v_id_new, dict) or validate_ref2va_prompt(r2v_id_new):
            issues.append("Prompt positif MiniMax H3 R2V harus memiliki enam section Ref2VA yang valid.")
        references = minimax_h3_r2v_prompt.get("references", {})
        references = references if isinstance(references, dict) else {}
        images = [str(value).strip() for value in references.get("images", []) if str(value).strip()]
        audios = [str(value).strip() for value in references.get("audios", []) if str(value).strip()]
        video = str(references.get("video", "")).strip()
        if len(images) > 3 or len(audios) > 3:
            issues.append("Reference R2V melebihi batas: maksimal 3 image, 3 audio, dan 1 video.")
        if not images and not audios and not video:
            issues.append("Scene MiniMax H3 R2V membutuhkan minimal satu reference image, audio, atau video.")
        if scene_dir:
            selected_files = images + audios + ([video] if video else [])
            missing = [name for name in selected_files if not (scene_dir / name).is_file()]
            if missing:
                issues.append("Reference R2V tidak ditemukan: " + ", ".join(missing[:3]))
    if scene_type == WAN22_T2V_BATCH_SCENE_TYPE:
        try:
            duration_value = int(meta.get("duration_seconds", 0))
        except Exception:
            duration_value = 0
        if duration_value not in (5, 10):
            issues.append("Durasi scene wan22_t2v_batch hanya boleh 5 atau 10 detik.")
        if not str(wan_t2v_prompt.get("positive_prompt", "")).strip():
            issues.append("Prompt positif WAN22 T2V wajib diisi.")
    if scene_type in {"wan22", "wan22_i2v"}:
        if not str(wan_prompt.get("positive_prompt_one", "")).strip():
            issues.append("Prompt positif WAN pertama wajib diisi.")
        if scene_dir and not find_latest_asset(scene_dir, IMAGE_EXTS):
            issues.append("Adegan WAN membutuhkan minimal satu gambar lokal di folder scene.")
    if scene_type == WAN22_T2V_SCENE_TYPE and not str(wan_prompt.get("positive_prompt_one", "")).strip():
        issues.append("Prompt positif WAN22 I2V pertama wajib diisi.")
    if scene_type == "wan22_s2v":
        if scene_dir and not find_latest_asset(scene_dir, IMAGE_EXTS):
            issues.append("Adegan WAN22 S2V membutuhkan minimal satu gambar di root folder scene.")
        if not str(meta.get("voice_text", "")).strip():
            issues.append("Teks suara wajib diisi untuk WAN22 S2V.")
        speech_asset = find_latest_speech_asset(scene_dir) if scene_dir else None
        if scene_dir and not speech_asset:
            issues.append("Adegan WAN22 S2V membutuhkan minimal satu file audio speech yang berawalan `speech_` di root folder scene.")
        elif speech_asset:
            try:
                duration = get_wan22_s2v_audio_duration(str(speech_asset))
            except Exception:
                issues.append("Durasi audio speech WAN22 S2V tidak dapat dibaca. Pastikan `ffprobe` tersedia dan file audionya valid.")
            else:
                if duration >= WAN22_S2V_MAX_AUDIO_DURATION:
                    issues.append(f"Durasi audio speech WAN22 S2V harus kurang dari {WAN22_S2V_MAX_AUDIO_DURATION} detik.")
    if scene_type == MINIMAX_H3_S2V_SCENE_TYPE:
        if scene_dir and not find_latest_asset(scene_dir, IMAGE_EXTS):
            issues.append("Adegan MiniMax H3 S2V membutuhkan minimal satu gambar di root folder scene.")
        speech_asset = find_latest_speech_asset(scene_dir) if scene_dir else None
        if scene_dir and not speech_asset:
            issues.append("Adegan MiniMax H3 S2V membutuhkan minimal satu file audio speech yang berawalan `speech_` di root folder scene.")
        elif speech_asset:
            try:
                duration = get_minimax_h3_s2v_audio_duration(str(speech_asset))
            except Exception:
                issues.append("Durasi audio speech MiniMax H3 S2V tidak dapat dibaca. Pastikan `ffprobe` tersedia dan file audionya valid.")
            else:
                if duration > MINIMAX_H3_S2V_MAX_AUDIO_DURATION:
                    issues.append(f"Durasi audio speech MiniMax H3 S2V tidak boleh lebih dari {MINIMAX_H3_S2V_MAX_AUDIO_DURATION:g} detik.")
        if not _prompt_text_for_validation(s2v_prompt.get("positive_prompt")):
            issues.append("Prompt positif MiniMax H3 S2V wajib diisi.")
    if scene_type == "web_scroll":
        url = str(web_prompt.get("url", "")).strip()
        if not url:
            issues.append("URL website wajib diisi untuk adegan web_scroll.")
        elif not _is_valid_web_url(url):
            issues.append("Format URL website tidak valid. Gunakan URL dengan http:// atau https://")
        try:
            duration_value = float(web_prompt.get("duration_seconds", -1))
        except Exception:
            issues.append("Durasi web_scroll harus berupa angka desimal 0.0 sampai 20.0 dengan 1 angka di belakang koma.")
        else:
            if duration_value < 0 or duration_value > 20:
                issues.append("Durasi web_scroll harus di antara 0.0 sampai 20.0 detik.")
            elif not _is_one_decimal_step(duration_value):
                issues.append("Durasi web_scroll harus kelipatan 0.1 detik (1 angka di belakang koma).")
        try:
            speed_value = int(web_prompt.get("speed", 0))
        except Exception:
            issues.append("Speed web_scroll harus berupa bilangan bulat positif dari 1 sampai 5.")
        else:
            if speed_value < 1 or speed_value > 5:
                issues.append("Speed web_scroll harus di antara 1 sampai 5.")
    if scene_type == "image_pan":
        if scene_dir and not find_latest_asset(scene_dir, IMAGE_EXTS):
            issues.append("Adegan image_pan membutuhkan satu gambar awal di folder scene.")
        try:
            pan_width = int(image_pan_prompt.get("width", DEFAULT_IMAGE_PAN_PROMPT["width"]))
            pan_height = int(image_pan_prompt.get("height", DEFAULT_IMAGE_PAN_PROMPT["height"]))
        except Exception:
            pan_width = 0
            pan_height = 0
        if pan_width <= 0 or pan_height <= 0:
            issues.append("Ukuran image_pan tidak valid.")
        elif pan_height <= pan_width:
            issues.append("Ukuran image_pan harus portrait (tinggi lebih besar dari lebar).")
        pan_direction = str(image_pan_prompt.get("direction", "from_right")).strip()
        if pan_direction not in {"from_right", "from_left"}:
            issues.append("Arah image_pan tidak valid. Pilih `from_right` atau `from_left`.")
    if scene_type == "image_zoom":
        if scene_dir and not find_latest_asset(scene_dir, IMAGE_EXTS):
            issues.append("Adegan image_zoom membutuhkan satu gambar awal di folder scene.")
        try:
            zoom_width = int(image_zoom_prompt.get("width", DEFAULT_IMAGE_ZOOM_PROMPT["width"]))
            zoom_height = int(image_zoom_prompt.get("height", DEFAULT_IMAGE_ZOOM_PROMPT["height"]))
        except Exception:
            zoom_width = 0
            zoom_height = 0
        if zoom_width <= 0 or zoom_height <= 0:
            issues.append("Ukuran image_zoom tidak valid.")
        zoom_direction = str(image_zoom_prompt.get("zoom_direction", "in")).strip()
        if zoom_direction not in {"in", "out"}:
            issues.append("Arah zoom tidak valid. Pilih `in` (zoom in) atau `out` (zoom out).")
        zoom_focal = str(image_zoom_prompt.get("focal_point", "center")).strip()
        if zoom_focal not in {
            "center", "top_left", "top_center", "top_right",
            "center_left", "center_right",
            "bottom_left", "bottom_center", "bottom_right",
        }:
            issues.append("Titik fokus image_zoom tidak valid.")
        try:
            zoom_strength = float(image_zoom_prompt.get("zoom_strength", 1.3))
        except Exception:
            zoom_strength = 0
        if zoom_strength < 1.0 or zoom_strength > 1.5:
            issues.append("Kekuatan zoom harus di antara 1.0 sampai 1.5.")
    if scene_type == "i2v" and scene_dir and not find_latest_asset(scene_dir, IMAGE_EXTS):
        issues.append("Adegan i2v membutuhkan minimal satu gambar lokal di folder scene.")
    if str(meta.get("voice_text", "")).strip():
        voice_key = resolve_scene_voice_key(meta)
        supported_keys = {key for _label, key in SCENE_VOICE_OPTIONS}
        if voice_key not in supported_keys:
            issues.append("Pilihan suara scene wajib dipilih.")
    return issues


class SceneListWidget(QListWidget):
    orderChanged = Signal()

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.orderChanged.emit()


class SceneTemplateDialog(QDialog):
    def __init__(self, parent=None, title="Tambah Adegan"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.title_input = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "wan22_i2v",
            WAN22_T2V_SCENE_TYPE,
        MINIMAX_H3_T2V_I2V_SCENE_TYPE,
        MINIMAX_H3_R2V_SCENE_TYPE,
            MINIMAX_H3_S2V_SCENE_TYPE,
            WAN22_T2V_BATCH_SCENE_TYPE,
            "wan22_s2v",
            "i2v",
            "web_scroll",
            "image_pan",
            "image_zoom",
        ])
        self.duration_combo = QComboBox()
        populate_duration_combo(self.duration_combo, self.type_combo.currentText(), selected_value=10)
        self.duration_text_input = QLineEdit("10.0")
        self.duration_text_input.setValidator(QDoubleValidator(1.0, 30.0, 1, self.duration_text_input))
        self.duration_text_input.setPlaceholderText("contoh: 15.5")
        self.duration_text_input.setFixedHeight(self.duration_input.sizeHint().height())
        self.duration_editor_stack = QStackedWidget()
        self.duration_editor_stack.addWidget(self.duration_combo)
        self.duration_editor_stack.addWidget(self.duration_text_input)
        self.duration_editor_stack.setFixedHeight(self.duration_input.sizeHint().height())
        form = QFormLayout(self)
        form.addRow("Judul Adegan", self.title_input)
        form.addRow("Tipe Adegan", self.type_combo)
        form.addRow("Durasi (detik)", self.duration_editor_stack)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.type_combo.currentTextChanged.connect(self.update_fields_for_scene_type)
        self.update_fields_for_scene_type(self.type_combo.currentText())

    def update_fields_for_scene_type(self, scene_type: str):
        decimal_scene = scene_type in {
            MINIMAX_H3_T2V_I2V_SCENE_TYPE,
            MINIMAX_H3_I2V_SCENE_TYPE,
            MINIMAX_H3_R2V_SCENE_TYPE,
        }
        if decimal_scene:
            maximum = 30.0 if scene_type == MINIMAX_H3_T2V_I2V_SCENE_TYPE else 15.0
            validator = self.duration_text_input.validator()
            if isinstance(validator, QDoubleValidator):
                validator.setBottom(1.0)
                validator.setTop(maximum)
            self.duration_editor_stack.setCurrentWidget(self.duration_text_input)
            self.duration_text_input.setEnabled(True)
        else:
            populate_duration_combo(self.duration_combo, scene_type)
            self.duration_editor_stack.setCurrentWidget(self.duration_combo)
            self.duration_combo.setEnabled(scene_type not in {"wan22_s2v", MINIMAX_H3_S2V_SCENE_TYPE, "web_scroll"})
            if scene_type == MINIMAX_H3_R2V_SCENE_TYPE:
                self.duration_combo.setEnabled(True)
        self.duration_editor_stack.setEnabled(True)

    def get_data(self):
        scene_type = self.type_combo.currentText()
        if scene_type in {
            MINIMAX_H3_T2V_I2V_SCENE_TYPE,
            MINIMAX_H3_I2V_SCENE_TYPE,
            MINIMAX_H3_R2V_SCENE_TYPE,
        }:
            try:
                duration = round(float(self.duration_text_input.text().strip() or "10.0"), 1)
            except ValueError as exc:
                raise ValueError("Durasi harus berupa angka dengan maksimal 1 angka desimal.") from exc
        else:
            duration = int(self.duration_combo.currentData() or 10)
        return {
            "scene_title": self.title_input.text().strip(),
            "scene_type": scene_type,
            "duration_seconds": duration,
        }


class ProcessDialog(QDialog):
    def __init__(self, log_widget, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Proses")
        self.resize(760, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Log Proses"))
        layout.addWidget(log_widget)


class UiLogEmitter(QObject):
    message = Signal(str)


class UiLogHandler(logging.Handler):
    def __init__(self, emitter: UiLogEmitter):
        super().__init__()
        self._emitter = emitter

    def emit(self, record):
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
            self._emitter.message.emit(str(message))


class RuntimeTaskWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, task):
        super().__init__()
        self.task = task

    def run(self):
        try:
            self.finished.emit(self.task())
        except Exception as exc:
            self.failed.emit(str(exc))


class PromptGenerationWorker(QObject):
    progress = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, prompt_text: str, context_text: str, project_dir: str = ""):
        super().__init__()
        self.prompt_text = prompt_text
        self.context_text = context_text
        self.project_dir = str(project_dir or "").strip()

    def run(self):
        translator = None
        try:
            translator = get_prompt_translator(project_dir=self.project_dir or None)
            provider_name = _normalize_prompt_provider(
                str(getattr(translator, "prompt_generation_provider", "gemini")).strip() or "gemini"
            )
            model_name = str(getattr(translator, "prompt_generation_model_name", "")).strip()
            self.progress.emit(
                f"Membuat prompt multibahasa via {provider_name}" + (f" ({model_name})..." if model_name else "...")
            )
            result = translator.generate_prompt_multilang(self.prompt_text, context=self.context_text)
            if isinstance(result, dict) and isinstance(result.get("en"), dict):
                self.finished.emit({"structured": {"positive_prompt": result}})
            else:
                self.finished.emit({
                    "en": str(result.get("en", "")).strip(),
                    "id_new": str(result.get("id_new", "")).strip(),
                })
        except Exception as e:
            self.failed.emit(str(e))


class WebSearchWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, api_key: str, search_term: str, width: int, height: int, scene_dir: str):
        super().__init__()
        self.api_key = str(api_key or "").strip()
        self.search_term = str(search_term or "").strip()
        self.width = int(width)
        self.height = int(height)
        self.scene_dir = Path(scene_dir)

    def run(self):
        logger = logging.getLogger(__name__)
        try:
            if not self.api_key:
                raise ValueError("API key Firecrawl tidak ditemukan. Tambahkan FIRECRAWLKEY di keys.cfg.")
            orientation_hint = "landscape orientation" if int(self.width) >= int(self.height) else "portrait orientation"
            ratio_hint = f"aspect ratio around {int(self.width)}:{int(self.height)}"
            query = f"{self.search_term} {orientation_hint} {ratio_hint} larger:{int(self.width)}x{int(self.height)}"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            logger.info(
                "[web_search] request firecrawl: query='%s', limit=%s, filter='larger:%sx%s', orientation_hint='%s'.",
                self.search_term,
                10,
                int(self.width),
                int(self.height),
                orientation_hint,
            )
            used_endpoint = "https://api.firecrawl.dev/v2/search"
            payload_v2 = {"query": query, "limit": 10, "sources": ["images"]}
            response = None
            try:
                response = self._post_with_retry(used_endpoint, headers, payload_v2, logger)
                response.raise_for_status()
            except requests.HTTPError as exc:
                status_code = getattr(exc.response, "status_code", None)
                if status_code in {400, 401, 403, 404, 405}:
                    logger.warning("[web_search] v2 search gagal (%s), fallback ke v1/search.", status_code)
                    used_endpoint = "https://api.firecrawl.dev/v1/search"
                    payload_v1 = {"query": query, "limit": 10}
                    response = self._post_with_retry(used_endpoint, headers, payload_v1, logger)
                    response.raise_for_status()
                else:
                    raise
            data = response.json() if response is not None else {}
            logger.info("[web_search] endpoint digunakan: %s", used_endpoint)

            data_root = data.get("data", {}) if isinstance(data, dict) else {}
            urls = []
            if isinstance(data_root, dict):
                image_results = data_root.get("images", [])
                if isinstance(image_results, list):
                    for item in image_results:
                        if isinstance(item, str) and item.startswith(("http://", "https://")):
                            urls.append(item.strip())
                            continue
                        if isinstance(item, dict):
                            for key in ("imageUrl", "url", "image", "src"):
                                value = item.get(key)
                                if isinstance(value, str) and value.startswith(("http://", "https://")):
                                    urls.append(value.strip())
                                    break
            raw_items = data_root if isinstance(data_root, list) else []
            if raw_items:
                for item in raw_items:
                    if not isinstance(item, dict):
                        continue
                    for key in ("imageUrl", "url", "image", "src"):
                        value = item.get(key)
                        if isinstance(value, str) and value.startswith(("http://", "https://")):
                            urls.append(value.strip())
                    image_candidates = item.get("images", [])
                    if isinstance(image_candidates, list):
                        for image_url in image_candidates:
                            if isinstance(image_url, str) and image_url.startswith(("http://", "https://")):
                                urls.append(image_url.strip())
            logger.info("[web_search] response firecrawl: data_type=%s, total_url_kandidat=%s.", type(data_root).__name__, len(urls))

            unique_urls = []
            seen = set()
            for url in urls:
                if url in seen:
                    continue
                seen.add(url)
                unique_urls.append(url)
                if len(unique_urls) >= 10:
                    break
            logger.info("[web_search] url unik gambar: %s.", len(unique_urls))

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            downloaded = []
            logger.info("[web_search] mulai download: total=%s, scene=%s", len(unique_urls), self.scene_dir)
            for index, url in enumerate(unique_urls, start=1):
                try:
                    parsed = urlparse(url)
                    suffix = Path(parsed.path).suffix.lower()
                    if suffix not in IMAGE_EXTS:
                        suffix = ".jpg"
                    filename = f"web_search_{timestamp}_{index:02d}{suffix}"
                    output_path = self.scene_dir / filename
                    with requests.get(url, timeout=30, stream=True) as image_response:
                        image_response.raise_for_status()
                        with output_path.open("wb") as f:
                            for chunk in image_response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                    downloaded.append(str(output_path))
                except Exception as exc:
                    logger.warning("[web_search] gagal download image: url=%s, error=%s", url, exc)
            logger.info("[web_search] selesai download: %s file berhasil disimpan.", len(downloaded))
            self.finished.emit({
                "downloaded_count": len(downloaded),
                "width": int(self.width),
                "height": int(self.height),
                "scene_dir": str(self.scene_dir),
            })
        except Exception as e:
            self.failed.emit(str(e))

    def _post_with_retry(self, url: str, headers: dict, payload: dict, logger: logging.Logger):
        last_error = None
        for attempt in range(1, 4):
            try:
                # Firecrawl search kadang lambat; pakai timeout baca lebih longgar.
                return requests.post(url, headers=headers, json=payload, timeout=(15, 90))
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                logger.warning("[web_search] request attempt %s/3 gagal: %s", attempt, exc)
                if attempt < 3:
                    QThread.msleep(1200 * attempt)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Request Firecrawl gagal tanpa detail error.")


class ComposeMusicDialog(QDialog):
    def __init__(self, music_files: list[Path], compose_song_enabled: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buat Video Final")
        self.music_combo = QComboBox(self)
        self.music_combo.addItem("(Tanpa music)", "")
        for path in music_files:
            self.music_combo.addItem(path.name, str(path))

        self.volume_input = QDoubleSpinBox(self)
        self.volume_input.setRange(0.0, 2.0)
        self.volume_input.setDecimals(2)
        self.volume_input.setSingleStep(0.05)
        self.volume_input.setValue(1.00)
        self.upscale_input = QComboBox(self)
        for label, value in UPSCALE_OPTIONS:
            self.upscale_input.addItem(label, value)
        self.compose_song_input = QCheckBox("Compose Lagu", self)
        self.compose_song_input.setEnabled(bool(compose_song_enabled))
        self.compose_song_input.setToolTip(
            "Gunakan audio S2V tanpa audio ganda; 4 frame ekstra hanya dipotong untuk WAN22 S2V."
            if compose_song_enabled
            else "Compose Lagu hanya tersedia jika semua scene bertipe wan22_s2v atau minimax-h3_s2v."
        )

        layout = QFormLayout(self)
        layout.addRow("File Music", self.music_combo)
        layout.addRow("Upscale", self.upscale_input)
        layout.addRow("Mode", self.compose_song_input)
        layout.addRow("Volume (0.00 - 2.00)", self.volume_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self):
        return (
            str(self.music_combo.currentData() or "").strip(),
            float(self.volume_input.value()),
            float(self.upscale_input.currentData() or 1.0),
            bool(self.compose_song_input.isChecked()),
        )


class UpscaleChoiceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Upscale Video")
        self.resize(320, 120)
        self.scale_input = QComboBox(self)
        for label, value in UPSCALE_ACTION_OPTIONS:
            self.scale_input.addItem(label, value)

        layout = QFormLayout(self)
        layout.addRow("Skala Upscale", self.scale_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_scale_factor(self) -> float:
        return float(self.scale_input.currentData() or 1.5)


class MultiProjectAgenticDialog(QDialog):
    def __init__(self, project_names: list[str], parent=None, on_run=None):
        super().__init__(parent)
        self.setWindowTitle("Jalankan Agentic Multi Project")
        self.resize(420, 520)
        self.on_run = on_run
        self.checkboxes: list[QCheckBox] = []

        root_layout = QVBoxLayout(self)
        info = QLabel("Pilih project yang ingin dijalankan agentic execute secara berurutan.", self)
        info.setWordWrap(True)
        root_layout.addWidget(info)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        for project_name in sorted(project_names, key=lambda value: value.lower()):
            checkbox = QCheckBox(project_name, container)
            self.checkboxes.append(checkbox)
            container_layout.addWidget(checkbox)
        container_layout.addStretch(1)
        scroll.setWidget(container)
        root_layout.addWidget(scroll, 1)

        self.run_button = QToolButton(self)
        self.run_button.setText("Agentic")
        self.run_button.clicked.connect(self._handle_run_clicked)
        root_layout.addWidget(self.run_button, 0, Qt.AlignLeft)

    def selected_projects(self) -> list[str]:
        return [checkbox.text().strip() for checkbox in self.checkboxes if checkbox.isChecked()]

    def _handle_run_clicked(self):
        callback = self.on_run
        if callback is None:
            return
        callback(self.selected_projects())


class ProjectPromptAppendDialog(QDialog):
    def __init__(self, parent=None, on_run=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Prompt")
        self.resize(760, 620)
        self.setMinimumSize(680, 520)
        self.on_run = on_run
        self.inputs: dict[str, QPlainTextEdit] = {}

        root_layout = QVBoxLayout(self)
        info_label = QLabel(
            "Tambahan prompt akan diterapkan ke semua scene dan semua folder variasi pada project aktif.",
            self,
        )
        info_label.setWordWrap(True)
        root_layout.addWidget(info_label)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        for operation_key, config in PROMPT_APPEND_OPERATIONS.items():
            group = QGroupBox(str(config.get("title", operation_key)), container)
            form = QFormLayout(group)
            input_widget = QPlainTextEdit(group)
            input_widget.setPlaceholderText("Masukkan kalimat tambahan dalam Bahasa Indonesia...")
            input_widget.setFixedHeight(88)
            self.inputs[operation_key] = input_widget
            run_button = QToolButton(group)
            run_button.setText("Jalankan")
            run_button.clicked.connect(
                lambda _checked=False, key=operation_key: self._handle_run_clicked(key)
            )
            form.addRow("Teks Tambahan", input_widget)
            form.addRow("", run_button)
            container_layout.addWidget(group)

        container_layout.addStretch(1)
        scroll.setWidget(container)
        root_layout.addWidget(scroll, 1)

    def _handle_run_clicked(self, operation_key: str):
        callback = self.on_run
        if callback is None:
            return
        input_widget = self.inputs.get(operation_key)
        prompt_text = input_widget.toPlainText().strip() if input_widget is not None else ""
        callback(operation_key, prompt_text)


class ProjectSettingsDialog(QDialog):
    def __init__(
        self,
        settings_data: dict,
        parent=None,
        project_dir: str | Path | None = None,
        on_generate_cover=None,
        on_run_agentic_generate=None,
        on_run_agentic_execute=None,
        on_run_clear_vram=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Konfigurasi Project")
        self.resize(760, 620)
        self.setMinimumSize(680, 520)
        self.setSizeGripEnabled(True)
        self.saved_data = None
        self.on_generate_cover = on_generate_cover
        self.on_run_agentic_generate = on_run_agentic_generate
        self.on_run_agentic_execute = on_run_agentic_execute
        self.on_run_clear_vram = on_run_clear_vram
        self.project_dir = Path(project_dir) if project_dir else None
        self._existing_cover_data = copy.deepcopy(DEFAULT_Z_IMAGE_PROMPT)

        self.description_input = QTextEdit(self)
        self.description_input.setMaximumHeight(90)
        self.comfyui_server_input = QLineEdit(self)
        self.video_size_input = QComboBox(self)
        for label, width, height in Z_IMAGE_SIZES:
            self.video_size_input.addItem(label, (width, height))

        self.prompt_provider_input = QComboBox(self)
        self.prompt_provider_input.addItem("Gemini", "gemini")
        self.prompt_provider_input.addItem("llama.cpp", "llama.cpp")
        global_config = load_server_config()
        global_prompt_config = global_config.get("prompt_generation", {})
        global_translate_config = global_config.get("translate", {})
        llama_model = str(global_prompt_config.get("model", "")).strip() if isinstance(global_prompt_config, dict) else ""
        gemini_model = str(global_translate_config.get("model", "")).strip() if isinstance(global_translate_config, dict) else ""
        self._prompt_models_by_provider = {
            "llama.cpp": [llama_model] if llama_model else [],
            "gemini": [gemini_model] if gemini_model else [],
        }
        self._gemini_prompt_models = list(self._prompt_models_by_provider["gemini"])
        self._pending_prompt_model_value = ""
        self._is_loading_project_settings = False
        self._ollama_models_refresh_timer = QTimer(self)
        self._ollama_models_refresh_timer.setSingleShot(True)
        self._ollama_models_refresh_timer.setInterval(450)
        self._ollama_models_refresh_timer.timeout.connect(self._refresh_ollama_models)

        self.prompt_model_input = QComboBox(self)
        self.prompt_model_input.setEditable(False)
        self.prompt_model_input.setPlaceholderText("Pilih model...")
        for model_name in self._gemini_prompt_models:
            self.prompt_model_input.addItem(model_name, model_name)
        self.prompt_ollama_host_input = QLineEdit(self)
        self.prompt_ollama_port_input = QSpinBox(self)
        self.prompt_ollama_port_input.setRange(1, 65535)
        self.prompt_ollama_port_input.setValue(8080)
        self.prompt_ollama_server_widget = QWidget(self)
        prompt_ollama_server_layout = QHBoxLayout(self.prompt_ollama_server_widget)
        prompt_ollama_server_layout.setContentsMargins(0, 0, 0, 0)
        prompt_ollama_server_layout.setSpacing(8)
        prompt_ollama_server_layout.addWidget(self.prompt_ollama_host_input, 1)
        prompt_ollama_server_layout.addWidget(self.prompt_ollama_port_input, 0)

        self.voice_provider_input = QComboBox(self)
        for provider_label, provider_key in VOICE_PROVIDER_OPTIONS:
            self.voice_provider_input.addItem(provider_label, provider_key)

        self.caption_enabled_input = QCheckBox("Aktifkan Generate Caption otomatis", self)

        self.cover_model_input = QComboBox(self)
        for model_key, label in IMAGE_MODEL_OPTIONS:
            self.cover_model_input.addItem(label, model_key)
        self.cover_gemini_model_input = QComboBox(self)
        for model_id in list_gemini_image_models():
            self.cover_gemini_model_input.addItem(model_id, model_id)
        self.cover_size_input = QComboBox(self)
        for label, width, height in Z_IMAGE_SIZES:
            self.cover_size_input.addItem(label, (width, height))
        self.cover_use_random_seed_input = QCheckBox("Random Seed", self)
        self.cover_seed_input = QLineEdit(self)
        self.cover_use_lora_input = QCheckBox("Pakai Lora", self)
        self.cover_lora_name_input = QComboBox(self)
        self.cover_lora_name_input.setEditable(False)
        self.cover_lora_strength_input = QLineEdit(self)
        self.cover_positive_input = QTextEdit(self)
        self.cover_negative_input = QTextEdit(self)
        self.cover_positive_input.setMaximumHeight(110)
        self.cover_negative_input.setMaximumHeight(110)

        root_layout = QVBoxLayout(self)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        container = QWidget(self)
        self.form_layout = QFormLayout(container)
        self.form_layout.addRow("Deskripsi Project", self.description_input)
        self.form_layout.addRow("ComfyUI Server", self.comfyui_server_input)
        self.form_layout.addRow("Ukuran Video Project", self.video_size_input)
        self.form_layout.addRow("Provider Prompt Generation", self.prompt_provider_input)
        self.form_layout.addRow("Model Prompt Generation", self.prompt_model_input)
        self.form_layout.addRow("llama.cpp Host / Port", self.prompt_ollama_server_widget)
        self.form_layout.addRow("Voice Project", self.voice_provider_input)
        self.form_layout.addRow("Caption Project", self.caption_enabled_input)

        self.form_layout.addRow(QLabel("Konfigurasi Cover"))
        self.form_layout.addRow("Model Cover", self.cover_model_input)
        self.form_layout.addRow("Model Gemini Cover", self.cover_gemini_model_input)
        self.form_layout.addRow("Ukuran Cover", self.cover_size_input)
        self.form_layout.addRow("", self.cover_use_random_seed_input)
        self.form_layout.addRow("Seed Statik Cover", self.cover_seed_input)
        self.form_layout.addRow("", self.cover_use_lora_input)
        self.form_layout.addRow("Nama Lora Cover", self.cover_lora_name_input)
        self.form_layout.addRow("Kekuatan Lora Cover", self.cover_lora_strength_input)
        self.form_layout.addRow("Prompt Positif Cover", self.cover_positive_input)
        self.form_layout.addRow("Prompt Negatif Cover", self.cover_negative_input)
        scroll.setWidget(container)
        root_layout.addWidget(scroll, 1)

        self.generate_cover_button = QToolButton(self)
        self.generate_cover_button.setText("Generate Cover")
        self.generate_cover_button.clicked.connect(self._on_generate_cover_clicked)
        self.run_agentic_generate_button = QToolButton(self)
        self.run_agentic_generate_button.setText("Generate Config Agentic")
        self.run_agentic_generate_button.clicked.connect(self._on_run_agentic_generate_clicked)
        self.run_agentic_execute_button = QToolButton(self)
        self.run_agentic_execute_button.setText("Execute Agentic")
        self.run_agentic_execute_button.clicked.connect(self._on_run_agentic_execute_clicked)
        self.clear_vram_button = QToolButton(self)
        self.clear_vram_button.setText("Clear VRAM")
        self.clear_vram_button.setToolTip("Jalankan VRAM cleaner di ComfyUI untuk project aktif.")
        self.clear_vram_button.clicked.connect(self._on_run_clear_vram_clicked)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        self.buttons.accepted.connect(self._on_save_clicked)
        self.buttons.rejected.connect(self.reject)
        button_row = QHBoxLayout()
        button_row.addWidget(self.generate_cover_button)
        button_row.addWidget(self.run_agentic_generate_button)
        button_row.addWidget(self.run_agentic_execute_button)
        button_row.addWidget(self.clear_vram_button)
        button_row.addStretch(1)
        button_row.addWidget(self.buttons)
        root_layout.addLayout(button_row, 0)

        self.cover_use_random_seed_input.toggled.connect(self._update_cover_seed_enabled)
        self.cover_use_lora_input.toggled.connect(self._update_cover_lora_enabled)
        self.cover_model_input.currentIndexChanged.connect(self._update_cover_model_fields)
        self.video_size_input.currentIndexChanged.connect(self._sync_cover_size_with_project_size)
        self.prompt_provider_input.currentIndexChanged.connect(self._update_prompt_generation_fields)
        self.prompt_model_input.currentIndexChanged.connect(self._remember_prompt_model_selection)

        self._load_data(settings_data)
        self._sync_cover_size_with_project_size()
        self._update_cover_seed_enabled()
        self._update_cover_lora_enabled()
        self._update_cover_model_fields()
        self._update_prompt_generation_fields()
        self._is_loading_project_settings = False

    def _set_model_combo_value(self, combo: QComboBox, value: str):
        value = str(value or "").strip()
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setCurrentIndex(0 if combo.count() > 0 else -1)

    def _load_data(self, data: dict):
        self._is_loading_project_settings = True
        self.description_input.setPlainText(str(data.get("project_description", "")))
        self.comfyui_server_input.setText(
            str(data.get("comfyui_server", DEFAULT_PROJECT_SETTINGS["comfyui_server"])).strip()
        )

        size = data.get("video_size", {})
        width = int(size.get("width", DEFAULT_PROJECT_SETTINGS["video_size"]["width"]))
        height = int(size.get("height", DEFAULT_PROJECT_SETTINGS["video_size"]["height"]))
        index = -1
        for i in range(self.video_size_input.count()):
            item_size = self.video_size_input.itemData(i)
            if isinstance(item_size, tuple) and item_size == (width, height):
                index = i
                break
        self.video_size_input.setCurrentIndex(max(index, 0))

        prompt_generation = data.get("prompt_generation", {})
        prompt_generation = prompt_generation if isinstance(prompt_generation, dict) else {}
        self.prompt_ollama_host_input.setText(
            str(prompt_generation.get("host", DEFAULT_PROJECT_SETTINGS["prompt_generation"]["host"])).strip()
        )
        self.prompt_ollama_port_input.setValue(
            int(prompt_generation.get("port", DEFAULT_PROJECT_SETTINGS["prompt_generation"]["port"]))
        )
        prompt_provider = str(prompt_generation.get("provider", "gemini")).strip().lower() or "gemini"
        prompt_provider = _normalize_prompt_provider(prompt_provider)
        self._pending_prompt_model_value = str(prompt_generation.get("model", "")).strip()
        prompt_provider_index = self.prompt_provider_input.findData(prompt_provider)
        self.prompt_provider_input.setCurrentIndex(max(prompt_provider_index, 0))

        voice = data.get("voice", {})
        voice_provider = normalize_provider(voice.get("voice_provider", VOICE_PROVIDER_GEMINI))
        voice_index = self.voice_provider_input.findData(voice_provider)
        self.voice_provider_input.setCurrentIndex(max(voice_index, 0))

        caption = data.get("caption", {})
        self.caption_enabled_input.setChecked(bool(caption.get("generate_caption", True)))

        cover = data.get("cover", {}) if isinstance(data.get("cover"), dict) else {}
        self._existing_cover_data = copy.deepcopy(cover)
        cover_model_key = get_z_image_model_key(cover)
        cover_model_index = self.cover_model_input.findData(cover_model_key)
        self.cover_model_input.setCurrentIndex(max(cover_model_index, 0))
        cover_gemini_model = str(cover.get("gemini_model_id", MODEL_GEMINI_FLASH_05K)).strip()
        cover_gemini_index = self.cover_gemini_model_input.findData(cover_gemini_model)
        if cover_gemini_index < 0 and cover_gemini_model:
            self.cover_gemini_model_input.addItem(cover_gemini_model, cover_gemini_model)
            cover_gemini_index = self.cover_gemini_model_input.findData(cover_gemini_model)
        self.cover_gemini_model_input.setCurrentIndex(max(cover_gemini_index, 0))
        cover_width = int(cover.get("width", DEFAULT_Z_IMAGE_PROMPT["width"]))
        cover_height = int(cover.get("height", DEFAULT_Z_IMAGE_PROMPT["height"]))
        cover_size_index = -1
        for i in range(self.cover_size_input.count()):
            size_val = self.cover_size_input.itemData(i)
            if isinstance(size_val, tuple) and size_val == (cover_width, cover_height):
                cover_size_index = i
                break
        self.cover_size_input.setCurrentIndex(max(cover_size_index, 0))
        self.cover_use_random_seed_input.setChecked(bool(cover.get("use_random_seed", True)))
        self.cover_seed_input.setText(str(cover.get("seed", 1)))
        self.cover_use_lora_input.setChecked(bool(cover.get("use_lora", False)))
        self._refresh_cover_lora_options(cover_model_key, str(cover.get("lora_name", "")), preserve_missing=True)
        self.cover_lora_strength_input.setText(str(cover.get("strength_model", 1.0)))
        cover_ui = convert_prompt_payload_for_ui("project_settings_cover.json", cover)
        self.cover_positive_input.setPlainText(str(cover_ui.get("positive_prompt", "")))
        self.cover_negative_input.setPlainText(str(cover_ui.get("negative_prompt", "")))
        self._update_prompt_generation_fields()

    def _sync_cover_size_with_project_size(self):
        size_data = self.video_size_input.currentData() or (
            DEFAULT_PROJECT_SETTINGS["video_size"]["width"],
            DEFAULT_PROJECT_SETTINGS["video_size"]["height"],
        )
        width = int(size_data[0])
        height = int(size_data[1])
        self.cover_size_input.blockSignals(True)
        self.cover_size_input.clear()
        self.cover_size_input.addItem(f"{width}x{height}", (width, height))
        self.cover_size_input.setCurrentIndex(0)
        self.cover_size_input.setEnabled(False)
        self.cover_size_input.blockSignals(False)

    def _update_cover_seed_enabled(self):
        self.cover_seed_input.setEnabled(not self.cover_use_random_seed_input.isChecked())

    def _update_prompt_generation_fields(self):
        provider = _normalize_prompt_provider(self.prompt_provider_input.currentData() or "gemini")
        is_ollama = _is_local_prompt_provider(provider)
        self.prompt_ollama_server_widget.setVisible(is_ollama)
        label = self.form_layout.labelForField(self.prompt_ollama_server_widget) if hasattr(self, "form_layout") else None
        if label is not None:
            label.setVisible(is_ollama)
        model_options = self._prompt_models_by_provider.get(provider, [])
        selected_value = model_options[0] if model_options else ""
        self._set_prompt_model_choices(model_options, selected_value)

    def _set_prompt_model_choices(self, model_names: list[str], selected_value: str = ""):
        selected_value = str(selected_value or "").strip()
        current_value = (
            str(self.prompt_model_input.currentData() or "").strip()
            or str(self.prompt_model_input.currentText() or "").strip()
        )
        target_value = selected_value or current_value
        normalized_models = []
        seen = set()
        for raw_name in model_names:
            name = str(raw_name or "").strip()
            if not name or name in seen:
                continue
            normalized_models.append(name)
            seen.add(name)
        self.prompt_model_input.blockSignals(True)
        self.prompt_model_input.clear()
        for name in normalized_models:
            self.prompt_model_input.addItem(name, name)
        if target_value and self.prompt_model_input.findData(target_value) < 0:
            self.prompt_model_input.addItem(target_value, target_value)
        self.prompt_model_input.blockSignals(False)
        if self.prompt_model_input.count() > 0:
            index = self.prompt_model_input.findData(target_value)
            if index < 0:
                index = 0
            self.prompt_model_input.setCurrentIndex(index)
            self._pending_prompt_model_value = (
                str(self.prompt_model_input.currentData() or "").strip()
                or str(self.prompt_model_input.currentText() or "").strip()
            )
        else:
            self.prompt_model_input.setCurrentIndex(-1)
            self._pending_prompt_model_value = target_value

    def _remember_prompt_model_selection(self):
        if self._is_loading_project_settings:
            return
        self._pending_prompt_model_value = (
            str(self.prompt_model_input.currentData() or "").strip()
            or str(self.prompt_model_input.currentText() or "").strip()
        )

    def _schedule_ollama_model_refresh(self):
        provider = _normalize_prompt_provider(self.prompt_provider_input.currentData() or "gemini")
        if not _is_local_prompt_provider(provider):
            return
        current_value = (
            str(self.prompt_model_input.currentData() or "").strip()
            or str(self.prompt_model_input.currentText() or "").strip()
        )
        self._pending_prompt_model_value = current_value or self._pending_prompt_model_value
        if self._is_loading_project_settings:
            return
        self._ollama_models_refresh_timer.start()

    def _refresh_ollama_models(self):
        provider = _normalize_prompt_provider(self.prompt_provider_input.currentData() or "gemini")
        if not _is_local_prompt_provider(provider):
            return
        host = self.prompt_ollama_host_input.text().strip()
        port = int(self.prompt_ollama_port_input.value())
        if not host or port <= 0:
            self._set_prompt_model_choices([], self._pending_prompt_model_value)
            return
        base_url = host if host.startswith(("http://", "https://")) else f"http://{host}"
        model_names = []
        for url, parser in (
            (f"{base_url.rstrip('/')}:{port}/v1/models", "openai"),
            (f"{base_url.rstrip('/')}:{port}/api/tags", "ollama"),
        ):
            try:
                response = requests.get(url, timeout=3)
                response.raise_for_status()
                payload = response.json() if response.content else {}
                if parser == "openai":
                    models = payload.get("data", []) if isinstance(payload, dict) else []
                    if isinstance(models, list):
                        for item in models:
                            if isinstance(item, dict):
                                model_name = str(item.get("id", "")).strip()
                                if model_name:
                                    model_names.append(model_name)
                else:
                    models = payload.get("models", []) if isinstance(payload, dict) else []
                    if isinstance(models, list):
                        for item in models:
                            if isinstance(item, dict):
                                model_name = str(item.get("name", "")).strip()
                                if model_name:
                                    model_names.append(model_name)
                if model_names:
                    break
            except Exception:
                continue
        self._set_prompt_model_choices(model_names, self._pending_prompt_model_value)

    def _update_cover_lora_enabled(self):
        enabled = self.cover_use_lora_input.isChecked()
        self.cover_lora_name_input.setEnabled(enabled)
        self.cover_lora_strength_input.setEnabled(enabled)

    def _refresh_cover_lora_options(
        self,
        model_key: str | None = None,
        current_value: str = "",
        *,
        preserve_missing: bool = False,
    ):
        model_key = str(model_key or self.cover_model_input.currentData() or MODEL_Z_IMAGE_TURBO).strip()
        server = str(self.comfyui_server_input.text().strip() or DEFAULT_PROJECT_SETTINGS["comfyui_server"])
        if model_key == MODEL_GEMINI_IMAGE:
            populate_lora_combo(
                self.cover_lora_name_input,
                [],
                current_value=current_value,
                template_default="",
                preserve_missing=preserve_missing,
            )
            self.cover_lora_name_input.setEnabled(False)
            return
        if model_key == MODEL_FLUX2_K9:
            options = get_lora_options_by_prefix(server, LORA_PREFIX_FLUX2_K9)
        elif model_key == MODEL_FLUX2:
            options = get_lora_options_by_prefix(server, LORA_PREFIX_FLUX2)
        else:
            options = get_lora_options_by_prefix(server, LORA_PREFIX_Z_IMAGE)
        populate_lora_combo(
            self.cover_lora_name_input,
            options,
            current_value=current_value,
            preserve_missing=preserve_missing,
        )

    def _update_cover_model_fields(self):
        model_key = str(self.cover_model_input.currentData() or MODEL_Z_IMAGE_TURBO)
        is_gemini = model_key == MODEL_GEMINI_IMAGE
        supports_negative = z_image_supports_negative_prompt({"image_model": model_key})
        self.cover_gemini_model_input.setVisible(is_gemini)
        label = self.form_layout.labelForField(self.cover_gemini_model_input) if hasattr(self, "form_layout") else None
        if label is not None:
            label.setVisible(is_gemini)
        self.cover_negative_input.setEnabled(supports_negative)
        if not supports_negative:
            self.cover_negative_input.setPlainText("")
        self.cover_use_lora_input.setEnabled(not is_gemini)
        self.cover_use_random_seed_input.setEnabled(not is_gemini)
        if is_gemini:
            self.cover_use_lora_input.setChecked(False)
            self.cover_use_random_seed_input.setChecked(True)
            self.cover_seed_input.setText("1")
            self.cover_lora_name_input.setEnabled(False)
        else:
            self._refresh_cover_lora_options(
                model_key,
                self.cover_lora_name_input.currentText().strip(),
                preserve_missing=bool(self._is_loading_project_settings),
            )
        self._update_cover_seed_enabled()
        self._update_cover_lora_enabled()

    def get_data(self):
        prompt_provider = _normalize_prompt_provider(self.prompt_provider_input.currentData() or "gemini")
        prompt_model = str(self.prompt_model_input.currentText() or "").strip()
        project_description = self.description_input.toPlainText().strip()
        comfyui_server = self.comfyui_server_input.text().strip()
        if not project_description:
            raise ValueError("Deskripsi project wajib diisi.")
        if not comfyui_server:
            raise ValueError("ComfyUI Server wajib diisi.")
        if ":" not in comfyui_server:
            raise ValueError("Format ComfyUI Server harus <ip/host>:<port>.")
        host_part, port_part = comfyui_server.rsplit(":", 1)
        if not host_part.strip():
            raise ValueError("Host ComfyUI tidak valid.")
        try:
            port_value = int(port_part.strip())
        except ValueError as e:
            raise ValueError("Port ComfyUI harus berupa angka.") from e
        if port_value <= 0:
            raise ValueError("Port ComfyUI harus lebih besar dari 0.")
        if not prompt_model:
            raise ValueError("Model Prompt Generation wajib diisi.")
        prompt_ollama_host = self.prompt_ollama_host_input.text().strip()
        prompt_ollama_port = int(self.prompt_ollama_port_input.value())
        if _is_local_prompt_provider(prompt_provider):
            if not prompt_ollama_host:
                raise ValueError("Host llama.cpp wajib diisi.")
            if prompt_ollama_port <= 0:
                raise ValueError("Port llama.cpp harus lebih besar dari 0.")
        size_data = self.video_size_input.currentData() or (
            DEFAULT_PROJECT_SETTINGS["video_size"]["width"],
            DEFAULT_PROJECT_SETTINGS["video_size"]["height"],
        )
        cover_model_key = str(self.cover_model_input.currentData() or MODEL_Z_IMAGE_TURBO)
        cover_use_lora = self.cover_use_lora_input.isChecked()
        cover_use_random_seed = self.cover_use_random_seed_input.isChecked()
        cover_seed_val = 1
        if not cover_use_random_seed:
            try:
                cover_seed_val = int(self.cover_seed_input.text().strip() or "1")
            except ValueError:
                raise ValueError("Seed statik cover harus berupa bilangan bulat positif.")
            if cover_seed_val <= 0:
                raise ValueError("Seed statik cover harus berupa bilangan bulat positif.")
        cover_lora_strength = 1.0
        if cover_use_lora:
            try:
                cover_lora_strength = float(self.cover_lora_strength_input.text().strip() or "1.0")
            except ValueError:
                raise ValueError("Kekuatan Lora cover harus berupa bilangan desimal positif.")
            if cover_lora_strength <= 0:
                raise ValueError("Kekuatan Lora cover harus berupa bilangan desimal positif.")
        cover_data = {
            "image_model": cover_model_key,
            "gemini_model_id": (
                str(self.cover_gemini_model_input.currentData() or MODEL_GEMINI_FLASH_05K).strip()
                if cover_model_key == MODEL_GEMINI_IMAGE
                else ""
            ),
            "positive_prompt": self.cover_positive_input.toPlainText().strip(),
            "negative_prompt": (
                self.cover_negative_input.toPlainText().strip()
                if z_image_supports_negative_prompt({"image_model": cover_model_key})
                else ""
            ),
            "width": int((self.cover_size_input.currentData() or (368, 640))[0]),
            "height": int((self.cover_size_input.currentData() or (368, 640))[1]),
            "use_random_seed": cover_use_random_seed,
            "seed": cover_seed_val,
            "use_lora": cover_use_lora,
            "lora_name": self.cover_lora_name_input.currentText().strip() if cover_use_lora else "",
            "strength_model": cover_lora_strength,
        }
        cover_data = prepare_prompt_payload_for_save(
            "project_settings_cover.json",
            cover_data,
            existing_data=self._existing_cover_data,
        )
        cover_data["json_api"] = get_z_image_template_name(cover_data)
        if not cover_data["positive_prompt"]:
            raise ValueError("Prompt positif cover wajib diisi.")
        if cover_use_lora and not cover_data["lora_name"]:
            raise ValueError("Nama Lora cover wajib diisi saat Lora digunakan.")

        return {
            "project_description": project_description,
            "comfyui_server": f"{host_part.strip()}:{port_value}",
            "video_size": {"width": int(size_data[0]), "height": int(size_data[1])},
            "prompt_generation": {
                "provider": prompt_provider,
                "model": prompt_model,
                "host": prompt_ollama_host or DEFAULT_PROJECT_SETTINGS["prompt_generation"]["host"],
                "port": prompt_ollama_port,
            },
            "translate": {
                "provider": prompt_provider,
                "model": prompt_model,
            },
            "voice": {"voice_provider": normalize_provider(self.voice_provider_input.currentData() or VOICE_PROVIDER_GEMINI)},
            "caption": {"generate_caption": bool(self.caption_enabled_input.isChecked())},
            "cover": cover_data,
        }

    def _on_save_clicked(self):
        try:
            self.saved_data = self.get_data()
        except ValueError as e:
            QMessageBox.warning(self, "Konfigurasi Project Tidak Valid", str(e))
            return
        self.accept()

    def _on_generate_cover_clicked(self):
        try:
            data = self.get_data()
        except ValueError as e:
            QMessageBox.warning(self, "Konfigurasi Project Tidak Valid", str(e))
            return
        if callable(self.on_generate_cover):
            self.on_generate_cover(data)

    def _on_run_agentic_generate_clicked(self):
        try:
            data = self.get_data()
        except ValueError as e:
            QMessageBox.warning(self, "Konfigurasi Project Tidak Valid", str(e))
            return
        if callable(self.on_run_agentic_generate):
            self.on_run_agentic_generate(data)

    def _on_run_agentic_execute_clicked(self):
        try:
            data = self.get_data()
        except ValueError as e:
            QMessageBox.warning(self, "Konfigurasi Project Tidak Valid", str(e))
            return
        if callable(self.on_run_agentic_execute):
            self.on_run_agentic_execute(data)

    def _on_run_clear_vram_clicked(self):
        try:
            data = self.get_data()
        except ValueError as e:
            QMessageBox.warning(self, "Konfigurasi Project Tidak Valid", str(e))
            return
        if callable(self.on_run_clear_vram):
            self.on_run_clear_vram(data)


class MediaPreviewLabel(QLabel):
    activated = Signal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._source_pixmap = QPixmap()
        self._source_path = None
        self._suppress_release = False
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(220)
        self._click_timer.timeout.connect(self.activated.emit)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("border: 1px solid #d1d5db; background: #fafafa;")

    def set_preview_pixmap(self, pixmap: QPixmap):
        self._source_pixmap = pixmap
        self._refresh_scaled_pixmap()

    def clear_preview(self, text=""):
        self._source_pixmap = QPixmap()
        self._source_path = None
        self._suppress_release = False
        self._click_timer.stop()
        self.clear()
        if text:
            self.setText(text)

    def set_source_path(self, path):
        self._source_path = Path(path) if path else None

    def source_path(self):
        return self._source_path

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._suppress_release:
                self._suppress_release = False
                event.accept()
                return
            self._click_timer.start()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._click_timer.isActive():
                self._click_timer.stop()
            self._suppress_release = True
            self.activated.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_scaled_pixmap()

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(240, 160)

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(160, 120)

    def _refresh_scaled_pixmap(self):
        if self._source_pixmap.isNull():
            return
        target_size = self.contentsRect().size()
        if target_size.width() <= 1 or target_size.height() <= 1:
            return
        scaled = self._source_pixmap.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)


class SceneEditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pengelola Adegan")
        self.resize(1700, 980)
        self.current_project_name = ""
        self.current_scene_dir = None
        self.current_scene_view_dir = None
        self.project_voice_config = copy.deepcopy(DEFAULT_PROJECT_VOICE_CONFIG)
        self.project_caption_config = copy.deepcopy(DEFAULT_PROJECT_CAPTION_CONFIG)
        self.project_settings = copy.deepcopy(DEFAULT_PROJECT_SETTINGS)
        self.process = None
        self.process_context = None
        self.runtime_task_thread = None
        self.runtime_task_worker = None
        self.multi_project_agentic_queue: list[str] = []
        self.multi_project_agentic_completed: list[str] = []
        self.loading_scene = False
        self.editor_tabs = None
        self.meta_tab = None
        self.z_tab = None
        self.wan_t2v_tab = None
        self.wan_tab = None
        self.minimax_h3_t2v_tab = None
        self.minimax_h3_i2v_tab = None
        self.minimax_h3_r2v_tab = None
        self.s2v_tab = None
        self.web_tab = None
        self.web_search_tab = None
        self.image_edit_tab = None
        self.t2v_batch_extra_tab = None
        self.agentic_tab = None
        self.assets_tab = None
        self.generate_initial_image_button = None
        self.duration_label = None
        self.s2v_negative_label = None
        self.s2v_cfg_label = None
        self.scene_list = SceneListWidget()
        self.scene_list.currentItemChanged.connect(self.on_scene_changed)
        self.scene_list.orderChanged.connect(self.on_scene_reordered)
        self.toolbar = None
        self.prompt_generation_thread = None
        self.prompt_generation_worker = None
        self.prompt_generation_context = None
        self.web_search_thread = None
        self.web_search_worker = None
        self._loading_variation_view = False
        self.project_action_group_widget = None
        self.scene_action_group_widget = None
        self.edit_prompt_action_group_widget = None
        self.variation_action_group_widget = None
        self.run_action_group_widget = None
        self.audio_action_group_widget = None
        self.backup_action_group_widget = None
        self.compose_action_group_widget = None
        self.runtime_action_group_widget = None
        self.runtime_switch_buttons = []
        self.runtime_status_button = None

        self.scene_title_input = QLineEdit()
        self.scene_description_input = QTextEdit()
        self.scene_description_input.setFixedHeight(80)
        self.scene_description_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.duration_input = QComboBox()
        populate_duration_combo(self.duration_input, "wan22_i2v", selected_value=10)
        self.duration_decimal_input = QLineEdit("10.0")
        self.duration_decimal_input.setValidator(QDoubleValidator(MINIMAX_H3_DURATION_MIN, 30.0, MINIMAX_H3_DURATION_DECIMALS, self.duration_decimal_input))
        self.duration_decimal_input.setPlaceholderText("contoh: 15.5")
        self.duration_decimal_input.setFixedHeight(self.duration_input.sizeHint().height())
        self.duration_input_stack = QStackedWidget()
        self.duration_input_stack.addWidget(self.duration_input)
        self.duration_input_stack.addWidget(self.duration_decimal_input)
        self.duration_input_stack.setFixedHeight(self.duration_input.sizeHint().height())
        self.scene_type_combo = QComboBox()
        self.scene_type_combo.addItems([
            "wan22_i2v",
            WAN22_T2V_SCENE_TYPE,
            MINIMAX_H3_T2V_I2V_SCENE_TYPE,
            MINIMAX_H3_I2V_SCENE_TYPE,
            MINIMAX_H3_S2V_SCENE_TYPE,
            MINIMAX_H3_R2V_SCENE_TYPE,
            WAN22_T2V_BATCH_SCENE_TYPE,
            "wan22_s2v",
            "i2v",
            "web_scroll",
            "image_pan",
            "image_zoom",
        ])
        self.scene_voice_character_input = QComboBox()
        for voice_label, voice_key in SCENE_VOICE_OPTIONS:
            self.scene_voice_character_input.addItem(voice_label, voice_key)
        self.voice_text_input = QTextEdit()
        voice_line_height = self.voice_text_input.fontMetrics().lineSpacing()
        self.voice_text_input.setFixedHeight((voice_line_height * 10) + 16)
        self.voice_text_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.sound_prompt_input = QTextEdit()
        self.sound_prompt_input.setFixedHeight(80)
        self.sound_prompt_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.sound_volume_input = QLineEdit()
        self.z_positive_input = QTextEdit()
        self.z_model_input = QComboBox()
        for model_key, label in IMAGE_MODEL_OPTIONS:
            self.z_model_input.addItem(label, model_key)
        self.z_gemini_model_input = QComboBox()
        self.z_gemini_model_ids = list_gemini_image_models()
        for model_id in self.z_gemini_model_ids:
            self.z_gemini_model_input.addItem(model_id, model_id)
        self.z_negative_input = QTextEdit()
        self.z_clipboard_button = QToolButton()
        self.z_clipboard_button.setText("Image Gen Prompt")
        self.z_clipboard_button.clicked.connect(self.copy_z_image_skill_prompt_to_clipboard)
        self.z_generate_prompt_button = QToolButton()
        self.z_generate_prompt_button.setText("Buat Prompt")
        self.z_generate_prompt_button.clicked.connect(self.generate_z_prompt_from_ui)
        self.copy_z_variations_button = QToolButton()
        self.copy_z_variations_button.setText("Edit Variasi")
        self.copy_z_variations_button.clicked.connect(self.copy_z_config_to_variations)
        self.z_extra_positive_inputs = []
        self.z_extra_negative_inputs = []
        self.z_extra_clipboard_buttons = []
        self.z_extra_generate_prompt_buttons = []
        self.z_extra_buttons = []
        self.z_size_input = QComboBox()
        for label, width, height in Z_IMAGE_SIZES:
            self.z_size_input.addItem(label, (width, height))
        self.z_use_random_seed_input = QCheckBox("Random Seed")
        self.z_use_random_seed_input.setChecked(True)
        self.z_seed_input = QLineEdit()
        self.z_use_lora_input = QCheckBox("Pakai Lora")
        self.z_lora_name_input = QComboBox()
        self.z_lora_name_input.setEditable(False)
        self.z_lora_strength_input = QLineEdit()
        self.z_lora_trigger_words_input = QLineEdit()
        for slot_index in range(3):
            positive_input = QTextEdit()
            negative_input = QTextEdit()
            clipboard_button = QToolButton()
            clipboard_button.setText("Image Gen Prompt")
            clipboard_button.clicked.connect(
                lambda _checked=False, idx=slot_index: self.copy_extra_image_skill_prompt_to_clipboard(idx)
            )
            generate_button = QToolButton()
            generate_button.setText("Buat Prompt")
            generate_button.clicked.connect(lambda _checked=False, idx=slot_index: self.generate_extra_prompt_from_ui(idx))
            button = QToolButton()
            button.setText("Buat Image")
            button.clicked.connect(lambda _checked=False, idx=slot_index: self.run_extra_image_slot(idx))
            self.z_extra_positive_inputs.append(positive_input)
            self.z_extra_negative_inputs.append(negative_input)
            self.z_extra_clipboard_buttons.append(clipboard_button)
            self.z_extra_generate_prompt_buttons.append(generate_button)
            self.z_extra_buttons.append(button)
        self.wan_size_input = QComboBox()
        for label, width, height in WAN_SIZE_OPTIONS:
            self.wan_size_input.addItem(label, (width, height))
        self.wan_lora_high_name_input = QComboBox()
        self.wan_lora_high_name_input.setEditable(False)
        self.wan_lora_high_strength_input = QLineEdit()
        self.wan_lora_low_name_input = QComboBox()
        self.wan_lora_low_name_input.setEditable(False)
        self.wan_lora_low_strength_input = QLineEdit()
        self.wan_lora_high2_name_input = QComboBox()
        self.wan_lora_high2_name_input.setEditable(False)
        self.wan_lora_high2_strength_input = QLineEdit()
        self.wan_lora_low2_name_input = QComboBox()
        self.wan_lora_low2_name_input.setEditable(False)
        self.wan_lora_low2_strength_input = QLineEdit()
        self.wan_lora_trigger_words_input = QLineEdit()
        self.wan_t2v_size_input = QComboBox()
        for label, width, height in WAN_SIZE_OPTIONS:
            self.wan_t2v_size_input.addItem(label, (width, height))
        self.wan_t2v_lora_high_name_input = QComboBox()
        self.wan_t2v_lora_high_name_input.setEditable(False)
        self.wan_t2v_lora_high_strength_input = QLineEdit()
        self.wan_t2v_lora_low_name_input = QComboBox()
        self.wan_t2v_lora_low_name_input.setEditable(False)
        self.wan_t2v_lora_low_strength_input = QLineEdit()
        self.wan_t2v_lora_high2_name_input = QComboBox()
        self.wan_t2v_lora_high2_name_input.setEditable(False)
        self.wan_t2v_lora_high2_strength_input = QLineEdit()
        self.wan_t2v_lora_low2_name_input = QComboBox()
        self.wan_t2v_lora_low2_name_input.setEditable(False)
        self.wan_t2v_lora_low2_strength_input = QLineEdit()
        self.wan_t2v_lora_trigger_words_input = QLineEdit()
        self.wan_t2v_positive_input = QTextEdit()
        self.wan_t2v_negative_input = QTextEdit()
        self.wan_t2v_generate_prompt_button = QToolButton()
        self.wan_t2v_generate_prompt_button.setText("Buat Prompt")
        self.wan_t2v_generate_prompt_button.clicked.connect(
            lambda _checked=False: self.generate_wan_prompt_from_ui("positive_prompt", prompt_kind="wan_t2v")
        )
        self.copy_wan_t2v_variations_button = QToolButton()
        self.copy_wan_t2v_variations_button.setText("Edit Variasi")
        self.copy_wan_t2v_variations_button.clicked.connect(self.copy_wan_t2v_config_to_variations)
        # wan22_t2v_batch extra prompt widgets
        self.t2v_batch_positive_inputs = []
        self.t2v_batch_negative_inputs = []
        self.t2v_batch_generate_prompt_buttons = []
        for slot_index in range(3):
            positive_input = QTextEdit()
            negative_input = QTextEdit()
            generate_button = QToolButton()
            generate_button.setText("Buat Prompt")
            generate_button.clicked.connect(lambda _checked=False, idx=slot_index: self.run_t2v_batch_prompt_generation(idx))
            self.t2v_batch_positive_inputs.append(positive_input)
            self.t2v_batch_negative_inputs.append(negative_input)
            self.t2v_batch_generate_prompt_buttons.append(generate_button)
        self.wan_prompt_inputs = {}
        self.wan_generate_prompt_buttons = {}
        for key in [
            "positive_prompt_one", "negative_prompt_one", "positive_prompt_two", "negative_prompt_two",
        ]:
            self.wan_prompt_inputs[key] = QTextEdit()
            if key.startswith("positive_"):
                button = QToolButton()
                button.setText("Buat Prompt")
                button.clicked.connect(lambda _checked=False, prompt_key=key: self.generate_wan_prompt_from_ui(prompt_key))
                self.wan_generate_prompt_buttons[key] = button
        self.copy_wan_i2v_variations_button = QToolButton()
        self.copy_wan_i2v_variations_button.setText("Edit Variasi")
        self.copy_wan_i2v_variations_button.clicked.connect(self.copy_wan_i2v_config_to_variations)
        self.minimax_h3_t2v_size_input = QComboBox()
        for label, width, height in MINIMAX_H3_SIZE_OPTIONS:
            self.minimax_h3_t2v_size_input.addItem(label, (width, height))
        self.minimax_h3_i2v_size_input = QComboBox()
        for label, width, height in MINIMAX_H3_SIZE_OPTIONS:
            self.minimax_h3_i2v_size_input.addItem(label, (width, height))
        self.minimax_h3_t2v_fps_input = QComboBox()
        self.minimax_h3_i2v_fps_input = QComboBox()
        self.minimax_h3_r2v_fps_input = QComboBox()
        self.minimax_h3_s2v_fps_input = QComboBox()
        self.minimax_h3_i2v_fps_label = QLabel("FPS")
        self.minimax_h3_s2v_fps_label = QLabel("FPS")
        for widget in (
            self.minimax_h3_t2v_fps_input,
            self.minimax_h3_i2v_fps_input,
            self.minimax_h3_r2v_fps_input,
            self.minimax_h3_s2v_fps_input,
        ):
            for fps in MINIMAX_H3_FPS_OPTIONS:
                widget.addItem(str(fps), fps)
            widget.setCurrentIndex(widget.findData(MINIMAX_H3_DEFAULT_FPS))
        self.minimax_h3_t2v_lora_name_input = QComboBox()
        self.minimax_h3_t2v_lora_name_input.setEditable(False)
        self.minimax_h3_t2v_lora_name_2_input = QComboBox()
        self.minimax_h3_t2v_lora_name_2_input.setEditable(False)
        self.minimax_h3_i2v_lora_name_input = QComboBox()
        self.minimax_h3_i2v_lora_name_input.setEditable(False)
        self.minimax_h3_i2v_lora_name_2_input = QComboBox()
        self.minimax_h3_i2v_lora_name_2_input.setEditable(False)
        self.minimax_h3_t2v_lora_strength_input = QLineEdit()
        self.minimax_h3_t2v_lora_strength_2_input = QLineEdit()
        self.minimax_h3_i2v_lora_strength_input = QLineEdit()
        self.minimax_h3_i2v_lora_strength_2_input = QLineEdit()
        self.minimax_h3_t2v_remove_sound_input = QCheckBox("Hapus Sound")
        self.minimax_h3_i2v_remove_sound_input = QCheckBox("Hapus Sound")
        self.minimax_h3_t2v_positive_input = QTextEdit()
        self.minimax_h3_i2v_positive_input = QTextEdit()
        self.minimax_h3_t2v_generate_prompt_button = QToolButton()
        self.minimax_h3_t2v_generate_prompt_button.setText("Buat Prompt")
        self.minimax_h3_t2v_generate_prompt_button.clicked.connect(
            lambda _checked=False: self.generate_minimax_h3_prompt_from_ui("t2v")
        )
        self.minimax_h3_i2v_generate_prompt_button = QToolButton()
        self.minimax_h3_i2v_generate_prompt_button.setText("Buat Prompt")
        self.minimax_h3_i2v_generate_prompt_button.clicked.connect(
            lambda _checked=False: self.generate_minimax_h3_prompt_from_ui("i2v")
        )
        self.copy_minimax_h3_t2v_variations_button = QToolButton()
        self.copy_minimax_h3_t2v_variations_button.setText("Edit Variasi")
        self.copy_minimax_h3_t2v_variations_button.clicked.connect(
            self.copy_minimax_h3_t2v_config_to_variations
        )
        self.copy_minimax_h3_i2v_variations_button = QToolButton()
        self.copy_minimax_h3_i2v_variations_button.setText("Edit Variasi")
        self.copy_minimax_h3_i2v_variations_button.clicked.connect(
            self.copy_minimax_h3_i2v_config_to_variations
        )
        self.s2v_positive_input = QTextEdit()
        self.s2v_negative_input = QTextEdit()
        self.minimax_h3_s2v_lora_name_input = QComboBox()
        self.minimax_h3_s2v_lora_name_input.setEditable(False)
        self.minimax_h3_s2v_lora_name_2_input = QComboBox()
        self.minimax_h3_s2v_lora_name_2_input.setEditable(False)
        self.minimax_h3_s2v_lora_strength_input = QLineEdit()
        self.minimax_h3_s2v_lora_strength_2_input = QLineEdit()
        self.s2v_generate_positive_button = QToolButton()
        self.s2v_generate_positive_button.setText("Buat Prompt")
        self.s2v_generate_positive_button.clicked.connect(
            lambda _checked=False: self.generate_s2v_prompt_from_ui("positive_prompt")
        )
        self.s2v_size_input = QComboBox()
        for label, width, height in MINIMAX_H3_S2V_SIZE_OPTIONS:
            self.s2v_size_input.addItem(label, (width, height))
        self.minimax_h3_r2v_size_input = QComboBox()
        for label, width, height in MINIMAX_H3_S2V_SIZE_OPTIONS:
            self.minimax_h3_r2v_size_input.addItem(label, (width, height))
        self.minimax_h3_r2v_positive_input = QTextEdit()
        self.minimax_h3_r2v_lora_name_input = QComboBox()
        self.minimax_h3_r2v_lora_name_input.setEditable(False)
        self.minimax_h3_r2v_lora_name_2_input = QComboBox()
        self.minimax_h3_r2v_lora_name_2_input.setEditable(False)
        self.minimax_h3_r2v_lora_strength_input = QLineEdit()
        self.minimax_h3_r2v_lora_strength_2_input = QLineEdit()
        self.minimax_h3_r2v_generate_prompt_button = QToolButton()
        self.minimax_h3_r2v_generate_prompt_button.setText("Buat Prompt")
        self.minimax_h3_r2v_generate_prompt_button.clicked.connect(
            lambda _checked=False: self.generate_r2v_prompt_from_ui()
        )
        self.minimax_h3_r2v_image_list = QListWidget()
        self.minimax_h3_r2v_audio_list = QListWidget()
        self.minimax_h3_r2v_video_list = QListWidget()
        for widget in (
            self.minimax_h3_r2v_image_list,
            self.minimax_h3_r2v_audio_list,
            self.minimax_h3_r2v_video_list,
        ):
            widget.setSelectionMode(QAbstractItemView.NoSelection)
            widget.setMaximumHeight(120)
        self.minimax_h3_r2v_image_list.itemChanged.connect(
            lambda _item: self._limit_r2v_reference_selection(self.minimax_h3_r2v_image_list, 3)
        )
        self.minimax_h3_r2v_audio_list.itemChanged.connect(
            lambda _item: self._limit_r2v_reference_selection(self.minimax_h3_r2v_audio_list, 3)
        )
        self.minimax_h3_r2v_video_list.itemChanged.connect(
            lambda _item: self._limit_r2v_reference_selection(self.minimax_h3_r2v_video_list, 1)
        )
        self.s2v_cfg_input = QDoubleSpinBox()
        self.s2v_cfg_input.setRange(1.0, 6.0)
        self.s2v_cfg_input.setSingleStep(0.1)
        self.s2v_cfg_input.setDecimals(1)
        self.s2v_cfg_input.setValue(float(DEFAULT_WAN22_S2V_PROMPT.get("cfg", 2.0)))
        self.web_url_input = QLineEdit()
        self.web_size_input = QComboBox()
        for label, width, height in Z_IMAGE_SIZES:
            self.web_size_input.addItem(label, (width, height))
        self.web_duration_input = QDoubleSpinBox()
        self.web_duration_input.setRange(0.0, 20.0)
        self.web_duration_input.setSingleStep(0.1)
        self.web_duration_input.setDecimals(1)
        self.web_duration_input.setValue(float(DEFAULT_WEB_SCROLL_PROMPT.get("duration_seconds", 5.0)))
        self.web_speed_input = QSpinBox()
        self.web_speed_input.setRange(1, 5)
        self.web_speed_input.setValue(int(DEFAULT_WEB_SCROLL_PROMPT.get("speed", 1)))
        self.image_pan_size_input = QComboBox()
        for label, width, height in Z_IMAGE_SIZES:
            if int(height) > int(width):
                self.image_pan_size_input.addItem(label, (width, height))
        self.image_pan_direction_input = QComboBox()
        self.image_pan_direction_input.addItem("Dari Kanan", "from_right")
        self.image_pan_direction_input.addItem("Dari Kiri", "from_left")
        self.image_zoom_size_input = QComboBox()
        for label, width, height in Z_IMAGE_SIZES:
            self.image_zoom_size_input.addItem(label, (width, height))
        self.image_zoom_direction_input = QComboBox()
        self.image_zoom_direction_input.addItem("Zoom In (Default)", "in")
        self.image_zoom_direction_input.addItem("Zoom Out", "out")
        self.image_zoom_focal_input = QComboBox()
        self.image_zoom_focal_input.addItem("Tengah", "center")
        self.image_zoom_focal_input.addItem("Atas Kiri", "top_left")
        self.image_zoom_focal_input.addItem("Atas Tengah", "top_center")
        self.image_zoom_focal_input.addItem("Atas Kanan", "top_right")
        self.image_zoom_focal_input.addItem("Tengah Kiri", "center_left")
        self.image_zoom_focal_input.addItem("Tengah Kanan", "center_right")
        self.image_zoom_focal_input.addItem("Bawah Kiri", "bottom_left")
        self.image_zoom_focal_input.addItem("Bawah Tengah", "bottom_center")
        self.image_zoom_focal_input.addItem("Bawah Kanan", "bottom_right")
        self.image_zoom_strength_input = QDoubleSpinBox()
        self.image_zoom_strength_input.setRange(1.0, 1.5)
        self.image_zoom_strength_input.setSingleStep(0.1)
        self.image_zoom_strength_input.setDecimals(1)
        self.image_zoom_strength_input.setValue(1.3)
        self.web_search_size_input = QComboBox()
        for label, width, height in Z_IMAGE_SIZES:
            self.web_search_size_input.addItem(label, (width, height))
        self.web_search_term_input = QLineEdit()
        self.web_search_run_button = QToolButton()
        self.web_search_run_button.setText("Cari Gambar Web")
        self.web_search_run_button.clicked.connect(self.run_web_search_images)
        self.web_search_result_label = QLabel("Hasil akan langsung disimpan ke folder scene dan terlihat di tab Aset.")
        self.image_edit_model_input = QComboBox()
        self.image_edit_model_input.addItem("Flux.2", MODEL_FLUX2)
        self.image_edit_model_input.addItem("Gemini", MODEL_GEMINI_IMAGE)
        self.image_edit_gemini_model_input = QComboBox()
        for model_id in self.z_gemini_model_ids:
            self.image_edit_gemini_model_input.addItem(model_id, model_id)
        self.image_edit_image_inputs = []
        self.image_edit_prompt_inputs = []
        self.image_edit_clipboard_buttons = []
        self.image_edit_generate_prompt_buttons = []
        self.image_edit_buttons = []
        self.agentic_number_of_variations_input = QSpinBox()
        self.agentic_number_of_variations_input.setRange(0, 999)
        self.agentic_special_command_input = QTextEdit()
        self.agentic_special_command_input.setFixedHeight(264)
        self.agentic_special_command_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.agentic_create_initial_image_input = QCheckBox("Buat image awal", self)
        self.agentic_create_initial_image_input.setChecked(bool(DEFAULT_AGENERIC_CONFIG.get("create_initial_image", True)))
        self.agentic_image_extra_mode_input = QComboBox()
        for label, mode in IMAGE_EXTRA_MODES:
            self.agentic_image_extra_mode_input.addItem(label, mode)
        for slot_index in range(3):
            image_input = QComboBox()
            prompt_input = QTextEdit()
            clipboard_button = QToolButton()
            clipboard_button.setText("Image Gen Prompt")
            clipboard_button.clicked.connect(
                lambda _checked=False, idx=slot_index: self.copy_image_edit_prompt_to_clipboard(idx)
            )
            generate_button = QToolButton()
            generate_button.setText("Buat Prompt")
            generate_button.clicked.connect(lambda _checked=False, idx=slot_index: self.generate_image_edit_prompt_from_ui(idx))
            button = QToolButton()
            button.setText("Edit Gambar")
            button.clicked.connect(lambda _checked=False, idx=slot_index: self.run_image_edit_slot(idx))
            self.image_edit_image_inputs.append(image_input)
            self.image_edit_prompt_inputs.append(prompt_input)
            self.image_edit_clipboard_buttons.append(clipboard_button)
            self.image_edit_generate_prompt_buttons.append(generate_button)
            self.image_edit_buttons.append(button)

        self.status_label = QPlainTextEdit()
        self.status_label.setReadOnly(True)
        self.variation_view_input = QComboBox()
        self.variation_view_input.currentIndexChanged.connect(self.on_variation_view_changed)
        self.copy_variation_to_root_button = None
        self.status_label.setPlainText("Belum ada adegan yang dipilih.")
        self.status_label.setFixedHeight(96)
        self.image_preview = MediaPreviewLabel("Klik ganda file pada tab Aset untuk melihat media.")
        self.video_preview = MediaPreviewLabel("Klik ganda file video pada tab Aset untuk melihat media.")
        self.audio_preview = MediaPreviewLabel()
        speaker_icon = self.style().standardIcon(QStyle.SP_MediaVolume)
        self.audio_preview.set_preview_pixmap(speaker_icon.pixmap(128, 128))
        self.image_preview.activated.connect(lambda: self.open_preview_in_default_app(self.image_preview))
        self.video_preview.activated.connect(lambda: self.open_preview_in_default_app(self.video_preview))
        self.audio_preview.activated.connect(lambda: self.open_preview_in_default_app(self.audio_preview))
        self.viewer_stack = QStackedWidget()
        self.viewer_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.viewer_stack.setMinimumSize(0, 0)
        self.viewer_stack.addWidget(self.image_preview)
        self.viewer_stack.addWidget(self.video_preview)
        self.viewer_stack.addWidget(self.audio_preview)
        self.viewer_title_label = QLabel("Tampilan")
        self.viewer_info_label = QLabel("Klik ganda file pada tab Aset untuk melihat media.")

        self.asset_list = QListWidget()
        self.asset_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.asset_list.currentItemChanged.connect(self.on_asset_selected)
        self.asset_list.itemClicked.connect(self.on_asset_clicked)
        self.asset_list.itemDoubleClicked.connect(self.on_asset_double_clicked)
        self.asset_list.customContextMenuRequested.connect(self.open_asset_context_menu)
        self.asset_info_label = QLabel("Belum ada aset yang dipilih.")
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.process_dialog = None
        self._lora_options_initialized = False
        self._lora_options_server = ""
        self._ui_log_emitter = UiLogEmitter(self)
        self._ui_log_emitter.message.connect(self.append_log)
        self._ui_log_handler = UiLogHandler(self._ui_log_emitter)
        self._ui_log_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [run_id=%(run_id)s] %(module)s:%(lineno)d %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        self._ui_log_handler.addFilter(RunIdFilter())
        logging.getLogger().addHandler(self._ui_log_handler)

        self.video_player = QMediaPlayer(self)
        self.video_audio_output = QAudioOutput(self)
        self.video_sink = QVideoSink(self)
        self.video_player.setAudioOutput(self.video_audio_output)
        self.video_player.setVideoOutput(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self.on_video_frame_changed)
        self.audio_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_player.setAudioOutput(self.audio_output)

        self.install_field_watchers()
        self.build_ui()
        self.update_seed_fields_enabled()
        self.update_lora_fields_enabled()
        self.update_wan_lora_fields_enabled()
        self.update_image_edit_model_fields_enabled()
        self.sync_image_edit_model_from_initial_image()
        self.update_scene_type_tabs()
        self.update_scene_type_specific_fields()
        self.update_run_action_buttons_state()
        self.reload_scene_list()
        self.refresh_project_state()
        QTimer.singleShot(0, self.initialize_lora_options_once)
        self.setMinimumSize(0, 0)

    def install_field_watchers(self):
        for signal in [
            self.scene_title_input.textChanged, self.duration_input.currentTextChanged,
            self.duration_decimal_input.textChanged,
            self.scene_type_combo.currentTextChanged,
            self.scene_voice_character_input.currentTextChanged,
            self.sound_volume_input.textChanged, self.z_model_input.currentIndexChanged,
            self.z_gemini_model_input.currentIndexChanged,
            self.z_size_input.currentTextChanged, self.wan_size_input.currentTextChanged,
            self.wan_t2v_size_input.currentTextChanged,
            self.minimax_h3_t2v_size_input.currentTextChanged,
            self.minimax_h3_t2v_fps_input.currentIndexChanged,
            self.minimax_h3_i2v_size_input.currentTextChanged,
            self.minimax_h3_i2v_fps_input.currentIndexChanged,
            self.minimax_h3_r2v_size_input.currentTextChanged,
            self.minimax_h3_r2v_fps_input.currentIndexChanged,
            self.minimax_h3_s2v_fps_input.currentIndexChanged,
            self.minimax_h3_t2v_remove_sound_input.checkStateChanged,
            self.minimax_h3_i2v_remove_sound_input.checkStateChanged,
            self.s2v_size_input.currentTextChanged, self.s2v_cfg_input.valueChanged, self.web_url_input.textChanged,
            self.web_size_input.currentTextChanged, self.web_duration_input.valueChanged, self.web_speed_input.valueChanged,
            self.image_pan_size_input.currentTextChanged,
            self.image_pan_direction_input.currentIndexChanged,
            self.image_zoom_size_input.currentTextChanged,
            self.image_zoom_direction_input.currentIndexChanged,
            self.image_zoom_focal_input.currentIndexChanged,
            self.image_zoom_strength_input.valueChanged,
            self.web_search_size_input.currentTextChanged,
            self.web_search_term_input.textChanged,
            self.image_edit_model_input.currentIndexChanged,
            self.image_edit_gemini_model_input.currentIndexChanged,
            self.z_use_random_seed_input.checkStateChanged, self.z_use_lora_input.checkStateChanged,
            self.agentic_number_of_variations_input.valueChanged,
            self.agentic_create_initial_image_input.checkStateChanged,
            self.agentic_image_extra_mode_input.currentIndexChanged,
        ]:
            signal.connect(self.refresh_scene_status)
        for widget in [
            self.scene_description_input, self.voice_text_input, self.sound_prompt_input, self.z_positive_input,
            self.z_negative_input, self.z_seed_input, self.z_lora_name_input, self.z_lora_strength_input,
            self.wan_lora_high_name_input, self.wan_lora_high_strength_input,
            self.wan_lora_low_name_input, self.wan_lora_low_strength_input,
            self.wan_lora_high2_name_input, self.wan_lora_high2_strength_input,
            self.wan_lora_low2_name_input, self.wan_lora_low2_strength_input,
            self.wan_t2v_positive_input, self.wan_t2v_negative_input,
            self.wan_t2v_lora_high_name_input, self.wan_t2v_lora_high_strength_input,
            self.wan_t2v_lora_low_name_input, self.wan_t2v_lora_low_strength_input,
            self.wan_t2v_lora_high2_name_input, self.wan_t2v_lora_high2_strength_input,
            self.wan_t2v_lora_low2_name_input, self.wan_t2v_lora_low2_strength_input,
            self.minimax_h3_t2v_lora_name_input, self.minimax_h3_t2v_lora_strength_input,
            self.minimax_h3_t2v_lora_name_2_input, self.minimax_h3_t2v_lora_strength_2_input,
            self.minimax_h3_i2v_lora_name_input, self.minimax_h3_i2v_lora_strength_input,
            self.minimax_h3_i2v_lora_name_2_input, self.minimax_h3_i2v_lora_strength_2_input,
            self.minimax_h3_t2v_positive_input, self.minimax_h3_i2v_positive_input,
            self.s2v_positive_input, self.s2v_negative_input,
            self.minimax_h3_s2v_lora_name_input, self.minimax_h3_s2v_lora_name_2_input,
            self.minimax_h3_s2v_lora_strength_input, self.minimax_h3_s2v_lora_strength_2_input,
            self.minimax_h3_r2v_positive_input,
            self.minimax_h3_r2v_lora_name_input, self.minimax_h3_r2v_lora_name_2_input,
            self.minimax_h3_r2v_lora_strength_input, self.minimax_h3_r2v_lora_strength_2_input,
            *self.wan_prompt_inputs.values(),
            *self.z_extra_positive_inputs, *self.z_extra_negative_inputs,
            self.agentic_special_command_input,
        ]:
            signal = getattr(widget, "textChanged", None) or getattr(widget, "currentTextChanged", None)
            if signal is not None:
                signal.connect(self.refresh_scene_status)
        self.z_use_lora_input.toggled.connect(self.update_lora_fields_enabled)
        self.z_use_random_seed_input.toggled.connect(self.update_seed_fields_enabled)
        self.z_model_input.currentIndexChanged.connect(self.update_image_model_fields_enabled)
        self.z_model_input.currentIndexChanged.connect(self.sync_image_edit_model_from_initial_image)
        self.z_gemini_model_input.currentIndexChanged.connect(self.sync_image_edit_model_from_initial_image)
        self.image_edit_model_input.currentIndexChanged.connect(self.update_image_edit_model_fields_enabled)
        self.scene_type_combo.currentTextChanged.connect(self.update_scene_type_tabs)
        self.scene_type_combo.currentTextChanged.connect(self.update_scene_type_specific_fields)
        self.scene_type_combo.currentTextChanged.connect(self.update_run_action_buttons_state)

    def build_ui(self):
        self.toolbar = QToolBar("Aksi")
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self.build_toolbar_actions()

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(True)
        root_layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Daftar Adegan"))
        left_layout.addWidget(self.scene_list)
        splitter.addWidget(left)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_scroll = QScrollArea()
        center_scroll.setWidgetResizable(True)
        center_scroll.setFrameShape(QFrame.NoFrame)
        editor_tabs = self.build_editor_tabs()
        editor_tabs.setMinimumSize(0, 0)
        center_scroll.setWidget(editor_tabs)
        center_layout.addWidget(center_scroll)
        splitter.addWidget(center)

        right = QWidget()
        right.setMinimumSize(0, 0)
        right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right)
        self.viewer_group = self.build_viewer_group()
        self.status_group = self.build_status_group()
        right_layout.addWidget(self.viewer_group, 3)
        right_layout.addWidget(self.status_group, 1)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 3)

    def build_editor_tabs(self):
        tabs = QTabWidget()
        self.editor_tabs = tabs

        def button_row(*widgets):
            row = QWidget(self)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            for widget in widgets:
                row_layout.addWidget(widget)
            row_layout.addStretch(1)
            return row

        self.meta_tab = QWidget()
        meta_layout = QFormLayout(self.meta_tab)
        meta_layout.setVerticalSpacing(4)
        self.duration_label = QLabel("Durasi (detik)")
        meta_layout.addRow("Judul Adegan", self.scene_title_input)
        meta_layout.addRow("Deskripsi Adegan", self.scene_description_input)
        meta_layout.addRow(self.duration_label, self.duration_input_stack)
        for label, widget in [
            ("Tipe Adegan", self.scene_type_combo),
            ("Pilihan Suara Scene", self.scene_voice_character_input),
            ("Teks Suara", self.voice_text_input), ("Prompt Suara Latar", self.sound_prompt_input),
            ("Volume Suara Latar", self.sound_volume_input),
        ]:
            meta_layout.addRow(label, widget)
        tabs.addTab(self.meta_tab, "Meta")

        self.z_tab = QWidget()
        z_layout = QFormLayout(self.z_tab)
        z_layout.addRow("Model", self.z_model_input)
        z_layout.addRow("Model Gemini", self.z_gemini_model_input)
        z_layout.addRow("Ukuran", self.z_size_input)
        z_layout.addRow("", self.z_use_random_seed_input)
        z_layout.addRow("Seed Statik", self.z_seed_input)
        z_layout.addRow("", self.z_use_lora_input)
        z_layout.addRow("Nama Lora", self.z_lora_name_input)
        z_layout.addRow("Kekuatan Lora", self.z_lora_strength_input)
        z_layout.addRow("Trigger Word Lora", self.z_lora_trigger_words_input)
        z_layout.addRow("", self.copy_z_variations_button)
        z_layout.addRow("Prompt Positif", self.z_positive_input)
        z_layout.addRow("", button_row(self.z_clipboard_button, self.z_generate_prompt_button))
        z_layout.addRow("Prompt Negatif", self.z_negative_input)
        tabs.addTab(self.z_tab, "Gambar Awal")

        self.z_extra_tab = QWidget()
        z_extra_layout = QVBoxLayout(self.z_extra_tab)
        for idx in range(3):
            group = QGroupBox(f"Prompt Tambahan {idx + 1}")
            group_layout = QFormLayout(group)
            group_layout.addRow("Prompt Positif", self.z_extra_positive_inputs[idx])
            group_layout.addRow(
                "",
                button_row(self.z_extra_clipboard_buttons[idx], self.z_extra_generate_prompt_buttons[idx]),
            )
            group_layout.addRow("Prompt Negatif", self.z_extra_negative_inputs[idx])
            group_layout.addRow("", self.z_extra_buttons[idx])
            z_extra_layout.addWidget(group)
        z_extra_layout.addStretch(1)
        tabs.addTab(self.z_extra_tab, "Prompt Tambahan")

        self.wan_t2v_tab = QWidget()
        wan_t2v_layout = QGridLayout(self.wan_t2v_tab)

        def add_t2v_lora_row(row: int, title: str, name_widget, strength_widget):
            strength_widget.setFixedWidth(84)
            strength_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            wan_t2v_layout.addWidget(QLabel(title), row, 0)
            wan_t2v_layout.addWidget(name_widget, row, 1)
            wan_t2v_layout.addWidget(QLabel("Kekuatan"), row, 2)
            wan_t2v_layout.addWidget(strength_widget, row, 3)

        wan_t2v_layout.addWidget(QLabel("Ukuran"), 0, 0)
        wan_t2v_layout.addWidget(self.wan_t2v_size_input, 0, 1, 1, 3)
        add_t2v_lora_row(1, "Lora High 1", self.wan_t2v_lora_high_name_input, self.wan_t2v_lora_high_strength_input)
        add_t2v_lora_row(2, "Lora Low 1", self.wan_t2v_lora_low_name_input, self.wan_t2v_lora_low_strength_input)
        add_t2v_lora_row(3, "Lora High 2", self.wan_t2v_lora_high2_name_input, self.wan_t2v_lora_high2_strength_input)
        add_t2v_lora_row(4, "Lora Low 2", self.wan_t2v_lora_low2_name_input, self.wan_t2v_lora_low2_strength_input)
        wan_t2v_layout.addWidget(QLabel("Trigger Word Lora"), 5, 0)
        wan_t2v_layout.addWidget(self.wan_t2v_lora_trigger_words_input, 5, 1, 1, 3)
        wan_t2v_layout.addWidget(self.copy_wan_t2v_variations_button, 6, 1, 1, 3, Qt.AlignLeft)
        wan_t2v_layout.addWidget(QLabel("Prompt Positif"), 7, 0)
        wan_t2v_layout.addWidget(self.wan_t2v_positive_input, 7, 1, 1, 3)
        wan_t2v_layout.addWidget(self.wan_t2v_generate_prompt_button, 8, 1, 1, 3, Qt.AlignLeft)
        wan_t2v_layout.addWidget(QLabel("Prompt Negatif"), 9, 0)
        wan_t2v_layout.addWidget(self.wan_t2v_negative_input, 9, 1, 1, 3)
        tabs.addTab(self.wan_t2v_tab, "WAN22_T2V")

        self.wan_tab = QWidget()
        wan_layout = QGridLayout(self.wan_tab)
        def add_lora_row(row: int, title: str, name_widget, strength_widget):
            strength_widget.setFixedWidth(84)
            strength_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            wan_layout.addWidget(QLabel(title), row, 0)
            wan_layout.addWidget(name_widget, row, 1)
            wan_layout.addWidget(QLabel("Kekuatan"), row, 2)
            wan_layout.addWidget(strength_widget, row, 3)

        wan_layout.addWidget(QLabel("Ukuran"), 0, 0)
        wan_layout.addWidget(self.wan_size_input, 0, 1, 1, 3)
        add_lora_row(1, "Lora High 1", self.wan_lora_high_name_input, self.wan_lora_high_strength_input)
        add_lora_row(2, "Lora Low 1", self.wan_lora_low_name_input, self.wan_lora_low_strength_input)
        add_lora_row(3, "Lora High 2", self.wan_lora_high2_name_input, self.wan_lora_high2_strength_input)
        add_lora_row(4, "Lora Low 2", self.wan_lora_low2_name_input, self.wan_lora_low2_strength_input)
        wan_layout.addWidget(QLabel("Trigger Word Lora"), 5, 0)
        wan_layout.addWidget(self.wan_lora_trigger_words_input, 5, 1, 1, 3)
        wan_layout.addWidget(self.copy_wan_i2v_variations_button, 6, 1, 1, 3, Qt.AlignLeft)
        row = 7
        for slot in ("one", "two"):
            positive_key = f"positive_prompt_{slot}"
            negative_key = f"negative_prompt_{slot}"
            wan_layout.addWidget(QLabel(positive_key.replace("_", " ").title()), row, 0)
            wan_layout.addWidget(self.wan_prompt_inputs[positive_key], row, 1, 1, 3)
            row += 1
            wan_layout.addWidget(self.wan_generate_prompt_buttons[positive_key], row, 1, 1, 3, Qt.AlignLeft)
            row += 1
            wan_layout.addWidget(QLabel(negative_key.replace("_", " ").title()), row, 0)
            wan_layout.addWidget(self.wan_prompt_inputs[negative_key], row, 1, 1, 3)
            row += 1
        tabs.addTab(self.wan_tab, "WAN22_I2V")

        self.minimax_h3_t2v_tab = QWidget()
        minimax_t2v_layout = QGridLayout(self.minimax_h3_t2v_tab)
        minimax_t2v_layout.setColumnStretch(0, 0)
        minimax_t2v_layout.setColumnStretch(1, 1)
        minimax_t2v_layout.setColumnStretch(2, 0)
        minimax_t2v_layout.setColumnStretch(3, 0)
        self.minimax_h3_t2v_lora_strength_input.setFixedWidth(84)
        minimax_t2v_layout.addWidget(QLabel("Ukuran"), 0, 0)
        minimax_t2v_layout.addWidget(self.minimax_h3_t2v_size_input, 0, 1, 1, 3)
        minimax_t2v_layout.addWidget(QLabel("FPS"), 1, 0)
        minimax_t2v_layout.addWidget(self.minimax_h3_t2v_fps_input, 1, 1, 1, 3)
        minimax_t2v_layout.addWidget(QLabel("Lora"), 2, 0)
        minimax_t2v_layout.addWidget(self.minimax_h3_t2v_lora_name_input, 2, 1)
        minimax_t2v_layout.addWidget(QLabel("Kekuatan"), 2, 2)
        minimax_t2v_layout.addWidget(self.minimax_h3_t2v_lora_strength_input, 2, 3)
        minimax_t2v_layout.addWidget(QLabel("Lora 2"), 3, 0)
        minimax_t2v_layout.addWidget(self.minimax_h3_t2v_lora_name_2_input, 3, 1)
        minimax_t2v_layout.addWidget(QLabel("Kekuatan 2"), 3, 2)
        minimax_t2v_layout.addWidget(self.minimax_h3_t2v_lora_strength_2_input, 3, 3)
        minimax_t2v_layout.addWidget(self.minimax_h3_t2v_remove_sound_input, 4, 1)
        minimax_t2v_layout.addWidget(self.copy_minimax_h3_t2v_variations_button, 4, 3, Qt.AlignLeft)
        minimax_t2v_layout.addWidget(QLabel("Prompt Positif"), 5, 0)
        minimax_t2v_layout.addWidget(self.minimax_h3_t2v_positive_input, 5, 1, 1, 3)
        minimax_t2v_layout.addWidget(self.minimax_h3_t2v_generate_prompt_button, 6, 1, 1, 3, Qt.AlignLeft)
        tabs.addTab(self.minimax_h3_t2v_tab, "MINIMAX-H3_T2V")

        self.minimax_h3_i2v_tab = QWidget()
        minimax_i2v_layout = QGridLayout(self.minimax_h3_i2v_tab)
        minimax_i2v_layout.setColumnStretch(0, 0)
        minimax_i2v_layout.setColumnStretch(1, 1)
        minimax_i2v_layout.setColumnStretch(2, 0)
        minimax_i2v_layout.setColumnStretch(3, 0)
        self.minimax_h3_i2v_lora_strength_input.setFixedWidth(84)
        minimax_i2v_layout.addWidget(QLabel("Ukuran"), 0, 0)
        minimax_i2v_layout.addWidget(self.minimax_h3_i2v_size_input, 0, 1, 1, 3)
        minimax_i2v_layout.addWidget(self.minimax_h3_i2v_fps_label, 1, 0)
        minimax_i2v_layout.addWidget(self.minimax_h3_i2v_fps_input, 1, 1, 1, 3)
        minimax_i2v_layout.addWidget(QLabel("Lora"), 2, 0)
        minimax_i2v_layout.addWidget(self.minimax_h3_i2v_lora_name_input, 2, 1)
        minimax_i2v_layout.addWidget(QLabel("Kekuatan"), 2, 2)
        minimax_i2v_layout.addWidget(self.minimax_h3_i2v_lora_strength_input, 2, 3)
        minimax_i2v_layout.addWidget(QLabel("Lora 2"), 3, 0)
        minimax_i2v_layout.addWidget(self.minimax_h3_i2v_lora_name_2_input, 3, 1)
        minimax_i2v_layout.addWidget(QLabel("Kekuatan 2"), 3, 2)
        minimax_i2v_layout.addWidget(self.minimax_h3_i2v_lora_strength_2_input, 3, 3)
        minimax_i2v_layout.addWidget(self.minimax_h3_i2v_remove_sound_input, 4, 1)
        minimax_i2v_layout.addWidget(self.copy_minimax_h3_i2v_variations_button, 4, 2, 1, 2, Qt.AlignLeft)
        minimax_i2v_layout.addWidget(QLabel("Prompt Positif"), 5, 0)
        minimax_i2v_layout.addWidget(self.minimax_h3_i2v_positive_input, 5, 1, 1, 3)
        minimax_i2v_layout.addWidget(self.minimax_h3_i2v_generate_prompt_button, 6, 1, 1, 3, Qt.AlignLeft)
        tabs.addTab(self.minimax_h3_i2v_tab, "MINIMAX-H3_I2V")

        self.minimax_h3_r2v_tab = QWidget()
        r2v_layout = QFormLayout(self.minimax_h3_r2v_tab)
        r2v_layout.addRow("Ukuran", self.minimax_h3_r2v_size_input)
        r2v_layout.addRow("FPS", self.minimax_h3_r2v_fps_input)
        r2v_layout.addRow("Lora", self.minimax_h3_r2v_lora_name_input)
        r2v_layout.addRow("Kekuatan Lora", self.minimax_h3_r2v_lora_strength_input)
        r2v_layout.addRow("Lora 2", self.minimax_h3_r2v_lora_name_2_input)
        r2v_layout.addRow("Kekuatan Lora 2", self.minimax_h3_r2v_lora_strength_2_input)
        r2v_layout.addRow("Gambar (maks. 3)", self.minimax_h3_r2v_image_list)
        r2v_layout.addRow("Video (maks. 1)", self.minimax_h3_r2v_video_list)
        r2v_layout.addRow("Audio (maks. 3)", self.minimax_h3_r2v_audio_list)
        r2v_layout.addRow("Prompt Positif", self.minimax_h3_r2v_positive_input)
        r2v_layout.addRow("", self.minimax_h3_r2v_generate_prompt_button)
        tabs.addTab(self.minimax_h3_r2v_tab, "MINIMAX-H3_R2V")

        self.t2v_batch_extra_tab = QWidget()
        t2v_batch_extra_layout = QVBoxLayout(self.t2v_batch_extra_tab)
        for idx in range(3):
            group = QGroupBox(f"Prompt Tambahan {idx + 1}")
            group_layout = QFormLayout(group)
            group_layout.addRow("Prompt Positif", self.t2v_batch_positive_inputs[idx])
            group_layout.addRow("", self.t2v_batch_generate_prompt_buttons[idx])
            group_layout.addRow("Prompt Negatif", self.t2v_batch_negative_inputs[idx])
            t2v_batch_extra_layout.addWidget(group)
        t2v_batch_extra_layout.addStretch(1)
        tabs.addTab(self.t2v_batch_extra_tab, "Prompt Tambahan")

        self.s2v_tab = QWidget()
        s2v_layout = QFormLayout(self.s2v_tab)
        s2v_layout.addRow("Ukuran", self.s2v_size_input)
        s2v_layout.addRow(self.minimax_h3_s2v_fps_label, self.minimax_h3_s2v_fps_input)
        self.minimax_h3_s2v_lora_label = QLabel("Lora")
        self.minimax_h3_s2v_lora_strength_label = QLabel("Kekuatan Lora")
        self.minimax_h3_s2v_lora_2_label = QLabel("Lora 2")
        self.minimax_h3_s2v_lora_strength_2_label = QLabel("Kekuatan Lora 2")
        s2v_layout.addRow(self.minimax_h3_s2v_lora_label, self.minimax_h3_s2v_lora_name_input)
        s2v_layout.addRow(self.minimax_h3_s2v_lora_strength_label, self.minimax_h3_s2v_lora_strength_input)
        s2v_layout.addRow(self.minimax_h3_s2v_lora_2_label, self.minimax_h3_s2v_lora_name_2_input)
        s2v_layout.addRow(self.minimax_h3_s2v_lora_strength_2_label, self.minimax_h3_s2v_lora_strength_2_input)
        self.s2v_cfg_label = QLabel("CFG")
        s2v_layout.addRow(self.s2v_cfg_label, self.s2v_cfg_input)
        s2v_layout.addRow("Prompt Positif", self.s2v_positive_input)
        s2v_layout.addRow("", self.s2v_generate_positive_button)
        self.s2v_negative_label = QLabel("Prompt Negatif")
        s2v_layout.addRow(self.s2v_negative_label, self.s2v_negative_input)
        tabs.addTab(self.s2v_tab, "WAN22 S2V")

        self.web_tab = QWidget()
        web_layout = QFormLayout(self.web_tab)
        web_layout.addRow("URL Website", self.web_url_input)
        web_layout.addRow("Ukuran", self.web_size_input)
        web_layout.addRow("Durasi (detik)", self.web_duration_input)
        web_layout.addRow("Speed", self.web_speed_input)
        tabs.addTab(self.web_tab, "Web Scroll")

        self.image_pan_tab = QWidget()
        image_pan_layout = QFormLayout(self.image_pan_tab)
        image_pan_layout.addRow("Ukuran (Portrait)", self.image_pan_size_input)
        image_pan_layout.addRow("Arah", self.image_pan_direction_input)
        tabs.addTab(self.image_pan_tab, "Image Pan")

        self.image_zoom_tab = QWidget()
        image_zoom_layout = QFormLayout(self.image_zoom_tab)
        image_zoom_layout.addRow("Ukuran", self.image_zoom_size_input)
        image_zoom_layout.addRow("Arah Zoom", self.image_zoom_direction_input)
        image_zoom_layout.addRow("Titik Fokus", self.image_zoom_focal_input)
        image_zoom_layout.addRow("Kekuatan Zoom", self.image_zoom_strength_input)
        tabs.addTab(self.image_zoom_tab, "Image Zoom")

        self.web_search_tab = QWidget()
        web_search_layout = QVBoxLayout(self.web_search_tab)
        web_search_form = QFormLayout()
        web_search_form.addRow("Ukuran", self.web_search_size_input)
        web_search_form.addRow("Search term", self.web_search_term_input)
        web_search_form.addRow("", self.web_search_run_button)
        web_search_layout.addLayout(web_search_form)
        web_search_layout.addWidget(self.web_search_result_label)
        web_search_layout.addStretch(1)
        tabs.addTab(self.web_search_tab, "Web Search")

        self.image_edit_tab = QWidget()
        image_edit_layout = QVBoxLayout(self.image_edit_tab)
        image_edit_form = QFormLayout()
        image_edit_form.addRow("Model", self.image_edit_model_input)
        image_edit_form.addRow("Model Gemini", self.image_edit_gemini_model_input)
        image_edit_layout.addLayout(image_edit_form)
        for idx in range(3):
            group = QGroupBox(f"Edit Gambar {idx + 1}")
            group_layout = QFormLayout(group)
            group_layout.addRow("Gambar Awal", self.image_edit_image_inputs[idx])
            group_layout.addRow("Prompt", self.image_edit_prompt_inputs[idx])
            group_layout.addRow(
                "",
                button_row(self.image_edit_clipboard_buttons[idx], self.image_edit_generate_prompt_buttons[idx]),
            )
            group_layout.addRow("", self.image_edit_buttons[idx])
            image_edit_layout.addWidget(group)
        image_edit_layout.addStretch(1)
        tabs.addTab(self.image_edit_tab, "Image Edit")

        self.assets_tab = QWidget()
        assets_layout = QVBoxLayout(self.assets_tab)
        assets_layout.addWidget(QLabel("Aset media dalam adegan. Klik ganda untuk membuka tampilan."))
        assets_layout.addWidget(self.asset_list)
        assets_layout.addWidget(self.asset_info_label)
        tabs.addTab(self.assets_tab, "Aset")

        self.agentic_tab = QWidget()
        agentic_layout = QFormLayout(self.agentic_tab)
        agentic_layout.setContentsMargins(12, 12, 12, 12)
        agentic_layout.setHorizontalSpacing(12)
        agentic_layout.setVerticalSpacing(8)
        agentic_layout.addRow("Jumlah Variasi", self.agentic_number_of_variations_input)
        agentic_layout.addRow("Buat Image Awal", self.agentic_create_initial_image_input)
        agentic_layout.addRow("Mode Variasi Tambahan", self.agentic_image_extra_mode_input)
        agentic_layout.addRow("Perintah Khusus", self.agentic_special_command_input)
        tabs.addTab(self.agentic_tab, "Agentic")
        return tabs

    def update_scene_type_tabs(self):
        if self.editor_tabs is None:
            return
        # Tab order must start from the same canonical order on every scene
        # switch.  The scene-specific moves below are intentionally kept, but
        # applying them to the previous scene's order makes the result depend
        # on the navigation history.
        self._reset_editor_tab_order()
        scene_type = self.scene_type_combo.currentText().strip()
        is_wan22_t2v = scene_type == WAN22_T2V_SCENE_TYPE
        is_minimax_h3 = scene_type == MINIMAX_H3_T2V_I2V_SCENE_TYPE
        is_minimax_h3_i2v = scene_type == MINIMAX_H3_I2V_SCENE_TYPE
        is_minimax_h3_s2v = scene_type == MINIMAX_H3_S2V_SCENE_TYPE
        is_minimax_h3_r2v = scene_type == MINIMAX_H3_R2V_SCENE_TYPE
        is_t2v_batch = scene_type == WAN22_T2V_BATCH_SCENE_TYPE
        is_s2v = scene_type in {"wan22_s2v", MINIMAX_H3_S2V_SCENE_TYPE}
        visible_map = {
            self.meta_tab: True,
            self.z_tab: scene_type not in {"web_scroll"} and not is_wan22_t2v and not is_t2v_batch and not is_minimax_h3,
            self.z_extra_tab: scene_type == "i2v",
            self.wan_t2v_tab: is_wan22_t2v or is_t2v_batch,
            self.wan_tab: scene_type in {"wan22", "wan22_i2v", WAN22_T2V_SCENE_TYPE},
            self.minimax_h3_t2v_tab: is_minimax_h3,
            self.minimax_h3_i2v_tab: is_minimax_h3 or is_minimax_h3_i2v,
            self.minimax_h3_r2v_tab: is_minimax_h3_r2v,
            self.s2v_tab: is_s2v,
            self.web_tab: scene_type == "web_scroll",
            self.image_pan_tab: scene_type == "image_pan",
            self.image_zoom_tab: scene_type == "image_zoom",
            self.web_search_tab: scene_type in {"i2v", "image_pan", "image_zoom"},
            self.image_edit_tab: scene_type not in {
                "web_scroll",
                "wan22_s2v",
                MINIMAX_H3_T2V_I2V_SCENE_TYPE,
                MINIMAX_H3_S2V_SCENE_TYPE,
                MINIMAX_H3_R2V_SCENE_TYPE,
            } and not is_wan22_t2v and not is_t2v_batch,
            self.t2v_batch_extra_tab: is_t2v_batch,
            self.agentic_tab: scene_type != "web_scroll",
            self.assets_tab: True,
        }
        current_widget = self.editor_tabs.currentWidget()
        self.editor_tabs.setTabText(self.editor_tabs.indexOf(self.s2v_tab), "MINIMAX-H3_S2V" if is_minimax_h3_s2v else "WAN22 S2V")
        if self.image_edit_tab is not None:
            if self.web_search_tab is not None and self.z_tab is not None:
                self._move_tab_after(self.web_search_tab, self.z_tab)
            if scene_type == "i2v" and self.z_extra_tab is not None:
                self._move_tab_after(self.image_edit_tab, self.z_extra_tab)
            elif scene_type in {"image_pan", "image_zoom"} and self.web_search_tab is not None:
                self._move_tab_after(self.image_edit_tab, self.web_search_tab)
            elif self.z_tab is not None:
                self._move_tab_after(self.image_edit_tab, self.z_tab)
            if is_minimax_h3:
                self._move_tab_after(self.minimax_h3_t2v_tab, self.meta_tab)
                self._move_tab_after(self.minimax_h3_i2v_tab, self.minimax_h3_t2v_tab)
                self._move_tab_after(self.agentic_tab, self.minimax_h3_i2v_tab)
                self._move_tab_after(self.assets_tab, self.agentic_tab)
            elif is_minimax_h3_r2v:
                self._move_tab_after(self.minimax_h3_r2v_tab, self.z_tab)
                self._move_tab_after(self.agentic_tab, self.minimax_h3_r2v_tab)
                self._move_tab_after(self.assets_tab, self.agentic_tab)
            elif is_minimax_h3_i2v:
                self._move_tab_after(self.image_edit_tab, self.z_tab)
                self._move_tab_after(self.minimax_h3_i2v_tab, self.image_edit_tab)
                self._move_tab_after(self.agentic_tab, self.minimax_h3_i2v_tab)
                self._move_tab_after(self.assets_tab, self.agentic_tab)
        for widget, visible in visible_map.items():
            if widget is None:
                continue
            index = self.editor_tabs.indexOf(widget)
            if index >= 0:
                self.editor_tabs.setTabVisible(index, visible)
        if current_widget and not visible_map.get(current_widget, True):
            self.editor_tabs.setCurrentWidget(self.meta_tab)

    def _reset_editor_tab_order(self):
        """Restore the order in which editor tabs are initially created."""
        if self.editor_tabs is None:
            return

        base_order = [
            self.meta_tab,
            self.z_tab,
            self.z_extra_tab,
            self.wan_t2v_tab,
            self.wan_tab,
            self.minimax_h3_t2v_tab,
            self.minimax_h3_i2v_tab,
            self.minimax_h3_r2v_tab,
            self.t2v_batch_extra_tab,
            self.s2v_tab,
            self.web_tab,
            self.image_pan_tab,
            self.image_zoom_tab,
            self.web_search_tab,
            self.image_edit_tab,
            self.assets_tab,
            self.agentic_tab,
        ]
        base_order = [widget for widget in base_order if widget is not None]
        tab_widget = self.editor_tabs
        current_widget = tab_widget.currentWidget()

        for desired_index, widget in enumerate(base_order):
            current_index = tab_widget.indexOf(widget)
            if current_index < 0 or current_index == desired_index:
                continue
            tab_text = tab_widget.tabText(current_index)
            tab_icon = tab_widget.tabIcon(current_index)
            tab_tooltip = tab_widget.tabToolTip(current_index)
            tab_whats_this = tab_widget.tabWhatsThis(current_index)
            tab_widget.removeTab(current_index)
            tab_widget.insertTab(desired_index, widget, tab_icon, tab_text)
            if tab_tooltip:
                tab_widget.setTabToolTip(desired_index, tab_tooltip)
            if tab_whats_this:
                tab_widget.setTabWhatsThis(desired_index, tab_whats_this)

        if current_widget is not None and tab_widget.indexOf(current_widget) >= 0:
            tab_widget.setCurrentWidget(current_widget)

    def _move_tab_after(self, widget: QWidget | None, after_widget: QWidget | None):
        if self.editor_tabs is None or widget is None or after_widget is None:
            return
        tab_widget = self.editor_tabs
        widget_index = tab_widget.indexOf(widget)
        after_index = tab_widget.indexOf(after_widget)
        if widget_index < 0 or after_index < 0:
            return
        desired_index = after_index + 1
        if widget_index == desired_index:
            return
        current_widget = tab_widget.currentWidget()
        tab_text = tab_widget.tabText(widget_index)
        tab_icon = tab_widget.tabIcon(widget_index)
        tab_tooltip = tab_widget.tabToolTip(widget_index)
        tab_whats_this = tab_widget.tabWhatsThis(widget_index)
        tab_widget.removeTab(widget_index)
        if widget_index < desired_index:
            desired_index -= 1
        tab_widget.insertTab(desired_index, widget, tab_icon, tab_text)
        if tab_tooltip:
            tab_widget.setTabToolTip(desired_index, tab_tooltip)
        if tab_whats_this:
            tab_widget.setTabWhatsThis(desired_index, tab_whats_this)
        if current_widget is not None:
            tab_widget.setCurrentWidget(current_widget)

    def update_scene_type_specific_fields(self):
        scene_type = self.scene_type_combo.currentText().strip()
        decimal_duration_scene = scene_type in {
            MINIMAX_H3_T2V_I2V_SCENE_TYPE,
            MINIMAX_H3_I2V_SCENE_TYPE,
            MINIMAX_H3_R2V_SCENE_TYPE,
        }
        if decimal_duration_scene:
            maximum = 30.0 if scene_type == MINIMAX_H3_T2V_I2V_SCENE_TYPE else 15.0
            validator = self.duration_decimal_input.validator()
            if isinstance(validator, QDoubleValidator):
                validator.setBottom(MINIMAX_H3_DURATION_MIN)
                validator.setTop(maximum)
            self.duration_input_stack.setCurrentWidget(self.duration_decimal_input)
        else:
            populate_duration_combo(self.duration_input, scene_type)
            self.duration_input_stack.setCurrentWidget(self.duration_input)
        hide_meta_duration = scene_type in {"wan22_s2v", MINIMAX_H3_S2V_SCENE_TYPE, "web_scroll"}
        self.duration_input_stack.setEnabled(not hide_meta_duration)
        if self.duration_label is not None:
            self.duration_label.setEnabled(not hide_meta_duration)
            self.duration_label.setVisible(not hide_meta_duration)
        self.duration_input_stack.setVisible(not hide_meta_duration)
        if scene_type == MINIMAX_H3_R2V_SCENE_TYPE and not self.is_viewing_variation():
            self.duration_input_stack.setEnabled(True)
            self.duration_input.setEnabled(True)
            self.duration_decimal_input.setEnabled(True)
            if self.duration_label is not None:
                self.duration_label.setEnabled(True)
                self.duration_label.setVisible(True)
        show_standalone_i2v_fps = scene_type == MINIMAX_H3_I2V_SCENE_TYPE
        self.minimax_h3_i2v_fps_label.setVisible(show_standalone_i2v_fps)
        self.minimax_h3_i2v_fps_input.setVisible(show_standalone_i2v_fps)
        is_wan22_s2v = scene_type == "wan22_s2v"
        is_minimax_h3_s2v = scene_type == MINIMAX_H3_S2V_SCENE_TYPE
        self.minimax_h3_s2v_fps_label.setVisible(is_minimax_h3_s2v)
        self.minimax_h3_s2v_fps_input.setVisible(is_minimax_h3_s2v)
        if self.s2v_negative_label is not None:
            self.s2v_negative_label.setVisible(is_wan22_s2v)
        self.s2v_negative_input.setVisible(is_wan22_s2v)
        self.s2v_cfg_input.setVisible(is_wan22_s2v)
        for widget in (
            self.minimax_h3_s2v_lora_label,
            self.minimax_h3_s2v_lora_name_input,
            self.minimax_h3_s2v_lora_strength_label,
            self.minimax_h3_s2v_lora_strength_input,
            self.minimax_h3_s2v_lora_2_label,
            self.minimax_h3_s2v_lora_name_2_input,
            self.minimax_h3_s2v_lora_strength_2_label,
            self.minimax_h3_s2v_lora_strength_2_input,
        ):
            widget.setVisible(is_minimax_h3_s2v)
        if self.s2v_cfg_label is not None:
            self.s2v_cfg_label.setVisible(is_wan22_s2v)
        self.s2v_tab.setWindowTitle("MINIMAX-H3_S2V" if is_minimax_h3_s2v else "WAN22 S2V")
        agentic_visible, forced_agentic_value = agentic_create_initial_image_policy(scene_type)
        if self.agentic_tab is not None:
            layout = self.agentic_tab.layout()
            self._set_form_field_visible(layout, self.agentic_create_initial_image_input, agentic_visible)
            self._set_form_field_visible(layout, self.agentic_image_extra_mode_input, scene_type == "i2v")
        if forced_agentic_value is not None:
            self.agentic_create_initial_image_input.setChecked(bool(forced_agentic_value))
        if scene_type != "i2v":
            default_mode_index = self.agentic_image_extra_mode_input.findData("image_extra")
            self.agentic_image_extra_mode_input.setCurrentIndex(default_mode_index if default_mode_index >= 0 else 0)
        self._apply_z_size_constraint_by_scene_type()

    def build_viewer_group(self):
        group = QGroupBox("Tampilan")
        group.setMinimumSize(0, 0)
        group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(group)
        layout.addWidget(self.viewer_title_label)
        layout.addWidget(self.viewer_stack)
        layout.addWidget(self.viewer_info_label)
        return group

    def build_status_group(self):
        group = QGroupBox("Status Adegan")
        layout = QVBoxLayout(group)
        self.status_label.setStyleSheet("padding: 6px; background: #f3f4f6; border: 1px solid #d1d5db;")
        layout.addWidget(self.status_label)
        return group

    def build_toolbar_actions(self):
        if self.toolbar is None:
            return
        self.toolbar.clear()
        self.project_action_group_widget = self.build_project_action_group()
        self.scene_action_group_widget = self.build_scene_action_group()
        self.edit_prompt_action_group_widget = self.build_edit_prompt_action_group()
        self.variation_action_group_widget = self.build_variation_action_group()
        self.run_action_group_widget = self.build_run_action_group()
        self.audio_action_group_widget = self.build_audio_action_group()
        self.backup_action_group_widget = self.build_backup_action_group()
        self.compose_action_group_widget = self.build_compose_action_group()
        self.runtime_action_group_widget = self.build_runtime_action_group()
        self.toolbar.addWidget(self.project_action_group_widget)
        self.toolbar.addWidget(self.scene_action_group_widget)
        self.toolbar.addWidget(self.edit_prompt_action_group_widget)
        self.toolbar.addWidget(self.variation_action_group_widget)
        self.toolbar.addWidget(self.run_action_group_widget)
        self.toolbar.addWidget(self.audio_action_group_widget)
        self.toolbar.addWidget(self.backup_action_group_widget)
        self.toolbar.addWidget(self.compose_action_group_widget)
        self.toolbar.addWidget(self.runtime_action_group_widget)
        self._apply_scene_view_mode()

    def build_project_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #eef2ff; border: 1px solid #a5b4fc; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        title = QLabel("Project", frame)
        title.setStyleSheet("font-weight: 600; color: #3730a3;")
        layout.addWidget(title)

        def add_button(tooltip, icon_kind, handler, theme_icon_name=""):
            button = QToolButton(frame)
            if theme_icon_name:
                icon = QIcon.fromTheme(theme_icon_name)
                if not icon.isNull():
                    button.setIcon(icon)
                else:
                    button.setIcon(self.style().standardIcon(icon_kind))
            else:
                button.setIcon(self.style().standardIcon(icon_kind))
            button.setToolTip(tooltip)
            button.setStatusTip(tooltip)
            button.clicked.connect(handler)
            layout.addWidget(button)

        add_button("Buat project baru.", QStyle.SP_FileDialogNewFolder, self.new_project)
        add_button("Buka project yang sudah ada.", QStyle.SP_DirOpenIcon, self.open_project)
        add_button("Jalankan agentic execute untuk beberapa project yang dipilih.", QStyle.SP_MediaPlay, self.open_multi_project_agentic_dialog)
        add_button("Tutup project aktif.", QStyle.SP_DialogCloseButton, self.close_project)
        add_button(
            "Buka konfigurasi project (deskripsi, ukuran video, model, voice, caption, cover).",
            QStyle.SP_DriveNetIcon,
            self.open_project_settings_dialog,
        )
        add_button("Buka atau tutup dialog status dan log proses.", QStyle.SP_FileDialogDetailedView, self.toggle_process_dialog)
        add_button("Muat ulang daftar adegan dan statusnya.", QStyle.SP_BrowserReload, self.reload_scene_list)
        return frame

    def build_scene_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #f0fdf4; border: 1px solid #86efac; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        title = QLabel("Scene", frame)
        title.setStyleSheet("font-weight: 600; color: #166534;")
        layout.addWidget(title)

        def add_button(tooltip, icon_kind, handler):
            button = QToolButton(frame)
            button.setIcon(self.style().standardIcon(icon_kind))
            button.setToolTip(tooltip)
            button.setStatusTip(tooltip)
            button.clicked.connect(handler)
            layout.addWidget(button)

        add_button("Tambahkan adegan baru di akhir daftar.", QStyle.SP_FileDialogNewFolder, self.add_scene)
        add_button("Sisipkan adegan baru sebelum adegan yang sedang dipilih.", QStyle.SP_ArrowDown, self.insert_scene)
        duplicate_button = QToolButton(frame)
        duplicate_icon = QIcon.fromTheme("edit-copy")
        duplicate_button.setIcon(
            duplicate_icon if not duplicate_icon.isNull() else self.style().standardIcon(QStyle.SP_FileIcon)
        )
        duplicate_button.setToolTip("Gandakan adegan yang sedang dipilih dan sisipkan setelahnya.")
        duplicate_button.setStatusTip(duplicate_button.toolTip())
        duplicate_button.clicked.connect(self.duplicate_scene)
        layout.addWidget(duplicate_button)
        add_button("Hapus adegan yang sedang dipilih.", QStyle.SP_DialogCloseButton, self.delete_scene)
        add_button("Simpan perubahan adegan yang sedang dibuka.", QStyle.SP_DialogSaveButton, self.save_current_scene)
        add_button("Upscale video terakhir pada root scene aktif.", QStyle.SP_ArrowUp, self.upscale_latest_scene_video)
        return frame

    def build_edit_prompt_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #f5f3ff; border: 1px solid #c4b5fd; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        title = QLabel("Edit", frame)
        title.setStyleSheet("font-weight: 600; color: #5b21b6;")
        layout.addWidget(title)

        button = QToolButton(frame)
        button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        button.setToolTip("Buka dialog append prompt untuk semua scene dan variasi.")
        button.setStatusTip(button.toolTip())
        button.clicked.connect(self.open_project_prompt_append_dialog)
        layout.addWidget(button)
        return frame

    def build_variation_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #fff7ed; border: 1px solid #fdba74; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        title = QLabel("Variasi", frame)
        title.setStyleSheet("font-weight: 600; color: #9a3412;")
        layout.addWidget(title)

        self.variation_view_input.setMinimumWidth(80)
        self.variation_view_input.addItem("Root Scene", "")
        self.variation_view_input.setEnabled(False)
        self.variation_view_input.setToolTip("Pilih root scene atau salah satu folder variasi untuk dilihat.")
        layout.addWidget(self.variation_view_input)

        self.copy_variation_to_root_button = QToolButton(frame)
        self.copy_variation_to_root_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.copy_variation_to_root_button.setToolTip("Kopikan video terbaru dari folder variasi terpilih ke root scene.")
        self.copy_variation_to_root_button.setStatusTip(self.copy_variation_to_root_button.toolTip())
        self.copy_variation_to_root_button.setEnabled(False)
        self.copy_variation_to_root_button.clicked.connect(self.copy_selected_variation_to_root)
        layout.addWidget(self.copy_variation_to_root_button)
        return frame

    def _scene_paths_equal(self, left: Path | None, right: Path | None) -> bool:
        if left is None or right is None:
            return left is right
        try:
            return left.resolve() == right.resolve()
        except Exception:
            return Path(left) == Path(right)

    def active_scene_dir(self) -> Path | None:
        return self.current_scene_view_dir or self.current_scene_dir

    def is_viewing_variation(self) -> bool:
        return (
            self.current_scene_dir is not None
            and self.current_scene_view_dir is not None
            and not self._scene_paths_equal(self.current_scene_dir, self.current_scene_view_dir)
        )

    def _variation_dirs_for_scene(self, scene_dir: Path | None) -> list[Path]:
        if scene_dir is None or not scene_dir.exists():
            return []
        variations = []
        for child in scene_dir.iterdir():
            if child.is_dir() and child.name.lower().startswith("variasi"):
                variations.append(child)
        return sorted(
            variations,
            key=lambda p: int("".join(ch for ch in p.name if ch.isdigit()) or "999999"),
        )

    def _refresh_variation_view_options(self, scene_dir: Path | None, selected_path: Path | None = None):
        self._loading_variation_view = True
        try:
            self.variation_view_input.clear()
            self.variation_view_input.addItem("Root Scene", "")
            for variation_dir in self._variation_dirs_for_scene(scene_dir):
                self.variation_view_input.addItem(variation_dir.name, str(variation_dir))
            target_path = selected_path if selected_path is not None else scene_dir
            index = 0
            if scene_dir is not None and target_path is not None and not self._scene_paths_equal(target_path, scene_dir):
                found = self.variation_view_input.findData(str(target_path))
                if found >= 0:
                    index = found
            self.variation_view_input.setCurrentIndex(index)
            self.variation_view_input.setEnabled(self.variation_view_input.count() > 1)
            self._update_copy_variation_button_state()
        finally:
            self._loading_variation_view = False

    def _reset_variation_view_for_scene(self, scene_dir: Path | None):
        self.current_scene_view_dir = scene_dir
        self._refresh_variation_view_options(scene_dir, selected_path=scene_dir)
        self._apply_scene_view_mode()
        if scene_dir is not None:
            self.load_scene(scene_dir, root_scene_dir=scene_dir)
        else:
            self.refresh_scene_status()
            self.refresh_assets_and_previews()

    def on_variation_view_changed(self, _index: int):
        if self._loading_variation_view or self.loading_scene:
            return
        if not self.current_scene_dir:
            return
        target_data = self.variation_view_input.currentData()
        target_path = self.current_scene_dir if not target_data else Path(str(target_data))
        previous_view = self.current_scene_view_dir
        if self._scene_paths_equal(previous_view, target_path):
            return
        if previous_view is not None and self._scene_paths_equal(previous_view, self.current_scene_dir):
            if not self.save_current_scene(silent=True, reload_list=False):
                self._refresh_variation_view_options(self.current_scene_dir, selected_path=previous_view)
                return
        self.release_media_locks()
        self.current_scene_view_dir = target_path
        self._apply_scene_view_mode()
        self.load_scene(target_path, root_scene_dir=self.current_scene_dir)

    def _selected_variation_dir(self) -> Path | None:
        if not self.current_scene_dir:
            return None
        target_data = self.variation_view_input.currentData()
        if not target_data:
            return None
        target_path = Path(str(target_data))
        if self._scene_paths_equal(target_path, self.current_scene_dir):
            return None
        return target_path

    def _has_variations_for_current_scene(self) -> bool:
        return bool(self._variation_dirs_for_scene(self.current_scene_dir))

    def _update_variation_config_copy_buttons_state(self):
        enabled = (
            self.current_scene_dir is not None
            and not self.is_viewing_variation()
            and self._has_variations_for_current_scene()
        )
        for button in (
            getattr(self, "copy_z_variations_button", None),
            getattr(self, "copy_wan_t2v_variations_button", None),
            getattr(self, "copy_wan_i2v_variations_button", None),
            getattr(self, "copy_minimax_h3_t2v_variations_button", None),
            getattr(self, "copy_minimax_h3_i2v_variations_button", None),
            getattr(self, "copy_minimax_h3_s2v_variations_button", None),
            getattr(self, "copy_minimax_h3_r2v_variations_button", None),
        ):
            if button is not None:
                button.setEnabled(enabled)

    def _update_copy_variation_button_state(self):
        if self.copy_variation_to_root_button is None:
            return
        selected_variation = self._selected_variation_dir()
        self.copy_variation_to_root_button.setEnabled(
            self.current_scene_dir is not None
            and selected_variation is not None
            and selected_variation.exists()
        )
        self._update_variation_config_copy_buttons_state()

    def _copy_selected_keys_to_variations(
        self,
        *,
        filename: str,
        source_data: dict,
        keys: list[str],
        action_title: str,
    ):
        if not self.current_scene_dir:
            return
        if self.is_viewing_variation():
            QMessageBox.information(
                self,
                "Mode Lihat Variasi",
                "Pilih `Root Scene` di dropdown Variasi untuk mengedit konfigurasi variasi.",
            )
            return
        variation_dirs = self._variation_dirs_for_scene(self.current_scene_dir)
        if not variation_dirs:
            QMessageBox.information(self, "Tidak Ada Variasi", "Scene aktif belum memiliki folder variasi.")
            return

        updated_count = 0
        skipped_count = 0
        errors = []
        for variation_dir in variation_dirs:
            target_path = variation_dir / filename
            if not target_path.exists():
                skipped_count += 1
                continue
            try:
                payload = _load_json_raw(target_path, {})
                changed = False
                for key in keys:
                    if key in source_data and payload.get(key) != source_data.get(key):
                        payload[key] = copy.deepcopy(source_data.get(key))
                        changed = True
                if changed:
                    write_json(target_path, payload)
                    updated_count += 1
            except Exception as e:
                errors.append(f"{variation_dir.name}: {e}")

        summary = (
            f"{action_title} selesai.\n\n"
            f"Variasi diupdate: {updated_count}\n"
            f"Variasi dilewati: {skipped_count}"
        )
        if errors:
            preview = "\n".join(errors[:8])
            if len(errors) > 8:
                preview += f"\n... dan {len(errors) - 8} error lain."
            QMessageBox.warning(self, f"{action_title} Dengan Error", f"{summary}\n\nError:\n{preview}")
            return
        QMessageBox.information(self, action_title, summary)

    def copy_wan_t2v_config_to_variations(self):
        if not self.save_current_scene(silent=True, reload_list=False):
            QMessageBox.warning(self, "Data Tidak Valid", "Simpan scene aktif gagal. Periksa dulu konfigurasi scene.")
            return
        _meta, _z_prompt, wan_t2v_prompt, _wan_prompt, *_rest = self.gather_scene_data()
        self._copy_selected_keys_to_variations(
            filename="wan22_t2v_prompt.json",
            source_data=wan_t2v_prompt,
            keys=[
                LORA_TRIGGER_WORDS_FIELD,
                "lora_high_name",
                "lora_high_strength",
                "lora_low_name",
                "lora_low_strength",
                "lora_high_name_2",
                "lora_high_strength_2",
                "lora_low_name_2",
                "lora_low_strength_2",
            ],
            action_title="Edit Variasi WAN22_T2V",
        )

    def copy_z_config_to_variations(self):
        if not self.save_current_scene(silent=True, reload_list=False):
            QMessageBox.warning(self, "Data Tidak Valid", "Simpan scene aktif gagal. Periksa dulu konfigurasi scene.")
            return
        _meta, z_prompt, _wan_t2v_prompt, _wan_prompt, *_rest = self.gather_scene_data()
        self._copy_selected_keys_to_variations(
            filename="z_image_prompt.json",
            source_data=z_prompt,
            keys=[
                "image_model",
                "gemini_model_id",
                "use_random_seed",
                "seed",
                "use_lora",
                "lora_name",
                "strength_model",
                LORA_TRIGGER_WORDS_FIELD,
            ],
            action_title="Edit Variasi Gambar Awal",
        )

    def copy_wan_i2v_config_to_variations(self):
        if not self.save_current_scene(silent=True, reload_list=False):
            QMessageBox.warning(self, "Data Tidak Valid", "Simpan scene aktif gagal. Periksa dulu konfigurasi scene.")
            return
        _meta, _z_prompt, _wan_t2v_prompt, wan_prompt, *_rest = self.gather_scene_data()
        self._copy_selected_keys_to_variations(
            filename="wan22_i2v_prompt.json",
            source_data=wan_prompt,
            keys=[
                LORA_TRIGGER_WORDS_FIELD,
                "lora_high_name",
                "lora_high_strength",
                "lora_low_name",
                "lora_low_strength",
                "lora_high_name_2",
                "lora_high_strength_2",
                "lora_low_name_2",
                "lora_low_strength_2",
            ],
            action_title="Edit Variasi WAN22_I2V",
        )

    def copy_minimax_h3_t2v_config_to_variations(self):
        if not self.save_current_scene(silent=True, reload_list=False):
            QMessageBox.warning(self, "Data Tidak Valid", "Simpan scene aktif gagal. Periksa dulu konfigurasi scene.")
            return
        minimax_t2v_prompt, _minimax_i2v_prompt = self.gather_minimax_h3_prompts()
        self._copy_selected_keys_to_variations(
            filename="minimax_h3_t2v_prompt.json",
            source_data=minimax_t2v_prompt,
            keys=["fps", "lora_name", "lora_strength", "lora_name_2", "lora_strength_2", "remove_sound"],
            action_title="Edit Variasi MiniMax H3 T2V",
        )

    def copy_minimax_h3_i2v_config_to_variations(self):
        if not self.save_current_scene(silent=True, reload_list=False):
            QMessageBox.warning(self, "Data Tidak Valid", "Simpan scene aktif gagal. Periksa dulu konfigurasi scene.")
            return
        _minimax_t2v_prompt, minimax_i2v_prompt = self.gather_minimax_h3_prompts()
        self._copy_selected_keys_to_variations(
            filename="minimax_h3_i2v_prompt.json",
            source_data=minimax_i2v_prompt,
            keys=["fps", "lora_name", "lora_strength", "lora_name_2", "lora_strength_2", "remove_sound"],
            action_title="Edit Variasi MiniMax H3 I2V",
        )

    def copy_selected_variation_to_root(self):
        if not self.current_scene_dir:
            return
        variation_dir = self._selected_variation_dir()
        if variation_dir is None:
            QMessageBox.information(
                self,
                "Pilih Variasi",
                "Pilih salah satu folder variasi di dropdown terlebih dahulu.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Kopikan Variasi ke Root",
            (
                f"Root scene {self.current_scene_dir.name} akan menerima video terbaru dari {variation_dir.name}.\n\n"
                "Video root lama akan dihapus, folder variasi tidak akan dihapus. Lanjutkan?"
            ),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.release_media_locks()
            latest_video = copy_latest_video_to_root(variation_dir, self.current_scene_dir)
        except Exception as e:
            QMessageBox.critical(self, "Gagal Copy Variasi", f"Gagal menyalin variasi ke root:\n{e}")
            return

        self.current_scene_view_dir = self.current_scene_dir
        self._refresh_variation_view_options(self.current_scene_dir, selected_path=self.current_scene_dir)
        self._apply_scene_view_mode()
        self.load_scene(self.current_scene_dir, root_scene_dir=self.current_scene_dir)
        self.statusBar().showMessage(
            f"Video terbaru {latest_video.name} dari {variation_dir.name} dikopikan ke root scene {self.current_scene_dir.name}.",
            5000,
        )

    def _capture_widget_view_base_state(self, widget: QWidget):
        if widget is self.status_label or widget is self.asset_list:
            return
        if isinstance(widget, (QPlainTextEdit, QTextEdit, QLineEdit)):
            widget.setProperty("_view_base_read_only_state", widget.isReadOnly())
            return
        if isinstance(widget, (QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QToolButton)):
            widget.setProperty("_view_base_enabled_state", widget.isEnabled())

    def _capture_scene_view_mode_baseline(self):
        if self.editor_tabs is None or self.is_viewing_variation():
            return
        for widget in self.editor_tabs.findChildren(QWidget):
            self._capture_widget_view_base_state(widget)

    def _set_widget_view_only_state(self, widget: QWidget, read_only: bool):
        if widget is self.status_label or widget is self.asset_list:
            return
        if isinstance(widget, QPlainTextEdit):
            if widget.property("_view_base_read_only_state") is None:
                self._capture_widget_view_base_state(widget)
            widget.setReadOnly(True if read_only else bool(widget.property("_view_base_read_only_state")))
            return
        if isinstance(widget, (QTextEdit, QLineEdit)):
            if widget.property("_view_base_read_only_state") is None:
                self._capture_widget_view_base_state(widget)
            widget.setReadOnly(True if read_only else bool(widget.property("_view_base_read_only_state")))
            return
        if isinstance(widget, (QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QToolButton)):
            if widget.property("_view_base_enabled_state") is None:
                self._capture_widget_view_base_state(widget)
            widget.setEnabled(False if read_only else bool(widget.property("_view_base_enabled_state")))

    def _apply_scene_view_mode(self):
        read_only = self.is_viewing_variation()
        active_dir = self.active_scene_dir()

        if self.editor_tabs is not None:
            for widget in self.editor_tabs.findChildren(QWidget):
                self._set_widget_view_only_state(widget, read_only)

        for group_widget in (
            self.scene_action_group_widget,
            self.run_action_group_widget,
            self.audio_action_group_widget,
            self.compose_action_group_widget,
        ):
            if group_widget is not None:
                group_widget.setEnabled(not read_only)

        if self.variation_action_group_widget is not None:
            self.variation_action_group_widget.setEnabled(self.current_scene_dir is not None)
            self.variation_view_input.setEnabled(self.variation_view_input.count() > 1)
            self._update_copy_variation_button_state()
        else:
            self._update_variation_config_copy_buttons_state()

        if read_only and active_dir is not None:
            self.statusBar().showMessage(
                f"Mode lihat variasi aktif: {active_dir.name}. Edit hanya tersedia untuk root scene.",
                5000,
            )

    def project_dir(self) -> Path | None:
        name = str(self.current_project_name or "").strip()
        if not name:
            return None
        return API_PRODUCTION / name

    def list_projects(self):
        API_PRODUCTION.mkdir(parents=True, exist_ok=True)
        items = []
        reserved = {"combined", "cover"}
        for child in API_PRODUCTION.iterdir():
            if (
                child.is_dir()
                and child.name not in reserved
                and not child.name.startswith("scene_")
                and not child.name.startswith("__")
            ):
                items.append(child.name)
        items.sort(key=lambda s: s.lower())
        return items

    def list_scene_dirs_current(self):
        return list_scene_dirs_in_project(self.project_dir())

    def _project_video_size(self) -> tuple[int, int]:
        size = self.project_settings.get("video_size", {}) if isinstance(self.project_settings, dict) else {}
        try:
            width = int(size.get("width", DEFAULT_PROJECT_SETTINGS["video_size"]["width"]))
        except (TypeError, ValueError):
            width = int(DEFAULT_PROJECT_SETTINGS["video_size"]["width"])
        try:
            height = int(size.get("height", DEFAULT_PROJECT_SETTINGS["video_size"]["height"]))
        except (TypeError, ValueError):
            height = int(DEFAULT_PROJECT_SETTINGS["video_size"]["height"])
        if width <= 0 or height <= 0:
            return (
                int(DEFAULT_PROJECT_SETTINGS["video_size"]["width"]),
                int(DEFAULT_PROJECT_SETTINGS["video_size"]["height"]),
            )
        return width, height

    def _set_locked_size_combo(self, combo: QComboBox, width: int, height: int):
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(f"{width}x{height}", (width, height))
        combo.setCurrentIndex(0)
        combo.setEnabled(False)
        combo.blockSignals(False)

    def _set_unlocked_z_size_combo(self, selected_size: tuple[int, int] | None = None):
        current_size = selected_size
        if current_size is None:
            current_data = self.z_size_input.currentData()
            if isinstance(current_data, tuple) and len(current_data) == 2:
                try:
                    current_size = (int(current_data[0]), int(current_data[1]))
                except (TypeError, ValueError):
                    current_size = None
        self.z_size_input.blockSignals(True)
        self.z_size_input.clear()
        target_index = -1
        for idx, (label, width, height) in enumerate(Z_IMAGE_SIZES):
            item_size = (int(width), int(height))
            self.z_size_input.addItem(label, item_size)
            if current_size == item_size:
                target_index = idx
        self.z_size_input.setCurrentIndex(max(target_index, 0))
        self.z_size_input.setEnabled(True)
        self.z_size_input.blockSignals(False)

    def _apply_z_size_constraint_by_scene_type(self):
        scene_type = str(self.scene_type_combo.currentText() or "").strip()
        if scene_type in {"image_pan", "image_zoom"}:
            self._set_unlocked_z_size_combo()
            return
        width, height = self._project_video_size()
        self._set_locked_size_combo(self.z_size_input, width, height)

    def apply_project_size_constraints_to_ui(self):
        width, height = self._project_video_size()
        for combo in (
            self.wan_size_input,
            self.wan_t2v_size_input,
            self.minimax_h3_t2v_size_input,
            self.minimax_h3_i2v_size_input,
            self.minimax_h3_r2v_size_input,
            self.s2v_size_input,
            self.web_size_input,
            self.image_pan_size_input,
            self.image_zoom_size_input,
            self.web_search_size_input,
        ):
            self._set_locked_size_combo(combo, width, height)
        self._apply_z_size_constraint_by_scene_type()

    def _sync_project_size_to_scene_file(self, scene_dir: Path, filename: str, width: int, height: int):
        path = scene_dir / filename
        if not path.exists():
            return
        try:
            data = load_json(path, {})
        except Exception:
            return
        if not isinstance(data, dict):
            return
        data["width"] = int(width)
        data["height"] = int(height)
        write_prompt_json(path, data)

    def sync_project_size_to_all_scenes(self):
        pdir = self.project_dir()
        if pdir is None:
            return
        width, height = self._project_video_size()
        for scene_dir in list_scene_dirs_in_project(pdir):
            meta = load_json(scene_dir / "scene_meta.json", DEFAULT_SCENE_META)
            scene_type = str(meta.get("scene_type", "wan22_i2v")).strip()
            if scene_type in {"wan22_i2v", "wan22_s2v", MINIMAX_H3_I2V_SCENE_TYPE, "i2v"}:
                self._sync_project_size_to_scene_file(scene_dir, "z_image_prompt.json", width, height)
            self._sync_project_size_to_scene_file(scene_dir, "wan22_i2v_prompt.json", width, height)
            self._sync_project_size_to_scene_file(scene_dir, "minimax_h3_t2v_prompt.json", width, height)
            self._sync_project_size_to_scene_file(scene_dir, "minimax_h3_i2v_prompt.json", width, height)
            self._sync_project_size_to_scene_file(scene_dir, MINIMAX_H3_R2V_PROMPT_FILENAME, width, height)
            self._sync_project_size_to_scene_file(scene_dir, "wan22_s2v_prompt.json", width, height)
            self._sync_project_size_to_scene_file(scene_dir, "web_scroll_prompt.json", width, height)
            self._sync_project_size_to_scene_file(scene_dir, "image_pan_prompt.json", width, height)
            self._sync_project_size_to_scene_file(scene_dir, "image_zoom_prompt.json", width, height)

    def load_project_settings(self):
        pdir = self.project_dir()
        if pdir is None:
            self.project_settings = copy.deepcopy(DEFAULT_PROJECT_SETTINGS)
            self.project_voice_config = copy.deepcopy(DEFAULT_PROJECT_VOICE_CONFIG)
            self.project_caption_config = copy.deepcopy(DEFAULT_PROJECT_CAPTION_CONFIG)
            self.apply_project_size_constraints_to_ui()
            return
        self.project_settings = load_project_settings_file(pdir)
        self.project_voice_config = copy.deepcopy(self.project_settings.get("voice", DEFAULT_PROJECT_VOICE_CONFIG))
        self.project_caption_config = copy.deepcopy(self.project_settings.get("caption", DEFAULT_PROJECT_CAPTION_CONFIG))
        self.apply_project_size_constraints_to_ui()

    def save_project_settings(self, settings: dict, sync_scene_sizes: bool = False):
        pdir = self.project_dir()
        if pdir is None:
            return
        self.project_settings = save_project_settings_file(pdir, settings)
        self.project_voice_config = copy.deepcopy(self.project_settings.get("voice", DEFAULT_PROJECT_VOICE_CONFIG))
        self.project_caption_config = copy.deepcopy(self.project_settings.get("caption", DEFAULT_PROJECT_CAPTION_CONFIG))

        self.apply_project_size_constraints_to_ui()
        if sync_scene_sizes:
            self.sync_project_size_to_all_scenes()

    def save_project_voice_settings(self, provider: str | None = None):
        if provider is None:
            provider = self.project_voice_config.get("voice_provider", VOICE_PROVIDER_GEMINI)
        provider = normalize_provider(provider)
        updated = copy.deepcopy(self.project_settings)
        updated["voice"] = {"voice_provider": provider}
        self.save_project_settings(updated, sync_scene_sizes=False)

    def open_project_settings_dialog(self):
        if not self.ensure_project_selected():
            return
        self._open_project_settings_dialog_now()

    def _open_project_settings_dialog_now(self):
        current_settings = copy.deepcopy(self.project_settings)
        dialog = ProjectSettingsDialog(
            current_settings,
            self,
            project_dir=self.project_dir(),
            on_generate_cover=self.generate_cover_from_project_settings_dialog,
            on_run_agentic_generate=self.run_agentic_generate_from_project_settings_dialog,
            on_run_agentic_execute=self.run_agentic_execute_from_project_settings_dialog,
            on_run_clear_vram=self.run_clear_vram_from_project_settings_dialog,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        new_settings = dialog.saved_data
        if not isinstance(new_settings, dict):
            return
        self.apply_project_settings_and_refresh(new_settings, notify=True)

    def open_project_prompt_append_dialog(self):
        if not self.ensure_project_selected():
            return
        dialog = ProjectPromptAppendDialog(self, on_run=self.run_project_prompt_append_operation)
        dialog.exec()

    def _comfyui_server_for_project_name(self, project_name: str) -> str:
        project_name = str(project_name or "").strip()
        if not project_name:
            return str(DEFAULT_PROJECT_SETTINGS.get("comfyui_server", "nextgenserver:8188")).strip()
        project_dir = API_PRODUCTION / project_name
        settings = load_project_settings_file(project_dir)
        return str(settings.get("comfyui_server", DEFAULT_PROJECT_SETTINGS.get("comfyui_server", "nextgenserver:8188"))).strip()

    def open_multi_project_agentic_dialog(self):
        project_names = self.list_projects()
        if not project_names:
            QMessageBox.information(self, "Belum Ada Project", "Belum ada project yang bisa dipilih.")
            return
        dialog = MultiProjectAgenticDialog(project_names, self, on_run=self.run_multi_project_agentic)
        dialog.exec()

    def run_multi_project_agentic(self, selected_projects: list[str]):
        selected = sorted(
            [str(project_name or "").strip() for project_name in selected_projects if str(project_name or "").strip()],
            key=lambda value: value.lower(),
        )
        if not selected:
            QMessageBox.information(self, "Belum Ada Pilihan", "Pilih minimal satu project terlebih dahulu.")
            return
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            QMessageBox.information(self, "Proses Sedang Berjalan", "Tunggu proses yang sedang berjalan selesai terlebih dahulu.")
            return
        reply = QMessageBox.question(
            self,
            "Jalankan Agentic",
            "Jalankan agentic execute untuk project terpilih secara berurutan?\n\n- " + "\n- ".join(selected),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.multi_project_agentic_queue = list(selected)
        self.multi_project_agentic_completed = []
        self._start_next_multi_project_agentic()

    def _start_next_multi_project_agentic(self):
        if not self.multi_project_agentic_queue:
            completed = list(self.multi_project_agentic_completed)
            self.multi_project_agentic_completed = []
            QMessageBox.information(
                self,
                "Agentic Selesai",
                "Agentic execute selesai untuk semua project terpilih.\n\n- " + "\n- ".join(completed),
            )
            self.statusBar().showMessage("Agentic multi project selesai.", 5000)
            return
        project_name = self.multi_project_agentic_queue.pop(0)
        server = self._comfyui_server_for_project_name(project_name)
        project_dir = API_PRODUCTION / project_name
        scene_dirs = list_scene_dirs_in_project(project_dir)
        started = self.start_process(
            AGENTIC_SCRIPT,
            ["--server", server, "--project", project_name, "--mode", "execute"],
            f"Execute agentic untuk project {project_name}",
            watch_dirs=scene_dirs,
            extra_context={
                "kind": "multi_project_agentic",
                "project_name": project_name,
            },
        )
        if not started:
            self.multi_project_agentic_queue = []
            self.multi_project_agentic_completed = []

    def run_project_prompt_append_operation(self, operation_key: str, prompt_text: str):
        if not self.ensure_project_selected():
            return
        operation = PROMPT_APPEND_OPERATIONS.get(str(operation_key or "").strip())
        if not isinstance(operation, dict):
            QMessageBox.warning(self, "Operasi Tidak Dikenal", "Jenis append prompt tidak dikenali.")
            return
        prompt_text = str(prompt_text or "").strip()
        if not prompt_text:
            QMessageBox.warning(self, "Input Kosong", "Isi teks tambahan terlebih dahulu.")
            return

        title = str(operation.get("title", operation_key))
        project_dir = self.project_dir()
        if project_dir is None:
            return

        self.ensure_process_dialog()
        self.append_log(f"[prompt-append] Menjalankan: {title}")
        self.append_log("[prompt-append] Menerjemahkan teks tambahan ke Inggris sekali di awal.")
        try:
            translator = get_prompt_translator(project_dir=project_dir)
            prompt_en = str(translator.translate_to_english(prompt_text) or "").strip()
        except Exception as e:
            QMessageBox.critical(self, "Gagal Translate Prompt", f"Gagal menerjemahkan prompt:\n{e}")
            self.append_log(f"[prompt-append][gagal] Translate gagal: {e}")
            return
        if not prompt_en:
            prompt_en = prompt_text

        folder_count = 0
        file_count = 0
        prompt_count = 0
        error_messages = []

        for scene_dir in list_scene_dirs_in_project(project_dir):
            for target_dir in _prompt_target_dirs_for_scene(scene_dir):
                folder_count += 1
                for target in operation.get("targets", []):
                    filename = str(target.get("filename", "")).strip()
                    if not filename:
                        continue
                    try:
                        changed, updated_prompts = _append_prompts_in_file(
                            target_dir / filename,
                            mode=str(target.get("mode", "top_level")).strip(),
                            keys=list(target.get("keys", [])),
                            default=copy.deepcopy(target.get("default", {})),
                            append_id=prompt_text,
                            append_en=prompt_en,
                        )
                    except Exception as e:
                        error_messages.append(f"{target_dir.name}/{filename}: {e}")
                        self.append_log(f"[prompt-append][gagal] {target_dir / filename}: {e}")
                        continue
                    if changed:
                        file_count += 1
                        prompt_count += updated_prompts
                        self.append_log(
                            f"[prompt-append][ok] {target_dir / filename} ({updated_prompts} prompt)"
                        )

        if self.current_scene_dir:
            active_view = self.active_scene_dir() or self.current_scene_dir
            self._refresh_variation_view_options(self.current_scene_dir, selected_path=active_view)
            self.load_scene(active_view, root_scene_dir=self.current_scene_dir)
        self.refresh_scene_status()

        summary = (
            f"{title} selesai.\n\n"
            f"Folder diproses: {folder_count}\n"
            f"File diubah: {file_count}\n"
            f"Prompt diubah: {prompt_count}"
        )
        if error_messages:
            preview = "\n".join(error_messages[:8])
            if len(error_messages) > 8:
                preview += f"\n... dan {len(error_messages) - 8} error lain."
            summary = f"{summary}\n\nError:\n{preview}"
            QMessageBox.warning(self, "Append Prompt Selesai Dengan Error", summary)
            self.append_log(f"[prompt-append] Selesai dengan {len(error_messages)} error.")
            self.statusBar().showMessage("Append prompt selesai dengan error.", 5000)
            return

        QMessageBox.information(self, "Append Prompt Selesai", summary)
        self.append_log("[prompt-append] Selesai tanpa error.")
        self.statusBar().showMessage("Append prompt selesai.", 4000)

    def apply_project_settings_and_refresh(self, settings: dict, notify: bool = False):
        self.save_project_settings(settings, sync_scene_sizes=True)
        if self.current_scene_dir:
            self.load_scene(self.current_scene_dir, root_scene_dir=self.current_scene_dir)
        self.refresh_scene_status()
        if notify:
            self.statusBar().showMessage("Konfigurasi project disimpan.", 3000)

    def generate_cover_from_project_settings_dialog(self, settings: dict):
        if not self.ensure_project_selected():
            return
        self.apply_project_settings_and_refresh(settings, notify=False)
        project_dir = self.project_dir()
        watch_dirs = [project_dir / "cover"] if project_dir else []
        self.start_process(
            COVER_IMAGE_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name],
            f"Membuat cover project {self.current_project_name}",
            watch_dirs=watch_dirs,
        )

    def _start_agentic_mode(self, settings: dict, mode: str, action_label: str):
        if not self.ensure_project_selected():
            return
        self.apply_project_settings_and_refresh(settings, notify=False)
        if self.current_scene_dir:
            self.save_current_scene(silent=True, reload_list=False)
        project_dir = self.project_dir()
        watch_dirs = self.list_scene_dirs_current() if project_dir else []
        self.start_process(
            AGENTIC_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name, "--mode", mode],
            f"{action_label} untuk project {self.current_project_name}",
            watch_dirs=watch_dirs,
        )

    def run_agentic_generate_from_project_settings_dialog(self, settings: dict):
        self._start_agentic_mode(settings, "generate", "Generate konfigurasi agentic")

    def run_agentic_execute_from_project_settings_dialog(self, settings: dict):
        self._start_agentic_mode(settings, "execute", "Execute agentic")

    def run_clear_vram_from_project_settings_dialog(self, settings: dict):
        if not self.ensure_project_selected():
            return
        self.apply_project_settings_and_refresh(settings, notify=False)
        self.run_clear_vram()

    def refresh_project_state(self):
        project_label = self.current_project_name if self.current_project_name else "(tidak ada project)"
        self.setWindowTitle(f"Pengelola Adegan - {project_label}")
        if not self.current_project_name:
            self.current_scene_dir = None
            self.scene_list.clear()
            self.refresh_image_edit_source_options()
            self.status_label.setPlainText("Belum ada project yang dibuka.")
            self.viewer_info_label.setText("Buka project terlebih dahulu.")
            self.load_project_settings()
        self.update_run_action_buttons_state()

    def snapshot_window_state(self):
        return {
            "geometry": self.geometry(),
            "state": self.windowState(),
        }

    def restore_window_state(self, snapshot):
        if not snapshot:
            return
        state = snapshot.get("state")
        geometry = snapshot.get("geometry")
        if state is not None and state & Qt.WindowFullScreen:
            self.showFullScreen()
            return
        if state is not None and state & Qt.WindowMaximized:
            self.showMaximized()
            return
        if geometry is not None:
            self.showNormal()
            self.setGeometry(geometry)

    def ensure_project_selected(self, notify=True):
        if self.project_dir() is not None:
            return True
        if notify:
            QMessageBox.information(self, "Belum Ada Project", "Buka atau buat project terlebih dahulu.")
        return False

    def new_project(self):
        window_snapshot = self.snapshot_window_state()
        if self.current_scene_dir:
            self.save_current_scene(silent=True, reload_list=False)
        name, ok = QInputDialog.getText(self, "Project Baru", "Masukkan nama project:")
        if not ok:
            return
        try:
            project_name = validate_project_name(name)
        except ValueError as exc:
            QMessageBox.warning(self, "Nama Tidak Valid", str(exc))
            return
        try:
            create_project_on_disk(project_name, create_default_scene=True)
        except FileExistsError as exc:
            QMessageBox.warning(self, "Project Sudah Ada", str(exc))
            return
        self.current_project_name = project_name
        self.load_project_settings()
        self.reload_scene_list()
        self.select_scene_by_name(scene_dir_name(1))
        self.refresh_project_state()
        QTimer.singleShot(0, lambda snap=window_snapshot: self.restore_window_state(snap))
        self.statusBar().showMessage(f"Project {project_name} dibuat.", 3000)

    def open_project(self):
        window_snapshot = self.snapshot_window_state()
        if self.current_scene_dir:
            self.save_current_scene(silent=True, reload_list=False)
        projects = self.list_projects()
        if not projects:
            QMessageBox.information(self, "Project Kosong", "Belum ada project di api_production.")
            return
        selected, ok = QInputDialog.getItem(self, "Buka Project", "Pilih project:", projects, 0, False)
        if not ok:
            return
        self.current_project_name = str(selected).strip()
        self.load_project_settings()
        self.save_project_settings(copy.deepcopy(self.project_settings), sync_scene_sizes=True)
        self.reload_scene_list()
        self.refresh_project_state()
        QTimer.singleShot(0, lambda snap=window_snapshot: self.restore_window_state(snap))
        self.statusBar().showMessage(f"Project {self.current_project_name} dibuka.", 3000)

    def close_project(self):
        window_snapshot = self.snapshot_window_state()
        if self.current_scene_dir and not self.is_viewing_variation():
            self.save_current_scene(silent=True, reload_list=False)
        self.release_media_locks()
        self.current_project_name = ""
        self.current_scene_dir = None
        self.current_scene_view_dir = None
        self._refresh_variation_view_options(None)
        self._apply_scene_view_mode()
        self.refresh_project_state()
        QTimer.singleShot(0, lambda snap=window_snapshot: self.restore_window_state(snap))

    def build_run_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #eef6ff; border: 1px solid #93c5fd; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        title = QLabel("Proses", frame)
        title.setStyleSheet("font-weight: 600; color: #1d4ed8;")
        layout.addWidget(title)

        def add_button(text, tooltip, icon_kind, handler):
            button = QToolButton(frame)
            button.setIcon(self.style().standardIcon(icon_kind))
            button.setToolTip(tooltip)
            button.setStatusTip(tooltip)
            button.clicked.connect(handler)
            layout.addWidget(button)
            return button

        self.generate_initial_image_button = add_button(
            "Buat Gambar Awal",
            "Buat gambar awal untuk adegan yang dipilih.",
            QStyle.SP_ComputerIcon,
            self.generate_initial_image_only,
        )
        add_button("Jalankan Adegan", "Jalankan alur untuk adegan yang dipilih.", QStyle.SP_MediaPlay, self.run_current_scene)
        add_button("Jalankan Semua", "Jalankan semua adegan secara berurutan.", QStyle.SP_MediaSkipForward, self.run_all_scenes)
        return frame

    def update_run_action_buttons_state(self):
        if self.generate_initial_image_button is None:
            return
        scene_type = self.scene_type_combo.currentText().strip()
        self.generate_initial_image_button.setEnabled(scene_type_supports_initial_image(scene_type))

    def build_audio_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #effaf5; border: 1px solid #86efac; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        title = QLabel("Audio", frame)
        title.setStyleSheet("font-weight: 600; color: #166534;")
        layout.addWidget(title)

        def add_button(tooltip, icon_kind, handler, theme_icon_name=""):
            button = QToolButton(frame)
            if theme_icon_name:
                icon = QIcon.fromTheme(theme_icon_name)
                if not icon.isNull():
                    button.setIcon(icon)
                else:
                    button.setIcon(self.style().standardIcon(icon_kind))
            else:
                button.setIcon(self.style().standardIcon(icon_kind))
            button.setToolTip(tooltip)
            button.setStatusTip(tooltip)
            button.clicked.connect(handler)
            layout.addWidget(button)

        add_button("Buat voice untuk adegan yang dipilih.", QStyle.SP_MediaVolume, self.generate_voice_current_scene)
        add_button("Buat voice untuk semua adegan.", QStyle.SP_MediaSeekForward, self.generate_voice_all_scenes)
        add_button("Buat sound untuk adegan yang dipilih.", QStyle.SP_DialogOpenButton, self.generate_sound_current_scene)
        add_button("Buat sound untuk semua adegan.", QStyle.SP_DialogApplyButton, self.generate_sound_all_scenes)
        return frame

    def build_backup_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #f5f3ff; border: 1px solid #c4b5fd; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        title = QLabel("Backup", frame)
        title.setStyleSheet("font-weight: 600; color: #5b21b6;")
        layout.addWidget(title)

        button = QToolButton(frame)
        button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        button.setToolTip("Simpan backup ZIP project aktif.")
        button.setStatusTip("Simpan backup ZIP project aktif.")
        button.clicked.connect(self.save_backup_zip)
        layout.addWidget(button)
        return frame

    def build_compose_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #fff7ed; border: 1px solid #fdba74; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        title = QLabel("Compose", frame)
        title.setStyleSheet("font-weight: 600; color: #9a3412;")
        layout.addWidget(title)

        def add_button(tooltip, icon_kind, handler):
            button = QToolButton(frame)
            button.setIcon(self.style().standardIcon(icon_kind))
            button.setToolTip(tooltip)
            button.setStatusTip(tooltip)
            button.clicked.connect(handler)
            layout.addWidget(button)

        add_button("Gabungkan video dan audio untuk semua adegan.", QStyle.SP_DialogYesButton, self.compose_all_scenes)
        return frame

    def build_runtime_action_group(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background: #eff6ff; border: 1px solid #93c5fd; border-radius: 6px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        llama_button = QToolButton(frame)
        llama_button.setText("L")
        llama_button.setToolTip("Hidupkan Llama dan matikan ComfyUI.")
        llama_button.setStatusTip(llama_button.toolTip())
        llama_button.clicked.connect(lambda: self.manual_runtime_switch("llama"))
        layout.addWidget(llama_button)

        comfyui_button = QToolButton(frame)
        comfyui_button.setText("C")
        comfyui_button.setToolTip("Hidupkan ComfyUI dan matikan Llama.")
        comfyui_button.setStatusTip(comfyui_button.toolTip())
        comfyui_button.clicked.connect(lambda: self.manual_runtime_switch("comfyui"))
        layout.addWidget(comfyui_button)
        self.runtime_switch_buttons = [llama_button, comfyui_button]

        status_button = QToolButton(frame)
        status_button.setText("V")
        status_button.setFixedWidth(30)
        status_button.setToolTip("Cek service Llama dan ComfyUI yang sedang hidup.")
        status_button.setStatusTip(status_button.toolTip())
        status_button.clicked.connect(self.check_runtime_status)
        layout.addWidget(status_button)
        self.runtime_status_button = status_button
        self._apply_runtime_status_colors(None)
        return frame

    def manual_runtime_switch(self, target: str):
        target = str(target or "").strip().lower()
        if target not in {"llama", "comfyui"}:
            return
        if self.runtime_task_thread is not None and self.runtime_task_thread.isRunning():
            self.statusBar().showMessage("Operasi runtime lain masih berjalan.", 4000)
            return
        for button in [*self.runtime_switch_buttons, self.runtime_status_button]:
            button.setEnabled(False)
        self.statusBar().showMessage(f"Switch ke {target} sedang berjalan...", 3000)
        started = self._start_runtime_task(
            lambda: self._manual_runtime_switch_task(target),
            lambda status: self._manual_runtime_switch_finished(target, status),
            lambda error: self._manual_runtime_switch_failed(target, error),
        )
        if not started:
            for button in [*self.runtime_switch_buttons, self.runtime_status_button]:
                button.setEnabled(True)

    @staticmethod
    def _manual_runtime_switch_task(target: str):
        controller = RuntimeServiceController.from_config()
        if target == "llama":
            controller.ensure_llama(reason="manual UI switch")
        else:
            controller.ensure_comfyui(reason="manual UI switch")
        return controller.status()

    def _manual_runtime_switch_finished(self, target: str, status: dict):
        self._apply_runtime_status_colors(status)
        for button in [*self.runtime_switch_buttons, self.runtime_status_button]:
            button.setEnabled(True)
        self.statusBar().showMessage(f"{target} aktif dan service lainnya mati.", 5000)

    def _manual_runtime_switch_failed(self, target: str, error: str):
        for button in [*self.runtime_switch_buttons, self.runtime_status_button]:
            button.setEnabled(True)
        self.append_log(f"[runtime] Manual switch ke {target} gagal: {error}")
        self.statusBar().showMessage(f"Switch ke {target} gagal.", 5000)

    def check_runtime_status(self):
        if self.runtime_task_thread is not None and self.runtime_task_thread.isRunning():
            self.statusBar().showMessage("Operasi runtime lain masih berjalan.", 4000)
            return
        for button in [*self.runtime_switch_buttons, self.runtime_status_button]:
            button.setEnabled(False)
        self.statusBar().showMessage("Memeriksa status service...", 3000)
        started = self._start_runtime_task(
            lambda: RuntimeServiceController.from_config().status(),
            self._runtime_status_checked,
            self._runtime_status_check_failed,
        )
        if not started:
            for button in [*self.runtime_switch_buttons, self.runtime_status_button]:
                button.setEnabled(True)

    def _runtime_status_checked(self, status: dict):
        self._apply_runtime_status_colors(status)
        for button in [*self.runtime_switch_buttons, self.runtime_status_button]:
            button.setEnabled(True)
        active = str(status.get("active", "none")) if isinstance(status, dict) else "none"
        self.statusBar().showMessage(f"Runtime aktif: {active}", 4000)

    def _runtime_status_check_failed(self, error: str):
        self._apply_runtime_status_colors(None)
        for button in [*self.runtime_switch_buttons, self.runtime_status_button]:
            button.setEnabled(True)
        self.append_log(f"[runtime] Gagal cek status service: {error}")
        self.statusBar().showMessage("Gagal memeriksa status service.", 5000)

    def _apply_runtime_status_colors(self, status: dict | None):
        services = status.get("services", {}) if isinstance(status, dict) else {}

        def is_healthy(service: str) -> bool:
            value = services.get(service, {}) if isinstance(services, dict) else {}
            return isinstance(value, dict) and bool(value.get("health"))

        llama_green = is_healthy("llama")
        comfyui_green = is_healthy("comfyui")
        if self.runtime_switch_buttons:
            self.runtime_switch_buttons[0].setStyleSheet(
                "QToolButton { background: #22c55e; color: white; font-weight: 700; }" if llama_green
                else "QToolButton { background: #9ca3af; color: white; font-weight: 700; }"
            )
            self.runtime_switch_buttons[1].setStyleSheet(
                "QToolButton { background: #22c55e; color: white; font-weight: 700; }" if comfyui_green
                else "QToolButton { background: #9ca3af; color: white; font-weight: 700; }"
            )
        if self.runtime_status_button is not None:
            self.runtime_status_button.setStyleSheet(
                "QToolButton { background: #2563eb; color: white; font-weight: 700; }"
            )

    def append_log(self, text: str):
        self.log_output.appendPlainText(text.rstrip())

    def ensure_process_dialog(self):
        if self.process_dialog is None:
            self.process_dialog = ProcessDialog(self.log_output, self)
        return self.process_dialog

    def toggle_process_dialog(self):
        dialog = self.ensure_process_dialog()
        if dialog.isVisible():
            dialog.hide()
        else:
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

    def comfyui_server_address(self):
        value = ""
        if isinstance(self.project_settings, dict):
            value = str(self.project_settings.get("comfyui_server", "")).strip()
        if not value:
            value = str(DEFAULT_PROJECT_SETTINGS.get("comfyui_server", "nextgenserver:8188")).strip()
        return value

    def initialize_lora_options_once(self):
        if self._lora_options_initialized:
            return
        server = self.comfyui_server_address()
        normalized_server = _normalize_server_url(server)
        self._lora_options_initialized = True
        self._lora_options_server = normalized_server
        if not normalized_server:
            QMessageBox.critical(
                self,
                "Gagal Memuat Daftar LoRa",
                "Konfigurasi ComfyUI Server tidak valid, sehingga daftar LoRa tidak bisa dimuat saat UI dijalankan.",
            )
            return
        self._start_runtime_task(
            lambda: self._fetch_startup_lora_options(normalized_server),
            lambda options: self._on_startup_lora_options_loaded(normalized_server, options),
            lambda error: self._on_startup_lora_options_failed(normalized_server, error),
        )

    @staticmethod
    def _fetch_startup_lora_options(normalized_server: str):
        ensure_comfyui(reason="UI startup LoRA options", restore_on_exit=False)
        response = requests.get(f"{normalized_server}/object_info", timeout=10)
        response.raise_for_status()
        payload = response.json() if response.content else {}
        return _extract_lora_options_from_object_info(payload)

    def _on_startup_lora_options_loaded(self, normalized_server: str, options):
        _COMFYUI_LORA_OPTIONS_CACHE[normalized_server] = list(options or [])
        self.append_log(f"[runtime] Daftar LoRA startup selesai: {len(options or [])} opsi")
        if self.current_scene_dir is not None:
            self._refresh_minimax_h3_lora_options(
                self.minimax_h3_t2v_lora_name_input.currentText().strip(),
                preserve_missing=True,
            )

    def _on_startup_lora_options_failed(self, normalized_server: str, error: str):
        _COMFYUI_LORA_OPTIONS_CACHE[normalized_server] = []
        QMessageBox.critical(
            self,
            "Gagal Memuat Daftar LoRa",
            f"Daftar LoRa gagal dimuat secara async.\n\nServer: {normalized_server}\nError: {error}",
        )

    def _start_runtime_task(self, task, on_finished, on_failed):
        if self.runtime_task_thread is not None and self.runtime_task_thread.isRunning():
            self.append_log("[runtime] Operasi runtime async masih berjalan; permintaan baru diabaikan.")
            return False
        thread = QThread(self)
        worker = RuntimeTaskWorker(task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_finished)
        worker.failed.connect(on_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._runtime_task_finished)
        self.runtime_task_thread = thread
        self.runtime_task_worker = worker
        thread.start()
        return True

    def _runtime_task_finished(self):
        self.runtime_task_thread = None
        self.runtime_task_worker = None

    def release_media_locks(self):
        self.video_player.stop()
        self.video_player.setSource(QUrl())
        self.audio_player.stop()
        self.audio_player.setSource(QUrl())

    def clear_viewer(self):
        self.release_media_locks()
        self.viewer_stack.setCurrentWidget(self.image_preview)
        self.image_preview.clear_preview("Klik ganda file pada tab Aset untuk melihat media.")
        self.video_preview.clear_preview("Klik ganda file video pada tab Aset untuk melihat media.")
        self.audio_preview.clear_preview()
        self.viewer_title_label.setText("Tampilan")
        self.viewer_info_label.setText("Klik ganda file pada tab Aset untuk melihat media.")

    def open_preview_in_default_app(self, preview_widget):
        asset_path = getattr(preview_widget, "source_path", lambda: None)()
        if not asset_path:
            return
        asset_path = Path(asset_path)
        if not asset_path.exists():
            QMessageBox.information(self, "File Tidak Ditemukan", f"File tidak ditemukan:\n{asset_path}")
            return
        if asset_path.suffix.lower() not in (IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS):
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(asset_path)))

    def open_asset_preview_only(self, asset_path: Path):
        suffix = asset_path.suffix.lower()
        if suffix in IMAGE_EXTS:
            pixmap = QPixmap(str(asset_path))
            if pixmap.isNull():
                self.clear_viewer()
                self.viewer_info_label.setText(f"Gagal memuat gambar: {asset_path.name}")
                return
            self.release_media_locks()
            self.image_preview.clear_preview()
            self.image_preview.set_source_path(asset_path)
            self.image_preview.set_preview_pixmap(pixmap)
            self.viewer_stack.setCurrentWidget(self.image_preview)
            self.viewer_title_label.setText("Tampilan")
            self.viewer_info_label.setText(asset_path.name)
            return
        if suffix in VIDEO_EXTS:
            self.release_media_locks()
            self.video_preview.clear_preview("Memuat video...")
            self.video_preview.set_source_path(asset_path)
            self.video_player.setSource(QUrl.fromLocalFile(str(asset_path)))
            self.viewer_stack.setCurrentWidget(self.video_preview)
            self.viewer_title_label.setText("Tampilan")
            self.viewer_info_label.setText(asset_path.name)
            self.video_player.play()
            QTimer.singleShot(0, self.video_player.pause)
            return
        if suffix in AUDIO_EXTS:
            self.release_media_locks()
            self.audio_preview.clear_preview()
            self.audio_preview.set_source_path(asset_path)
            self.audio_preview.set_preview_pixmap(self.style().standardIcon(QStyle.SP_MediaVolume).pixmap(128, 128))
            self.viewer_stack.setCurrentWidget(self.audio_preview)
            self.viewer_title_label.setText("Tampilan")
            self.viewer_info_label.setText(asset_path.name)
            return
        self.clear_viewer()

    def update_lora_fields_enabled(self):
        enabled = self.z_use_lora_input.isChecked()
        self.z_lora_name_input.setEnabled(enabled)
        self.z_lora_strength_input.setEnabled(enabled)

    def _refresh_image_lora_options(
        self,
        model_key: str | None = None,
        current_value: str = "",
        *,
        preserve_missing: bool = False,
    ):
        model_key = str(model_key or self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO).strip()
        server = self.comfyui_server_address()
        if model_key == MODEL_GEMINI_IMAGE:
            populate_lora_combo(
                self.z_lora_name_input,
                [],
                current_value=current_value,
                template_default="",
                preserve_missing=preserve_missing,
            )
            self.z_lora_name_input.setEnabled(False)
            return
        if model_key == MODEL_FLUX2_K9:
            options = get_lora_options_by_prefix(server, LORA_PREFIX_FLUX2_K9)
        elif model_key == MODEL_FLUX2:
            options = get_lora_options_by_prefix(server, LORA_PREFIX_FLUX2)
        else:
            options = get_lora_options_by_prefix(server, LORA_PREFIX_Z_IMAGE)
        populate_lora_combo(
            self.z_lora_name_input,
            options,
            current_value=current_value,
            preserve_missing=preserve_missing,
        )

    def _refresh_wan_lora_options(self, current_values: dict[str, str] | None = None, *, preserve_missing: bool = False):
        current_values = current_values or {}
        server = self.comfyui_server_address()
        high_options = get_lora_options_by_prefix(server, LORA_PREFIX_WAN_HIGH)
        low_options = get_lora_options_by_prefix(server, LORA_PREFIX_WAN_LOW)
        populate_lora_combo(
            self.wan_lora_high_name_input,
            high_options,
            current_value=current_values.get("lora_high_name", ""),
            template_default=DEFAULT_WAN_PROMPT["lora_high_name"],
            preserve_missing=preserve_missing,
        )
        populate_lora_combo(
            self.wan_lora_low_name_input,
            low_options,
            current_value=current_values.get("lora_low_name", ""),
            template_default=DEFAULT_WAN_PROMPT["lora_low_name"],
            preserve_missing=preserve_missing,
        )
        populate_lora_combo(
            self.wan_lora_high2_name_input,
            high_options,
            current_value=current_values.get("lora_high_name_2", ""),
            template_default=DEFAULT_WAN_PROMPT["lora_high_name_2"],
            preserve_missing=preserve_missing,
        )
        populate_lora_combo(
            self.wan_lora_low2_name_input,
            low_options,
            current_value=current_values.get("lora_low_name_2", ""),
            template_default=DEFAULT_WAN_PROMPT["lora_low_name_2"],
            preserve_missing=preserve_missing,
        )
        populate_lora_combo(
            self.wan_t2v_lora_high_name_input,
            high_options,
            current_value=current_values.get("t2v_lora_high_name", ""),
            template_default=DEFAULT_WAN22_T2V_PROMPT["lora_high_name"],
            preserve_missing=preserve_missing,
        )
        populate_lora_combo(
            self.wan_t2v_lora_low_name_input,
            low_options,
            current_value=current_values.get("t2v_lora_low_name", ""),
            template_default=DEFAULT_WAN22_T2V_PROMPT["lora_low_name"],
            preserve_missing=preserve_missing,
        )
        populate_lora_combo(
            self.wan_t2v_lora_high2_name_input,
            high_options,
            current_value=current_values.get("t2v_lora_high_name_2", ""),
            template_default=DEFAULT_WAN22_T2V_PROMPT["lora_high_name_2"],
            preserve_missing=preserve_missing,
        )
        populate_lora_combo(
            self.wan_t2v_lora_low2_name_input,
            low_options,
            current_value=current_values.get("t2v_lora_low_name_2", ""),
            template_default=DEFAULT_WAN22_T2V_PROMPT["lora_low_name_2"],
            preserve_missing=preserve_missing,
        )

    def _refresh_minimax_h3_lora_options(
        self,
        current_value: str = "",
        *,
        current_value_2: str | None = None,
        i2v_current_value: str | None = None,
        i2v_current_value_2: str | None = None,
        s2v_current_value: str | None = None,
        s2v_current_value_2: str | None = None,
        r2v_current_value: str | None = None,
        r2v_current_value_2: str | None = None,
        preserve_missing: bool = False,
    ):
        options = get_lora_options_by_prefix(
            self.comfyui_server_address(),
            LORA_PREFIX_MINIMAX_H3,
        )
        selected = populate_lora_combo(
            self.minimax_h3_t2v_lora_name_input,
            options,
            current_value=current_value,
            template_default=DEFAULT_MINIMAX_H3_T2V_PROMPT["lora_name"],
            preserve_missing=preserve_missing,
        )
        populate_lora_combo(
            self.minimax_h3_t2v_lora_name_2_input,
            options,
            current_value=(
                self.minimax_h3_t2v_lora_name_2_input.currentText().strip()
                if current_value_2 is None
                else str(current_value_2 or "").strip()
            ),
            template_default=DEFAULT_MINIMAX_H3_T2V_PROMPT["lora_name_2"],
            preserve_missing=preserve_missing,
        )
        populate_lora_combo(
            self.minimax_h3_i2v_lora_name_input,
            options,
            current_value=(
                self.minimax_h3_i2v_lora_name_input.currentText().strip()
                if i2v_current_value is None
                else str(i2v_current_value or "").strip()
            ),
            template_default=DEFAULT_MINIMAX_H3_I2V_PROMPT["lora_name"],
            preserve_missing=preserve_missing,
        )
        populate_lora_combo(
            self.minimax_h3_i2v_lora_name_2_input,
            options,
            current_value=(
                self.minimax_h3_i2v_lora_name_2_input.currentText().strip()
                if i2v_current_value_2 is None
                else str(i2v_current_value_2 or "").strip()
            ),
            template_default=DEFAULT_MINIMAX_H3_I2V_PROMPT["lora_name_2"],
            preserve_missing=preserve_missing,
        )
        for combo, value, default in (
            (self.minimax_h3_s2v_lora_name_input, s2v_current_value, DEFAULT_MINIMAX_H3_S2V_PROMPT["lora_name"]),
            (self.minimax_h3_s2v_lora_name_2_input, s2v_current_value_2, DEFAULT_MINIMAX_H3_S2V_PROMPT["lora_name_2"]),
            (self.minimax_h3_r2v_lora_name_input, r2v_current_value, DEFAULT_MINIMAX_H3_R2V_PROMPT["lora_name"]),
            (self.minimax_h3_r2v_lora_name_2_input, r2v_current_value_2, DEFAULT_MINIMAX_H3_R2V_PROMPT["lora_name_2"]),
        ):
            populate_lora_combo(
                combo,
                options,
                current_value=combo.currentText().strip() if value is None else str(value or "").strip(),
                template_default=default,
                preserve_missing=preserve_missing,
            )
        return selected

    def update_seed_fields_enabled(self):
        self.z_seed_input.setEnabled(not self.z_use_random_seed_input.isChecked())

    def update_image_model_fields_enabled(self):
        model_key = str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO)
        is_gemini = model_key == MODEL_GEMINI_IMAGE
        can_use_negative = z_image_supports_negative_prompt({"image_model": model_key})
        self.z_gemini_model_input.setVisible(is_gemini)
        if self.z_tab is not None:
            layout = self.z_tab.layout()
            if isinstance(layout, QFormLayout):
                label = layout.labelForField(self.z_gemini_model_input)
                if label is not None:
                    label.setVisible(is_gemini)
        self.z_negative_input.setEnabled(can_use_negative)
        if not can_use_negative:
            self.z_negative_input.setPlainText("")
        for negative_input in self.z_extra_negative_inputs:
            negative_input.setEnabled(can_use_negative)
            if not can_use_negative:
                negative_input.setPlainText("")
        self.z_use_lora_input.setEnabled(not is_gemini)
        if is_gemini and self.z_use_lora_input.isChecked():
            self.z_use_lora_input.setChecked(False)
        self.z_use_random_seed_input.setEnabled(not is_gemini)
        if is_gemini:
            self.z_use_random_seed_input.setChecked(True)
            self.z_seed_input.setText("1")
        self._refresh_image_lora_options(
            model_key,
            self.z_lora_name_input.currentText().strip(),
            preserve_missing=bool(self.loading_scene),
        )
        self.update_seed_fields_enabled()
        self.update_lora_fields_enabled()

    def update_wan_lora_fields_enabled(self):
        for widget in [
            self.wan_lora_high_name_input,
            self.wan_lora_high_strength_input,
            self.wan_lora_low_name_input,
            self.wan_lora_low_strength_input,
            self.wan_lora_high2_name_input,
            self.wan_lora_high2_strength_input,
            self.wan_lora_low2_name_input,
            self.wan_lora_low2_strength_input,
        ]:
            widget.setEnabled(True)

    def _set_form_field_visible(self, form_layout, widget, visible: bool):
        widget.setVisible(visible)
        if isinstance(form_layout, QFormLayout):
            label = form_layout.labelForField(widget)
            if label is not None:
                label.setVisible(visible)

    def update_image_edit_model_fields_enabled(self):
        model_key = str(self.image_edit_model_input.currentData() or MODEL_FLUX2)
        is_gemini = model_key == MODEL_GEMINI_IMAGE
        self.image_edit_model_input.setEnabled(False)
        self.image_edit_gemini_model_input.setVisible(is_gemini)
        self.image_edit_gemini_model_input.setEnabled(False)
        if self.image_edit_tab is not None:
            layout = self.image_edit_tab.layout()
            if isinstance(layout, QVBoxLayout) and layout.count() > 0:
                form_item = layout.itemAt(0)
                form_layout = form_item.layout() if form_item else None
                if isinstance(form_layout, QFormLayout):
                    label = form_layout.labelForField(self.image_edit_gemini_model_input)
                    if label is not None:
                        label.setVisible(is_gemini)

    def open_asset_in_viewer(self, asset_path: Path):
        suffix = asset_path.suffix.lower()
        if suffix in IMAGE_EXTS:
            self.open_asset_preview_only(asset_path)
            return
        if suffix in VIDEO_EXTS:
            self.release_media_locks()
            self.video_preview.clear_preview("Memuat video...")
            self.video_preview.set_source_path(asset_path)
            self.video_player.setSource(QUrl.fromLocalFile(str(asset_path)))
            self.viewer_stack.setCurrentWidget(self.video_preview)
            self.viewer_title_label.setText("Tampilan")
            self.viewer_info_label.setText(asset_path.name)
            self.video_player.play()
            return
        if suffix in AUDIO_EXTS:
            self.release_media_locks()
            self.audio_preview.clear_preview()
            self.audio_preview.set_source_path(asset_path)
            self.audio_preview.set_preview_pixmap(self.style().standardIcon(QStyle.SP_MediaVolume).pixmap(128, 128))
            self.viewer_stack.setCurrentWidget(self.audio_preview)
            self.viewer_title_label.setText("Tampilan")
            self.viewer_info_label.setText(asset_path.name)
            self.audio_player.setSource(QUrl.fromLocalFile(str(asset_path)))
            self.audio_player.play()
            return
        self.clear_viewer()

    def on_video_frame_changed(self, frame):
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self.video_preview.set_preview_pixmap(QPixmap.fromImage(image))

    def item_scene_path(self, item):
        if item is None:
            return None
        try:
            value = item.data(Qt.UserRole)
        except RuntimeError:
            return None
        return Path(value) if value else None

    def reload_scene_list(self):
        if not self.ensure_project_selected(notify=False):
            self.scene_list.clear()
            self.current_scene_dir = None
            self.current_scene_view_dir = None
            self._refresh_variation_view_options(None)
            self._apply_scene_view_mode()
            return
        current_name = self.current_scene_dir.name if self.current_scene_dir else None
        was_loading = self.loading_scene
        self.loading_scene = True
        self.scene_list.clear()
        for scene_dir in self.list_scene_dirs_current():
            meta = load_json(scene_dir / "scene_meta.json", DEFAULT_SCENE_META)
            z_prompt = load_json(scene_dir / "z_image_prompt.json", DEFAULT_Z_IMAGE_PROMPT)
            wan_t2v_prompt = load_json(scene_dir / "wan22_t2v_prompt.json", DEFAULT_WAN22_T2V_PROMPT)
            wan_prompt = load_json(scene_dir / "wan22_i2v_prompt.json", DEFAULT_WAN_PROMPT)
            minimax_h3_t2v_prompt = load_json(
                scene_dir / "minimax_h3_t2v_prompt.json",
                DEFAULT_MINIMAX_H3_T2V_PROMPT,
            )
            minimax_h3_i2v_prompt = load_json(
                scene_dir / "minimax_h3_i2v_prompt.json",
                DEFAULT_MINIMAX_H3_I2V_PROMPT,
            )
            # Root scene list entries do not have a variation fallback scope.
            # Older projects may not contain the new R2V file, so use the
            # default payload without referencing an undefined fallback_dir.
            minimax_h3_r2v_prompt = load_json(
                scene_dir / MINIMAX_H3_R2V_PROMPT_FILENAME,
                DEFAULT_MINIMAX_H3_R2V_PROMPT,
            )
            scene_type = str(meta.get("scene_type", "wan22_i2v")).strip()
            s2v_prompt = load_json(scene_dir / s2v_prompt_filename(scene_type), s2v_prompt_default(scene_type))
            web_prompt = load_json(scene_dir / "web_scroll_prompt.json", DEFAULT_WEB_SCROLL_PROMPT)
            image_pan_prompt = load_json(scene_dir / "image_pan_prompt.json", DEFAULT_IMAGE_PAN_PROMPT)
            image_zoom_prompt = load_json(scene_dir / "image_zoom_prompt.json", DEFAULT_IMAGE_ZOOM_PROMPT)
            issues = validate_scene_data(
                meta,
                z_prompt,
                wan_t2v_prompt,
                wan_prompt,
                s2v_prompt,
                web_prompt,
                image_pan_prompt,
                image_zoom_prompt,
                scene_dir,
                minimax_h3_t2v_prompt,
                minimax_h3_i2v_prompt,
            )
            label = scene_dir.name if not issues else f"{scene_dir.name} ({len(issues)} masalah)"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, str(scene_dir))
            item.setToolTip("\n".join(issues) if issues else "Siap")
            self.scene_list.addItem(item)
            if scene_dir.name == current_name:
                self.scene_list.setCurrentItem(item)
        if self.scene_list.count() and self.scene_list.currentRow() < 0:
            self.scene_list.setCurrentRow(0)
        self.loading_scene = was_loading
        selected = self.current_scene_path_from_ui()
        self.current_scene_dir = selected
        self.current_scene_view_dir = selected
        self._refresh_variation_view_options(selected, selected_path=selected)
        self._apply_scene_view_mode()
        if selected and not self.loading_scene:
            self.load_scene(selected, root_scene_dir=selected)
        elif not selected:
            self.refresh_image_edit_source_options()

    def current_scene_path_from_ui(self):
        item = self.scene_list.currentItem()
        return self.item_scene_path(item)

    def on_scene_changed(self, current, previous):
        if self.loading_scene:
            return
        if previous and self.current_scene_dir and not self.is_viewing_variation():
            self.save_current_scene(silent=True, reload_list=False)
        self.release_media_locks()
        self.current_scene_dir = self.item_scene_path(current)
        if self.current_scene_dir:
            self._reset_variation_view_for_scene(self.current_scene_dir)
        else:
            self.current_scene_view_dir = None
            self._refresh_variation_view_options(None)
            self._apply_scene_view_mode()

    def on_scene_reordered(self):
        if self.loading_scene:
            return
        project_dir = self.project_dir()
        if project_dir is None:
            return
        self.release_media_locks()
        if self.current_scene_dir:
            self.save_current_scene(silent=True, reload_list=False)
        ordered_paths = [Path(self.scene_list.item(i).data(Qt.UserRole)) for i in range(self.scene_list.count())]
        if not ordered_paths:
            return
        temp_paths = []
        for idx, old_path in enumerate(ordered_paths, start=1):
            temp_path = project_dir / f"__reorder_tmp_{idx}"
            if temp_path.exists():
                shutil.rmtree(temp_path)
            old_path.rename(temp_path)
            temp_paths.append(temp_path)
        for idx, temp_path in enumerate(temp_paths, start=1):
            temp_path.rename(project_dir / scene_dir_name(idx))
        current_row = self.scene_list.currentRow()
        self.reload_scene_list()
        if 0 <= current_row < self.scene_list.count():
            self.scene_list.setCurrentRow(current_row)

    def load_scene(self, scene_dir: Path, root_scene_dir: Path | None = None):
        self.loading_scene = True
        preferred_tab = self.editor_tabs.currentWidget() if self.editor_tabs is not None else None
        try:
            root_scene_dir = root_scene_dir if root_scene_dir is not None else scene_dir
            fallback_dir = None if self._scene_paths_equal(scene_dir, root_scene_dir) else root_scene_dir
            meta = load_json_with_fallback(scene_dir / "scene_meta.json", (fallback_dir / "scene_meta.json") if fallback_dir else None, DEFAULT_SCENE_META)
            z_prompt = load_json(scene_dir / "z_image_prompt.json", DEFAULT_Z_IMAGE_PROMPT)
            wan_t2v_prompt = load_json(scene_dir / "wan22_t2v_prompt.json", DEFAULT_WAN22_T2V_PROMPT)
            wan_prompt = load_json(scene_dir / "wan22_i2v_prompt.json", DEFAULT_WAN_PROMPT)
            minimax_h3_t2v_prompt = load_json(
                scene_dir / "minimax_h3_t2v_prompt.json",
                DEFAULT_MINIMAX_H3_T2V_PROMPT,
            )
            minimax_h3_i2v_prompt = load_json(
                scene_dir / "minimax_h3_i2v_prompt.json",
                DEFAULT_MINIMAX_H3_I2V_PROMPT,
            )
            minimax_h3_r2v_prompt = load_json_with_fallback(
                scene_dir / MINIMAX_H3_R2V_PROMPT_FILENAME,
                (fallback_dir / MINIMAX_H3_R2V_PROMPT_FILENAME) if fallback_dir else None,
                DEFAULT_MINIMAX_H3_R2V_PROMPT,
            )
            scene_type = str(meta.get("scene_type", "wan22_i2v")).strip()
            s2v_filename = s2v_prompt_filename(scene_type)
            s2v_default = s2v_prompt_default(scene_type)
            s2v_prompt = load_json_with_fallback(scene_dir / s2v_filename, (fallback_dir / s2v_filename) if fallback_dir else None, s2v_default)
            web_prompt = load_json_with_fallback(scene_dir / "web_scroll_prompt.json", (fallback_dir / "web_scroll_prompt.json") if fallback_dir else None, DEFAULT_WEB_SCROLL_PROMPT)
            image_pan_prompt = load_json_with_fallback(scene_dir / "image_pan_prompt.json", (fallback_dir / "image_pan_prompt.json") if fallback_dir else None, DEFAULT_IMAGE_PAN_PROMPT)
            image_zoom_prompt = load_json_with_fallback(scene_dir / "image_zoom_prompt.json", (fallback_dir / "image_zoom_prompt.json") if fallback_dir else None, DEFAULT_IMAGE_ZOOM_PROMPT)
            web_search_prompt = load_json_with_fallback(scene_dir / "web_search_prompt.json", (fallback_dir / "web_search_prompt.json") if fallback_dir else None, DEFAULT_WEB_SEARCH_PROMPT)
            self.scene_title_input.setText(str(meta.get("scene_title", "")))
            self.scene_description_input.setPlainText(str(meta.get("scene_description", "")))
            self.scene_type_combo.blockSignals(True)
            try:
                self.scene_type_combo.setCurrentText(str(meta.get("scene_type", "wan22_i2v")))
            finally:
                self.scene_type_combo.blockSignals(False)
            self.update_scene_type_tabs()
            self.update_scene_type_specific_fields()
            duration_value = str(meta.get("duration_seconds", ""))
            if self._uses_decimal_duration_input():
                try:
                    self.duration_decimal_input.setText(f"{float(duration_value or 10.0):.1f}")
                except (TypeError, ValueError):
                    self.duration_decimal_input.setText("10.0")
            else:
                index = self.duration_input.findData(int(float(duration_value))) if duration_value else -1
                if index < 0:
                    index = self.duration_input.findText(duration_value)
                self.duration_input.setCurrentIndex(max(index, 0))
            voice_key = resolve_scene_voice_key(meta)
            index = self.scene_voice_character_input.findData(voice_key)
            self.scene_voice_character_input.setCurrentIndex(max(index, 0))
            self.voice_text_input.setPlainText(str(meta.get("voice_text", "")))
            self.sound_prompt_input.setPlainText(str(meta.get("sound_prompt", "")))
            self.sound_volume_input.setText(str(meta.get("sound_volume", "")))
            z_width = int(z_prompt.get("width", DEFAULT_Z_IMAGE_PROMPT["width"]))
            z_height = int(z_prompt.get("height", DEFAULT_Z_IMAGE_PROMPT["height"]))
            model_key = get_z_image_model_key(z_prompt)
            index = self.z_model_input.findData(model_key)
            self.z_model_input.setCurrentIndex(max(index, 0))
            selected_gemini_model = str(z_prompt.get("gemini_model_id", MODEL_GEMINI_FLASH_05K)).strip()
            index = self.z_gemini_model_input.findData(selected_gemini_model)
            if index < 0 and selected_gemini_model:
                self.z_gemini_model_input.addItem(selected_gemini_model, selected_gemini_model)
                index = self.z_gemini_model_input.findData(selected_gemini_model)
            self.z_gemini_model_input.setCurrentIndex(max(index, 0))
            index = -1
            for i in range(self.z_size_input.count()):
                size_value = self.z_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (z_width, z_height):
                    index = i
                    break
            self.z_size_input.setCurrentIndex(max(index, 0))
            self.z_use_random_seed_input.setChecked(bool(z_prompt.get("use_random_seed", True)))
            self.z_seed_input.setText(str(z_prompt.get("seed", 1)))
            self.z_use_lora_input.setChecked(bool(z_prompt.get("use_lora", False)))
            self._refresh_image_lora_options(model_key, str(z_prompt.get("lora_name", "")), preserve_missing=True)
            self.z_lora_strength_input.setText(str(z_prompt.get("strength_model", 1.0)))
            self.update_image_model_fields_enabled()
            self.update_seed_fields_enabled()
            self.update_lora_fields_enabled()
            self.z_lora_trigger_words_input.setText(str(z_prompt.get(LORA_TRIGGER_WORDS_FIELD, "")))
            self.z_positive_input.setPlainText(str(z_prompt.get("positive_prompt", "")))
            self.z_negative_input.setPlainText(str(z_prompt.get("negative_prompt", "")))
            wan_t2v_width = int(wan_t2v_prompt.get("width", DEFAULT_WAN22_T2V_PROMPT["width"]))
            wan_t2v_height = int(wan_t2v_prompt.get("height", DEFAULT_WAN22_T2V_PROMPT["height"]))
            index = -1
            for i in range(self.wan_t2v_size_input.count()):
                size_value = self.wan_t2v_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (wan_t2v_width, wan_t2v_height):
                    index = i
                    break
            self.wan_t2v_size_input.setCurrentIndex(max(index, 0))
            self._refresh_wan_lora_options(
                {
                    "t2v_lora_high_name": str(wan_t2v_prompt.get("lora_high_name", DEFAULT_WAN22_T2V_PROMPT["lora_high_name"])),
                    "t2v_lora_low_name": str(wan_t2v_prompt.get("lora_low_name", DEFAULT_WAN22_T2V_PROMPT["lora_low_name"])),
                    "t2v_lora_high_name_2": str(wan_t2v_prompt.get("lora_high_name_2", DEFAULT_WAN22_T2V_PROMPT["lora_high_name_2"])),
                    "t2v_lora_low_name_2": str(wan_t2v_prompt.get("lora_low_name_2", DEFAULT_WAN22_T2V_PROMPT["lora_low_name_2"])),
                    "lora_high_name": str(wan_prompt.get("lora_high_name", DEFAULT_WAN_PROMPT["lora_high_name"])),
                    "lora_low_name": str(wan_prompt.get("lora_low_name", DEFAULT_WAN_PROMPT["lora_low_name"])),
                    "lora_high_name_2": str(wan_prompt.get("lora_high_name_2", DEFAULT_WAN_PROMPT["lora_high_name_2"])),
                    "lora_low_name_2": str(wan_prompt.get("lora_low_name_2", DEFAULT_WAN_PROMPT["lora_low_name_2"])),
                },
                preserve_missing=True,
            )
            self.wan_t2v_lora_high_strength_input.setText(str(wan_t2v_prompt.get("lora_high_strength", DEFAULT_WAN22_T2V_PROMPT["lora_high_strength"])))
            self.wan_t2v_lora_low_strength_input.setText(str(wan_t2v_prompt.get("lora_low_strength", DEFAULT_WAN22_T2V_PROMPT["lora_low_strength"])))
            self.wan_t2v_lora_high2_strength_input.setText(str(wan_t2v_prompt.get("lora_high_strength_2", DEFAULT_WAN22_T2V_PROMPT["lora_high_strength_2"])))
            self.wan_t2v_lora_low2_strength_input.setText(str(wan_t2v_prompt.get("lora_low_strength_2", DEFAULT_WAN22_T2V_PROMPT["lora_low_strength_2"])))
            self.wan_t2v_lora_trigger_words_input.setText(str(wan_t2v_prompt.get(LORA_TRIGGER_WORDS_FIELD, "")))
            self.wan_t2v_positive_input.setPlainText(str(wan_t2v_prompt.get("positive_prompt", "")))
            self.wan_t2v_negative_input.setPlainText(str(wan_t2v_prompt.get("negative_prompt", "")))
            wan_width = int(wan_prompt.get("width", DEFAULT_WAN_PROMPT["width"]))
            wan_height = int(wan_prompt.get("height", DEFAULT_WAN_PROMPT["height"]))
            index = -1
            for i in range(self.wan_size_input.count()):
                size_value = self.wan_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (wan_width, wan_height):
                    index = i
                    break
            self.wan_size_input.setCurrentIndex(max(index, 0))
            self.wan_lora_high_strength_input.setText(str(wan_prompt.get("lora_high_strength", DEFAULT_WAN_PROMPT["lora_high_strength"])))
            self.wan_lora_low_strength_input.setText(str(wan_prompt.get("lora_low_strength", DEFAULT_WAN_PROMPT["lora_low_strength"])))
            self.wan_lora_high2_strength_input.setText(str(wan_prompt.get("lora_high_strength_2", DEFAULT_WAN_PROMPT["lora_high_strength_2"])))
            self.wan_lora_low2_strength_input.setText(str(wan_prompt.get("lora_low_strength_2", DEFAULT_WAN_PROMPT["lora_low_strength_2"])))
            self.wan_lora_trigger_words_input.setText(str(wan_prompt.get(LORA_TRIGGER_WORDS_FIELD, "")))
            self.update_wan_lora_fields_enabled()
            for key, widget in self.wan_prompt_inputs.items():
                widget.setPlainText(str(wan_prompt.get(key, "")))
            minimax_t2v_width = int(minimax_h3_t2v_prompt.get("width", DEFAULT_MINIMAX_H3_T2V_PROMPT["width"]))
            minimax_t2v_height = int(minimax_h3_t2v_prompt.get("height", DEFAULT_MINIMAX_H3_T2V_PROMPT["height"]))
            minimax_t2v_index = self.minimax_h3_t2v_size_input.findData((minimax_t2v_width, minimax_t2v_height))
            self.minimax_h3_t2v_size_input.setCurrentIndex(max(minimax_t2v_index, 0))
            minimax_t2v_fps = int(minimax_h3_t2v_prompt.get("fps", MINIMAX_H3_DEFAULT_FPS))
            minimax_t2v_fps_index = self.minimax_h3_t2v_fps_input.findData(minimax_t2v_fps)
            self.minimax_h3_t2v_fps_input.setCurrentIndex(
                minimax_t2v_fps_index if minimax_t2v_fps_index >= 0 else self.minimax_h3_t2v_fps_input.findData(MINIMAX_H3_DEFAULT_FPS)
            )
            minimax_i2v_width = int(minimax_h3_i2v_prompt.get("width", DEFAULT_MINIMAX_H3_I2V_PROMPT["width"]))
            minimax_i2v_height = int(minimax_h3_i2v_prompt.get("height", DEFAULT_MINIMAX_H3_I2V_PROMPT["height"]))
            minimax_i2v_index = self.minimax_h3_i2v_size_input.findData((minimax_i2v_width, minimax_i2v_height))
            self.minimax_h3_i2v_size_input.setCurrentIndex(max(minimax_i2v_index, 0))
            minimax_i2v_fps = int(minimax_h3_i2v_prompt.get("fps", MINIMAX_H3_DEFAULT_FPS))
            minimax_i2v_fps_index = self.minimax_h3_i2v_fps_input.findData(minimax_i2v_fps)
            self.minimax_h3_i2v_fps_input.setCurrentIndex(
                minimax_i2v_fps_index if minimax_i2v_fps_index >= 0 else self.minimax_h3_i2v_fps_input.findData(MINIMAX_H3_DEFAULT_FPS)
            )
            minimax_t2v_lora_name = str(
                minimax_h3_t2v_prompt.get(
                    "lora_name",
                    DEFAULT_MINIMAX_H3_T2V_PROMPT["lora_name"],
                )
            ).strip()
            minimax_i2v_lora_name = str(
                minimax_h3_i2v_prompt.get(
                    "lora_name",
                    DEFAULT_MINIMAX_H3_I2V_PROMPT["lora_name"],
                )
            ).strip()
            minimax_t2v_lora_name_2 = str(
                minimax_h3_t2v_prompt.get(
                    "lora_name_2",
                    DEFAULT_MINIMAX_H3_T2V_PROMPT["lora_name_2"],
                )
            ).strip()
            minimax_i2v_lora_name_2 = str(
                minimax_h3_i2v_prompt.get(
                    "lora_name_2",
                    DEFAULT_MINIMAX_H3_I2V_PROMPT["lora_name_2"],
                )
            ).strip()
            s2v_lora_name = str(s2v_prompt.get("lora_name", DEFAULT_MINIMAX_H3_S2V_PROMPT["lora_name"])).strip()
            s2v_lora_name_2 = str(s2v_prompt.get("lora_name_2", DEFAULT_MINIMAX_H3_S2V_PROMPT["lora_name_2"])).strip()
            r2v_lora_name = str(minimax_h3_r2v_prompt.get("lora_name", DEFAULT_MINIMAX_H3_R2V_PROMPT["lora_name"])).strip()
            r2v_lora_name_2 = str(minimax_h3_r2v_prompt.get("lora_name_2", DEFAULT_MINIMAX_H3_R2V_PROMPT["lora_name_2"])).strip()
            self._refresh_minimax_h3_lora_options(
                minimax_t2v_lora_name,
                current_value_2=minimax_t2v_lora_name_2,
                i2v_current_value=minimax_i2v_lora_name,
                i2v_current_value_2=minimax_i2v_lora_name_2,
                s2v_current_value=s2v_lora_name,
                s2v_current_value_2=s2v_lora_name_2,
                r2v_current_value=r2v_lora_name,
                r2v_current_value_2=r2v_lora_name_2,
                preserve_missing=True,
            )
            minimax_t2v_lora_strength = minimax_h3_t2v_prompt.get(
                "lora_strength",
                DEFAULT_MINIMAX_H3_T2V_PROMPT["lora_strength"],
            )
            minimax_i2v_lora_strength = minimax_h3_i2v_prompt.get(
                "lora_strength",
                DEFAULT_MINIMAX_H3_I2V_PROMPT["lora_strength"],
            )
            minimax_t2v_lora_strength_2 = minimax_h3_t2v_prompt.get(
                "lora_strength_2",
                DEFAULT_MINIMAX_H3_T2V_PROMPT["lora_strength_2"],
            )
            minimax_i2v_lora_strength_2 = minimax_h3_i2v_prompt.get(
                "lora_strength_2",
                DEFAULT_MINIMAX_H3_I2V_PROMPT["lora_strength_2"],
            )
            self.minimax_h3_t2v_lora_strength_input.setText(str(minimax_t2v_lora_strength))
            self.minimax_h3_i2v_lora_strength_input.setText(str(minimax_i2v_lora_strength))
            self.minimax_h3_t2v_lora_strength_2_input.setText(str(minimax_t2v_lora_strength_2))
            self.minimax_h3_i2v_lora_strength_2_input.setText(str(minimax_i2v_lora_strength_2))
            self.minimax_h3_s2v_lora_strength_input.setText(str(s2v_prompt.get("lora_strength", DEFAULT_MINIMAX_H3_S2V_PROMPT["lora_strength"])))
            self.minimax_h3_s2v_lora_strength_2_input.setText(str(s2v_prompt.get("lora_strength_2", DEFAULT_MINIMAX_H3_S2V_PROMPT["lora_strength_2"])))
            self.minimax_h3_r2v_lora_strength_input.setText(str(minimax_h3_r2v_prompt.get("lora_strength", DEFAULT_MINIMAX_H3_R2V_PROMPT["lora_strength"])))
            self.minimax_h3_r2v_lora_strength_2_input.setText(str(minimax_h3_r2v_prompt.get("lora_strength_2", DEFAULT_MINIMAX_H3_R2V_PROMPT["lora_strength_2"])))
            self.minimax_h3_t2v_remove_sound_input.setChecked(
                bool(minimax_h3_t2v_prompt.get("remove_sound", False))
            )
            self.minimax_h3_i2v_remove_sound_input.setChecked(
                bool(minimax_h3_i2v_prompt.get("remove_sound", False))
            )
            minimax_t2v_entry = normalize_minimax_prompt_payload(minimax_h3_t2v_prompt, "T2VA").get(
                "positive_prompt", ""
            )
            minimax_i2v_entry = normalize_minimax_prompt_payload(minimax_h3_i2v_prompt, "I2VA").get(
                "positive_prompt", ""
            )
            minimax_t2v_id_new = minimax_t2v_entry.get("id_new", "") if isinstance(minimax_t2v_entry, dict) else minimax_t2v_entry
            minimax_i2v_id_new = minimax_i2v_entry.get("id_new", "") if isinstance(minimax_i2v_entry, dict) else minimax_i2v_entry
            self.minimax_h3_t2v_positive_input.setPlainText(
                json.dumps(minimax_t2v_id_new, ensure_ascii=False, indent=2)
                if isinstance(minimax_t2v_id_new, dict) else str(minimax_t2v_id_new)
            )
            self.minimax_h3_i2v_positive_input.setPlainText(
                json.dumps(minimax_i2v_id_new, ensure_ascii=False, indent=2)
                if isinstance(minimax_i2v_id_new, dict) else str(minimax_i2v_id_new)
            )
            s2v_width = int(s2v_prompt.get("width", DEFAULT_WAN22_S2V_PROMPT["width"]))
            s2v_height = int(s2v_prompt.get("height", DEFAULT_WAN22_S2V_PROMPT["height"]))
            index = -1
            for i in range(self.s2v_size_input.count()):
                size_value = self.s2v_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (s2v_width, s2v_height):
                    index = i
                    break
            self.s2v_size_input.setCurrentIndex(max(index, 0))
            s2v_fps = int(s2v_prompt.get("fps", MINIMAX_H3_DEFAULT_FPS))
            s2v_fps_index = self.minimax_h3_s2v_fps_input.findData(s2v_fps)
            self.minimax_h3_s2v_fps_input.setCurrentIndex(
                s2v_fps_index
                if s2v_fps_index >= 0
                else self.minimax_h3_s2v_fps_input.findData(MINIMAX_H3_DEFAULT_FPS)
            )
            self.s2v_cfg_input.setValue(float(s2v_prompt.get("cfg", DEFAULT_WAN22_S2V_PROMPT["cfg"])))
            self.s2v_positive_input.setPlainText(
                json.dumps(
                    s2v_prompt.get("positive_prompt", {}).get("id_new", {})
                    if isinstance(s2v_prompt.get("positive_prompt"), dict)
                    and isinstance(s2v_prompt.get("positive_prompt", {}).get("id_new"), dict)
                    else s2v_prompt.get("positive_prompt", s2v_prompt_default(scene_type)["positive_prompt"]),
                    ensure_ascii=False,
                    indent=2,
                ) if scene_type == MINIMAX_H3_S2V_SCENE_TYPE else _prompt_text_for_validation(
                    s2v_prompt.get("positive_prompt", s2v_prompt_default(scene_type)["positive_prompt"])
                )
            )
            self.s2v_negative_input.setPlainText(str(s2v_prompt.get("negative_prompt", DEFAULT_WAN22_S2V_PROMPT["negative_prompt"])))
            r2v_width = int(minimax_h3_r2v_prompt.get("width", DEFAULT_MINIMAX_H3_R2V_PROMPT["width"]))
            r2v_height = int(minimax_h3_r2v_prompt.get("height", DEFAULT_MINIMAX_H3_R2V_PROMPT["height"]))
            r2v_index = self.minimax_h3_r2v_size_input.findData((r2v_width, r2v_height))
            self.minimax_h3_r2v_size_input.setCurrentIndex(max(r2v_index, 0))
            r2v_fps = int(minimax_h3_r2v_prompt.get("fps", MINIMAX_H3_DEFAULT_FPS))
            r2v_fps_index = self.minimax_h3_r2v_fps_input.findData(r2v_fps)
            self.minimax_h3_r2v_fps_input.setCurrentIndex(
                r2v_fps_index if r2v_fps_index >= 0 else self.minimax_h3_r2v_fps_input.findData(MINIMAX_H3_DEFAULT_FPS)
            )
            r2v_entry = minimax_h3_r2v_prompt.get("positive_prompt", {})
            r2v_id_new = r2v_entry.get("id_new", {}) if isinstance(r2v_entry, dict) else {}
            self.minimax_h3_r2v_positive_input.setPlainText(
                json.dumps(r2v_id_new, ensure_ascii=False, indent=2) if isinstance(r2v_id_new, dict) else str(r2v_id_new)
            )
            references = minimax_h3_r2v_prompt.get("references", {})
            if not isinstance(references, dict):
                references = {}
            self.refresh_r2v_reference_options({
                "images": references.get("images", []),
                "video": references.get("video", ""),
                "audios": references.get("audios", []),
            })
            self.web_url_input.setText(str(web_prompt.get("url", DEFAULT_WEB_SCROLL_PROMPT["url"])))
            try:
                web_width = int(web_prompt.get("width", DEFAULT_WEB_SCROLL_PROMPT["width"]))
            except (TypeError, ValueError):
                web_width = int(DEFAULT_WEB_SCROLL_PROMPT["width"])
            try:
                web_height = int(web_prompt.get("height", DEFAULT_WEB_SCROLL_PROMPT["height"]))
            except (TypeError, ValueError):
                web_height = int(DEFAULT_WEB_SCROLL_PROMPT["height"])
            index = -1
            for i in range(self.web_size_input.count()):
                size_value = self.web_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (web_width, web_height):
                    index = i
                    break
            self.web_size_input.setCurrentIndex(max(index, 0))
            try:
                web_duration = float(web_prompt.get("duration_seconds", DEFAULT_WEB_SCROLL_PROMPT["duration_seconds"]))
            except (TypeError, ValueError):
                web_duration = float(DEFAULT_WEB_SCROLL_PROMPT["duration_seconds"])
            try:
                web_speed = int(web_prompt.get("speed", DEFAULT_WEB_SCROLL_PROMPT["speed"]))
            except (TypeError, ValueError):
                web_speed = int(DEFAULT_WEB_SCROLL_PROMPT["speed"])
            web_duration = round(max(0.0, min(20.0, web_duration)), 1)
            self.web_duration_input.setValue(web_duration)
            self.web_speed_input.setValue(max(1, min(5, web_speed)))
            try:
                pan_width = int(image_pan_prompt.get("width", DEFAULT_IMAGE_PAN_PROMPT["width"]))
            except (TypeError, ValueError):
                pan_width = int(DEFAULT_IMAGE_PAN_PROMPT["width"])
            try:
                pan_height = int(image_pan_prompt.get("height", DEFAULT_IMAGE_PAN_PROMPT["height"]))
            except (TypeError, ValueError):
                pan_height = int(DEFAULT_IMAGE_PAN_PROMPT["height"])
            index = -1
            for i in range(self.image_pan_size_input.count()):
                size_value = self.image_pan_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (pan_width, pan_height):
                    index = i
                    break
            self.image_pan_size_input.setCurrentIndex(max(index, 0))
            pan_direction = str(image_pan_prompt.get("direction", DEFAULT_IMAGE_PAN_PROMPT["direction"])).strip()
            index = self.image_pan_direction_input.findData(pan_direction)
            self.image_pan_direction_input.setCurrentIndex(max(index, 0))
            try:
                zoom_width = int(image_zoom_prompt.get("width", DEFAULT_IMAGE_ZOOM_PROMPT["width"]))
            except (TypeError, ValueError):
                zoom_width = int(DEFAULT_IMAGE_ZOOM_PROMPT["width"])
            try:
                zoom_height = int(image_zoom_prompt.get("height", DEFAULT_IMAGE_ZOOM_PROMPT["height"]))
            except (TypeError, ValueError):
                zoom_height = int(DEFAULT_IMAGE_ZOOM_PROMPT["height"])
            index = -1
            for i in range(self.image_zoom_size_input.count()):
                size_value = self.image_zoom_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (zoom_width, zoom_height):
                    index = i
                    break
            self.image_zoom_size_input.setCurrentIndex(max(index, 0))
            zoom_direction = str(image_zoom_prompt.get("zoom_direction", DEFAULT_IMAGE_ZOOM_PROMPT["zoom_direction"])).strip()
            index = self.image_zoom_direction_input.findData(zoom_direction)
            self.image_zoom_direction_input.setCurrentIndex(max(index, 0))
            zoom_focal = str(image_zoom_prompt.get("focal_point", DEFAULT_IMAGE_ZOOM_PROMPT["focal_point"])).strip()
            index = self.image_zoom_focal_input.findData(zoom_focal)
            self.image_zoom_focal_input.setCurrentIndex(max(index, 0))
            try:
                zoom_strength = float(image_zoom_prompt.get("zoom_strength", DEFAULT_IMAGE_ZOOM_PROMPT["zoom_strength"]))
            except (TypeError, ValueError):
                zoom_strength = float(DEFAULT_IMAGE_ZOOM_PROMPT["zoom_strength"])
            self.image_zoom_strength_input.setValue(max(1.0, min(1.5, zoom_strength)))
            try:
                ws_width = int(web_search_prompt.get("width", DEFAULT_WEB_SEARCH_PROMPT["width"]))
            except (TypeError, ValueError):
                ws_width = int(DEFAULT_WEB_SEARCH_PROMPT["width"])
            try:
                ws_height = int(web_search_prompt.get("height", DEFAULT_WEB_SEARCH_PROMPT["height"]))
            except (TypeError, ValueError):
                ws_height = int(DEFAULT_WEB_SEARCH_PROMPT["height"])
            index = -1
            for i in range(self.web_search_size_input.count()):
                size_value = self.web_search_size_input.itemData(i)
                if isinstance(size_value, tuple) and size_value == (ws_width, ws_height):
                    index = i
                    break
            self.web_search_size_input.setCurrentIndex(max(index, 0))
            self.web_search_term_input.setText(str(web_search_prompt.get("search_term", "")))
            self.web_search_result_label.setText("Hasil akan langsung disimpan ke folder scene dan terlihat di tab Aset.")
            self.load_z_image_extra_prompts_into_ui(scene_dir)
            self.load_image_edit_into_ui(scene_dir)
            self.load_agentic_config_into_ui(scene_dir)
            self.load_t2v_batch_extra_prompts_into_ui(scene_dir)
        finally:
            self.loading_scene = False
        self.apply_project_size_constraints_to_ui()
        self._capture_scene_view_mode_baseline()
        if preferred_tab is not None and self.editor_tabs is not None:
            preferred_index = self.editor_tabs.indexOf(preferred_tab)
            if preferred_index >= 0 and self.editor_tabs.isTabVisible(preferred_index):
                self.editor_tabs.setCurrentWidget(preferred_tab)
        self._apply_scene_view_mode()
        self.refresh_scene_status()
        self.refresh_assets_and_previews()
        self.update_run_action_buttons_state()

    def gather_minimax_h3_prompts(self):
        t2v_lora_name = self.minimax_h3_t2v_lora_name_input.currentText().strip()
        t2v_lora_name_2 = self.minimax_h3_t2v_lora_name_2_input.currentText().strip()
        i2v_lora_name = self.minimax_h3_i2v_lora_name_input.currentText().strip()
        i2v_lora_name_2 = self.minimax_h3_i2v_lora_name_2_input.currentText().strip()
        try:
            t2v_lora_strength = float(self.minimax_h3_t2v_lora_strength_input.text().strip() or 0)
        except ValueError:
            raise ValueError("Kekuatan Lora MiniMax H3 T2V harus berupa angka.")
        try:
            i2v_lora_strength = float(self.minimax_h3_i2v_lora_strength_input.text().strip() or 0)
        except ValueError:
            raise ValueError("Kekuatan Lora MiniMax H3 I2V harus berupa angka.")
        try:
            t2v_lora_strength_2 = float(self.minimax_h3_t2v_lora_strength_2_input.text().strip() or 0)
        except ValueError:
            raise ValueError("Kekuatan Lora MiniMax H3 T2V kedua harus berupa angka.")
        try:
            i2v_lora_strength_2 = float(self.minimax_h3_i2v_lora_strength_2_input.text().strip() or 0)
        except ValueError:
            raise ValueError("Kekuatan Lora MiniMax H3 I2V kedua harus berupa angka.")
        t2v_size = self.minimax_h3_t2v_size_input.currentData() or (368, 640)
        i2v_size = self.minimax_h3_i2v_size_input.currentData() or t2v_size
        shared_fps = int(self.minimax_h3_t2v_fps_input.currentData() or MINIMAX_H3_DEFAULT_FPS)
        standalone_i2v_fps = int(self.minimax_h3_i2v_fps_input.currentData() or MINIMAX_H3_DEFAULT_FPS)
        scene_type = self.scene_type_combo.currentText().strip()
        t2v_prompt = {
            "width": int(t2v_size[0]),
            "height": int(t2v_size[1]),
            "fps": int(self.minimax_h3_t2v_fps_input.currentData() or MINIMAX_H3_DEFAULT_FPS),
            "positive_prompt": self._merge_minimax_h3_prompt_entry(
                self.current_scene_dir / "minimax_h3_t2v_prompt.json",
                "T2VA",
                self.minimax_h3_t2v_positive_input.toPlainText().strip(),
            ),
            "lora_name": t2v_lora_name,
            "lora_strength": t2v_lora_strength,
            "lora_name_2": t2v_lora_name_2,
            "lora_strength_2": t2v_lora_strength_2,
            "remove_sound": bool(self.minimax_h3_t2v_remove_sound_input.isChecked()),
        }
        i2v_prompt = {
            "width": int(i2v_size[0]),
            "height": int(i2v_size[1]),
            "fps": standalone_i2v_fps if scene_type == MINIMAX_H3_I2V_SCENE_TYPE else shared_fps,
            "positive_prompt": self._merge_minimax_h3_prompt_entry(
                self.current_scene_dir / "minimax_h3_i2v_prompt.json",
                "I2VA",
                self.minimax_h3_i2v_positive_input.toPlainText().strip(),
            ),
            "lora_name": i2v_lora_name,
            "lora_strength": i2v_lora_strength,
            "lora_name_2": i2v_lora_name_2,
            "lora_strength_2": i2v_lora_strength_2,
            "remove_sound": bool(self.minimax_h3_i2v_remove_sound_input.isChecked()),
        }
        return t2v_prompt, i2v_prompt

    def _synchronize_minimax_h3_prompt_translation(self, prompt: dict, mode: str) -> dict:
        """Validate MiniMax id_new before saving; translation happens at runtime."""
        result = copy.deepcopy(prompt or {})
        entry = result.get("positive_prompt")
        if not isinstance(entry, dict):
            return result
        id_new = entry.get("id_new")
        id_old = entry.get("id_old")
        if not isinstance(id_new, dict):
            raise ValueError("id_new MiniMax harus berupa object JSON.")
        probe = {"id_old": id_new, "id_new": id_new, "en": id_new}
        errors = validate_structured_prompt(probe, expected_mode=mode)
        if errors:
            raise ValueError(f"Prompt MiniMax {mode} tidak valid: " + "; ".join(errors[:3]))
        entry["id_new"] = copy.deepcopy(id_new)
        result["positive_prompt"] = entry
        return result

    def _synchronize_minimax_h3_s2v_prompt_translation(self, prompt: dict) -> dict:
        result = copy.deepcopy(prompt or {})
        entry = result.get("positive_prompt")
        if not isinstance(entry, dict):
            return result
        id_new = entry.get("id_new")
        if not isinstance(id_new, dict):
            raise ValueError("id_new MiniMax H3 S2V harus berupa object JSON.")
        errors = validate_ref2va_prompt(id_new)
        if errors:
            raise ValueError("Prompt MiniMax H3 S2V tidak valid: " + "; ".join(errors[:3]))
        # Translation is deferred to runtime; save only validates id_new.
        entry["id_new"] = copy.deepcopy(id_new)
        result["positive_prompt"] = entry
        return result

    def _synchronize_minimax_h3_r2v_prompt_translation(self, prompt: dict) -> dict:
        result = copy.deepcopy(prompt or {})
        entry = result.get("positive_prompt")
        if not isinstance(entry, dict):
            return result
        id_new = entry.get("id_new")
        if not isinstance(id_new, dict):
            raise ValueError("id_new MiniMax H3 R2V harus berupa object JSON.")
        errors = validate_ref2va_prompt(id_new)
        if errors:
            raise ValueError("Prompt MiniMax H3 R2V tidak valid: " + "; ".join(errors[:3]))
        # Translation is deferred to runtime; save only validates id_new.
        entry["id_new"] = copy.deepcopy(id_new)
        result["positive_prompt"] = entry
        return result

    def _refresh_minimax_h3_json_prompt_widgets(self, t2v_prompt: dict, i2v_prompt: dict):
        """Keep both MiniMax id_new editors pretty-printed after saving."""
        for widget, prompt in (
            (self.minimax_h3_t2v_positive_input, t2v_prompt),
            (self.minimax_h3_i2v_positive_input, i2v_prompt),
        ):
            entry = prompt.get("positive_prompt") if isinstance(prompt, dict) else None
            id_new = entry.get("id_new") if isinstance(entry, dict) else None
            if isinstance(id_new, dict):
                widget.setPlainText(json.dumps(id_new, ensure_ascii=False, indent=2))

    def _load_generated_minimax_id_new_into_ui(
        self,
        prompt_kind: str,
        scene_dir: Path,
        id_new: dict,
    ) -> bool:
        """Immediately show a generated MiniMax id_new in the active editor."""
        if not self.current_scene_dir:
            return False
        if Path(self.current_scene_dir).resolve() != Path(scene_dir).resolve():
            return False
        if not isinstance(id_new, dict):
            return False
        widget = (
            self.minimax_h3_t2v_positive_input
            if prompt_kind == "minimax_h3_t2v"
            else self.minimax_h3_i2v_positive_input
        )
        if prompt_kind == "minimax_h3_s2v":
            widget = self.s2v_positive_input
        elif prompt_kind == "minimax_h3_r2v":
            widget = self.minimax_h3_r2v_positive_input
        display_text = json.dumps(id_new, ensure_ascii=False, indent=2)
        widget.setPlainText(display_text)
        widget.document().setModified(True)
        widget.viewport().update()
        return widget.toPlainText() == display_text

    def _merge_minimax_h3_prompt_entry(self, path: Path, mode: str, id_new: str) -> dict:
        """Keep the generated nested English structure while syncing both ids."""
        existing = load_json(path, {})
        normalized = normalize_minimax_prompt_payload(existing, mode)
        entry = normalized.get("positive_prompt", {})
        if not isinstance(entry, dict):
            entry = {}
        entry = dict(entry)
        try:
            current_id_new = json.loads(str(id_new or "").strip())
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON id_new MiniMax tidak valid: {exc.msg}.") from exc
        if not isinstance(current_id_new, dict):
            raise ValueError("JSON id_new MiniMax harus berupa object.")
        # Repair the one-shot wrapper that could have been loaded into the
        # editor by older versions before comparing it with id_old.
        repaired_payload = normalize_minimax_prompt_payload(
            {
                "positive_prompt": {
                    "id_old": current_id_new,
                    "id_new": current_id_new,
                    "en": current_id_new,
                }
            },
            mode,
        )
        repaired_entry = repaired_payload.get("positive_prompt", {})
        if isinstance(repaired_entry, dict) and isinstance(repaired_entry.get("id_new"), dict):
            current_id_new = repaired_entry["id_new"]
        entry["id_new"] = current_id_new
        # Keep id_old and en for comparison/synchronization during save.
        return entry

    def gather_scene_data(self):
        meta = {
            "scene_title": self.scene_title_input.text().strip(),
            "scene_description": self.scene_description_input.toPlainText().strip(),
            "duration_seconds": self.parse_duration_value(),
            "voice_text": self.voice_text_input.toPlainText().strip(),
            "voice_character": str(self.scene_voice_character_input.currentData() or DEFAULT_SCENE_VOICE_KEY).strip(),
            "sound_prompt": self.sound_prompt_input.toPlainText().strip(),
            "sound_volume": self.sound_volume_input.text().strip(),
            "scene_type": self.scene_type_combo.currentText().strip(),
        }
        z_prompt = {
            "image_model": str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO),
            "gemini_model_id": (
                str(self.z_gemini_model_input.currentData() or MODEL_GEMINI_FLASH_05K).strip()
                if str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO) == MODEL_GEMINI_IMAGE
                else ""
            ),
            "positive_prompt": self.z_positive_input.toPlainText().strip(),
            "negative_prompt": (
                self.z_negative_input.toPlainText().strip()
                if z_image_supports_negative_prompt({"image_model": str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO)})
                else ""
            ),
            "width": int((self.z_size_input.currentData() or (368, 640))[0]),
            "height": int((self.z_size_input.currentData() or (368, 640))[1]),
            "use_random_seed": self.z_use_random_seed_input.isChecked(),
            "seed": self.parse_seed_value(),
            "use_lora": self.z_use_lora_input.isChecked(),
            "lora_name": self.z_lora_name_input.currentText().strip(),
            "strength_model": self.parse_lora_strength_value(),
            LORA_TRIGGER_WORDS_FIELD: self.z_lora_trigger_words_input.text().strip(),
        }
        z_prompt["json_api"] = get_z_image_template_name(z_prompt)
        wan_t2v_prompt = {
            "width": int((self.wan_t2v_size_input.currentData() or (368, 640))[0]),
            "height": int((self.wan_t2v_size_input.currentData() or (368, 640))[1]),
            "positive_prompt": self.wan_t2v_positive_input.toPlainText().strip(),
            "negative_prompt": self.wan_t2v_negative_input.toPlainText().strip(),
            "lora_high_name": self.wan_t2v_lora_high_name_input.currentText().strip(),
            "lora_high_strength": self.parse_wan_lora_strength_value(self.wan_t2v_lora_high_strength_input, "High 1"),
            "lora_low_name": self.wan_t2v_lora_low_name_input.currentText().strip(),
            "lora_low_strength": self.parse_wan_lora_strength_value(self.wan_t2v_lora_low_strength_input, "Low 1"),
            "lora_high_name_2": self.wan_t2v_lora_high2_name_input.currentText().strip(),
            "lora_high_strength_2": self.parse_wan_lora_strength_value(self.wan_t2v_lora_high2_strength_input, "High 2"),
            "lora_low_name_2": self.wan_t2v_lora_low2_name_input.currentText().strip(),
            "lora_low_strength_2": self.parse_wan_lora_strength_value(self.wan_t2v_lora_low2_strength_input, "Low 2"),
            LORA_TRIGGER_WORDS_FIELD: self.wan_t2v_lora_trigger_words_input.text().strip(),
        }
        wan_prompt = {
            "width": int((self.wan_size_input.currentData() or (368, 640))[0]),
            "height": int((self.wan_size_input.currentData() or (368, 640))[1]),
            "lora_high_name": self.wan_lora_high_name_input.currentText().strip(),
            "lora_high_strength": self.parse_wan_lora_strength_value(self.wan_lora_high_strength_input, "High 1"),
            "lora_low_name": self.wan_lora_low_name_input.currentText().strip(),
            "lora_low_strength": self.parse_wan_lora_strength_value(self.wan_lora_low_strength_input, "Low 1"),
            "lora_high_name_2": self.wan_lora_high2_name_input.currentText().strip(),
            "lora_high_strength_2": self.parse_wan_lora_strength_value(self.wan_lora_high2_strength_input, "High 2"),
            "lora_low_name_2": self.wan_lora_low2_name_input.currentText().strip(),
            "lora_low_strength_2": self.parse_wan_lora_strength_value(self.wan_lora_low2_strength_input, "Low 2"),
            LORA_TRIGGER_WORDS_FIELD: self.wan_lora_trigger_words_input.text().strip(),
        }
        for key, widget in self.wan_prompt_inputs.items():
            wan_prompt[key] = widget.toPlainText().strip()
        current_scene_type = self.scene_type_combo.currentText().strip()
        s2v_default = s2v_prompt_default(current_scene_type)
        s2v_prompt = {
            "positive_prompt": self.s2v_positive_input.toPlainText().strip() or _prompt_text_for_validation(s2v_default["positive_prompt"]),
            "negative_prompt": self.s2v_negative_input.toPlainText().strip() or DEFAULT_WAN22_S2V_PROMPT["negative_prompt"],
            "width": int((self.s2v_size_input.currentData() or (480, 848))[0]),
            "height": int((self.s2v_size_input.currentData() or (480, 848))[1]),
            "cfg": float(self.s2v_cfg_input.value()),
            "json_api": "auto_by_speech_duration",
        }
        if current_scene_type == MINIMAX_H3_S2V_SCENE_TYPE:
            raw_text = self.s2v_positive_input.toPlainText().strip()
            try:
                id_new_value = json.loads(raw_text) if raw_text else copy.deepcopy(s2v_default["positive_prompt"].get("id_new", {}))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON id_new MiniMax H3 S2V tidak valid: {exc.msg}.") from exc
            if not isinstance(id_new_value, dict):
                raise ValueError("JSON id_new MiniMax H3 S2V harus berupa object.")
            try:
                s2v_lora_strength = float(self.minimax_h3_s2v_lora_strength_input.text().strip() or 0)
                s2v_lora_strength_2 = float(self.minimax_h3_s2v_lora_strength_2_input.text().strip() or 0)
            except ValueError as exc:
                raise ValueError("Kekuatan LoRA MiniMax H3 S2V harus berupa angka.") from exc
            existing_payload = load_json(self.current_scene_dir / MINIMAX_H3_S2V_PROMPT_FILENAME, s2v_default)
            existing_entry = existing_payload.get("positive_prompt", {}) if isinstance(existing_payload, dict) else {}
            s2v_prompt = {
                "positive_prompt": {
                    "id_old": copy.deepcopy(existing_entry.get("id_old", id_new_value)) if isinstance(existing_entry, dict) else copy.deepcopy(id_new_value),
                    "id_new": id_new_value,
                    "en": copy.deepcopy(existing_entry.get("en", id_new_value)) if isinstance(existing_entry, dict) else copy.deepcopy(id_new_value),
                },
                "width": s2v_prompt["width"],
                "height": s2v_prompt["height"],
                "fps": int(self.minimax_h3_s2v_fps_input.currentData() or MINIMAX_H3_DEFAULT_FPS),
                "lora_name": self.minimax_h3_s2v_lora_name_input.currentText().strip(),
                "lora_strength": s2v_lora_strength,
                "lora_name_2": self.minimax_h3_s2v_lora_name_2_input.currentText().strip(),
                "lora_strength_2": s2v_lora_strength_2,
            }
        web_prompt = {
            "url": self.web_url_input.text().strip(),
            "width": int((self.web_size_input.currentData() or (368, 640))[0]),
            "height": int((self.web_size_input.currentData() or (368, 640))[1]),
            "duration_seconds": round(float(self.web_duration_input.value()), 1),
            "speed": int(self.web_speed_input.value()),
        }
        image_pan_prompt = {
            "width": int((self.image_pan_size_input.currentData() or (480, 848))[0]),
            "height": int((self.image_pan_size_input.currentData() or (480, 848))[1]),
            "direction": str(self.image_pan_direction_input.currentData() or "from_right").strip(),
        }
        image_zoom_prompt = {
            "width": int((self.image_zoom_size_input.currentData() or (480, 848))[0]),
            "height": int((self.image_zoom_size_input.currentData() or (480, 848))[1]),
            "zoom_direction": str(self.image_zoom_direction_input.currentData() or "in").strip(),
            "focal_point": str(self.image_zoom_focal_input.currentData() or "center").strip(),
            "zoom_strength": round(float(self.image_zoom_strength_input.value()), 1),
        }
        return meta, z_prompt, wan_t2v_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt, image_zoom_prompt

    def gather_web_search_prompt(self):
        size_data = self.web_search_size_input.currentData() or (480, 848)
        return {
            "width": int(size_data[0]),
            "height": int(size_data[1]),
            "search_term": self.web_search_term_input.text().strip(),
        }

    def _firecrawl_search_image_urls(self, search_term: str, width: int, height: int, limit: int = 10):
        logger = logging.getLogger(__name__)
        api_key = read_key_from_cfg("FIRECRAWLKEY")
        if not api_key:
            api_key = read_key_from_cfg("FIRECRAWL_API_KEY")
        if not api_key:
            logger.error("[web_search] gagal: FIRECRAWLKEY/FIRECRAWL_API_KEY tidak ditemukan di keys.cfg.")
            raise RuntimeError("API key Firecrawl tidak ditemukan. Tambahkan FIRECRAWLKEY di keys.cfg.")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        orientation_hint = "landscape orientation" if int(width) >= int(height) else "portrait orientation"
        ratio_hint = f"aspect ratio around {int(width)}:{int(height)}"
        query = f"{search_term.strip()} {orientation_hint} {ratio_hint} larger:{int(width)}x{int(height)}"
        logger.info(
            "[web_search] request firecrawl: query='%s', limit=%s, filter='larger:%sx%s', orientation_hint='%s'.",
            search_term.strip(),
            max(10, int(limit)),
            int(width),
            int(height),
            orientation_hint,
        )
        payload_v2 = {
            "query": query,
            "limit": max(10, int(limit)),
            "sources": ["images"],
        }
        response = None
        used_endpoint = ""
        try:
            used_endpoint = "https://api.firecrawl.dev/v2/search"
            response = requests.post(
                used_endpoint,
                headers=headers,
                json=payload_v2,
                timeout=45,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", None)
            # Backward-compatible fallback when v2 is not available for a given account.
            if status_code in {400, 401, 403, 404, 405}:
                logger.warning("[web_search] v2 search gagal (%s), fallback ke v1/search.", status_code)
                used_endpoint = "https://api.firecrawl.dev/v1/search"
                payload_v1 = {
                    "query": query,
                    "limit": max(10, int(limit)),
                }
                response = requests.post(
                    used_endpoint,
                    headers=headers,
                    json=payload_v1,
                    timeout=45,
                )
                response.raise_for_status()
            else:
                raise
        data = response.json()
        logger.info("[web_search] endpoint digunakan: %s", used_endpoint)
        data_root = data.get("data", {}) if isinstance(data, dict) else {}
        urls = []

        # Format A (common): data.images -> [{imageUrl: "..."}] or ["..."]
        if isinstance(data_root, dict):
            image_results = data_root.get("images", [])
            if isinstance(image_results, list):
                for item in image_results:
                    if isinstance(item, str) and item.startswith(("http://", "https://")):
                        urls.append(item.strip())
                        continue
                    if isinstance(item, dict):
                        for key in ("imageUrl", "url", "image", "src"):
                            value = item.get(key)
                            if isinstance(value, str) and value.startswith(("http://", "https://")):
                                urls.append(value.strip())
                                break

        # Format B (older): data is list of web results with image fields per item.
        raw_items = data_root if isinstance(data_root, list) else []
        if raw_items:
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                for key in ("imageUrl", "url", "image", "src"):
                    value = item.get(key)
                    if isinstance(value, str) and value.startswith(("http://", "https://")):
                        urls.append(value.strip())
                image_candidates = item.get("images", [])
                if isinstance(image_candidates, list):
                    for image_url in image_candidates:
                        if isinstance(image_url, str) and image_url.startswith(("http://", "https://")):
                            urls.append(image_url.strip())

        logger.info(
            "[web_search] response firecrawl: data_type=%s, total_url_kandidat=%s.",
            type(data_root).__name__,
            len(urls),
        )
        unique_urls = []
        seen = set()
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            unique_urls.append(url)
            if len(unique_urls) >= limit:
                break
        logger.info("[web_search] url unik gambar: %s.", len(unique_urls))
        return unique_urls

    def _download_web_search_images(self, scene_dir: Path, urls: list[str]):
        logger = logging.getLogger(__name__)
        if not urls:
            logger.info("[web_search] download dilewati: daftar URL kosong.")
            return []
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        downloaded = []
        logger.info("[web_search] mulai download: total=%s, scene=%s", len(urls), scene_dir)
        for index, url in enumerate(urls, start=1):
            try:
                parsed = urlparse(url)
                suffix = Path(parsed.path).suffix.lower()
                if suffix not in IMAGE_EXTS:
                    suffix = ".jpg"
                filename = f"web_search_{timestamp}_{index:02d}{suffix}"
                output_path = scene_dir / filename
                with requests.get(url, timeout=30, stream=True) as response:
                    response.raise_for_status()
                    with output_path.open("wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                downloaded.append(output_path)
            except Exception as exc:
                logger.warning("[web_search] gagal download image: url=%s, error=%s", url, exc)
        logger.info("[web_search] selesai download: %s file berhasil disimpan.", len(downloaded))
        return downloaded

    def run_web_search_images(self):
        logger = logging.getLogger(__name__)
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        scene_type = self.scene_type_combo.currentText().strip()
        if scene_type not in {"i2v", "image_pan", "image_zoom"}:
            QMessageBox.information(self, "Tipe Adegan Tidak Didukung", "Web Search hanya untuk i2v, image_pan, dan image_zoom.")
            return
        if not self.save_current_scene(silent=True, reload_list=False):
            return
        search_term = self.web_search_term_input.text().strip()
        if not search_term:
            QMessageBox.warning(self, "Data Tidak Valid", "Search term wajib diisi.")
            return
        if self.web_search_thread is not None and self.web_search_thread.isRunning():
            QMessageBox.information(self, "Web Search Berjalan", "Proses Web Search sebelumnya masih berjalan.")
            return

        api_key = read_key_from_cfg("FIRECRAWLKEY") or read_key_from_cfg("FIRECRAWL_API_KEY")
        if not api_key:
            logger.error("[web_search] gagal: FIRECRAWLKEY/FIRECRAWL_API_KEY tidak ditemukan di keys.cfg.")
            QMessageBox.warning(self, "Web Search Gagal", "API key Firecrawl tidak ditemukan di keys.cfg.")
            return

        web_search_prompt = self.gather_web_search_prompt()
        width = int(web_search_prompt.get("width", 480))
        height = int(web_search_prompt.get("height", 848))
        logger.info(
            "[web_search] mulai: scene=%s, scene_type=%s, search_term='%s', width=%s, height=%s.",
            self.current_scene_dir,
            scene_type,
            search_term,
            width,
            height,
        )
        self.web_search_run_button.setEnabled(False)
        self.statusBar().showMessage("Web Search sedang berjalan...", 0)
        self.web_search_result_label.setText("Web Search sedang berjalan...")

        self.web_search_thread = QThread(self)
        self.web_search_worker = WebSearchWorker(
            api_key=api_key,
            search_term=search_term,
            width=width,
            height=height,
            scene_dir=str(self.current_scene_dir),
        )
        self.web_search_worker.moveToThread(self.web_search_thread)
        self.web_search_thread.started.connect(self.web_search_worker.run)
        self.web_search_worker.finished.connect(self._on_web_search_finished)
        self.web_search_worker.failed.connect(self._on_web_search_failed)
        self.web_search_worker.finished.connect(self.web_search_thread.quit)
        self.web_search_worker.failed.connect(self.web_search_thread.quit)
        self.web_search_thread.finished.connect(self._cleanup_web_search_thread)
        self.web_search_thread.start()

    def _on_web_search_finished(self, result: dict):
        downloaded_count = int(result.get("downloaded_count", 0)) if isinstance(result, dict) else 0
        width = int(result.get("width", 480)) if isinstance(result, dict) else 480
        height = int(result.get("height", 848)) if isinstance(result, dict) else 848
        self.refresh_assets_and_previews()
        self.refresh_scene_status()
        self.web_search_result_label.setText(
            f"Hasil: {downloaded_count} gambar tersimpan ke scene. Filter: larger:{width}x{height}."
        )
        QMessageBox.information(
            self,
            "Proses Berhasil",
            f"Web Search berhasil.\n\n{downloaded_count} gambar tersimpan ke folder scene.",
        )
        self.statusBar().showMessage("Proses selesai.", 5000)
        logging.getLogger(__name__).info(
            "[web_search] sukses: downloaded=%s, scene=%s, filter='larger:%sx%s'.",
            downloaded_count,
            self.current_scene_dir,
            width,
            height,
        )

    def _on_web_search_failed(self, error: str):
        logging.getLogger(__name__).error("[web_search] gagal: %s", error)
        self.web_search_result_label.setText("Web Search gagal.")
        QMessageBox.critical(self, "Proses Gagal", f"Web Search gagal.\n\n{error}")
        self.statusBar().showMessage("Proses gagal.", 5000)

    def _cleanup_web_search_thread(self):
        self.web_search_run_button.setEnabled(True)
        if self.web_search_worker is not None:
            self.web_search_worker.deleteLater()
        if self.web_search_thread is not None:
            self.web_search_thread.deleteLater()
        self.web_search_worker = None
        self.web_search_thread = None

    def _uses_decimal_duration_input(self) -> bool:
        return self.scene_type_combo.currentText().strip() in {
            MINIMAX_H3_T2V_I2V_SCENE_TYPE,
            MINIMAX_H3_I2V_SCENE_TYPE,
            MINIMAX_H3_R2V_SCENE_TYPE,
        }

    def _duration_text(self) -> str:
        if self._uses_decimal_duration_input():
            return self.duration_decimal_input.text().strip()
        return self.duration_input.currentText().strip()

    def parse_duration_value(self):
        scene_type = self.scene_type_combo.currentText().strip()
        if self._uses_decimal_duration_input():
            text = self.duration_decimal_input.text().strip()
            if not text:
                raise ValueError("Durasi wajib diisi.")
            try:
                value = round(float(text), MINIMAX_H3_DURATION_DECIMALS)
            except ValueError as exc:
                raise ValueError("Durasi harus berupa angka dengan maksimal 1 angka desimal.") from exc
            maximum = 30.0 if scene_type == MINIMAX_H3_T2V_I2V_SCENE_TYPE else 15.0
            if value < MINIMAX_H3_DURATION_MIN or value > maximum:
                raise ValueError(f"Durasi harus antara {MINIMAX_H3_DURATION_MIN:g} dan {maximum:g} detik.")
            return value

        value = self.duration_input.currentText().strip()
        if not value:
            return 10
        try:
            parsed = int(float(value))
        except ValueError:
            raise ValueError("Durasi harus berupa angka.")
        allowed = set(duration_options_for_scene_type(self.scene_type_combo.currentText().strip()))
        if parsed not in allowed:
            allowed_text = ", ".join(str(value) for value in sorted(allowed))
            raise ValueError(f"Durasi hanya boleh {allowed_text} detik.")
        return parsed

    def parse_lora_strength_value(self):
        if not self.z_use_lora_input.isChecked():
            return 1.0
        value = self.z_lora_strength_input.text().strip()
        if not value:
            return 1.0
        try:
            parsed = float(value)
        except ValueError:
            raise ValueError("Kekuatan Lora harus berupa bilangan desimal positif.")
        if parsed <= 0:
            raise ValueError("Kekuatan Lora harus berupa bilangan desimal positif.")
        return parsed

    def parse_seed_value(self):
        if self.z_use_random_seed_input.isChecked():
            # Ignore any stale value in the static seed input when random mode is enabled.
            return 1
        value = self.z_seed_input.text().strip()
        if not value:
            raise ValueError("Seed statik wajib diisi saat Random Seed dimatikan.")
        try:
            parsed = int(value)
        except ValueError:
            raise ValueError("Seed statik harus berupa bilangan bulat positif.")
        if parsed <= 0:
            raise ValueError("Seed statik harus berupa bilangan bulat positif.")
        return parsed

    def parse_wan_lora_strength_value(self, widget: QLineEdit, label: str):
        value = widget.text().strip()
        if not value:
            return 0.0
        try:
            parsed = float(value)
        except ValueError:
            raise ValueError(f"Kekuatan Lora {label} WAN harus berupa bilangan desimal.")
        if parsed < 0:
            raise ValueError(f"Kekuatan Lora {label} WAN tidak boleh negatif.")
        return parsed

    def load_image_edit_prompt(self, scene_dir: Path):
        data = load_json(scene_dir / "image_edit_prompt.json", DEFAULT_IMAGE_EDIT_PROMPT)
        groups = data.get("groups")
        if not isinstance(groups, list):
            groups = []
        normalized_groups = []
        for index in range(3):
            item = groups[index] if index < len(groups) and isinstance(groups[index], dict) else {}
            normalized_groups.append(
                {
                    "source_image": str(item.get("source_image", "")).strip(),
                    "prompt": str(item.get("prompt", "")).strip(),
                }
            )
        return {"groups": normalized_groups}

    def load_z_image_extra_prompts(self, scene_dir: Path):
        data = load_json(scene_dir / "z_image_extra_prompts.json", DEFAULT_Z_IMAGE_EXTRA_PROMPTS)
        groups = data.get("groups")
        if not isinstance(groups, list):
            groups = []
        normalized_groups = []
        for index in range(3):
            item = groups[index] if index < len(groups) and isinstance(groups[index], dict) else {}
            normalized_groups.append(
                {
                    "positive_prompt": str(item.get("positive_prompt", "")).strip(),
                    "negative_prompt": str(item.get("negative_prompt", "")).strip(),
                }
            )
        return {"groups": normalized_groups}

    def gather_z_image_extra_prompts(self):
        groups = []
        model_key = str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO)
        supports_negative = z_image_supports_negative_prompt({"image_model": model_key})
        for positive_input, negative_input in zip(self.z_extra_positive_inputs, self.z_extra_negative_inputs):
            groups.append(
                {
                    "positive_prompt": positive_input.toPlainText().strip(),
                    "negative_prompt": negative_input.toPlainText().strip() if supports_negative else "",
                }
            )
        return {"groups": groups}

    def gather_image_edit_prompt(self):
        groups = []
        for image_input, prompt_input in zip(self.image_edit_image_inputs, self.image_edit_prompt_inputs):
            groups.append(
                {
                    "source_image": str(image_input.currentData() or "").strip(),
                    "prompt": prompt_input.toPlainText().strip(),
                }
            )
        return {"groups": groups}

    def gather_t2v_batch_extra_prompts(self):
        groups = []
        for positive_input, negative_input in zip(self.t2v_batch_positive_inputs, self.t2v_batch_negative_inputs):
            groups.append(
                {
                    "positive_prompt": positive_input.toPlainText().strip(),
                    "negative_prompt": negative_input.toPlainText().strip(),
                }
            )
        return {"groups": groups}

    def refresh_image_edit_source_options(self, preferred_images=None):
        preferred_images = preferred_images or ["", "", ""]
        image_names = []
        scene_dir = self.active_scene_dir()
        if scene_dir and scene_dir.exists():
            image_names = sorted(
                [
                    p.name for p in scene_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTS
                ],
                key=lambda name: name.lower(),
            )

        for index, combo in enumerate(self.image_edit_image_inputs):
            preferred = str(preferred_images[index] if index < len(preferred_images) else "").strip()
            current_value = str(combo.currentData() or "").strip()
            wanted = preferred or current_value
            combo.blockSignals(True)
            combo.clear()
            for image_name in image_names:
                combo.addItem(image_name, image_name)
            if image_names:
                selected_index = combo.findData(wanted)
                combo.setCurrentIndex(selected_index if selected_index >= 0 else 0)
            combo.blockSignals(False)

    def load_image_edit_into_ui(self, scene_dir: Path):
        data = self.load_image_edit_prompt(scene_dir)
        self.sync_image_edit_model_from_initial_image()
        self.update_image_edit_model_fields_enabled()
        groups = data.get("groups", [])
        preferred_images = [str(group.get("source_image", "")).strip() for group in groups[:3]]
        self.refresh_image_edit_source_options(preferred_images=preferred_images)
        for index, prompt_input in enumerate(self.image_edit_prompt_inputs):
            group_data = groups[index] if index < len(groups) else {}
            prompt_input.setPlainText(str(group_data.get("prompt", "")))

    def sync_image_edit_model_from_initial_image(self):
        model_key = str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO).strip()
        model_index = self.image_edit_model_input.findData(model_key)
        self.image_edit_model_input.setCurrentIndex(model_index if model_index >= 0 else 0)

        selected_gemini_model = str(self.z_gemini_model_input.currentData() or MODEL_GEMINI_FLASH_05K).strip()
        gemini_index = self.image_edit_gemini_model_input.findData(selected_gemini_model)
        if gemini_index < 0 and selected_gemini_model:
            self.image_edit_gemini_model_input.addItem(selected_gemini_model, selected_gemini_model)
            gemini_index = self.image_edit_gemini_model_input.findData(selected_gemini_model)
        self.image_edit_gemini_model_input.setCurrentIndex(gemini_index if gemini_index >= 0 else 0)

    def load_z_image_extra_prompts_into_ui(self, scene_dir: Path):
        data = self.load_z_image_extra_prompts(scene_dir)
        groups = data.get("groups", [])
        for index in range(3):
            group_data = groups[index] if index < len(groups) else {}
            self.z_extra_positive_inputs[index].setPlainText(str(group_data.get("positive_prompt", "")))
            self.z_extra_negative_inputs[index].setPlainText(str(group_data.get("negative_prompt", "")))

    def load_agentic_config_into_ui(self, scene_dir: Path):
        data = load_agentic_config(scene_dir)
        self.agentic_number_of_variations_input.setValue(int(data.get("number_of_variations", 0)))
        self.agentic_special_command_input.setPlainText(str(data.get("special_command", "")))
        scene_type = self.scene_type_combo.currentText().strip()
        visible_in_ui, forced_value = agentic_create_initial_image_policy(scene_type)
        resolved_create_initial_image = bool(data.get("create_initial_image", True)) if forced_value is None else bool(forced_value)
        self.agentic_create_initial_image_input.setChecked(resolved_create_initial_image)
        if self.agentic_tab is not None:
            layout = self.agentic_tab.layout()
            self._set_form_field_visible(layout, self.agentic_create_initial_image_input, visible_in_ui)
        mode = str(data.get("image_extra_mode", DEFAULT_AGENERIC_CONFIG.get("image_extra_mode", "image_extra"))).strip()
        mode_index = self.agentic_image_extra_mode_input.findData(mode)
        self.agentic_image_extra_mode_input.setCurrentIndex(mode_index if mode_index >= 0 else 0)

    def gather_agentic_config(self):
        scene_type = self.scene_type_combo.currentText().strip()
        _, forced_create_initial_image = agentic_create_initial_image_policy(scene_type)
        create_initial_image = (
            bool(self.agentic_create_initial_image_input.isChecked())
            if forced_create_initial_image is None
            else bool(forced_create_initial_image)
        )
        return {
            "number_of_variations": int(self.agentic_number_of_variations_input.value()),
            "special_command": self.agentic_special_command_input.toPlainText().strip(),
            "create_initial_image": create_initial_image,
            "image_extra_mode": str(self.agentic_image_extra_mode_input.currentData() or "image_extra").strip(),
        }

    def refresh_scene_status(self):
        scene_dir = self.active_scene_dir()
        if not scene_dir:
            self.status_label.setPlainText("Belum ada adegan yang dipilih.")
            return
        try:
            meta, z_prompt, wan_t2v_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt, image_zoom_prompt = self.gather_scene_data()
            minimax_h3_t2v_prompt, minimax_h3_i2v_prompt = self.gather_minimax_h3_prompts()
            r2v_prompt = self.gather_minimax_h3_r2v_prompt()
            issues = validate_scene_data(
                meta,
                z_prompt,
                wan_t2v_prompt,
                wan_prompt,
                s2v_prompt,
                web_prompt,
                image_pan_prompt,
                image_zoom_prompt,
                scene_dir,
                minimax_h3_t2v_prompt,
                minimax_h3_i2v_prompt,
            )
        except ValueError as e:
            issues = [str(e)]
        if issues:
            prefix = "Mode lihat variasi (read-only).\n" if self.is_viewing_variation() else ""
            self.status_label.setPlainText(prefix + "Masalah:\n- " + "\n- ".join(issues))
            self.status_label.setStyleSheet("padding: 6px; background: #fef2f2; border: 1px solid #ef4444; color: #991b1b;")
        else:
            suffix = " (lihat variasi, read-only)" if self.is_viewing_variation() else ""
            self.status_label.setPlainText(f"Status: Siap{suffix}")
            self.status_label.setStyleSheet("padding: 6px; background: #ecfdf5; border: 1px solid #10b981; color: #065f46;")

    def get_scene_issues(self, scene_dir: Path):
        meta = load_json(scene_dir / "scene_meta.json", DEFAULT_SCENE_META)
        z_prompt = load_json(scene_dir / "z_image_prompt.json", DEFAULT_Z_IMAGE_PROMPT)
        wan_t2v_prompt = load_json(scene_dir / "wan22_t2v_prompt.json", DEFAULT_WAN22_T2V_PROMPT)
        wan_prompt = load_json(scene_dir / "wan22_i2v_prompt.json", DEFAULT_WAN_PROMPT)
        scene_type = str(meta.get("scene_type", "wan22_i2v")).strip()
        s2v_prompt = load_json(scene_dir / s2v_prompt_filename(scene_type), s2v_prompt_default(scene_type))
        web_prompt = load_json(scene_dir / "web_scroll_prompt.json", DEFAULT_WEB_SCROLL_PROMPT)
        image_pan_prompt = load_json(scene_dir / "image_pan_prompt.json", DEFAULT_IMAGE_PAN_PROMPT)
        image_zoom_prompt = load_json(scene_dir / "image_zoom_prompt.json", DEFAULT_IMAGE_ZOOM_PROMPT)
        minimax_h3_t2v_prompt = load_json(
            scene_dir / "minimax_h3_t2v_prompt.json",
            DEFAULT_MINIMAX_H3_T2V_PROMPT,
        )
        minimax_h3_i2v_prompt = load_json(
            scene_dir / "minimax_h3_i2v_prompt.json",
            DEFAULT_MINIMAX_H3_I2V_PROMPT,
        )
        return validate_scene_data(
            meta,
            z_prompt,
            wan_t2v_prompt,
            wan_prompt,
            s2v_prompt,
            web_prompt,
            image_pan_prompt,
            image_zoom_prompt,
            scene_dir,
            minimax_h3_t2v_prompt,
            minimax_h3_i2v_prompt,
        )

    def ensure_scene_is_runnable(self, scene_dir: Path):
        issues = self.get_scene_issues(scene_dir)
        if issues:
            QMessageBox.warning(
                self,
                "Adegan Masih Bermasalah",
                "Adegan tidak bisa dijalankan karena masih ada masalah:\n- " + "\n- ".join(issues),
            )
            return False
        return True

    def ensure_all_scenes_are_runnable(self):
        problem_summaries = []
        for scene_dir in self.list_scene_dirs_current():
            issues = self.get_scene_issues(scene_dir)
            if issues:
                problem_summaries.append(f"{scene_dir.name}: " + "; ".join(issues))
        if problem_summaries:
            QMessageBox.warning(
                self,
                "Masih Ada Adegan Bermasalah",
                "Semua adegan tidak bisa dijalankan karena masih ada masalah:\n- " + "\n- ".join(problem_summaries),
            )
            return False
        return True

    def refresh_assets_and_previews(self):
        scene_dir = self.active_scene_dir()
        if not scene_dir:
            self.refresh_image_edit_source_options()
            return
        self.clear_viewer()
        assets = sorted(
            [
                p for p in scene_dir.iterdir()
                if p.is_file() and p.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS)
            ],
            key=lambda p: p.name.lower(),
        )
        self.asset_list.clear()
        self.asset_info_label.setText("Belum ada aset yang dipilih.")
        for asset in assets:
            item = QListWidgetItem(asset.name)
            item.setData(Qt.UserRole, str(asset))
            self.asset_list.addItem(item)
        self.refresh_image_edit_source_options()
        self.refresh_r2v_reference_options()
        if not assets:
            self.viewer_info_label.setText("Tidak ada file media di scene ini.")

    def _r2v_selected_names(self, widget: QListWidget) -> list[str]:
        selected = []
        for index in range(widget.count()):
            item = widget.item(index)
            if item.checkState() == Qt.Checked:
                selected.append(str(item.data(Qt.UserRole) or item.text()).strip())
        return [name for name in selected if name]

    def _limit_r2v_reference_selection(self, widget: QListWidget, maximum: int):
        selected = [widget.item(index) for index in range(widget.count()) if widget.item(index).checkState() == Qt.Checked]
        if len(selected) <= maximum:
            return
        widget.blockSignals(True)
        for item in selected[maximum:]:
            item.setCheckState(Qt.Unchecked)
        widget.blockSignals(False)
        self.refresh_scene_status()

    def _set_r2v_reference_list(self, widget: QListWidget, names: list[str], selected: list[str], maximum: int):
        selected_set = {str(value).strip() for value in selected if str(value).strip()}
        widget.blockSignals(True)
        widget.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in selected_set else Qt.Unchecked)
            widget.addItem(item)
        widget.blockSignals(False)

    def refresh_r2v_reference_options(self, preferred: dict | None = None):
        scene_dir = self.active_scene_dir()
        if not scene_dir or not scene_dir.exists():
            return
        assets = [path for path in scene_dir.iterdir() if path.is_file()]
        image_names = sorted([p.name for p in assets if p.suffix.lower() in IMAGE_EXTS], key=str.lower)
        video_names = sorted([p.name for p in assets if p.suffix.lower() in VIDEO_EXTS], key=str.lower)
        audio_names = sorted([p.name for p in assets if p.suffix.lower() in AUDIO_EXTS], key=str.lower)
        current = preferred if isinstance(preferred, dict) else {
            "images": self._r2v_selected_names(self.minimax_h3_r2v_image_list),
            "video": self._r2v_selected_names(self.minimax_h3_r2v_video_list)[:1],
            "audios": self._r2v_selected_names(self.minimax_h3_r2v_audio_list),
        }
        self._set_r2v_reference_list(
            self.minimax_h3_r2v_image_list, image_names, list(current.get("images", []))[:3], 3
        )
        self._set_r2v_reference_list(
            self.minimax_h3_r2v_audio_list, audio_names, list(current.get("audios", []))[:3], 3
        )
        video_value = current.get("video", "")
        video_selected = [video_value] if isinstance(video_value, str) and video_value else list(video_value or [])[:1]
        self._set_r2v_reference_list(self.minimax_h3_r2v_video_list, video_names, video_selected, 1)

    def gather_minimax_h3_r2v_prompt(self) -> dict:
        size = self.minimax_h3_r2v_size_input.currentData() or (368, 640)
        raw_text = self.minimax_h3_r2v_positive_input.toPlainText().strip()
        try:
            id_new = json.loads(raw_text) if raw_text else copy.deepcopy(DEFAULT_MINIMAX_H3_R2V_PROMPT["positive_prompt"]["id_new"])
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON id_new MiniMax H3 R2V tidak valid: {exc.msg}.") from exc
        if not isinstance(id_new, dict):
            raise ValueError("id_new MiniMax H3 R2V harus berupa object.")
        existing = load_json(self.current_scene_dir / MINIMAX_H3_R2V_PROMPT_FILENAME, DEFAULT_MINIMAX_H3_R2V_PROMPT)
        existing_entry = existing.get("positive_prompt", {}) if isinstance(existing, dict) else {}
        references = {
            "images": self._r2v_selected_names(self.minimax_h3_r2v_image_list)[:3],
            "video": (self._r2v_selected_names(self.minimax_h3_r2v_video_list) or [""])[0],
            "audios": self._r2v_selected_names(self.minimax_h3_r2v_audio_list)[:3],
        }
        try:
            r2v_lora_strength = float(self.minimax_h3_r2v_lora_strength_input.text().strip() or 0)
            r2v_lora_strength_2 = float(self.minimax_h3_r2v_lora_strength_2_input.text().strip() or 0)
        except ValueError as exc:
            raise ValueError("Kekuatan LoRA MiniMax H3 R2V harus berupa angka.") from exc
        return {
            "positive_prompt": {
                "id_old": copy.deepcopy(existing_entry.get("id_old", id_new)) if isinstance(existing_entry, dict) else copy.deepcopy(id_new),
                "id_new": id_new,
                "en": copy.deepcopy(existing_entry.get("en", id_new)) if isinstance(existing_entry, dict) else copy.deepcopy(id_new),
            },
            "width": int(size[0]),
            "height": int(size[1]),
            "fps": int(self.minimax_h3_r2v_fps_input.currentData() or MINIMAX_H3_DEFAULT_FPS),
            "references": references,
            "lora_name": self.minimax_h3_r2v_lora_name_input.currentText().strip(),
            "lora_strength": r2v_lora_strength,
            "lora_name_2": self.minimax_h3_r2v_lora_name_2_input.currentText().strip(),
            "lora_strength_2": r2v_lora_strength_2,
        }

    def save_current_scene(self, silent=False, reload_list=True):
        if not self.current_scene_dir:
            self.append_log("[gagal] Save Scene: belum ada adegan yang dipilih.")
            self.statusBar().showMessage("Save Scene gagal: belum ada adegan yang dipilih.", 5000)
            return False
        if self.is_viewing_variation():
            message = "Pilih `Root Scene` di dropdown Variasi sebelum menyimpan atau membuat prompt."
            self.append_log(f"[gagal] Save Scene: {message}")
            self.statusBar().showMessage(message, 6000)
            if not silent:
                QMessageBox.information(
                    self,
                    "Mode Lihat Variasi",
                    "Variasi hanya bisa dilihat. " + message,
                )
            return False
        try:
            meta, z_prompt, wan_t2v_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt, image_zoom_prompt = self.gather_scene_data()
            minimax_h3_t2v_prompt, minimax_h3_i2v_prompt = self.gather_minimax_h3_prompts()
            r2v_prompt = self.gather_minimax_h3_r2v_prompt()
            minimax_h3_t2v_prompt = self._synchronize_minimax_h3_prompt_translation(
                minimax_h3_t2v_prompt, "T2VA"
            )
            minimax_h3_i2v_prompt = self._synchronize_minimax_h3_prompt_translation(
                minimax_h3_i2v_prompt, "I2VA"
            )
            if meta.get("scene_type") == MINIMAX_H3_S2V_SCENE_TYPE:
                s2v_prompt = self._synchronize_minimax_h3_s2v_prompt_translation(s2v_prompt)
            if meta.get("scene_type") == MINIMAX_H3_R2V_SCENE_TYPE:
                r2v_prompt = self._synchronize_minimax_h3_r2v_prompt_translation(r2v_prompt)
        except ValueError as e:
            self.append_log(f"[gagal] Data scene tidak valid saat Save: {e}")
            self.statusBar().showMessage(f"Save Scene gagal: {e}", 8000)
            if not silent:
                QMessageBox.warning(self, "Data Tidak Valid", str(e))
            return False
        except Exception as e:
            self.append_log(f"[gagal] Sinkronisasi prompt MiniMax saat Save: {e}")
            self.statusBar().showMessage(f"Save Scene gagal: {e}", 8000)
            if not silent:
                QMessageBox.warning(self, "Gagal Menyimpan", str(e))
            return False
        issues = validate_scene_data(
            meta,
            z_prompt,
            wan_t2v_prompt,
            wan_prompt,
            s2v_prompt,
            web_prompt,
            image_pan_prompt,
            image_zoom_prompt,
            self.current_scene_dir,
            minimax_h3_t2v_prompt,
            minimax_h3_i2v_prompt,
            r2v_prompt,
        )
        if issues and not silent:
            reply = QMessageBox.question(
                self, "Masalah Validasi",
                "Adegan masih memiliki masalah:\n- " + "\n- ".join(issues) + "\n\nTetap simpan?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False
        scene_type = str(meta.get("scene_type", "wan22_i2v")).strip()
        image_edit_prompt = self.gather_image_edit_prompt()
        z_image_extra_prompts = self.gather_z_image_extra_prompts()
        t2v_batch_extra_prompts = self.gather_t2v_batch_extra_prompts()
        agentic_config = self.gather_agentic_config()
        self.save_project_voice_settings()
        write_prompt_json(self.current_scene_dir / "scene_meta.json", meta)
        sync_scene_prompt_files(
            self.current_scene_dir,
            scene_type=scene_type,
            z_prompt=z_prompt,
            wan_t2v_prompt=wan_t2v_prompt,
            wan_prompt=wan_prompt,
            s2v_prompt=s2v_prompt,
            web_prompt=web_prompt,
            image_pan_prompt=image_pan_prompt,
            image_zoom_prompt=image_zoom_prompt,
            web_search_prompt=self.gather_web_search_prompt(),
            image_edit_prompt=image_edit_prompt,
            z_image_extra_prompts=z_image_extra_prompts,
            t2v_batch_extra_prompts=t2v_batch_extra_prompts,
            minimax_h3_t2v_prompt=minimax_h3_t2v_prompt,
            minimax_h3_i2v_prompt=minimax_h3_i2v_prompt,
            minimax_h3_s2v_prompt=(s2v_prompt if scene_type == MINIMAX_H3_S2V_SCENE_TYPE else None),
            minimax_h3_r2v_prompt=(r2v_prompt if scene_type == MINIMAX_H3_R2V_SCENE_TYPE else None),
        )
        self._refresh_minimax_h3_json_prompt_widgets(
            minimax_h3_t2v_prompt,
            minimax_h3_i2v_prompt,
        )
        save_agentic_config(self.current_scene_dir, agentic_config)
        self.refresh_scene_status()
        if reload_list:
            self.reload_scene_list()
            self.select_scene_by_name(self.current_scene_dir.name)
        if not silent:
            self.statusBar().showMessage(f"Adegan {self.current_scene_dir.name} disimpan.", 3000)
        return True

    def open_scene_dialog(self, title):
        dialog = SceneTemplateDialog(self, title=title)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.get_data()

    def add_scene(self):
        if not self.ensure_project_selected():
            return
        data = self.open_scene_dialog("Tambah Adegan")
        if data is None:
            return
        project_dir = self.project_dir()
        if project_dir is None:
            QMessageBox.information(self, "Belum Ada Project", "Buka atau buat project terlebih dahulu.")
            return
        new_dir = create_scene_in_project(
            project_dir,
            scene_type=data["scene_type"],
            scene_title=data["scene_title"],
            duration=data["duration_seconds"],
        )
        self.reload_scene_list()
        self.select_scene_by_name(new_dir.name)

    def insert_scene(self):
        if not self.ensure_project_selected():
            return
        current = self.current_scene_path_from_ui()
        if current is None:
            self.add_scene()
            return
        self.release_media_locks()
        data = self.open_scene_dialog("Sisipkan Adegan")
        if data is None:
            return
        insert_index = int(current.name.split("_", 1)[1])
        project_dir = self.project_dir()
        if project_dir is None:
            QMessageBox.information(self, "Belum Ada Project", "Buka atau buat project terlebih dahulu.")
            return
        scenes = self.list_scene_dirs_current()
        temp_root = project_dir / "__insert_tmp__"
        if temp_root.exists():
            shutil.rmtree(temp_root)
        temp_root.mkdir(parents=True, exist_ok=True)
        for scene in scenes:
            target_index = int(scene.name.split("_", 1)[1])
            name = scene_dir_name(target_index + 1) if target_index >= insert_index else scene.name
            duplicate_directory(scene, temp_root / name)
        meta, z_prompt, wan_t2v_prompt, wan_prompt, s2v_prompt, web_prompt, image_pan_prompt, image_zoom_prompt, web_search_prompt = build_scene_templates(data["scene_title"], data["scene_type"], data["duration_seconds"])
        create_scene_files(
            temp_root / scene_dir_name(insert_index),
            meta=meta,
            z_prompt=z_prompt,
            wan_t2v_prompt=wan_t2v_prompt,
            wan_prompt=wan_prompt,
            wan22_s2v_prompt=s2v_prompt,
            web_scroll_prompt=web_prompt,
            image_pan_prompt=image_pan_prompt,
            image_zoom_prompt=image_zoom_prompt,
            web_search_prompt=web_search_prompt,
            t2v_batch_extra_prompts=DEFAULT_WAN22_T2V_BATCH_EXTRA_PROMPTS,
            minimax_h3_r2v_prompt=DEFAULT_MINIMAX_H3_R2V_PROMPT,
        )
        for scene in scenes:
            shutil.rmtree(scene)
        for child in sorted(temp_root.iterdir(), key=lambda p: p.name):
            child.rename(project_dir / child.name)
        temp_root.rmdir()
        self.reload_scene_list()
        self.select_scene_by_name(scene_dir_name(insert_index))

    def duplicate_scene(self):
        if not self.ensure_project_selected():
            return
        current = self.current_scene_path_from_ui()
        if current is None:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan yang akan digandakan terlebih dahulu.")
            return
        if self.is_viewing_variation():
            QMessageBox.information(
                self,
                "Mode Lihat Variasi",
                "Gandakan scene hanya bisa dilakukan saat melihat Root Scene.",
            )
            return

        project_dir = self.project_dir()
        if project_dir is None:
            QMessageBox.information(self, "Belum Ada Project", "Buka atau buat project terlebih dahulu.")
            return

        current_index = int(current.name.split("_", 1)[1])
        new_index = current_index + 1
        target = project_dir / scene_dir_name(new_index)
        while target.exists():
            new_index += 1
            target = project_dir / scene_dir_name(new_index)

        if not self.save_current_scene(silent=True, reload_list=False):
            return

        try:
            duplicate_directory(current, target)
        except Exception as e:
            QMessageBox.critical(self, "Gagal Gandakan", f"Gagal menggandakan scene:\n{e}")
            return

        self.reload_scene_list()
        self.select_scene_by_name(current.name)

    def delete_scene(self):
        if not self.ensure_project_selected():
            return
        current = self.current_scene_path_from_ui()
        if current is None:
            return
        self.release_media_locks()
        reply = QMessageBox.question(self, "Hapus Adegan", f"Hapus {current.name}?", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        if not current.exists():
            self.reload_scene_list()
            QMessageBox.information(
                self,
                "Adegan Tidak Ditemukan",
                f"Folder {current.name} sudah tidak ada. Daftar adegan telah dimuat ulang.",
            )
            return

        current_index = int(current.name.split("_", 1)[1])
        project_dir = self.project_dir()
        if project_dir is None:
            QMessageBox.information(self, "Belum Ada Project", "Buka atau buat project terlebih dahulu.")
            return

        scenes = self.list_scene_dirs_current()
        max_index = max((int(scene.name.split("_", 1)[1]) for scene in scenes), default=current_index)

        shutil.rmtree(current)

        # If deleting the last scene, nothing else needs renumbering.
        if current_index >= max_index:
            self.reload_scene_list()
            return

        # Only shift scenes after the deleted index down by one.
        temp_moves = []
        for old_index in range(current_index + 1, max_index + 1):
            src = project_dir / scene_dir_name(old_index)
            if not src.exists():
                continue
            temp = project_dir / f"__delete_tmp_{old_index}"
            if temp.exists():
                shutil.rmtree(temp)
            src.rename(temp)
            temp_moves.append((old_index, temp))

        for old_index, temp in temp_moves:
            temp.rename(project_dir / scene_dir_name(old_index - 1))

        self.reload_scene_list()

    def add_asset_to_scene(self):
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Pilih Aset")
        for file_path in files:
            src = Path(file_path)
            shutil.copy2(src, self.current_scene_dir / src.name)
        self.refresh_assets_and_previews()
        self.refresh_scene_status()
        self.statusBar().showMessage(f"{len(files)} aset ditambahkan ke {self.current_scene_dir.name}.", 3000)

    def select_scene_by_name(self, scene_name: str):
        for row in range(self.scene_list.count()):
            item = self.scene_list.item(row)
            if Path(item.data(Qt.UserRole)).name == scene_name:
                self.scene_list.setCurrentItem(item)
                return

    def snapshot_outputs(self, watch_dirs):
        snapshot = {}
        for directory in watch_dirs or []:
            snapshot.update(list_output_files(directory))
        return snapshot

    def collect_changed_outputs(self, watch_dirs, before_snapshot):
        changed = []
        before_snapshot = before_snapshot or {}
        for directory in watch_dirs or []:
            for path_str, mtime in list_output_files(directory).items():
                old_mtime = before_snapshot.get(path_str)
                if old_mtime is None or mtime > old_mtime + 1e-6:
                    changed.append(Path(path_str))
        changed.sort(key=lambda p: (str(p.parent).lower(), p.name.lower()))
        return changed

    def format_output_summary(self, outputs):
        if not outputs:
            return "Proses selesai tanpa file output baru yang terdeteksi."
        lines = []
        for path in outputs:
            rel_path = path.relative_to(ROOT) if ROOT in path.parents or path == ROOT else path
            lines.append(str(rel_path))
        return "File output:\n- " + "\n- ".join(lines)

    def build_z_image_skill_clipboard_text(self, positive_prompt: str, image_path: str | None = None):
        if not self.current_project_name:
            return None, "Belum ada project yang dibuka."
        if not self.current_scene_dir:
            return None, "Belum ada scene yang dipilih."

        size_label = self.z_size_input.currentText().strip()
        project_dir = self.project_dir()
        if project_dir is None:
            return None, "Belum ada project yang dibuka."
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        imagegen_skill_path = codex_home / "skills" / ".system" / "imagegen" / "SKILL.md"

        if image_path:
            prompt_text = (
                f"Gunakan skill Image Gen untuk mengedit gambar {image_path} dengan prompt :\n"
                f"{positive_prompt}. Ukuran gambar {size_label}.\n\n"
                f"Kemudian kopikan hasil image yang dibuat direktori project {project_dir.resolve()} "
                f"dalam scene {self.current_scene_dir.name}. Jangan lupa scale ke ukuran diminta tanpa strecth."
            )
        else:
            prompt_text = (
                f"[$imagegen]({imagegen_skill_path}) {positive_prompt}. "
                f"Ukuran gambar {size_label}.\n\n"
                f"Kemudian kopikan hasil image yang dibuat direktori project {project_dir.resolve()} "
                f"dalam scene {self.current_scene_dir.name}. Jangan lupa scale ke ukuran diminta tanpa strecth."
            )
        return prompt_text, None

    def copy_z_image_skill_prompt_to_clipboard(self):
        prompt_text, error = self.build_z_image_skill_clipboard_text(self.z_positive_input.toPlainText().strip())
        if error:
            QMessageBox.information(self, "Belum Siap", error)
            return
        QApplication.clipboard().setText(prompt_text)
        self.statusBar().showMessage("Teks Image Gen disalin ke clipboard.", 3000)

    def copy_extra_image_skill_prompt_to_clipboard(self, slot_index: int):
        if slot_index < 0 or slot_index >= len(self.z_extra_positive_inputs):
            QMessageBox.information(self, "Belum Siap", "Slot prompt tambahan tidak valid.")
            return
        prompt_text, error = self.build_z_image_skill_clipboard_text(
            self.z_extra_positive_inputs[slot_index].toPlainText().strip()
        )
        if error:
            QMessageBox.information(self, "Belum Siap", error)
            return
        QApplication.clipboard().setText(prompt_text)
        self.statusBar().showMessage(f"Teks Image Gen slot {slot_index + 1} disalin ke clipboard.", 3000)

    def copy_image_edit_prompt_to_clipboard(self, slot_index: int):
        if slot_index < 0 or slot_index >= len(self.image_edit_image_inputs):
            QMessageBox.information(self, "Belum Siap", "Slot edit gambar tidak valid.")
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Siap", "Belum ada scene yang dipilih.")
            return
        image_name = str(self.image_edit_image_inputs[slot_index].currentData() or "").strip()
        if not image_name:
            QMessageBox.information(self, "Belum Siap", f"Pilih gambar awal pada Edit Gambar {slot_index + 1}.")
            return
        image_path = str((self.current_scene_dir / image_name).resolve())
        prompt_text, error = self.build_z_image_skill_clipboard_text(
            self.image_edit_prompt_inputs[slot_index].toPlainText().strip(),
            image_path=image_path,
        )
        if error:
            QMessageBox.information(self, "Belum Siap", error)
            return
        QApplication.clipboard().setText(prompt_text)
        self.statusBar().showMessage(f"Teks Image Gen edit slot {slot_index + 1} disalin ke clipboard.", 3000)

    def _minimax_h3_prompt_reference_lines(self, stage: str, scene_type: str | None = None) -> list[str]:
        stage = str(stage or "").strip().lower()
        scene_type = str(scene_type or self.scene_type_combo.currentText() or "").strip()
        standalone_i2v = scene_type == MINIMAX_H3_I2V_SCENE_TYPE
        if stage == "r2v":
            template_path = "api_template/minimax_h3_r2v_api.json"
            output_path = MINIMAX_H3_R2V_PROMPT_FILENAME if scene_type == MINIMAX_H3_R2V_SCENE_TYPE else MINIMAX_H3_S2V_PROMPT_FILENAME
            if scene_type == MINIMAX_H3_R2V_SCENE_TYPE:
                reference_paths = [
                    "api_production/AGENT-SKILLS/SCENE-GENERAL.md",
                    "api_production/AGENT-SKILLS/SCENE-MINIMAX-H3-R2V.md",
                    "api_production/AGENT-SKILLS/MINIMAX-H3-R2V-PROMPT.md",
                ]
            else:
                reference_paths = [
                    "api_production/AGENT-SKILLS/SCENE-GENERAL.md",
                    "api_production/AGENT-SKILLS/SCENE-MINIMAX-H3-S2V.md",
                    "api_production/AGENT-SKILLS/MINIMAX-H3-S2V-PROMPT.md",
                    "api_production/AGENT-SKILLS/TEXT-TO-IMAGE.md",
                    "api_production/AGENT-SKILLS/IMAGE-PROMPT.md",
                ]
        elif stage == "t2v":
            template_path = "api_template/minimax_h3_t2v_api.json"
            output_path = "minimax_h3_t2v_prompt.json"
            reference_paths = [
                "api_production/AGENT-SKILLS/SCENE-GENERAL.md",
                "api_production/AGENT-SKILLS/SCENE-MINIMAX-H3-T2V-I2V.md",
                "api_production/AGENT-SKILLS/MINIMAX-H3-T2V-PROMPT.md",
            ]
        else:
            template_path = "api_template/minimax_h3_i2v_api.json"
            output_path = "minimax_h3_i2v_prompt.json"
            reference_paths = [
                "api_production/AGENT-SKILLS/SCENE-GENERAL.md",
                "api_production/AGENT-SKILLS/SCENE-MINIMAX-H3-I2V.md"
                if standalone_i2v
                else "api_production/AGENT-SKILLS/SCENE-MINIMAX-H3-T2V-I2V.md",
                "api_production/AGENT-SKILLS/MINIMAX-H3-I2V-PROMPT.md",
            ]
        reference_paths.append("api_production/AGENT-SKILLS/MINIMAX-H3-DIALOG.md")
        lines = [
            f"Authoritative workflow template file: {template_path}",
            f"Authoritative prompt output file: {output_path}",
            "Authoritative scene-building references for this MiniMax H3 stage: do not substitute another scene or stage template:",
        ]
        project_root = Path(__file__).resolve().parent
        for relative_path in reference_paths:
            reference_path = project_root / relative_path
            try:
                reference_text = reference_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                reference_text = f"Reference file could not be loaded: {exc}"
            lines.extend([
                f"--- BEGIN REFERENCE FILE: {relative_path} ---",
                reference_text,
                f"--- END REFERENCE FILE: {relative_path} ---",
            ])
        if stage == "r2v":
            if scene_type == MINIMAX_H3_R2V_SCENE_TYPE:
                active_images = self._r2v_selected_names(self.minimax_h3_r2v_image_list)[:3]
                active_audios = self._r2v_selected_names(self.minimax_h3_r2v_audio_list)[:3]
                active_video = bool(self._r2v_selected_names(self.minimax_h3_r2v_video_list))
                active_picture_tokens = ", ".join(f"<Picture {i + 1}>" for i, _ in enumerate(active_images)) or "none"
                active_audio_tokens = ", ".join(f"<Audio {i + 1}>" for i, _ in enumerate(active_audios)) or "none"
                active_video_token = "<Video 1>" if active_video else "none"
                active_reference_rule = (
                    "ACTIVE R2V MANIFEST OVERRIDE: only these reference tokens exist in this scene: "
                    f"Picture={active_picture_tokens}; Video={active_video_token}; Audio={active_audio_tokens}. "
                    "Ignore any Picture/Video/Audio tokens appearing in illustrative examples in the reference files. "
                    "Do not invent, rename, or renumber reference tokens. Non-reference tokens such as <Subject N>, "
                    "<Shot N>, <d>, </d>, and speaker IDs remain allowed."
                )
            else:
                active_reference_rule = (
                    "S2V ACTIVE MANIFEST: only <Picture 1> and <Audio 1> exist. "
                    "Do not use any other Picture, Video, or Audio token."
                )
            lines.extend([
                f"ACTIVE MODE OVERRIDE: Ref2VA / {'MiniMax H3 R2V' if scene_type == MINIMAX_H3_R2V_SCENE_TYPE else 'MiniMax H3 S2V'}.",
                "Use exactly six sections in this order: subject_definitions, summary, retention_analysis, detailed_description, overall_soundscape, non_diegetic_music.",
                "Write detailed_description as one timeline string. If the user requests multiple shots, mark them explicitly as [Shot 1], [Shot 2], and so on, with timing, action, camera, and continuity. Do not add a JSON shots array to Ref2VA.",
                active_reference_rule,
                "Return the prompt in English and preserve reference tokens exactly.",
                "This manifest has priority over all examples in the loaded skill/reference documents.",
            ])
        elif stage == "t2v":
            lines.extend([
                "ACTIVE STAGE OVERRIDE: T2VA.",
                "Use the shared scene-building references above, but apply only the Prompt T2VA rules for this request.",
                "The I2VA section describes a later workflow stage and is not active here.",
                "Do not output any first-frame or image-alignment instruction, especially the sentence beginning `For the target video, at 0.00 seconds`.",
                "The English prompt must begin directly with `integrated_multimodal_description:`.",
            ])
        else:
            lines.extend([
                "ACTIVE STAGE OVERRIDE: I2VA.",
                "Use the shared scene-building references above, but apply the Prompt I2VA rules for this request.",
                "The English prompt must begin exactly with `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.` followed by one blank line.",
                "The first shot visual must use exactly `At 0.00 seconds, <Picture 1> is the first frame of the video`; the application will overwrite this field with the exact English and Indonesian sentences after generation.",
                "Describe the selected Picture 1 image first, then describe motion developing continuously from that exact initial state.",
            ])
        return lines

    def _build_prompt_generation_context(
        self,
        prompt_kind: str,
        slot_index: int | None = None,
        prompt_key: str | None = None,
    ) -> str:
        scene_title = self.scene_title_input.text().strip() or "(tanpa judul)"
        scene_type = self.scene_type_combo.currentText().strip() or "(unknown)"
        lines = [
            f"Scene title: {scene_title}",
            f"Scene type: {scene_type}",
        ]
        if prompt_kind == "z_image":
            image_model = str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO).strip()
            size_data = self.z_size_input.currentData() or (368, 640)
            lines.extend([
                "Target: initial image positive prompt",
                f"Image model: {image_model}",
                f"Image size: {int(size_data[0])}x{int(size_data[1])}",
                f"Random seed: {'yes' if self.z_use_random_seed_input.isChecked() else 'no'}",
                f"Lora enabled: {'yes' if self.z_use_lora_input.isChecked() else 'no'}",
            ])
        elif prompt_kind == "z_extra":
            image_model = str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO).strip()
            size_data = self.z_size_input.currentData() or (368, 640)
            lines.extend([
                f"Target: extra image prompt slot {slot_index + 1 if slot_index is not None else 1}",
                f"Image model: {image_model}",
                f"Image size: {int(size_data[0])}x{int(size_data[1])}",
            ])
        elif prompt_kind == "image_edit":
            edit_model = str(self.image_edit_model_input.currentData() or MODEL_FLUX2).strip()
            source_name = ""
            if slot_index is not None and 0 <= slot_index < len(self.image_edit_image_inputs):
                source_name = str(self.image_edit_image_inputs[slot_index].currentData() or "").strip()
            lines.extend([
                f"Target: image edit prompt slot {slot_index + 1 if slot_index is not None else 1}",
                f"Edit model: {edit_model}",
                f"Source image: {source_name or '(none)'}",
            ])
        elif prompt_kind == "wan_t2v":
            size_data = self.wan_t2v_size_input.currentData() or (368, 640)
            lines.extend([
                f"Target: WAN22 T2V prompt field `{prompt_key or 'unknown'}`",
                f"Scene duration: {self._duration_text() or '10'}",
                f"WAN22 T2V size: {int(size_data[0])}x{int(size_data[1])}",
            ])
        elif prompt_kind == "wan_i2v":
            size_data = self.wan_size_input.currentData() or (368, 640)
            lines.extend([
                f"Target: WAN I2V prompt field `{prompt_key or 'unknown'}`",
                f"WAN duration: from scene_meta.json",
                f"WAN size: {int(size_data[0])}x{int(size_data[1])}",
            ])
        elif prompt_kind == "minimax_h3_t2v":
            size_data = self.minimax_h3_t2v_size_input.currentData() or (368, 640)
            lines.extend([
                "Target: MiniMax H3 T2VA positive prompt",
                "Active MiniMax H3 mode: T2VA",
                "T2VA format: return integrated_multimodal_description, overall_soundscape, and non_diegetic_music in English.",
                f"Scene duration: {self._duration_text() or '10'}",
                f"MiniMax H3 T2V size: {int(size_data[0])}x{int(size_data[1])}",
            ])
            lines.extend(self._minimax_h3_prompt_reference_lines("t2v", scene_type=scene_type))
        elif prompt_kind in {"minimax_h3_i2v", "minimax_h3_i2v_standalone"}:
            size_data = self.minimax_h3_i2v_size_input.currentData() or (368, 640)
            lines.extend([
                "Target: MiniMax H3 I2VA positive prompt",
                "Active MiniMax H3 mode: I2VA",
                "I2VA format: begin with the exact first-frame alignment instruction, then return the fields required by the referenced skill.",
                f"Scene duration: {self._duration_text() or '10'}",
                f"MiniMax H3 I2V size: {int(size_data[0])}x{int(size_data[1])}",
            ])
            lines.extend(self._minimax_h3_prompt_reference_lines("i2v", scene_type=scene_type))
        elif prompt_kind == "wan_s2v":
            size_data = self.s2v_size_input.currentData() or (480, 848)
            lines.extend([
                f"Target: WAN22 S2V prompt field `{prompt_key or 'unknown'}`",
                f"WAN22 S2V size: {int(size_data[0])}x{int(size_data[1])}",
                f"WAN22 S2V cfg: {float(self.s2v_cfg_input.value()):.1f}",
            ])
        elif prompt_kind == "minimax_h3_s2v":
            size_data = self.s2v_size_input.currentData() or (368, 640)
            lines.extend([
                "Target: MiniMax H3 S2V Ref2VA positive prompt",
                "Active MiniMax H3 mode: Ref2VA",
                "Use only Picture 1 and Audio 1.",
                "The prompt must contain the six Ref2VA sections in the required order.",
                f"MiniMax H3 S2V size: {int(size_data[0])}x{int(size_data[1])}",
                "Audio duration is determined from the selected speech audio and must be at most 15 seconds.",
            ])
            lines.extend(self._minimax_h3_prompt_reference_lines("r2v", scene_type=scene_type))
        elif prompt_kind == "minimax_h3_r2v":
            size_data = self.minimax_h3_r2v_size_input.currentData() or (368, 640)
            references = {
                "images": self._r2v_selected_names(self.minimax_h3_r2v_image_list)[:3],
                "video": (self._r2v_selected_names(self.minimax_h3_r2v_video_list) or [""])[0],
                "audios": self._r2v_selected_names(self.minimax_h3_r2v_audio_list)[:3],
            }
            lines.extend([
                "Target: MiniMax H3 R2V Ref2VA positive prompt",
                "Active MiniMax H3 mode: Ref2VA",
                "STRICT REFERENCE RULE: use only the active Picture, Video, and Audio tokens listed below; never invent, rename, or renumber them.",
                f"Active image references: {', '.join(f'<Picture {i + 1}>' for i, _ in enumerate(references['images'])) or '(none)'}",
                f"Active video reference: {'<Video 1>' if references['video'] else '(none)'}",
                f"Active audio references: {', '.join(f'<Audio {i + 1}>' for i, _ in enumerate(references['audios'])) or '(none)'}",
                "If a category is marked (none), do not mention that reference category.",
                "Do not use any unavailable <Picture N>, <Video N>, or <Audio N> token.",
                "Non-reference semantic tokens such as <Subject N>, <Shot N>, <d>, </d>, and speaker IDs remain allowed.",
                "Keep every active reference token exactly unchanged across all six Ref2VA sections.",
                "The prompt must contain the six Ref2VA sections in the required order.",
                f"Scene duration: {self._duration_text() or '10'} seconds (maximum 15).",
                f"MiniMax H3 R2V size: {int(size_data[0])}x{int(size_data[1])}",
            ])
            lines.extend(self._minimax_h3_prompt_reference_lines("r2v", scene_type=scene_type))
        return "\n".join(lines)

    def _set_prompt_widget_text(
        self,
        prompt_kind: str,
        slot_index: int | None,
        text: str,
        prompt_key: str | None = None,
    ):
        if prompt_kind == "z_image":
            self.z_positive_input.setPlainText(text)
            return
        if prompt_kind == "z_extra" and slot_index is not None and 0 <= slot_index < len(self.z_extra_positive_inputs):
            self.z_extra_positive_inputs[slot_index].setPlainText(text)
            return
        if prompt_kind == "image_edit" and slot_index is not None and 0 <= slot_index < len(self.image_edit_prompt_inputs):
            self.image_edit_prompt_inputs[slot_index].setPlainText(text)
            return
        if prompt_kind == "wan_t2v":
            if prompt_key == "positive_prompt":
                self.wan_t2v_positive_input.setPlainText(text)
                return
            if prompt_key == "negative_prompt":
                self.wan_t2v_negative_input.setPlainText(text)
                return
        if prompt_kind == "t2v_batch" and slot_index is not None and 0 <= slot_index < len(self.t2v_batch_positive_inputs):
            self.t2v_batch_positive_inputs[slot_index].setPlainText(text)
            return
        if prompt_kind == "wan_i2v" and prompt_key in self.wan_prompt_inputs:
            self.wan_prompt_inputs[prompt_key].setPlainText(text)
            return
        if prompt_kind == "minimax_h3_t2v" and prompt_key == "positive_prompt":
            self.minimax_h3_t2v_positive_input.setPlainText(text)
            return
        if prompt_kind in {"minimax_h3_i2v", "minimax_h3_i2v_standalone"} and prompt_key == "positive_prompt":
            self.minimax_h3_i2v_positive_input.setPlainText(text)
            return
        if prompt_kind == "wan_s2v":
            if prompt_key == "positive_prompt":
                self.s2v_positive_input.setPlainText(text)
                return
            if prompt_key == "negative_prompt":
                self.s2v_negative_input.setPlainText(text)
        if prompt_kind == "minimax_h3_s2v" and prompt_key == "positive_prompt":
            self.s2v_positive_input.setPlainText(text)
        if prompt_kind == "minimax_h3_r2v" and prompt_key == "positive_prompt":
            self.minimax_h3_r2v_positive_input.setPlainText(text)

    def _prompt_file_and_key(self, prompt_kind: str, prompt_key: str | None = None):
        if prompt_kind == "z_image":
            return self.current_scene_dir / "z_image_prompt.json", "positive_prompt", None
        if prompt_kind == "z_extra":
            return self.current_scene_dir / "z_image_extra_prompts.json", "positive_prompt", None
        if prompt_kind == "image_edit":
            return self.current_scene_dir / "image_edit_prompt.json", "prompt", None
        if prompt_kind == "wan_t2v":
            return self.current_scene_dir / "wan22_t2v_prompt.json", str(prompt_key or "").strip(), None
        if prompt_kind == "t2v_batch":
            return self.current_scene_dir / "wan22_t2v_batch_extra_prompts.json", "positive_prompt", None
        if prompt_kind == "wan_i2v":
            return self.current_scene_dir / "wan22_i2v_prompt.json", str(prompt_key or "").strip(), None
        if prompt_kind == "minimax_h3_t2v":
            return self.current_scene_dir / "minimax_h3_t2v_prompt.json", "positive_prompt", None
        if prompt_kind == "minimax_h3_i2v":
            return self.current_scene_dir / "minimax_h3_i2v_prompt.json", "positive_prompt", None
        if prompt_kind == "minimax_h3_i2v_standalone":
            return self.current_scene_dir / "minimax_h3_i2v_prompt.json", "positive_prompt", None
        if prompt_kind == "wan_s2v":
            return self.current_scene_dir / "wan22_s2v_prompt.json", str(prompt_key or "").strip(), None
        if prompt_kind == "minimax_h3_s2v":
            return self.current_scene_dir / MINIMAX_H3_S2V_PROMPT_FILENAME, "positive_prompt", None
        if prompt_kind == "minimax_h3_r2v":
            return self.current_scene_dir / MINIMAX_H3_R2V_PROMPT_FILENAME, "positive_prompt", None
        raise ValueError(f"prompt_kind tidak dikenal: {prompt_kind}")

    def _prompt_group_index(self, prompt_kind: str, slot_index: int | None):
        if prompt_kind in {"z_extra", "image_edit", "t2v_batch"} and slot_index is not None:
            return slot_index
        return None

    def _start_prompt_generation(
        self,
        prompt_kind: str,
        slot_index: int | None,
        prompt_text: str,
        prompt_key: str | None = None,
    ):
        if not self.ensure_project_selected():
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        # Buat Prompt memakai nilai yang sedang tampil di UI dan tidak perlu
        # menyimpan scene terlebih dahulu.
        process_dialog = self.ensure_process_dialog()
        process_dialog.show()
        process_dialog.raise_()
        process_dialog.activateWindow()
        self.log_output.clear()
        prompt_text = str(prompt_text or "").strip()
        if not prompt_text:
            QMessageBox.warning(self, "Data Tidak Valid", "Prompt yang akan diproses tidak boleh kosong.")
            return

        context_text = self._build_prompt_generation_context(
            prompt_kind,
            slot_index=slot_index,
            prompt_key=prompt_key,
        )
        scene_dir = Path(self.current_scene_dir)
        prompt_label = {
            "z_image": "Gambar Awal",
            "z_extra": f"Prompt Tambahan {slot_index + 1 if slot_index is not None else 1}",
            "image_edit": f"Edit Gambar {slot_index + 1 if slot_index is not None else 1}",
            "wan_t2v": f"WAN T2V ({prompt_key or 'prompt'})",
            "wan_i2v": f"WAN I2V ({prompt_key or 'prompt'})",
            "minimax_h3_t2v": "MiniMax H3 T2VA",
            "minimax_h3_i2v": "MiniMax H3 I2VA",
            "minimax_h3_s2v": "MiniMax H3 Ref2VA",
            "minimax_h3_r2v": "MiniMax H3 R2V Ref2VA",
            "wan_s2v": f"WAN22 S2V ({prompt_key or 'prompt'})",
        }.get(prompt_kind, prompt_kind)

        self.log_output.clear()
        self.append_log(f"Membuat prompt {prompt_label} untuk {scene_dir.name}")
        prompt_provider = str(
            self.project_settings.get("prompt_generation", {}).get(
                "provider", DEFAULT_PROJECT_SETTINGS["prompt_generation"]["provider"]
            )
        ).strip().lower() or DEFAULT_PROJECT_SETTINGS["prompt_generation"]["provider"]
        prompt_model = str(
            self.project_settings.get("prompt_generation", {}).get(
                "model", DEFAULT_PROJECT_SETTINGS["prompt_generation"]["model"]
            )
        ).strip() or DEFAULT_PROJECT_SETTINGS["prompt_generation"]["model"]
        self.append_log(f"Provider prompt generation: {prompt_provider} ({prompt_model})")
        if prompt_kind in {"minimax_h3_t2v", "minimax_h3_i2v", "minimax_h3_i2v_standalone", "minimax_h3_s2v", "minimax_h3_r2v"}:
            self.append_log("LLM MiniMax dipanggil dalam dua tahap: generate `en`, lalu terjemahkan field menjadi `id_new`; `id_old` adalah salinan `id_new`.")
        else:
            self.append_log("LLM dipanggil sekali untuk mengembalikan `en` dan `id_new`; `id_old` akan disamakan dengan `id_new`.")

        if self.prompt_generation_thread is not None and self.prompt_generation_thread.isRunning():
            self.append_log("[warning] Proses buat prompt sebelumnya masih berjalan. Tunggu selesai dulu.")
            self.statusBar().showMessage("Proses buat prompt masih berjalan.", 4000)
            return

        self.prompt_generation_context = {
            "prompt_kind": prompt_kind,
            "slot_index": slot_index,
            "scene_dir": scene_dir,
            "prompt_key": str(prompt_key or "").strip(),
        }

        self.prompt_generation_thread = QThread(self)
        self.prompt_generation_worker = PromptGenerationWorker(
            prompt_text,
            context_text,
            project_dir=str(self.project_dir() or ""),
        )
        self.prompt_generation_worker.moveToThread(self.prompt_generation_thread)
        self.prompt_generation_worker.progress.connect(self.append_log)
        self.prompt_generation_thread.started.connect(self.prompt_generation_worker.run)
        self.prompt_generation_worker.finished.connect(self._on_prompt_generation_finished)
        self.prompt_generation_worker.failed.connect(self._on_prompt_generation_failed)
        self.prompt_generation_worker.finished.connect(self.prompt_generation_thread.quit)
        self.prompt_generation_worker.failed.connect(self.prompt_generation_thread.quit)
        self.prompt_generation_thread.finished.connect(self._cleanup_prompt_generation_thread)
        self.statusBar().showMessage("Membuat prompt dengan LLM...", 3000)
        self.prompt_generation_thread.start()

    def _cleanup_prompt_generation_thread(self):
        if self.prompt_generation_worker is not None:
            self.prompt_generation_worker.deleteLater()
        if self.prompt_generation_thread is not None:
            self.prompt_generation_thread.deleteLater()
        self.prompt_generation_worker = None
        self.prompt_generation_thread = None
        self.prompt_generation_context = None

    def _on_prompt_generation_failed(self, error: str):
        ctx = self.prompt_generation_context or {}
        prompt_kind = str(ctx.get("prompt_kind", "unknown"))
        self.append_log(f"[gagal] Prompt generation {prompt_kind}: {error}")
        self.statusBar().showMessage("Gagal membuat prompt.", 4000)

    def _on_prompt_generation_finished(self, result: dict):
        ctx = self.prompt_generation_context or {}
        prompt_kind = str(ctx.get("prompt_kind", "unknown"))
        slot_index = ctx.get("slot_index")
        scene_dir = ctx.get("scene_dir")
        prompt_key = str(ctx.get("prompt_key", "")).strip() or None
        if not isinstance(scene_dir, Path):
            scene_dir = Path(self.current_scene_dir) if self.current_scene_dir else Path(".")
        if not isinstance(result, dict):
            self.append_log("[gagal] Hasil LLM tidak valid.")
            return
        if prompt_kind in {"minimax_h3_t2v", "minimax_h3_i2v", "minimax_h3_i2v_standalone", "minimax_h3_s2v", "minimax_h3_r2v"}:
            structured = result.get("structured")
            if prompt_kind in {"minimax_h3_s2v", "minimax_h3_r2v"}:
                entry = structured.get("positive_prompt") if isinstance(structured, dict) else None
                if isinstance(entry, dict) and isinstance(entry.get("en"), dict):
                    entry["id_old"] = copy.deepcopy(entry.get("id_new", {}))
                    entry["id_new"] = copy.deepcopy(entry.get("id_new", {}))
                errors = [] if isinstance(entry, dict) and not validate_ref2va_prompt(entry.get("en")) else validate_ref2va_prompt(entry.get("en") if isinstance(entry, dict) else None)
                if not errors and prompt_kind == "minimax_h3_r2v":
                    errors.extend(validate_ref2va_reference_tokens(
                        entry.get("en"),
                        image_count=len(self._r2v_selected_names(self.minimax_h3_r2v_image_list)),
                        audio_count=len(self._r2v_selected_names(self.minimax_h3_r2v_audio_list)),
                        has_video=bool(self._r2v_selected_names(self.minimax_h3_r2v_video_list)),
                    ))
                if not errors and prompt_kind == "minimax_h3_s2v":
                    errors.extend(validate_ref2va_reference_tokens(
                        entry.get("en"),
                        image_count=1,
                        audio_count=1,
                        has_video=False,
                    ))
            else:
                expected_mode = "I2VA" if prompt_kind != "minimax_h3_t2v" else "T2VA"
                entry, errors = parse_structured_response(structured, expected_mode=expected_mode)
                if not errors and expected_mode == "I2VA":
                    entry = enforce_i2va_first_shot_visual(entry)
            if errors:
                self.append_log("[gagal] Response nested MiniMax tidak valid: " + "; ".join(errors[:3]))
                self.statusBar().showMessage("Format JSON MiniMax tidak sesuai.", 4000)
                return
            try:
                prompt_path, field_key, _ = self._prompt_file_and_key(prompt_kind, prompt_key=prompt_key)
                payload = json.loads(prompt_path.read_text(encoding="utf-8")) if prompt_path.exists() else {}
                payload[field_key] = entry
                write_prompt_json(prompt_path, payload)
            except Exception as e:
                self.append_log(f"[gagal] Gagal menyimpan JSON nested MiniMax: {e}")
                return
            id_new_value = entry.get("id_new", {})
            loaded_into_ui = self._load_generated_minimax_id_new_into_ui(
                prompt_kind,
                scene_dir,
                id_new_value,
            )
            if loaded_into_ui:
                # Run once more after the current signal callback returns so a
                # pending paint/layout event cannot leave the old text visible.
                QTimer.singleShot(
                    0,
                    lambda kind=prompt_kind, target=scene_dir, value=copy.deepcopy(id_new_value):
                        self._load_generated_minimax_id_new_into_ui(kind, target, value),
                )
                self.refresh_scene_status()
            else:
                self.append_log(
                    f"[warning] Prompt tersimpan, tetapi id_new tidak dimuat ke UI; target={scene_dir.name}"
                )
            self.append_log(
                f"[sukses] JSON nested prompt disimpan ke {prompt_path.name}; "
                f"id_new dimuat ke UI={loaded_into_ui}"
            )
            self.statusBar().showMessage("Prompt MiniMax berhasil dibuat.", 4000)
            return
        english = str(result.get("en", "")).strip()
        indonesian = str(result.get("id_new", "")).strip()
        if not english and not indonesian:
            self.append_log("[gagal] LLM tidak mengembalikan prompt yang valid.")
            return
        if prompt_kind in {"minimax_h3_i2v", "minimax_h3_i2v_standalone"}:
            if not english or not indonesian:
                self.append_log(
                    "[gagal] Prompt MiniMax H3 I2VA wajib memiliki `en` dan `id_new`."
                )
                self.statusBar().showMessage("Format prompt I2VA tidak lengkap.", 4000)
                return
            if not is_valid_minimax_h3_i2v_prompt(english):
                self.append_log(
                    "[gagal] Prompt Inggris MiniMax H3 I2VA tidak mengikuti format alignment dan tiga section wajib."
                )
                self.statusBar().showMessage("Format prompt I2VA tidak sesuai skill.", 4000)
                return
        if not indonesian:
            indonesian = english

        try:
            prompt_path, field_key, _ = self._prompt_file_and_key(prompt_kind, prompt_key=prompt_key)
            if not field_key:
                raise ValueError(f"Key prompt tidak valid untuk {prompt_kind}.")
            group_index = self._prompt_group_index(prompt_kind, slot_index)
            if prompt_path.exists():
                with prompt_path.open("r", encoding="utf-8") as f:
                    payload = json.load(f)
            else:
                payload = {}
            updated = update_generated_prompt_entry(
                prompt_path.name,
                payload,
                field_key,
                indonesian,
                english,
                group_index=group_index,
            )
            write_json(prompt_path, updated)
        except Exception as e:
            self.append_log(f"[gagal] Gagal menyimpan hasil prompt ke {prompt_path.name}: {e}")
            return

        if self.current_scene_dir and self.current_scene_dir.resolve() == scene_dir.resolve():
            self._set_prompt_widget_text(prompt_kind, slot_index, indonesian, prompt_key=prompt_key)
            self.save_current_scene(silent=True, reload_list=False)
            self.refresh_scene_status()
        self.append_log(f"[sukses] Prompt disimpan ke {prompt_path.name}")
        self.statusBar().showMessage("Prompt berhasil dibuat.", 4000)

    def generate_z_prompt_from_ui(self):
        self._start_prompt_generation("z_image", None, self.z_positive_input.toPlainText().strip())

    def generate_extra_prompt_from_ui(self, slot_index: int):
        if slot_index < 0 or slot_index >= len(self.z_extra_positive_inputs):
            QMessageBox.information(self, "Belum Siap", "Slot prompt tambahan tidak valid.")
            return
        self._start_prompt_generation("z_extra", slot_index, self.z_extra_positive_inputs[slot_index].toPlainText().strip())

    def generate_image_edit_prompt_from_ui(self, slot_index: int):
        if slot_index < 0 or slot_index >= len(self.image_edit_prompt_inputs):
            QMessageBox.information(self, "Belum Siap", "Slot edit gambar tidak valid.")
            return
        self._start_prompt_generation("image_edit", slot_index, self.image_edit_prompt_inputs[slot_index].toPlainText().strip())

    def generate_wan_prompt_from_ui(self, prompt_key: str, prompt_kind: str = "wan_i2v"):
        key = str(prompt_key or "").strip()
        prompt_kind = str(prompt_kind or "wan_i2v").strip()
        if prompt_kind == "wan_t2v":
            if key != "positive_prompt":
                QMessageBox.information(self, "Belum Siap", "Buat Prompt hanya tersedia untuk Prompt Positif WAN22 T2V.")
                return
            widget = self.wan_t2v_positive_input
        elif prompt_kind == "wan_i2v":
            if not key.startswith("positive_prompt_"):
                QMessageBox.information(self, "Belum Siap", "Buat Prompt hanya tersedia untuk Prompt Positif WAN.")
                return
            widget = self.wan_prompt_inputs.get(key)
        else:
            QMessageBox.information(self, "Belum Siap", "Buat Prompt tidak tersedia untuk field ini.")
            return
        if widget is None:
            QMessageBox.information(self, "Belum Siap", "Field prompt WAN tidak valid.")
            return
        self._start_prompt_generation(prompt_kind, None, widget.toPlainText().strip(), prompt_key=key)

    def generate_minimax_h3_prompt_from_ui(self, stage: str):
        stage = str(stage or "").strip().lower()
        scene_type = self.scene_type_combo.currentText().strip()
        if stage == "t2v":
            prompt_kind = "minimax_h3_t2v"
            widget = self.minimax_h3_t2v_positive_input
        elif stage == "i2v":
            prompt_kind = (
                "minimax_h3_i2v_standalone"
                if scene_type == MINIMAX_H3_I2V_SCENE_TYPE
                else "minimax_h3_i2v"
            )
            widget = self.minimax_h3_i2v_positive_input
        else:
            QMessageBox.information(self, "Belum Siap", "Tahap prompt MiniMax H3 tidak valid.")
            return
        self._start_prompt_generation(
            prompt_kind,
            None,
            widget.toPlainText().strip(),
            prompt_key="positive_prompt",
        )

    def generate_s2v_prompt_from_ui(self, prompt_key: str):
        key = str(prompt_key or "").strip()
        if key != "positive_prompt":
            QMessageBox.information(self, "Belum Siap", "Buat Prompt hanya tersedia untuk Prompt Positif S2V.")
            return
        prompt_text = self.s2v_positive_input.toPlainText().strip()
        prompt_kind = "minimax_h3_s2v" if self.scene_type_combo.currentText().strip() == MINIMAX_H3_S2V_SCENE_TYPE else "wan_s2v"
        self._start_prompt_generation(prompt_kind, None, prompt_text, prompt_key=key)

    def generate_r2v_prompt_from_ui(self):
        prompt_text = self.minimax_h3_r2v_positive_input.toPlainText().strip()
        self._start_prompt_generation(
            "minimax_h3_r2v",
            None,
            prompt_text,
            prompt_key="positive_prompt",
        )

    def tail_process_log(self, max_lines=12):
        text = self.log_output.toPlainText().strip()
        if not text:
            return ""
        lines = text.splitlines()
        return "\n".join(lines[-max_lines:])

    def start_process(self, script_path: Path, args, title, watch_dirs=None, extra_context=None):
        python_exe = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            QMessageBox.information(self, "Proses Sedang Berjalan", "Tunggu proses yang sedang berjalan selesai terlebih dahulu.")
            return False
        self.process = QProcess(self)
        self.process_context = {
            "title": title,
            "watch_dirs": list(watch_dirs or []),
            "before_snapshot": self.snapshot_outputs(watch_dirs or []),
        }
        if isinstance(extra_context, dict):
            self.process_context.update(extra_context)
        self.process.setProgram(str(python_exe))
        self.process.setArguments([str(script_path), *args])
        self.process.setWorkingDirectory(str(ROOT))
        self.process.readyReadStandardOutput.connect(self.on_process_stdout)
        self.process.readyReadStandardError.connect(self.on_process_stderr)
        self.process.finished.connect(self.on_process_finished)
        self.log_output.clear()
        self.append_log(f"{title} dengan {python_exe}")
        self.process.start()
        if not self.process.waitForStarted(3000):
            self.process_context = None
            QMessageBox.critical(self, "Proses Gagal", "Gagal memulai proses.")
            self.process = None
            return False
        return True

    def confirm_run_action(self, title: str, message: str):
        reply = QMessageBox.question(self, title, message, QMessageBox.Yes | QMessageBox.No)
        return reply == QMessageBox.Yes

    def run_current_scene(self):
        if not self.confirm_run_action("Jalankan Adegan", "Jalankan adegan yang sedang dipilih?"):
            return
        self._run_current_scene()

    def _run_current_scene(self):
        if not self.ensure_project_selected():
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.save_current_scene():
            return
        if not self.ensure_scene_is_runnable(self.current_scene_dir):
            return
        self.start_process(
            MAIN_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name, "--scene", self.current_scene_dir.name],
            f"Menjalankan {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def run_all_scenes(self):
        if not self.confirm_run_action("Jalankan Semua Adegan", "Jalankan semua adegan?"):
            return
        self._run_all_scenes()

    def _run_all_scenes(self):
        if not self.ensure_project_selected():
            return
        if self.current_scene_dir:
            self.save_current_scene(silent=True)
        if not self.ensure_all_scenes_are_runnable():
            return
        self.start_process(
            MAIN_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name],
            "Menjalankan semua adegan",
            watch_dirs=self.list_scene_dirs_current(),
        )

    def generate_initial_image_only(self):
        if not self.confirm_run_action("Buat Gambar Awal", "Buat gambar awal untuk adegan yang sedang dipilih?"):
            return
        self._generate_initial_image_only()

    def _generate_initial_image_only(self):
        if not self.ensure_project_selected():
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        scene_type = self.scene_type_combo.currentText().strip()
        if not scene_type_supports_initial_image(scene_type):
            QMessageBox.information(
                self,
                "Tidak Tersedia",
                f"Buat Gambar Awal tidak tersedia untuk scene {scene_type or '-'}.",
            )
            return
        if not self.save_current_scene():
            return
        self.start_process(
            INITIAL_IMAGE_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name, "--scene", self.current_scene_dir.name],
            f"Membuat gambar awal untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def run_extra_image_slot(self, slot_index: int):
        if slot_index < 0 or slot_index >= len(self.z_extra_positive_inputs):
            return
        if not self.ensure_project_selected():
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.save_current_scene():
            return

        positive_prompt = self.z_extra_positive_inputs[slot_index].toPlainText().strip()
        if not positive_prompt:
            QMessageBox.warning(self, "Data Tidak Valid", f"Prompt Positif pada Prompt Tambahan {slot_index + 1} wajib diisi.")
            return

        self.start_process(
            INITIAL_IMAGE_SCRIPT,
            [
                "--server", self.comfyui_server_address(),
                "--project", self.current_project_name,
                "--scene", self.current_scene_dir.name,
                "--prompt-file", "z_image_extra_prompts.json",
                "--prompt-index", str(slot_index + 1),
            ],
            f"Membuat image tambahan {slot_index + 1} untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def run_t2v_batch_prompt_generation(self, slot_index: int):
        self.append_log(f"[debug] run_t2v_batch_prompt_generation called, slot={slot_index}")
        if slot_index < 0 or slot_index >= len(self.t2v_batch_positive_inputs):
            self.append_log(f"[debug] Invalid slot_index={slot_index}")
            return
        if not self.ensure_project_selected():
            self.append_log("[debug] ensure_project_selected failed")
            return
        if not self.current_scene_dir:
            self.append_log("[debug] current_scene_dir is None")
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        positive_text = self.t2v_batch_positive_inputs[slot_index].toPlainText().strip()
        self.append_log(f"[debug] positive_text len={len(positive_text)}")
        if not positive_text:
            QMessageBox.warning(self, "Data Tidak Valid", f"Prompt Positif pada Prompt Tambahan {slot_index + 1} wajib diisi.")
            return
        # Read context from wan_t2v_prompt and scene_meta
        try:
            wan_t2v_prompt = load_json(self.current_scene_dir / "wan22_t2v_prompt.json", DEFAULT_WAN22_T2V_PROMPT)
            scene_meta = load_json(self.current_scene_dir / "scene_meta.json", DEFAULT_SCENE_META)
            project_settings = load_project_settings_file(self.project_dir())
            context = f"Project: {project_settings.get('project_description', '')}\nScene: {scene_meta.get('scene_description', '')}"
            self.append_log(f"[debug] Context built, calling _start_prompt_generation...")
        except Exception as e:
            self.append_log(f"[debug] Error reading context: {e}")
            return
        # Store slot_index so _handle_prompt_generation_finished can update the correct field
        self._pending_t2v_batch_slot = slot_index
        self._start_prompt_generation("t2v_batch", slot_index, positive_text, context_text=context)

    def _start_prompt_generation(
        self,
        prompt_kind: str,
        slot_index: int | None = None,
        prompt_text: str | None = None,
        prompt_key: str | None = None,
        context_text: str | None = None,
    ):
        if not self.ensure_project_selected():
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        # Buat Prompt memakai nilai yang sedang tampil di UI dan tidak perlu
        # menyimpan scene terlebih dahulu.
        process_dialog = self.ensure_process_dialog()
        process_dialog.show()
        process_dialog.raise_()
        process_dialog.activateWindow()
        self.log_output.clear()
        prompt_text = str(prompt_text or "").strip()
        if not prompt_text:
            QMessageBox.warning(self, "Data Tidak Valid", "Prompt yang akan diproses tidak boleh kosong.")
            return

        # Support both old signature (prompt_kind, slot_index, prompt_text, prompt_key)
        # and new signature with explicit context_text for t2v_batch
        if context_text is not None and prompt_text is not None:
            # t2v_batch mode: use provided context_text directly
            pass
        elif prompt_text is not None:
            # Standard mode: build context from prompt_kind
            context_text = self._build_prompt_generation_context(
                prompt_kind,
                slot_index=slot_index,
                prompt_key=prompt_key,
            )
        else:
            raise TypeError("_start_prompt_generation requires valid arguments")

        scene_dir = Path(self.current_scene_dir)
        prompt_label = {
            "z_image": "Gambar Awal",
            "z_extra": f"Prompt Tambahan {slot_index + 1 if slot_index is not None else 1}",
            "image_edit": f"Edit Gambar {slot_index + 1 if slot_index is not None else 1}",
            "wan_t2v": f"WAN T2V ({prompt_key or 'prompt'})",
            "wan_i2v": f"WAN I2V ({prompt_key or 'prompt'})",
            "minimax_h3_t2v": "MiniMax H3 T2VA",
            "minimax_h3_i2v": "MiniMax H3 I2VA",
            "minimax_h3_i2v_standalone": "MiniMax H3 I2VA",
            "wan_s2v": f"WAN22 S2V ({prompt_key or 'prompt'})",
            "t2v_batch": f"Prompt Tambahan {slot_index + 1 if slot_index is not None else 1}",
        }.get(prompt_kind, prompt_kind)

        self.log_output.clear()
        self.append_log(f"Membuat prompt {prompt_label} untuk {scene_dir.name}")
        prompt_provider = str(
            self.project_settings.get("prompt_generation", {}).get(
                "provider", DEFAULT_PROJECT_SETTINGS["prompt_generation"]["provider"]
            )
        ).strip().lower() or DEFAULT_PROJECT_SETTINGS["prompt_generation"]["provider"]
        prompt_model = str(
            self.project_settings.get("prompt_generation", {}).get(
                "model", DEFAULT_PROJECT_SETTINGS["prompt_generation"]["model"]
            )
        ).strip() or DEFAULT_PROJECT_SETTINGS["prompt_generation"]["model"]
        self.append_log(f"Provider prompt generation: {prompt_provider} ({prompt_model})")
        if prompt_kind in {"minimax_h3_t2v", "minimax_h3_i2v", "minimax_h3_i2v_standalone", "minimax_h3_s2v", "minimax_h3_r2v"}:
            self.append_log("LLM MiniMax dipanggil dalam dua tahap: generate `en`, lalu terjemahkan field menjadi `id_new`; `id_old` adalah salinan `id_new`.")
        else:
            self.append_log("LLM dipanggil sekali untuk mengembalikan `en` dan `id_new`; `id_old` akan disamakan dengan `id_new`.")

        if self.prompt_generation_thread is not None and self.prompt_generation_thread.isRunning():
            self.append_log("[warning] Proses buat prompt sebelumnya masih berjalan. Tunggu selesai dulu.")
            self.statusBar().showMessage("Proses buat prompt masih berjalan.", 4000)
            return

        self.prompt_generation_context = {
            "prompt_kind": prompt_kind,
            "slot_index": slot_index,
            "scene_dir": scene_dir,
            "prompt_key": str(prompt_key or "").strip(),
        }

        self.prompt_generation_thread = QThread(self)
        self.prompt_generation_worker = PromptGenerationWorker(
            str(prompt_text or ""),
            context_text,
            project_dir=str(self.project_dir() or ""),
        )
        self.prompt_generation_worker.moveToThread(self.prompt_generation_thread)
        self.prompt_generation_worker.progress.connect(self.append_log)
        self.prompt_generation_thread.started.connect(self.prompt_generation_worker.run)
        self.prompt_generation_worker.finished.connect(self._on_prompt_generation_finished)
        self.prompt_generation_worker.failed.connect(self._on_prompt_generation_failed)
        self.prompt_generation_worker.finished.connect(self.prompt_generation_thread.quit)
        self.prompt_generation_worker.failed.connect(self.prompt_generation_thread.quit)
        self.prompt_generation_thread.finished.connect(self._cleanup_prompt_generation_thread)
        self.statusBar().showMessage("Membuat prompt dengan LLM...", 3000)
        self.prompt_generation_thread.start()

    def _handle_prompt_generation_finished(self, result: dict):
        self._on_prompt_generation_finished(result)

    def _handle_prompt_generation_failed(self, error: str):
        self._on_prompt_generation_failed(error)

    def _save_t2v_batch_extra_prompts(self):
        """Save t2v_batch extra prompts from UI widgets to the JSON file."""
        if not self.current_scene_dir:
            return
        groups = []
        for idx in range(min(3, len(self.t2v_batch_positive_inputs))):
            groups.append(
                {
                    "positive_prompt": self.t2v_batch_positive_inputs[idx].toPlainText(),
                    "negative_prompt": self.t2v_batch_negative_inputs[idx].toPlainText(),
                }
            )
        payload = {"groups": groups}
        target = Path(self.current_scene_dir) / "wan22_t2v_batch_extra_prompts.json"
        try:
            write_prompt_json(target, payload)
        except Exception as e:
            self.append_log(f"[warning] Gagal menyimpan extra prompts: {e}")

    def load_t2v_batch_extra_prompts_into_ui(self, scene_dir: Path):
        """Load t2v_batch extra prompts from JSON file into UI widgets."""
        extra_path = Path(scene_dir) / "wan22_t2v_batch_extra_prompts.json"
        try:
            data = load_json(extra_path, DEFAULT_WAN22_T2V_BATCH_EXTRA_PROMPTS)
        except Exception:
            data = DEFAULT_WAN22_T2V_BATCH_EXTRA_PROMPTS
        groups = data.get("groups", []) if isinstance(data, dict) else []
        for idx in range(min(3, len(self.t2v_batch_positive_inputs))):
            group = groups[idx] if idx < len(groups) and isinstance(groups[idx], dict) else {}
            positive = group.get("positive_prompt", "")
            negative = group.get("negative_prompt", "")
            self.t2v_batch_positive_inputs[idx].setPlainText(str(positive))
            self.t2v_batch_negative_inputs[idx].setPlainText(str(negative))

    def run_image_edit_slot(self, slot_index: int):
        if slot_index < 0 or slot_index >= len(self.image_edit_image_inputs):
            return
        if not self.ensure_project_selected():
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.save_current_scene():
            return

        source_image = str(self.image_edit_image_inputs[slot_index].currentData() or "").strip()
        prompt = self.image_edit_prompt_inputs[slot_index].toPlainText().strip()
        if not source_image:
            QMessageBox.warning(self, "Data Tidak Valid", f"Pilih gambar awal pada Edit Gambar {slot_index + 1}.")
            return
        if not prompt:
            QMessageBox.warning(self, "Data Tidak Valid", f"Prompt pada Edit Gambar {slot_index + 1} wajib diisi.")
            return

        prompt_json_path = self.current_scene_dir / "image_edit_prompt.json"
        try:
            runtime_payload = read_json_for_runtime(
                str(prompt_json_path),
                required=True,
            )
            runtime_groups = runtime_payload.get("groups") if isinstance(runtime_payload, dict) else None
            if isinstance(runtime_groups, list) and slot_index < len(runtime_groups) and isinstance(runtime_groups[slot_index], dict):
                runtime_prompt = str(runtime_groups[slot_index].get("prompt", "")).strip()
                if runtime_prompt:
                    prompt = runtime_prompt
        except Exception as e:
            self.append_log(f"[warning] Gagal sinkronisasi prompt image edit runtime: {e}")

        model_key = str(self.z_model_input.currentData() or MODEL_Z_IMAGE_TURBO).strip()
        gemini_model_id = str(self.z_gemini_model_input.currentData() or MODEL_GEMINI_FLASH_05K).strip()
        args = [
            "--server", self.comfyui_server_address(),
            "--project", self.current_project_name,
            "--scene", self.current_scene_dir.name,
            "--model", model_key,
            "--source-image", source_image,
            "--prompt", prompt,
        ]
        if model_key == MODEL_GEMINI_IMAGE and gemini_model_id:
            args.extend(["--gemini-model-id", gemini_model_id])

        self.start_process(
            IMAGE_EDIT_SCRIPT,
            args,
            f"Edit gambar {slot_index + 1} untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def generate_voice_current_scene(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Buat Voice", "Buat voice untuk adegan yang sedang dipilih?"):
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.save_current_scene():
            return
        self.save_project_voice_settings()
        self.start_process(
            VOICE_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name, "--scene", self.current_scene_dir.name],
            f"Membuat voice untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def generate_voice_all_scenes(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Buat Semua Voice", "Buat voice untuk semua adegan?"):
            return
        if self.current_scene_dir:
            self.save_current_scene(silent=True)
        self.save_project_voice_settings()
        self.start_process(
            VOICE_SCRIPT,
            ["--server", self.comfyui_server_address(), "--project", self.current_project_name],
            "Membuat voice untuk semua adegan",
            watch_dirs=self.list_scene_dirs_current(),
        )

    def generate_sound_current_scene(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Buat Sound", "Buat sound untuk adegan yang sedang dipilih?"):
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.save_current_scene():
            return
        self.start_process(
            SOUND_SCRIPT,
            ["--project", self.current_project_name, "--scene", self.current_scene_dir.name],
            f"Membuat sound untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def generate_sound_all_scenes(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Buat Semua Sound", "Buat sound untuk semua adegan?"):
            return
        if self.current_scene_dir:
            self.save_current_scene(silent=True)
        self.start_process(
            SOUND_SCRIPT,
            ["--project", self.current_project_name],
            "Membuat sound untuk semua adegan",
            watch_dirs=self.list_scene_dirs_current(),
        )

    def compose_current_scene(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Compose Adegan", "Gabungkan video dan audio untuk adegan yang sedang dipilih?"):
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if not self.save_current_scene():
            return
        self.start_process(
            COMPOSE_SCRIPT,
            ["--project", self.current_project_name, "--scene", self.current_scene_dir.name, "--no-final-merge"],
            f"Menggabungkan video dan audio untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir, (self.project_dir() / "combined") if self.project_dir() else (API_PRODUCTION / "combined")],
        )

    def compose_all_scenes(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Compose Semua Adegan", "Gabungkan video dan audio untuk semua adegan?"):
            return
        if self.current_scene_dir:
            self.save_current_scene(silent=True)

        music_files = []
        if MUSIC_DIR.exists():
            exts = {".m4a", ".mp3", ".wav"}
            music_files = sorted(
                [p for p in MUSIC_DIR.iterdir() if p.is_file() and p.suffix.lower() in exts],
                key=lambda p: p.name.lower(),
            )
        scene_dirs = self.list_scene_dirs_current()
        all_scenes_are_s2v = bool(scene_dirs) and all(
            str(load_json(scene_dir / "scene_meta.json", DEFAULT_SCENE_META).get("scene_type", "")).strip()
            in {"wan22_s2v", MINIMAX_H3_S2V_SCENE_TYPE}
            for scene_dir in scene_dirs
        )
        dialog = ComposeMusicDialog(music_files, all_scenes_are_s2v, self)
        if dialog.exec() != QDialog.Accepted:
            return
        music_file, music_volume, upscale_factor, compose_song = dialog.get_values()
        args = []
        args.extend(["--project", self.current_project_name])
        if music_file:
            args.extend(["--music-file", music_file, "--music-volume", f"{music_volume:.2f}"])
        if float(upscale_factor) > 1.0:
            args.extend(["--upscale-factor", f"{float(upscale_factor):.2f}"])
        if compose_song:
            args.append("--compose-song")

        self.start_process(
            COMPOSE_SCRIPT,
            args,
            "Menggabungkan video dan audio untuk semua adegan",
            watch_dirs=[*self.list_scene_dirs_current(), self.project_dir() / "combined" if self.project_dir() else API_PRODUCTION / "combined", MUSIC_DIR],
        )

    def upscale_latest_scene_video(self):
        if not self.ensure_project_selected():
            return
        if not self.current_scene_dir:
            QMessageBox.information(self, "Belum Ada Adegan", "Pilih adegan terlebih dahulu.")
            return
        if self.is_viewing_variation():
            QMessageBox.information(
                self,
                "Mode Lihat Variasi",
                "Upscale video terakhir hanya bisa dijalankan saat melihat Root Scene.",
            )
            return
        latest_video = find_latest_asset(self.current_scene_dir, VIDEO_EXTS)
        if latest_video is None:
            QMessageBox.information(self, "Video Tidak Ditemukan", "Tidak ada video di root scene aktif.")
            return
        dialog = UpscaleChoiceDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        scale_factor = dialog.get_scale_factor()
        source_video = Path(latest_video)
        stem = source_video.stem
        scale_tag = str(scale_factor).replace(".", "_")
        output_video = source_video.with_name(f"{stem}_upscale_{scale_tag}x{source_video.suffix}")
        frames_dir = self.current_scene_dir / stem
        self.start_process(
            UPSCALE_VIDEO_SCRIPT,
            [
                "--video", str(source_video),
                "--scale-factor", f"{float(scale_factor):.2f}",
                "--output", str(output_video),
                "--frames-dir", str(frames_dir),
            ],
            f"Upscale video {source_video.name} untuk {self.current_scene_dir.name}",
            watch_dirs=[self.current_scene_dir],
        )

    def save_backup_zip(self):
        if not self.ensure_project_selected():
            return
        display_name = f"{self.current_project_name}.zip"
        if not self.confirm_run_action("Konfirmasi Save", f"Simpan backup sebagai `{display_name}`?"):
            return
        if self.current_scene_dir:
            self.save_current_scene(silent=True)
        self.start_process(
            BACKUP_SCRIPT,
            ["--project", self.current_project_name],
            f"Menyimpan backup ZIP project {self.current_project_name}",
            watch_dirs=[ROOT / "backup_production"],
        )

    def run_clear_vram(self):
        if not self.ensure_project_selected():
            return
        if not self.confirm_run_action("Clear VRAM", "Jalankan VRAM cleaner di ComfyUI sekarang?"):
            return
        self.ensure_process_dialog()
        self.log_output.clear()
        server = self.comfyui_server_address()
        self.append_log(f"Menjalankan VRAM cleaner di {server}")
        ok = comfyui_api.run_vram_cleaner(server)
        if ok:
            self.append_log("[sukses] VRAM cleaner berhasil dikirim ke ComfyUI.")
            self.statusBar().showMessage("VRAM cleaner berhasil dijalankan.", 4000)
        else:
            self.append_log("[gagal] VRAM cleaner gagal dikirim ke ComfyUI.")
            self.statusBar().showMessage("VRAM cleaner gagal dijalankan.", 4000)

    def on_asset_selected(self, current, previous):
        if not current:
            self.asset_info_label.setText("Belum ada aset yang dipilih.")
            return
        asset_path = Path(current.data(Qt.UserRole))
        self.asset_info_label.setText(asset_path.name)

    def on_asset_clicked(self, item):
        if not item:
            return
        self.open_asset_preview_only(Path(item.data(Qt.UserRole)))

    def on_asset_double_clicked(self, item):
        if not item:
            return
        self.open_asset_in_viewer(Path(item.data(Qt.UserRole)))

    def open_asset_context_menu(self, position):
        item = self.asset_list.itemAt(position)
        if not item:
            return
        self.asset_list.setCurrentItem(item)
        menu = QMenu(self.asset_list)
        delete_action = QAction("Hapus", self.asset_list)
        delete_action.triggered.connect(lambda: self.delete_selected_asset(item))
        menu.addAction(delete_action)
        menu.exec(self.asset_list.mapToGlobal(position))

    def delete_selected_asset(self, item):
        if not item or not self.current_scene_dir:
            return
        asset_path = Path(item.data(Qt.UserRole))
        if not asset_path.exists():
            self.refresh_assets_and_previews()
            return
        reply = QMessageBox.question(
            self,
            "Hapus Aset",
            f"Hapus aset `{asset_path.name}`?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            if (
                self.video_player.source().toLocalFile() == str(asset_path)
                or self.audio_player.source().toLocalFile() == str(asset_path)
            ):
                self.clear_viewer()
            asset_path.unlink()
        except Exception as e:
            QMessageBox.critical(self, "Gagal Menghapus", f"Gagal menghapus aset:\n{e}")
            return
        self.refresh_assets_and_previews()
        self.refresh_scene_status()
        self.statusBar().showMessage(f"Aset {asset_path.name} dihapus.", 3000)

    def on_process_stdout(self):
        if self.process:
            self.append_log(bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace"))

    def on_process_stderr(self):
        if self.process:
            self.append_log(bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace"))

    def on_process_finished(self, exit_code, exit_status):
        self.append_log(f"\nProses selesai dengan kode keluar {exit_code}")
        context = self.process_context or {}
        process_kind = str(context.get("kind", "")).strip()
        finished_project_name = str(context.get("project_name", "")).strip()
        if self.current_scene_dir:
            self.refresh_assets_and_previews()
            self.refresh_scene_status()
        if exit_code == 0:
            if process_kind == "multi_project_agentic":
                if finished_project_name:
                    self.multi_project_agentic_completed.append(finished_project_name)
                self.statusBar().showMessage(f"Agentic selesai untuk {finished_project_name}.", 4000)
            else:
                outputs = self.collect_changed_outputs(
                    context.get("watch_dirs", []),
                    context.get("before_snapshot", {}),
                )
                QMessageBox.information(
                    self,
                    "Proses Berhasil",
                    f"{context.get('title', 'Proses')} berhasil.\n\n{self.format_output_summary(outputs)}",
                )
                self.statusBar().showMessage("Proses selesai.", 5000)
        else:
            tail_log = self.tail_process_log()
            message = f"{context.get('title', 'Proses')} gagal dengan kode keluar {exit_code}."
            if tail_log:
                message += f"\n\nRingkasan log terakhir:\n{tail_log}"
            QMessageBox.critical(self, "Proses Gagal", message)
            self.statusBar().showMessage("Proses gagal.", 5000)
            if process_kind == "multi_project_agentic":
                self.multi_project_agentic_queue = []
                self.multi_project_agentic_completed = []
        self.process_context = None
        self.process = None
        if exit_code == 0 and process_kind == "multi_project_agentic":
            self._start_next_multi_project_agentic()


def main():
    setup_logging()
    app = QApplication(sys.argv)
    window = SceneEditorWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
