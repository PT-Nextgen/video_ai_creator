import argparse
import json
import os
import shutil
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in os.sys.path:
    os.sys.path.insert(0, PROJECT_ROOT)

from logging_config import setup_logging, write_log
from scripts import comfyui_api
from scripts.server_config import get_server_address
from z_image.z_image import build_z_image_workflow, get_model_display_name, send_workflow
from gemini.gemini_image import generate_scene_image, is_gemini_prompt
from prompt_localization import read_json_for_runtime, resolve_prompt_payload_for_runtime


def _replace_or_copy(src: str, dst: str):
    dst_dir = os.path.dirname(os.path.abspath(dst))
    if dst_dir:
        os.makedirs(dst_dir, exist_ok=True)
    try:
        if os.path.exists(dst):
            os.remove(dst)
        os.replace(src, dst)
        return
    except OSError:
        pass
    shutil.copy2(src, dst)
    try:
        os.remove(src)
    except OSError:
        pass


def process_cover(project_dir: str, server: str, timeout: int = 600, interval: float = 2.0):
    cover_config_path = os.path.join(project_dir, "cover_prompt.json")
    if not os.path.exists(cover_config_path):
        write_log(f"cover_prompt.json not found in {project_dir}", level="error")
        return False

    try:
        prompts = read_json_for_runtime(cover_config_path, required=True, log_fn=write_log)
    except Exception as e:
        write_log(f"Gagal sinkronisasi prompt runtime untuk {cover_config_path}: {e}", level="warning")
        with open(cover_config_path, "r", encoding="utf-8") as f:
            raw_prompts = json.load(f)
        prompts, _, _ = resolve_prompt_payload_for_runtime(
            "cover_prompt.json",
            raw_prompts,
            translate_fn=lambda text: text,
            log_fn=write_log,
        )
    model_name = get_model_display_name(prompts)

    cover_dir = os.path.join(project_dir, "cover")
    os.makedirs(cover_dir, exist_ok=True)
    final_cover_path = os.path.join(cover_dir, "cover.png")

    if is_gemini_prompt(prompts):
        try:
            tmp_out = generate_scene_image(cover_dir, prompts)
            if os.path.abspath(tmp_out) != os.path.abspath(final_cover_path):
                _replace_or_copy(tmp_out, final_cover_path)
            write_log(f"Saved cover image to {final_cover_path}")
            return True
        except Exception as e:
            write_log(f"Failed to generate Gemini cover image for {project_dir}: {e}", level="error")
            return False

    try:
        workflow = build_z_image_workflow(prompts)
        result = send_workflow(
            workflow,
            server,
            log_file=None,
            source_label=cover_config_path,
            model_name=model_name,
        )
    except Exception as e:
        write_log(f"Failed to post cover workflow for {project_dir}: {e}", level="error")
        return False

    prompt_id = result.get("prompt_id") or result.get("id")
    write_log(f"Posted {model_name} cover workflow for {project_dir}, prompt_id={prompt_id}")
    if not prompt_id:
        write_log(f"No prompt id returned for cover generation: {json.dumps(result)}", level="error")
        return False

    image_out = comfyui_api.wait_for_output(server, prompt_id, output_type="image", timeout=timeout, interval=interval)
    if not image_out:
        write_log(f"No image output for cover (prompt_id={prompt_id})", level="error")
        return False

    image_filename = image_out.get("filename") or image_out.get("name") or image_out.get("file")
    image_subfolder = image_out.get("subfolder")
    image_type = image_out.get("type")
    if not image_filename:
        write_log(f"Cannot determine cover image filename from output: {json.dumps(image_out)}", level="error")
        return False

    image_url = comfyui_api.get_file_url(server, image_filename, subfolder=image_subfolder, type_=image_type)
    with tempfile.TemporaryDirectory(prefix="cover_img_") as td:
        tmp_out_path = os.path.join(td, image_filename)
        try:
            comfyui_api.download_file_url(image_url, tmp_out_path)
        except Exception as e:
            write_log(f"Failed to download cover image {image_filename}: {e}", level="error")
            return False
        if not os.path.exists(tmp_out_path) or os.path.getsize(tmp_out_path) <= 0:
            write_log(f"Downloaded cover image missing or empty: {tmp_out_path}", level="error")
            return False
        _replace_or_copy(tmp_out_path, final_cover_path)
    write_log(f"Saved cover image to {final_cover_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate project cover image from cover_prompt.json")
    parser.add_argument("--server", "-s", default=get_server_address("comfyui"), help="ComfyUI server host:port")
    parser.add_argument("--project", "-p", required=True, help="Nama project di dalam folder api_production")
    args = parser.parse_args()

    setup_logging()

    project_dir = os.path.join(PROJECT_ROOT, "api_production", str(args.project).strip())
    if not os.path.isdir(project_dir):
        write_log(f"Project folder not found: {project_dir}", level="error")
        print("Project folder not found; aborting")
        return 1

    ok = process_cover(project_dir, args.server)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
