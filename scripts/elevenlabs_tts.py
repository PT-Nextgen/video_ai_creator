import json
import os
import time
import types

from scripts.voice_profiles import get_voice_character, resolve_scene_voice_key
from scripts.timeout_config import TTS_CALL_TIMEOUT_SECONDS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ELEVENLABS_MODEL_ID_FIXED = "eleven_v3"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_elevenlabs_key():
    cfg_path = os.path.join(ROOT, "keys.cfg")
    if not os.path.exists(cfg_path):
        return None
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("ELEVENLABSKEY"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        return parts[1].strip()
    except Exception:
        return None
    return None


def synthesize(text, voice_id, api_key, timeout=TTS_CALL_TIMEOUT_SECONDS):
    try:
        from elevenlabs.client import ElevenLabs
    except Exception as e:
        raise RuntimeError("elevenlabs SDK not installed; please pip install elevenlabs") from e
    client = ElevenLabs(base_url="https://api.elevenlabs.io", api_key=api_key, timeout=timeout)
    res = client.text_to_speech.convert(
        voice_id=voice_id,
        output_format="mp3_44100_128",
        text=text,
        model_id=ELEVENLABS_MODEL_ID_FIXED,
    )
    if isinstance(res, (bytes, bytearray)):
        return bytes(res)
    if isinstance(res, types.GeneratorType):
        buf = bytearray()
        for chunk in res:
            if not chunk:
                continue
            if isinstance(chunk, (bytes, bytearray)):
                buf.extend(chunk)
            elif hasattr(chunk, "content"):
                try:
                    buf.extend(chunk.content)
                except Exception:
                    continue
            elif hasattr(chunk, "read"):
                try:
                    buf.extend(chunk.read())
                except Exception:
                    continue
        return bytes(buf)
    raise RuntimeError("Unexpected response type from ElevenLabs SDK")


def process_scene(scene_dir, api_key, logger=None, write_log=None):
    meta_path = os.path.join(scene_dir, "scene_meta.json")
    if not os.path.exists(meta_path):
        if logger:
            logger.debug("no scene_meta.json in %s", scene_dir)
        return False

    try:
        meta = load_json(meta_path)
    except Exception as e:
        if write_log:
            write_log(f"Failed to load {meta_path}: {e}")
        if logger:
            logger.error("Failed to load %s: %s", meta_path, e)
        return False

    text = str(meta.get("voice_text", "")).strip()
    voice_key = resolve_scene_voice_key(meta)
    voice = get_voice_character(voice_key)
    voice_id = str(voice.get("elevenlabs_voice_id", "")).strip()
    if not voice_id or not text:
        if write_log:
            write_log(f"Scene {scene_dir} tidak memiliki voice character atau voice_text yang valid.", level="error")
        if logger:
            logger.warning("scene %s missing voice character or text", scene_dir)
        return False

    try:
        audio_bytes = synthesize(text, voice_id, api_key)
    except Exception as e:
        if logger:
            logger.error("ElevenLabs synth failed for %s: %s", scene_dir, e)
        if write_log:
            write_log(f"ElevenLabs gagal untuk {scene_dir}: {e}", level="error")
        return False
    if not audio_bytes:
        if write_log:
            write_log(f"ElevenLabs mengembalikan audio kosong untuk {scene_dir}.", level="error")
        if logger:
            logger.error("ElevenLabs returned empty audio for %s", scene_dir)
        return False

    fname = f"speech_elevenlabs_{int(time.time())}.mp3"
    out_path = os.path.join(scene_dir, fname)
    try:
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
        if logger:
            logger.info("Wrote ElevenLabs audio %s", out_path)
        return True
    except Exception as e:
        if logger:
            logger.error("Failed to write audio for %s: %s", scene_dir, e)
        return False
