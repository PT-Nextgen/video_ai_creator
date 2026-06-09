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
    "translate": {
        "provider": "gemini",
        "model": "gemini-2.5-flash-lite",
    },
    "prompt_generation": {
        "provider": "gemini",
        "model": "gemini-3.5-flash",
        "host": "nextgenserver",
        "port": 11434,
    },
}


def _normalize_config(data: dict | None) -> dict:
    config = copy.deepcopy(DEFAULT_SERVER_CONFIG)
    if isinstance(data, dict):
        for key in ("comfyui",):
            value = data.get(key)
            if isinstance(value, dict):
                config[key].update(value)
        for key in ("translate", "prompt_generation"):
            value = data.get(key)
            if isinstance(value, dict):
                config[key].update(value)
    for key in ("comfyui",):
        config[key]["host"] = str(config[key].get("host", "")).strip() or "127.0.0.1"
        try:
            config[key]["port"] = int(config[key].get("port", DEFAULT_SERVER_CONFIG[key]["port"]))
        except (TypeError, ValueError):
            config[key]["port"] = DEFAULT_SERVER_CONFIG[key]["port"]
    for key in ("translate", "prompt_generation"):
        sub_config = config.get(key, {})
        if not isinstance(sub_config, dict):
            sub_config = copy.deepcopy(DEFAULT_SERVER_CONFIG[key])
        provider = str(sub_config.get("provider", "gemini")).strip().lower()
        if key == "prompt_generation":
            sub_config["provider"] = provider if provider in {"gemini", "ollama"} else "gemini"
            sub_config["host"] = str(sub_config.get("host", DEFAULT_SERVER_CONFIG[key]["host"])).strip() or DEFAULT_SERVER_CONFIG[key]["host"]
            try:
                sub_config["port"] = int(sub_config.get("port", DEFAULT_SERVER_CONFIG[key]["port"]))
            except (TypeError, ValueError):
                sub_config["port"] = DEFAULT_SERVER_CONFIG[key]["port"]
            if sub_config["port"] <= 0:
                sub_config["port"] = DEFAULT_SERVER_CONFIG[key]["port"]
            sub_config.pop("temperature", None)
            sub_config.pop("thinking_mode", None)
        else:
            sub_config["provider"] = "gemini" if provider != "gemini" else provider
        model_name = str(sub_config.get("model", DEFAULT_SERVER_CONFIG[key]["model"])).strip()
        sub_config["model"] = model_name or DEFAULT_SERVER_CONFIG[key]["model"]
        config[key] = sub_config
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
