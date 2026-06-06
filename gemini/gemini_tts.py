import base64
import json
import os
import re
import time
import wave
from typing import Optional

import requests

from gemini.gemini_image import find_gemini_key
from scripts.voice_profiles import get_voice_character, resolve_scene_voice_key

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_TTS_LANGUAGE_CODE = "id-ID"
GEMINI_TTS_MODEL_ID_FIXED = "gemini-3.1-flash-tts-preview"
GEMINI_TTS_MODE_DEFAULT = "structured"
GEMINI_VOICE_NAME_BY_CHARACTER = {
    "yetty": "Kore",
    "nilasari": "Kore",
    "dany_saputra": "Charon",
    "dakocan": "Puck",
    "candy": "Leda",
    "lily": "Leda",
    "finn": "Puck",
    "kevin": "Charon",
}


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


def _build_tts_text(voice_key: str, raw_text: str, mode: str = GEMINI_TTS_MODE_DEFAULT) -> str:
    text = str(raw_text or "").strip()
    mode = str(mode or "").strip().lower()
    if mode == "consistent":
        return text
    if mode == "minimal":
        return (
            "Bacakan teks berikut dalam Bahasa Indonesia dengan suara natural, jelas, "
            "dan tanpa menambahkan kata lain.\n\n"
            f"Teks:\n{text}"
        )
    if mode == "plain":
        return text
    voice = get_voice_character(voice_key)
    profile_name = voice.get("display_name", "Voice Talent")
    profile_text = voice.get("gemini_profile_text", "")
    if "#### TRANSCRIPT" in profile_text:
        return profile_text.rstrip() + "\n" + text
    prompt_template = (
        f"# AUDIO PROFILE: {profile_name}\n"
        "## \"Indonesian Voice Performance\"\n\n"
        "## THE SCENE: Voice Over Recording Session\n"
        "The talent is in a professional voice-over booth. Keep delivery emotionally\n"
        "engaging while preserving clear diction and stable pacing for Indonesian content.\n\n"
        "### DIRECTOR'S NOTES\n"
        "Style:\n"
        f"* {profile_text}\n"
        "* Keep pronunciation clean and listener-friendly in Indonesian.\n\n"
        "Pace: Natural and adaptive to sentence meaning. Avoid awkward dead air.\n\n"
        "Accent: Indonesian.\n\n"
        "### SAMPLE CONTEXT\n"
        "Use this voice for content where expressive, clear, and audience-fit narration is required.\n\n"
        "#### TRANSCRIPT\n"
        "{transcript}"
    )
    return prompt_template.format(transcript=text)


def _normalize_tts_text(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_prohibited_content_error(exc: Exception) -> bool:
    message = str(exc or "")
    normalized = message.upper()
    return "PROHIBITED_CONTENT" in normalized or '"BLOCKREASON": "PROHIBITED_CONTENT"' in normalized


def _write_wav_from_pcm(pcm_bytes: bytes, out_path: str, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2):
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def synthesize(text: str, voice_name: str, api_key: Optional[str] = None, language_code: str = GEMINI_TTS_LANGUAGE_CODE, timeout: int = 180) -> bytes:
    api_key = api_key or _api_key()
    if not api_key:
        raise RuntimeError("Gemini API key tidak ditemukan.")
    url = f"{GEMINI_API_URL}/models/{GEMINI_TTS_MODEL_ID_FIXED}:generateContent"
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
            f"{resp.status_code} Client Error for model {GEMINI_TTS_MODEL_ID_FIXED}: {resp.text[:1200]}",
            response=resp,
        )
    result = resp.json()
    audio_bytes = _extract_inline_audio_bytes(result)
    if not audio_bytes:
        raise RuntimeError(f"Gemini TTS response has no audio data: {json.dumps(result)[:500]}")
    return audio_bytes


def synthesize_with_fallbacks(
    raw_text: str,
    voice_key: str,
    voice_name: str,
    api_key: Optional[str] = None,
    language_code: str = GEMINI_TTS_LANGUAGE_CODE,
    timeout: int = 180,
    logger=None,
    write_log=None,
) -> bytes:
    normalized_text = _normalize_tts_text(raw_text)
    candidates = [
        ("structured", _build_tts_text(voice_key, raw_text, mode="structured")),
        ("minimal", _build_tts_text(voice_key, raw_text, mode="minimal")),
    ]
    if normalized_text and normalized_text != str(raw_text or "").strip():
        candidates.append(("minimal_normalized", _build_tts_text(voice_key, normalized_text, mode="minimal")))
    candidates.append(("plain", _build_tts_text(voice_key, normalized_text or raw_text, mode="plain")))

    last_error = None
    for idx, (mode_name, prompt_text) in enumerate(candidates):
        try:
            if idx > 0:
                if write_log:
                    write_log(
                        f"Gemini TTS retry dengan mode `{mode_name}` untuk voice `{voice_key}`.",
                        level="warning",
                    )
                if logger:
                    logger.warning("Retrying Gemini TTS with mode `%s` for voice `%s`.", mode_name, voice_key)
            return synthesize(
                prompt_text,
                voice_name,
                api_key=api_key,
                language_code=language_code,
                timeout=timeout,
            )
        except Exception as exc:
            last_error = exc
            if not _is_prohibited_content_error(exc):
                raise
    if last_error is not None:
        raise last_error
    raise RuntimeError("Gemini TTS gagal tanpa detail error.")


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

    text = str(meta.get("voice_text", "")).strip()
    voice_key = resolve_scene_voice_key(meta)
    voice_name = GEMINI_VOICE_NAME_BY_CHARACTER.get(voice_key, "Kore")
    if not text:
        if write_log:
            write_log(f"Scene {scene_dir} belum memiliki voice_text untuk Gemini TTS.", level="error")
        return False

    try:
        audio_bytes = synthesize_with_fallbacks(
            text,
            voice_key,
            voice_name,
            logger=logger,
            write_log=write_log,
        )
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
