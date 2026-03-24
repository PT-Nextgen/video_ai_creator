import os
import json
import argparse
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in os.sys.path:
    os.sys.path.insert(0, PROJECT_ROOT)

from logging_config import setup_logging, write_log
from scripts import comfyui_api
from scripts.server_config import get_server_address
from scripts.workflow_builders import load_json
from z_image.z_image import build_z_image_workflow, get_model_display_name, send_workflow


def process_scene(scene_dir: str, server: str, timeout: int = 600, interval: float = 2.0):
    scene_dir = os.path.abspath(scene_dir)
    write_log(f"Processing scene {scene_dir}")

    z_prompt_path = os.path.join(scene_dir, "z_image_prompt.json")
    if not os.path.exists(z_prompt_path):
        write_log(f"z_image_prompt.json not found in {scene_dir}", level="error")
        return False

    prompts = load_json(z_prompt_path)
    model_name = get_model_display_name(prompts)
    workflow = build_z_image_workflow(prompts)

    try:
        result = send_workflow(workflow, server, log_file=None, source_label=z_prompt_path, model_name=model_name)
    except Exception as e:
        write_log(f"Failed to post workflow for {scene_dir}: {e}", level="error")
        return False

    prompt_id = result.get("prompt_id") or result.get("id")
    write_log(f"Posted {model_name} workflow for {scene_dir}, prompt_id={prompt_id}")

    if not prompt_id:
        write_log(f"No prompt id returned for {scene_dir}: {json.dumps(result)}", level="error")
        return False

    try:
        hist = comfyui_api.get_history_for_prompt(server, prompt_id)
        write_log(f"History for prompt_id={prompt_id}: {json.dumps(hist)}")
    except Exception as e:
        write_log(f"Failed to fetch history for prompt_id={prompt_id}: {e}")

    image_out = comfyui_api.wait_for_output(server, prompt_id, output_type="image", timeout=timeout, interval=interval)
    if not image_out:
        write_log(f"No image output for {scene_dir} (prompt_id={prompt_id})", level="error")
        return False

    image_filename = image_out.get("filename") or image_out.get("name") or image_out.get("file")
    image_subfolder = image_out.get("subfolder")
    image_type = image_out.get("type")
    if not image_filename:
        write_log(f"Cannot determine image filename from output: {json.dumps(image_out)}", level="error")
        return False

    image_url = comfyui_api.get_file_url(server, image_filename, subfolder=image_subfolder, type_=image_type)
    image_out_path = os.path.join(scene_dir, image_filename)
    try:
        comfyui_api.download_file_url(image_url, image_out_path)
    except Exception as e:
        write_log(f"Failed to download image {image_filename} from {image_url}: {e}", level="error")
        return False
    try:
        if not os.path.exists(image_out_path) or os.path.getsize(image_out_path) <= 0:
            write_log(f"Downloaded image missing or empty: {image_out_path}", level="error")
            return False
    except Exception as e:
        write_log(f"Failed to validate downloaded image {image_out_path}: {e}", level="error")
        return False

    write_log(f"Saved image to {image_out_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate initial images for scenes via ComfyUI")
    parser.add_argument("--server", "-s", default=get_server_address("comfyui"), help="ComfyUI server host:port")
    parser.add_argument("--scene", "-S", action="append", help="Scene name to process (e.g., scene_1). Repeatable")
    parser.add_argument("--loop", "-L", type=int, default=1, help="Number of times to process each selected scene")
    args = parser.parse_args()

    setup_logging()

    base = os.path.join(PROJECT_ROOT, "api_production")
    if not os.path.exists(base):
        write_log(f"api_production folder not found: {base}", level="error")
        print("api_production folder not found; aborting")
        return 1

    scenes = sorted([d for d in os.listdir(base) if d.startswith("scene_")])
    if args.scene:
        requested = set(args.scene)
        scenes = [s for s in scenes if s in requested]
    if not scenes:
        write_log("Tidak ada scene yang cocok untuk diproses.", level="error")
        print("No matching scenes found")
        return 1

    loop_count = int(args.loop or 1)
    if loop_count < 1:
        print("Loop count must be >= 1")
        return 1

    for loop_index in range(loop_count):
        if loop_count > 1:
            print(f"Loop {loop_index + 1}/{loop_count}")
        for scene in scenes:
            scene_dir = os.path.join(base, scene)
            print(f"Processing {scene_dir}")
            ok = process_scene(scene_dir, args.server)
            if not ok:
                write_log(f"Failed processing {scene}; stopping further work", level="error")
                print(f"Failed processing {scene}")
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
