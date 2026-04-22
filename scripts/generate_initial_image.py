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
from gemini.gemini_image import generate_scene_image, is_gemini_prompt
from prompt_localization import read_json_for_runtime, resolve_prompt_payload_for_runtime


def _scene_sort_key(name: str):
    if not str(name).startswith("scene_"):
        return (10**9, str(name))
    try:
        return (int(str(name).split("_", 1)[1]), str(name))
    except Exception:
        return (10**9, str(name))


def process_scene(scene_dir: str, server: str, timeout: int = 600, interval: float = 2.0):
    return process_scene_prompt(scene_dir, server, "z_image_prompt.json", 1, timeout=timeout, interval=interval)


def process_scene_prompt(scene_dir: str, server: str, prompt_file: str, prompt_index: int = 1, timeout: int = 600, interval: float = 2.0):
    scene_dir = os.path.abspath(scene_dir)
    write_log(f"Processing scene {scene_dir}")

    prompt_filename = str(prompt_file or "z_image_prompt.json").strip() or "z_image_prompt.json"
    z_prompt_path = os.path.join(scene_dir, prompt_filename)
    if not os.path.exists(z_prompt_path):
        write_log(f"{prompt_filename} not found in {scene_dir}", level="error")
        return False

    try:
        prompts = read_json_for_runtime(z_prompt_path, required=True, log_fn=write_log)
    except Exception as e:
        write_log(f"Gagal sinkronisasi prompt runtime untuk {z_prompt_path}: {e}", level="warning")
        raw_prompts = load_json(z_prompt_path)
        prompts, _, _ = resolve_prompt_payload_for_runtime(
            prompt_filename,
            raw_prompts,
            translate_fn=lambda text: text,
            log_fn=write_log,
        )
    prompt_index = max(1, int(prompt_index or 1))
    if prompt_filename != "z_image_prompt.json":
        groups = prompts.get("groups")
        if not isinstance(groups, list) or prompt_index > len(groups):
            write_log(f"Prompt group index {prompt_index} not found in {prompt_filename}", level="error")
            return False
        base_prompt_path = os.path.join(scene_dir, "z_image_prompt.json")
        if not os.path.exists(base_prompt_path):
            write_log(f"z_image_prompt.json not found in {scene_dir}", level="error")
            return False
        try:
            base_prompts = read_json_for_runtime(base_prompt_path, required=True, log_fn=write_log)
        except Exception as e:
            write_log(f"Gagal sinkronisasi prompt runtime untuk {base_prompt_path}: {e}", level="warning")
            raw_base_prompts = load_json(base_prompt_path)
            base_prompts, _, _ = resolve_prompt_payload_for_runtime(
                "z_image_prompt.json",
                raw_base_prompts,
                translate_fn=lambda text: text,
                log_fn=write_log,
            )
        group = groups[prompt_index - 1] if isinstance(groups[prompt_index - 1], dict) else {}
        prompts = dict(base_prompts)
        prompts["positive_prompt"] = str(group.get("positive_prompt", "")).strip()
        prompts["negative_prompt"] = str(group.get("negative_prompt", "")).strip()

    model_name = get_model_display_name(prompts)

    if is_gemini_prompt(prompts):
        try:
            out_path = generate_scene_image(scene_dir, prompts)
            write_log(f"Saved image to {out_path}")
            return True
        except Exception as e:
            write_log(f"Failed to generate Gemini image for {scene_dir}: {e}", level="error")
            return False

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
    parser.add_argument("--project", "-p", required=True, help="Nama project di dalam folder api_production")
    parser.add_argument("--scene", "-S", action="append", help="Scene name to process (e.g., scene_1). Repeatable")
    parser.add_argument("--prompt-file", default="z_image_prompt.json", help="Nama file prompt di folder scene")
    parser.add_argument("--prompt-index", type=int, default=1, help="Index group prompt (1-based) untuk file prompt bertipe groups")
    parser.add_argument("--loop", "-L", type=int, default=1, help="Number of times to process each selected scene")
    args = parser.parse_args()

    setup_logging()

    base = os.path.join(PROJECT_ROOT, "api_production", str(args.project).strip())
    if not os.path.exists(base):
        write_log(f"Project folder not found: {base}", level="error")
        print("Project folder not found; aborting")
        return 1

    scenes = sorted([d for d in os.listdir(base) if d.startswith("scene_")], key=_scene_sort_key)
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
            ok = process_scene_prompt(scene_dir, args.server, args.prompt_file, args.prompt_index)
            if not ok:
                write_log(f"Failed processing {scene}; stopping further work", level="error")
                print(f"Failed processing {scene}")
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
