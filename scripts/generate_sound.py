import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

# Ensure project root is importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from logging_config import setup_logging, get_logger
from prompt_localization import read_json_for_runtime, resolve_prompt_payload_for_runtime

setup_logging()
logger = get_logger(__name__)

API_PRODUCTION = os.path.join(ROOT, "api_production")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"
ELEVENLABS_SFX_MODEL = "eleven_text_to_sound_v2"


def _scene_sort_key(name: str):
    if not str(name).startswith("scene_"):
        return (10**9, str(name))
    try:
        return (int(str(name).split("_", 1)[1]), str(name))
    except Exception:
        return (10**9, str(name))


def find_elevenlabs_key():
    cfg_path = os.path.join(ROOT, "keys.cfg")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("ELEVENLABSKEY"):
                        parts = line.split("=", 1)
                        if len(parts) == 2 and parts[1].strip():
                            return parts[1].strip()
        except Exception:
            pass
    env_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if env_key:
        return env_key
    return None


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_filename(prompt: str) -> str:
    return prompt.strip().replace(" ", "_")


def generate_sound_effect_mp3(api_key: str, prompt: str, duration_seconds: float, prompt_influence: float = 0.3, timeout: int = 180) -> bytes:
    url = f"{ELEVENLABS_BASE_URL}/v1/sound-generation"
    payload = {
        "text": prompt,
        "model_id": ELEVENLABS_SFX_MODEL,
        "duration_seconds": max(0.5, min(30.0, float(duration_seconds))),
        "prompt_influence": max(0.0, min(1.0, float(prompt_influence))),
    }
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"ElevenLabs sound-generation error {resp.status_code}: {resp.text[:500]}")
    return bytes(resp.content or b"")


def convert_mp3_bytes_to_wav(mp3_bytes: bytes, out_path: str):
    out_file = Path(out_path)
    tmp_mp3 = out_file.with_suffix(out_file.suffix + ".tmp.mp3")
    tmp_mp3.write_bytes(mp3_bytes)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(tmp_mp3),
        str(out_file),
    ]
    try:
        subprocess.run(cmd, check=True)
    finally:
        if tmp_mp3.exists():
            try:
                tmp_mp3.unlink()
            except OSError:
                pass


def generate_sound_for_prompt(api_key: str, prompt: str, duration_seconds: float, out_path: str):
    try:
        mp3_bytes = generate_sound_effect_mp3(api_key, prompt, duration_seconds)
    except Exception as e:
        logger.error('Failed request ElevenLabs for prompt "%s": %s', prompt, e)
        return False
    if not mp3_bytes:
        logger.error('ElevenLabs returned empty audio for prompt "%s"', prompt)
        return False
    try:
        if os.path.exists(out_path):
            base, ext = os.path.splitext(out_path)
            archive_path = f"{base}_{int(time.time())}{ext}"
            try:
                os.rename(out_path, archive_path)
                logger.info("Archived existing audio to %s", archive_path)
            except Exception as e:
                logger.warning("Failed to archive existing file %s: %s", out_path, e)
        convert_mp3_bytes_to_wav(mp3_bytes, out_path)
        logger.info('Wrote audio %s for prompt "%s"', out_path, prompt)
        return True
    except Exception as e:
        logger.error("Failed to convert/write audio to %s: %s", out_path, e)
        return False


def main(project_name, specific_scenes=None):
    project_dir = os.path.join(API_PRODUCTION, str(project_name).strip())
    if not os.path.exists(project_dir):
        print("Project folder not found:", project_dir)
        return 1

    scenes = sorted([d for d in os.listdir(project_dir) if d.startswith("scene_")], key=_scene_sort_key)
    if specific_scenes:
        scenes = [s for s in scenes if s in specific_scenes]

    api_key = find_elevenlabs_key()
    if not api_key:
        print("ELEVENLABSKEY not found. Put keys.cfg in project root or set env variable ELEVENLABS_API_KEY")
        return 1

    for scene in scenes:
        scene_dir = os.path.join(project_dir, scene)
        meta_path = os.path.join(scene_dir, "scene_meta.json")
        if not os.path.exists(meta_path):
            logger.debug("no scene_meta.json in %s", scene_dir)
            continue
        try:
            meta = read_json_for_runtime(meta_path, required=True, log_fn=lambda msg: logger.info(msg))
        except Exception as e:
            logger.warning("Failed runtime localization for %s: %s", meta_path, e)
            try:
                raw_meta = load_json(meta_path)
                meta, _, _ = resolve_prompt_payload_for_runtime(
                    "scene_meta.json",
                    raw_meta,
                    translate_fn=lambda text: text,
                )
            except Exception as inner_e:
                logger.error("Failed to load %s: %s", meta_path, inner_e)
                continue

        sound_prompt = meta.get("sound_prompt")
        duration = meta.get("duration_seconds") or meta.get("duration")
        try:
            duration = float(duration)
        except Exception:
            duration = None

        if not sound_prompt:
            logger.debug("no sound_prompt for %s", scene)
            continue
        if duration is None or duration <= 0:
            logger.warning("no valid duration for %s, skipping", scene)
            continue

        prompts = [p.strip() for p in str(sound_prompt).split(",") if p.strip()]
        for p in prompts:
            filename = safe_filename(p) + ".wav"
            out_path = os.path.join(scene_dir, filename)
            logger.info("Generating audio %s (will overwrite if exists)", out_path)
            ok = generate_sound_for_prompt(api_key, p, duration, out_path)
            if not ok:
                logger.error('Failed to generate audio for scene %s prompt "%s"', scene, p)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate sound assets via ElevenLabs Sound Effects API")
    parser.add_argument("--project", "-p", required=True, help="Nama project di dalam folder api_production")
    parser.add_argument("--scene", "-s", action="append", help="Scene to process (repeatable)")
    args = parser.parse_args()
    raise SystemExit(main(project_name=args.project, specific_scenes=args.scene))
