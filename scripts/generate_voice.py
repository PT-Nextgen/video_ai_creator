import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts import comfyui_api
from logging_config import setup_logging, get_logger, write_log
from scripts.server_config import get_server_address
from scripts.workflow_builders import load_json
from edgetts.edgetts import build_edgetts_workflow
from elevenlabs.elevenlabs_tts import API_PRODUCTION, find_elevenlabs_key, process_scene as process_elevenlabs_scene


setup_logging()
logger = get_logger(__name__)

POLL_INTERVAL = 3.0
POLL_TIMEOUT = 600


def wait_for_audio_output(server: str, prompt_id: str, timeout: int = POLL_TIMEOUT, interval: float = POLL_INTERVAL):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            hist = comfyui_api.get_history_for_prompt(server, prompt_id, timeout=5, interval=interval)
        except Exception as e:
            write_log(f"Error fetching history for {prompt_id}: {e}", level="warning")
            time.sleep(interval)
            continue

        if not isinstance(hist, dict):
            time.sleep(interval)
            continue

        outputs = hist.get("outputs")
        if not outputs and len(hist) == 1:
            sole = next(iter(hist.values()))
            outputs = sole.get("outputs") if isinstance(sole, dict) else None

        if outputs and isinstance(outputs, dict):
            for node_val in outputs.values():
                if not isinstance(node_val, dict):
                    continue
                for items in node_val.values():
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if isinstance(item, dict) and item.get("filename", "").lower().endswith((".mp3", ".wav", ".ogg")):
                            return {
                                "filename": item.get("filename"),
                                "subfolder": item.get("subfolder"),
                                "type": item.get("type"),
                            }

        time.sleep(interval)
    return None


def process_edgetts_scene(scene_dir, server, timeout=POLL_TIMEOUT, interval=POLL_INTERVAL):
    meta_path = os.path.join(scene_dir, "scene_meta.json")
    if not os.path.exists(meta_path):
        logger.debug("No scene_meta.json in %s", scene_dir)
        return False

    try:
        scene_meta = load_json(meta_path)
    except Exception as e:
        write_log(f"Failed to load {meta_path}: {e}")
        return False

    if scene_meta.get("voice_provider") != "edgetts":
        logger.debug("Scene %s not configured for edgetts", scene_dir)
        return False

    try:
        workflow = build_edgetts_workflow(scene_meta)
        res = comfyui_api.post_workflow_api(workflow, server)
    except Exception as e:
        write_log(f"Failed to post edgetts workflow for {scene_dir}: {e}")
        return False

    prompt_id = res.get("prompt_id") or res.get("id")
    write_log(f"Posted edgetts workflow for {scene_dir}, prompt_id={prompt_id}")
    if not prompt_id:
        write_log(f"No prompt_id returned for edgetts in {scene_dir}")
        return False

    audio_out = wait_for_audio_output(server, prompt_id, timeout=timeout, interval=interval)
    if not audio_out:
        write_log(f"No audio output found for {scene_dir} (prompt_id={prompt_id})")
        return False

    try:
        file_url = comfyui_api.get_file_url(
            server,
            audio_out.get("filename"),
            subfolder=audio_out.get("subfolder"),
            type_=audio_out.get("type"),
        )
        filename = audio_out.get("filename") or "edgetts_output.wav"
        if not filename.startswith("speech_"):
            filename = f"speech_{filename}"
        out_path = os.path.join(scene_dir, filename)
        comfyui_api.download_file_url(file_url, out_path)
        write_log(f"Downloaded audio for {scene_dir} -> {out_path}")
        return True
    except Exception as e:
        write_log(f"Failed to download audio for {scene_dir}: {e}")
        return False


def main(specific_scenes=None, comfyui_server=None):
    if not os.path.exists(API_PRODUCTION):
        print("api_production folder not found:", API_PRODUCTION)
        return

    scenes = sorted([d for d in os.listdir(API_PRODUCTION) if d.startswith("scene_")])
    if specific_scenes:
        scenes = [s for s in scenes if s in specific_scenes]

    elevenlabs_key = find_elevenlabs_key()
    comfyui_server = comfyui_server or get_server_address("comfyui")

    for scene in scenes:
        scene_dir = os.path.join(API_PRODUCTION, scene)
        meta_path = os.path.join(scene_dir, "scene_meta.json")
        if not os.path.exists(meta_path):
            logger.debug("No scene_meta.json in %s", scene_dir)
            continue
        try:
            meta = load_json(meta_path)
        except Exception as e:
            write_log(f"Gagal membaca {meta_path}: {e}")
            continue

        provider = str(meta.get("voice_provider", "")).strip().lower()
        print("Processing", scene_dir)
        if provider == "edgetts":
            process_edgetts_scene(scene_dir, comfyui_server)
        elif provider == "elevenlabs":
            if not elevenlabs_key:
                write_log("ElevenLabs API key tidak ditemukan.")
                continue
            process_elevenlabs_scene(scene_dir, elevenlabs_key, logger=logger, write_log=write_log)
        else:
            logger.debug("Scene %s tidak memiliki voice_provider yang didukung", scene_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate voice untuk scene sesuai voice_provider")
    parser.add_argument("--scene", "-s", action="append", help="Scene yang diproses (repeatable)")
    parser.add_argument("--server", default=get_server_address("comfyui"), help="ComfyUI server host:port untuk EdgeTTS")
    args = parser.parse_args()
    main(specific_scenes=args.scene, comfyui_server=args.server)
