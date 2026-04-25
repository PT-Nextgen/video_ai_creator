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
    "translate": {
        "provider": "gemini",
        "ollama": {
            "host": "nextgenserver",
            "port": 11434,
            "model": "",
        },
    },
}


def _normalize_config(data: dict | None) -> dict:
    config = copy.deepcopy(DEFAULT_SERVER_CONFIG)
    if isinstance(data, dict):
        for key in ("comfyui", "audio"):
            value = data.get(key)
            if isinstance(value, dict):
                config[key].update(value)
        translate_value = data.get("translate")
        if isinstance(translate_value, dict):
            config["translate"].update({k: v for k, v in translate_value.items() if k != "ollama"})
            ollama_value = translate_value.get("ollama")
            if isinstance(ollama_value, dict):
                config["translate"]["ollama"].update(ollama_value)
    for key in ("comfyui", "audio"):
        config[key]["host"] = str(config[key].get("host", "")).strip() or "127.0.0.1"
        try:
            config[key]["port"] = int(config[key].get("port", DEFAULT_SERVER_CONFIG[key]["port"]))
        except (TypeError, ValueError):
            config[key]["port"] = DEFAULT_SERVER_CONFIG[key]["port"]
    translate_config = config.get("translate", {})
    if not isinstance(translate_config, dict):
        translate_config = copy.deepcopy(DEFAULT_SERVER_CONFIG["translate"])
    provider = str(translate_config.get("provider", "gemini")).strip().lower()
    if provider not in {"gemini", "ollama"}:
        provider = "gemini"
    translate_config["provider"] = provider
    ollama_config = translate_config.get("ollama", {})
    if not isinstance(ollama_config, dict):
        ollama_config = {}
    ollama_config["host"] = str(ollama_config.get("host", "")).strip() or DEFAULT_SERVER_CONFIG["translate"]["ollama"]["host"]
    try:
        ollama_config["port"] = int(ollama_config.get("port", DEFAULT_SERVER_CONFIG["translate"]["ollama"]["port"]))
    except (TypeError, ValueError):
        ollama_config["port"] = DEFAULT_SERVER_CONFIG["translate"]["ollama"]["port"]
    ollama_config["model"] = str(ollama_config.get("model", "")).strip()
    translate_config["ollama"] = ollama_config
    config["translate"] = translate_config
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
