import base64
import json
import os
import time
import wave
from typing import Optional

import requests

from gemini.gemini_image import find_gemini_key

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_TTS_LANGUAGE_CODE = "id-ID"
GEMINI_TTS_FALLBACK_MODELS = [
    ("Gemini 2.5 Flash Preview TTS", "gemini-2.5-flash-preview-tts"),
    ("Gemini 2.5 Pro Preview TTS", "gemini-2.5-pro-preview-tts"),
]
GEMINI_TTS_VOICE_OPTIONS = [
    ("Zephyr", "Zephyr"),
    ("Puck", "Puck"),
    ("Charon", "Charon"),
    ("Kore", "Kore"),
    ("Fenrir", "Fenrir"),
    ("Leda", "Leda"),
    ("Orus", "Orus"),
    ("Aoede", "Aoede"),
    ("Callirrhoe", "Callirrhoe"),
    ("Autonoe", "Autonoe"),
    ("Enceladus", "Enceladus"),
    ("Iapetus", "Iapetus"),
    ("Umbriel", "Umbriel"),
    ("Algieba", "Algieba"),
    ("Despina", "Despina"),
    ("Erinome", "Erinome"),
    ("Algenib", "Algenib"),
    ("Rasalgethi", "Rasalgethi"),
    ("Laomedeia", "Laomedeia"),
    ("Achernar", "Achernar"),
    ("Alnilam", "Alnilam"),
    ("Schedar", "Schedar"),
    ("Gacrux", "Gacrux"),
    ("Pulcherrima", "Pulcherrima"),
    ("Achird", "Achird"),
    ("Zubenelgenubi", "Zubenelgenubi"),
    ("Vindemiatrix", "Vindemiatrix"),
    ("Sadachbia", "Sadachbia"),
    ("Sadaltager", "Sadaltager"),
    ("Sulafat", "Sulafat"),
]
GEMINI_TTS_GENDER_OPTIONS = [
    ("Pria", "pria"),
    ("Wanita", "wanita"),
]

def _api_key() -> Optional[str]:
    return find_gemini_key()


def _api_headers(api_key: str) -> dict:
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }


def _extract_inline_audio_bytes(response_json: dict) -> Optional[bytes]:
    candidates = response_json.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
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


def _list_models_from_api(api_key: str) -> list[tuple[str, str]]:
    url = f"{GEMINI_API_URL}/models"
    models: list[tuple[str, str]] = []
    page_token = None
    for _ in range(10):
        params = {"pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token
        resp = requests.get(url, headers=_api_headers(api_key), params=params, timeout=30)
        if resp.status_code >= 400:
            break
        data = resp.json()
        for item in data.get("models", []):
            methods = item.get("supportedGenerationMethods") or []
            name = str(item.get("name", "")).strip()
            display_name = str(item.get("displayName", "")).strip()
            if not name or "generateContent" not in methods:
                continue
            model_id = name.split("/", 1)[1] if name.startswith("models/") else name
            haystack = f"{model_id} {display_name}".lower()
            if "tts" not in haystack:
                continue
            label = display_name or model_id
            models.append((label, model_id))
        page_token = str(data.get("nextPageToken", "")).strip() or None
        if not page_token:
            break
    seen = set()
    unique: list[tuple[str, str]] = []
    for label, model_id in models:
        if model_id in seen:
            continue
        seen.add(model_id)
        unique.append((label, model_id))
    return unique


def list_gemini_tts_models(api_key: Optional[str] = None) -> list[tuple[str, str]]:
    api_key = api_key or _api_key()
    if api_key:
        try:
            models = _list_models_from_api(api_key)
            if models:
                return models
        except Exception:
            pass
    return GEMINI_TTS_FALLBACK_MODELS[:]


def list_gemini_tts_voices(gender: str | None = None) -> list[tuple[str, str]]:
    # Gender is accepted for compatibility with the UI, but Gemini TTS does
    # not expose gender-based filtering. All voices remain available.
    _ = gender
    return GEMINI_TTS_VOICE_OPTIONS[:]


def default_gemini_tts_model_id() -> str:
    models = list_gemini_tts_models()
    return models[0][1] if models else GEMINI_TTS_FALLBACK_MODELS[0][1]


def _write_wav_from_pcm(pcm_bytes: bytes, out_path: str, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2):
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def synthesize(text: str, model_id: str, voice_name: str, api_key: Optional[str] = None, language_code: str = GEMINI_TTS_LANGUAGE_CODE, timeout: int = 180) -> bytes:
    api_key = api_key or _api_key()
    if not api_key:
        raise RuntimeError("Gemini API key tidak ditemukan.")
    url = f"{GEMINI_API_URL}/models/{model_id}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice_name,
                    }
                },
                "languageCode": language_code,
            },
        },
    }
    resp = requests.post(url, headers=_api_headers(api_key), data=json.dumps(payload), timeout=timeout)
    if resp.status_code >= 400:
        raise requests.HTTPError(
            f"{resp.status_code} Client Error for model {model_id}: {resp.text[:1200]}",
            response=resp,
        )
    result = resp.json()
    audio_bytes = _extract_inline_audio_bytes(result)
    if not audio_bytes:
        raise RuntimeError(f"Gemini TTS response has no audio data: {json.dumps(result)[:500]}")
    return audio_bytes


def process_scene(scene_dir, logger=None, write_log=None):
    meta_path = os.path.join(scene_dir, "scene_meta.json")
    if not os.path.exists(meta_path):
        return False
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        if write_log:
            write_log(f"Gagal membaca {meta_path}: {e}")
        if logger:
            logger.error("Failed to load %s: %s", meta_path, e)
        return False

    if str(meta.get("voice_provider", "")).strip().lower() != "gemini_tts":
        return False

    text = str(meta.get("voice_text", "")).strip()
    model_id = str(meta.get("gemini_tts_model_id", default_gemini_tts_model_id())).strip()
    voice_name = str(meta.get("gemini_tts_voice_name", "")).strip()
    if not text or not model_id or not voice_name:
        if write_log:
            write_log(f"Scene {scene_dir} belum memiliki konfigurasi Gemini TTS yang lengkap.", level="error")
        return False

    try:
        audio_bytes = synthesize(text, model_id, voice_name)
    except Exception as e:
        if write_log:
            write_log(f"Gemini TTS gagal untuk {scene_dir}: {e}", level="error")
        if logger:
            logger.error("Gemini TTS failed for %s: %s", scene_dir, e)
        return False

    if not audio_bytes:
        if write_log:
            write_log(f"Gemini TTS mengembalikan audio kosong untuk {scene_dir}.", level="error")
        return False

    out_name = f"speech_gemini_tts_{int(time.time())}.wav"
    out_path = os.path.join(scene_dir, out_name)
    try:
        _write_wav_from_pcm(audio_bytes, out_path)
        if logger:
            logger.info("Wrote Gemini TTS audio %s", out_path)
        return True
    except Exception as e:
        if write_log:
            write_log(f"Gagal menyimpan output Gemini TTS untuk {scene_dir}: {e}", level="error")
        if logger:
            logger.error("Failed to write Gemini TTS audio for %s: %s", scene_dir, e)
        return False
