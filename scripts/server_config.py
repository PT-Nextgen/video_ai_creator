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
        "model": "gemini-3.1-flash-lite",
    },
    "prompt_generation": {
        "provider": "hipfire",
        "model": "qwen3.8-27",
        "host": "nextgenserver",
        "port": 11435,
    },
    "runtime_controller": {
        "url": "http://nextgenserver:9000",
        "api_key_env": "VIDEO_RUNTIME_API_KEY",
        "default_service": "hipfire",
        "request_timeout_seconds": 30,
        "switch_timeout_seconds": 300,
        "health_timeout_seconds": 600,
        "health_interval_seconds": 2,
        "services": {
            "hipfire": {
                "health_url": "http://nextgenserver:11435/v1/models",
                "health_path": "/v1/models"
            },
            "comfyui": {
                "health_url": "http://nextgenserver:8188/system_stats",
                "health_path": "/system_stats"
            }
        }
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
            legacy_local_provider = provider in {"llama.cpp", "ollama", "llama"}
            if legacy_local_provider:
                provider = "hipfire"
            sub_config["provider"] = provider if provider in {"gemini", "hipfire"} else "gemini"
            sub_config["host"] = str(sub_config.get("host", DEFAULT_SERVER_CONFIG[key]["host"])).strip() or DEFAULT_SERVER_CONFIG[key]["host"]
            try:
                sub_config["port"] = int(sub_config.get("port", DEFAULT_SERVER_CONFIG[key]["port"]))
            except (TypeError, ValueError):
                sub_config["port"] = DEFAULT_SERVER_CONFIG[key]["port"]
            if sub_config["port"] <= 0:
                sub_config["port"] = DEFAULT_SERVER_CONFIG[key]["port"]
            if sub_config["provider"] == "hipfire":
                if sub_config["host"] == "nextgenserver" and sub_config["port"] == 8080:
                    sub_config["port"] = DEFAULT_SERVER_CONFIG[key]["port"]
                if sub_config["model"] in {"qwen3.8-27b", "qwen3.8-27b-uc-q4_k_m"}:
                    sub_config["model"] = DEFAULT_SERVER_CONFIG[key]["model"]
            sub_config.pop("temperature", None)
            sub_config.pop("thinking_mode", None)
        else:
            sub_config["provider"] = "gemini" if provider != "gemini" else provider
        model_name = str(sub_config.get("model", DEFAULT_SERVER_CONFIG[key]["model"])).strip()
        sub_config["model"] = model_name or DEFAULT_SERVER_CONFIG[key]["model"]
        config[key] = sub_config
    if isinstance(data, dict):
        runtime = data.get("runtime_controller")
        if isinstance(runtime, dict):
            config["runtime_controller"].update(runtime)
            if isinstance(runtime.get("services"), dict):
                config["runtime_controller"]["services"].update(runtime["services"])
                for service in ("hipfire", "comfyui"):
                    if isinstance(runtime["services"].get(service), dict):
                        config["runtime_controller"]["services"][service].update(runtime["services"][service])
    runtime = config["runtime_controller"]
    runtime["url"] = str(runtime.get("url", "")).strip().rstrip("/")
    runtime["api_key_env"] = str(runtime.get("api_key_env", "VIDEO_RUNTIME_API_KEY")).strip() or "VIDEO_RUNTIME_API_KEY"
    default_service = str(runtime.get("default_service", "hipfire")).strip().lower()
    if default_service in {"llama", "llama.cpp", "ollama"}:
        default_service = "hipfire"
    runtime["default_service"] = default_service if default_service in {"hipfire", "comfyui"} else "hipfire"
    for key, fallback in (("request_timeout_seconds", 30), ("switch_timeout_seconds", 300), ("health_timeout_seconds", 600), ("health_interval_seconds", 2)):
        try:
            runtime[key] = max(1, float(runtime.get(key, fallback)))
        except (TypeError, ValueError):
            runtime[key] = fallback
    for service in ("hipfire", "comfyui"):
        entry = runtime.setdefault("services", {}).setdefault(service, {})
        entry["health_url"] = str(entry.get("health_url", DEFAULT_SERVER_CONFIG["runtime_controller"]["services"][service]["health_url"])).strip()
        entry["health_path"] = str(entry.get("health_path", DEFAULT_SERVER_CONFIG["runtime_controller"]["services"][service]["health_path"])).strip() or DEFAULT_SERVER_CONFIG["runtime_controller"]["services"][service]["health_path"]
    # Drop service names from the pre-Hipfire schema after normalizing an old
    # server_config.json. The runtime controller must only receive Hipfire or
    # ComfyUI targets.
    runtime.setdefault("services", {}).pop("llama", None)
    runtime.setdefault("services", {}).pop("ollama", None)
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
