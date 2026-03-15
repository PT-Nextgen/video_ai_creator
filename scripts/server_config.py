import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "server_config.json"

DEFAULT_SERVER_CONFIG = {
    "comfyui": {
        "host": "127.0.0.1",
        "port": 8188,
    },
    "audio": {
        "host": "127.0.0.1",
        "port": 7777,
    },
}


def _normalize_config(data: dict | None) -> dict:
    config = copy.deepcopy(DEFAULT_SERVER_CONFIG)
    if isinstance(data, dict):
        for key in ("comfyui", "audio"):
            value = data.get(key)
            if isinstance(value, dict):
                config[key].update(value)
    for key in ("comfyui", "audio"):
        config[key]["host"] = str(config[key].get("host", "")).strip() or "127.0.0.1"
        try:
            config[key]["port"] = int(config[key].get("port", DEFAULT_SERVER_CONFIG[key]["port"]))
        except (TypeError, ValueError):
            config[key]["port"] = DEFAULT_SERVER_CONFIG[key]["port"]
    return config


def load_server_config() -> dict:
    if not CONFIG_PATH.exists():
        save_server_config(DEFAULT_SERVER_CONFIG)
        return copy.deepcopy(DEFAULT_SERVER_CONFIG)
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return _normalize_config(json.load(f))
    except (OSError, json.JSONDecodeError):
        save_server_config(DEFAULT_SERVER_CONFIG)
        return copy.deepcopy(DEFAULT_SERVER_CONFIG)


def save_server_config(data: dict) -> dict:
    config = _normalize_config(data)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return config


def get_server_address(service: str) -> str:
    config = load_server_config()
    entry = config.get(service, {})
    return f"{entry.get('host')}:{entry.get('port')}"
