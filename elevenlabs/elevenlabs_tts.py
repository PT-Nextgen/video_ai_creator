import json
import os
import time
import types


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(ROOT)
API_PRODUCTION = os.path.join(PARENT, os.path.basename(ROOT), "api_production")

ELEVENLABS_VOICES = [
    ("Yetty Indonesia", "Lpe7uP03WRpCk9XkpFnf"),
    ("Iwan Indonesia", "1kNciG1jHVSuFBPoxdRZ"),
]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_elevenlabs_key():
    cfg_path = os.path.join(PARENT, "venv", "keys.cfg")
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


def synthesize(text, voice_id, api_key, timeout=60):
    try:
        from elevenlabs import ElevenLabs
    except Exception as e:
        raise RuntimeError("elevenlabs SDK not installed; please pip install elevenlabs") from e
    client = ElevenLabs(base_url="https://api.elevenlabs.io", api_key=api_key)
    res = client.text_to_speech.convert(
        voice_id=voice_id,
        output_format="mp3_44100_128",
        text=text,
        model_id="eleven_multilingual_v2",
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


def build_request(scene_meta: dict) -> dict:
    return {
        "voice_id": scene_meta.get("elevenlabs_voice_id"),
        "text": scene_meta.get("voice_text"),
        "model_id": "eleven_multilingual_v2",
        "output_format": "mp3_44100_128",
    }


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

    if meta.get("voice_provider") != "elevenlabs":
        if logger:
            logger.debug("scene %s not configured for elevenlabs", scene_dir)
        return False

    request = build_request(meta)
    voice_id = request.get("voice_id")
    text = request.get("text")
    if not voice_id or not text:
        if logger:
            logger.warning("scene %s missing voice_id or text", scene_dir)
        return False

    try:
        audio_bytes = synthesize(text, voice_id, api_key)
    except Exception as e:
        if logger:
            logger.error("ElevenLabs synth failed for %s: %s", scene_dir, e)
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
