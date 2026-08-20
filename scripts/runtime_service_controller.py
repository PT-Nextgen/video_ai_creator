"""Switch and verify the mutually-exclusive Llama/ComfyUI services.

The remote controller API is specified in SERVER-SWITCH.md. This client never
considers a start/stop request successful until the service health check agrees.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from scripts.server_config import load_server_config
from logging_config import write_log


KEY_FILE = Path(__file__).resolve().parent.parent / "switch-key.cfg"


class RuntimeServiceError(RuntimeError):
    pass


def _load_api_key() -> str:
    if KEY_FILE.exists():
        try:
            for raw_line in KEY_FILE.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("api_key="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
                return line
        except OSError as exc:
            raise RuntimeServiceError(f"Gagal membaca {KEY_FILE.name}: {exc}") from exc
    return ""


def project_uses_llama(project_dir: str | Path) -> bool:
    """Return whether this project selects the local Llama provider."""
    try:
        from scripts.project_settings import load_project_settings
        provider = str(load_project_settings(Path(project_dir)).get("prompt_generation", {}).get("provider", "gemini")).strip().lower()
        return provider in {"llama.cpp", "ollama"}
    except Exception:
        return False


@dataclass
class RuntimeServiceController:
    config: dict

    @classmethod
    def from_config(cls) -> "RuntimeServiceController":
        return cls(load_server_config().get("runtime_controller", {}))

    def _request(self, method: str, path: str, payload: dict | None = None, timeout: float | None = None):
        base = str(self.config.get("url", "")).rstrip("/")
        if not base:
            raise RuntimeServiceError("runtime_controller.url belum dikonfigurasi")
        key_env = str(self.config.get("api_key_env", "VIDEO_RUNTIME_API_KEY"))
        api_key = _load_api_key() or os.environ.get(key_env, "").strip()
        if not api_key:
            raise RuntimeServiceError(f"API key belum diisi di {KEY_FILE.name}")
        write_log(f"[runtime] API request {method.upper()} {path}")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{base}/{path.lstrip('/')}",
            data=body,
            method=method.upper(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or float(self.config.get("request_timeout_seconds", 30))) as response:
                raw = response.read().decode("utf-8", errors="replace")
                write_log(f"[runtime] API response {method.upper()} {path}: HTTP {response.status}")
                return json.loads(raw) if raw else {}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            write_log(f"[runtime] API error {method.upper()} {path}: {exc}", level="warning")
            raise RuntimeServiceError(f"Runtime controller request {method} {path} gagal: {exc}") from exc

    def status(self) -> dict:
        return self._request("GET", "/v1/runtime/status")

    def _health(self, service: str) -> bool:
        entry = self.config.get("services", {}).get(service, {})
        health_url = str(entry.get("health_url", "")).strip()
        if not health_url:
            return False
        try:
            request = urllib.request.Request(health_url, method="GET", headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=float(self.config.get("request_timeout_seconds", 30))) as response:
                if response.status < 200 or response.status >= 300:
                    write_log(f"[runtime] Health {service}: HTTP {response.status}", level="debug")
                    return False
                json.loads(response.read().decode("utf-8", errors="replace"))
            write_log(f"[runtime] Health {service}: healthy")
            return True
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
            write_log(f"[runtime] Health {service}: belum siap", level="debug")
            return False

    def wait_health(self, service: str, expected: bool) -> None:
        deadline = time.monotonic() + float(self.config.get("health_timeout_seconds", 600))
        interval = float(self.config.get("health_interval_seconds", 2))
        write_log(f"[runtime] Menunggu health {service} expected={expected}, timeout={self.config.get('health_timeout_seconds', 600)} detik")
        attempts = 0
        while time.monotonic() < deadline:
            attempts += 1
            if self._health(service) is expected:
                write_log(f"[runtime] Health {service} terverifikasi expected={expected} setelah {attempts} cek")
                return
            time.sleep(interval)
        state = "hidup" if expected else "mati"
        write_log(f"[runtime] Timeout menunggu {service} {state} setelah {attempts} cek", level="error")
        raise RuntimeServiceError(f"{service} tidak terverifikasi {state} setelah timeout")

    def switch(self, target: str, reason: str = "video_ai_creator") -> None:
        target = str(target).strip().lower()
        if target not in {"llama", "comfyui"}:
            raise RuntimeServiceError(f"Target service tidak valid: {target}")
        write_log(f"[runtime] Switch mulai target={target}, reason={reason}")
        self._request("POST", "/v1/runtime/switch", {
            "target": target,
            "reason": reason,
            "wait_ready": False,
        }, timeout=float(self.config.get("switch_timeout_seconds", 300)))
        other = "comfyui" if target == "llama" else "llama"
        self.wait_health(other, False)
        self.wait_health(target, True)
        write_log(f"[runtime] Switch selesai target={target}")

    def ensure(self, target: str, reason: str = "video_ai_creator") -> None:
        target = str(target).strip().lower()
        write_log(f"[runtime] Ensure mulai target={target}, reason={reason}")
        if self._health(target):
            other = "comfyui" if target == "llama" else "llama"
            if not self._health(other):
                return
        self.switch(target, reason=reason)
        write_log(f"[runtime] Ensure selesai target={target}")

    def ensure_llama(self, reason: str = "prompt_generation") -> None:
        self.ensure("llama", reason)

    def ensure_comfyui(self, reason: str = "workflow_execution") -> None:
        self.ensure("comfyui", reason)


def ensure_llama(reason: str = "prompt_generation") -> None:
    RuntimeServiceController.from_config().ensure_llama(reason)


def ensure_comfyui(reason: str = "workflow_execution", restore_on_exit: bool = False) -> None:
    """Ensure ComfyUI is active without scheduling an automatic switch-back.

    ``restore_on_exit`` is retained for caller compatibility, but is ignored.
    Runtime ownership must follow the next operation that actually requires a
    service; process exit is not a reason to start Llama.
    """
    RuntimeServiceController.from_config().ensure_comfyui(reason)
