import argparse
import importlib.util
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
from gemini.gemini_tts import process_scene as process_gemini_tts_scene


def _load_local_elevenlabs_tts():
    module_path = os.path.join(ROOT, "elevenlabs", "elevenlabs_tts.py")
    spec = importlib.util.spec_from_file_location("project_elevenlabs_tts", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load local elevenlabs_tts module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_elevenlabs_tts = _load_local_elevenlabs_tts()
find_elevenlabs_key = _elevenlabs_tts.find_elevenlabs_key
process_elevenlabs_scene = _elevenlabs_tts.process_scene


setup_logging()
logger = get_logger(__name__)

POLL_INTERVAL = 3.0
POLL_TIMEOUT = 600


def _scene_sort_key(name: str):
    if not str(name).startswith("scene_"):
        return (10**9, str(name))
    try:
        return (int(str(name).split("_", 1)[1]), str(name))
    except Exception:
        return (10**9, str(name))


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
    if not str(scene_meta.get("voice_text", "")).strip() or not str(scene_meta.get("edgetts_voice_id", "")).strip():
        write_log(f"Scene {scene_dir} tidak memiliki edgetts_voice_id atau voice_text yang valid.")
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
        if not os.path.exists(out_path) or os.path.getsize(out_path) <= 0:
            write_log(f"File audio EdgeTTS untuk {scene_dir} kosong atau gagal tersimpan.")
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
            except OSError:
                pass
            return False
        write_log(f"Downloaded audio for {scene_dir} -> {out_path}")
        return True
    except Exception as e:
        write_log(f"Failed to download audio for {scene_dir}: {e}")
        return False


def main(project_name, specific_scenes=None, comfyui_server=None):
    project_dir = os.path.join(ROOT, "api_production", str(project_name).strip())
    if not os.path.exists(project_dir):
        print("Project folder not found:", project_dir)
        return 1

    scenes = sorted([d for d in os.listdir(project_dir) if d.startswith("scene_")], key=_scene_sort_key)
    if specific_scenes:
        scenes = [s for s in scenes if s in specific_scenes]
    if not scenes:
        write_log("Tidak ada scene yang cocok untuk diproses.")
        return 1

    elevenlabs_key = find_elevenlabs_key()
    comfyui_server = comfyui_server or get_server_address("comfyui")
    had_error = False
    processed_count = 0

    for scene in scenes:
        scene_dir = os.path.join(project_dir, scene)
        meta_path = os.path.join(scene_dir, "scene_meta.json")
        if not os.path.exists(meta_path):
            logger.debug("No scene_meta.json in %s", scene_dir)
            continue
        try:
            meta = load_json(meta_path)
        except Exception as e:
            write_log(f"Gagal membaca {meta_path}: {e}")
            had_error = True
            continue

        provider = str(meta.get("voice_provider", "")).strip().lower()
        print("Processing", scene_dir)
        if provider == "edgetts":
            processed_count += 1
            if not process_edgetts_scene(scene_dir, comfyui_server):
                write_log(f"Gagal membuat voice EdgeTTS untuk {scene}.")
                had_error = True
        elif provider == "gemini_tts":
            processed_count += 1
            if not process_gemini_tts_scene(scene_dir, logger=logger, write_log=write_log):
                write_log(f"Gagal membuat voice Gemini TTS untuk {scene}.")
                had_error = True
        elif provider == "elevenlabs":
            processed_count += 1
            if not elevenlabs_key:
                write_log(f"ElevenLabs API key tidak ditemukan. Gagal memproses {scene}.")
                had_error = True
                continue
            if not process_elevenlabs_scene(scene_dir, elevenlabs_key, logger=logger, write_log=write_log):
                write_log(f"Gagal membuat voice ElevenLabs untuk {scene}.")
                had_error = True
        else:
            logger.debug("Scene %s tidak memiliki voice_provider yang didukung", scene_dir)

    if processed_count == 0:
        write_log("Tidak ada scene dengan voice_provider yang didukung untuk diproses.")
        return 1
    return 1 if had_error else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate voice untuk scene sesuai voice_provider")
    parser.add_argument("--project", "-p", required=True, help="Nama project di dalam folder api_production")
    parser.add_argument("--scene", "-s", action="append", help="Scene yang diproses (repeatable)")
    parser.add_argument("--server", default=get_server_address("comfyui"), help="ComfyUI server host:port untuk EdgeTTS")
    args = parser.parse_args()
    sys.exit(main(project_name=args.project, specific_scenes=args.scene, comfyui_server=args.server))
