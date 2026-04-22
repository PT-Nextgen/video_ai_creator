import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in os.sys.path:
    os.sys.path.insert(0, PROJECT_ROOT)

from gemini.gemini_image import generate_scene_image, is_gemini_prompt
from logging_config import setup_logging, write_log
from scripts.workflow_builders import load_json
from prompt_localization import read_json_for_runtime, resolve_prompt_payload_for_runtime


API_PRODUCTION = os.path.join(PROJECT_ROOT, "api_production")


def _scene_sort_key(name: str):
    if not str(name).startswith("scene_"):
        return (10**9, str(name))
    try:
        return (int(str(name).split("_", 1)[1]), str(name))
    except Exception:
        return (10**9, str(name))


def process_scene(scene_dir: str):
    z_prompt_path = os.path.join(scene_dir, "z_image_prompt.json")
    if not os.path.exists(z_prompt_path):
        write_log(f"z_image_prompt.json not found in {scene_dir}", level="error")
        return False
    try:
        z_prompt = read_json_for_runtime(z_prompt_path, required=True, log_fn=write_log)
    except Exception as e:
        write_log(f"Gagal sinkronisasi prompt runtime untuk {z_prompt_path}: {e}", level="warning")
        raw_prompt = load_json(z_prompt_path)
        z_prompt, _, _ = resolve_prompt_payload_for_runtime(
            "z_image_prompt.json",
            raw_prompt,
            translate_fn=lambda text: text,
            log_fn=write_log,
        )
    if not is_gemini_prompt(z_prompt):
        write_log(f"Scene {scene_dir} bukan model Gemini; skip.")
        return True
    try:
        out = generate_scene_image(scene_dir, z_prompt)
        write_log(f"Generated Gemini initial image: {out}")
        return True
    except Exception as e:
        write_log(f"Gagal generate Gemini image untuk {scene_dir}: {e}", level="error")
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate initial Gemini images for scenes")
    parser.add_argument("--project", "-p", required=True, help="Nama project di dalam folder api_production")
    parser.add_argument("--scene", "-S", action="append", help="Scene name to process (e.g., scene_1). Repeatable")
    args = parser.parse_args()

    setup_logging()

    project_root = os.path.join(API_PRODUCTION, str(args.project).strip())
    if not os.path.exists(project_root):
        write_log(f"Project folder not found: {project_root}", level="error")
        print("Project folder not found; aborting")
        return 1

    scenes = sorted([d for d in os.listdir(project_root) if d.startswith("scene_")], key=_scene_sort_key)
    if args.scene:
        requested = set(args.scene)
        scenes = [s for s in scenes if s in requested]
    if not scenes:
        write_log("Tidak ada scene yang cocok untuk diproses.", level="error")
        print("No matching scenes found")
        return 1

    for scene in scenes:
        scene_dir = os.path.join(project_root, scene)
        print(f"Processing {scene_dir}")
        ok = process_scene(scene_dir)
        if not ok:
            print(f"Failed processing {scene}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
