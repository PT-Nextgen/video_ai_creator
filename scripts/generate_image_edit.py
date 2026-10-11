import argparse
import os
import sys
from pathlib import Path

from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in os.sys.path:
    os.sys.path.insert(0, PROJECT_ROOT)

from gemini.gemini_image import MODEL_GEMINI_IMAGE, generate_scene_image_edit
from logging_config import setup_logging, write_log
from prompt_localization import prepare_project_prompts_for_runtime, read_json_for_runtime
from scripts.runtime_service_controller import project_uses_llama
from scripts.server_config import get_server_address

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _resolve_source_image(scene_dir: str, source_image: str) -> str:
    source_name = str(source_image or "").strip()
    if not source_name:
        raise RuntimeError("Gambar awal belum dipilih.")
    source_path = os.path.abspath(os.path.join(scene_dir, source_name))
    if not source_path.startswith(os.path.abspath(scene_dir) + os.sep):
        raise RuntimeError("Path gambar awal tidak valid.")
    if not os.path.exists(source_path):
        raise RuntimeError(f"Gambar awal tidak ditemukan: {source_name}")
    ext = os.path.splitext(source_path)[1].lower()
    if ext not in IMAGE_EXTS:
        raise RuntimeError(f"File gambar tidak didukung: {source_name}")
    return source_path


def _resolve_prompt_slot(scene_dir: str, prompt_file: str, prompt_index: int) -> tuple[str, str, str, str]:
    prompt_filename = str(prompt_file or "image_edit_prompt.json").strip() or "image_edit_prompt.json"
    prompt_path = os.path.join(scene_dir, prompt_filename)
    if not os.path.exists(prompt_path):
        raise RuntimeError(f"File prompt tidak ditemukan: {prompt_filename}")

    payload = read_json_for_runtime(prompt_path, required=True, log_fn=write_log)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Format file prompt tidak valid: {prompt_filename}")

    groups = payload.get("groups")
    if not isinstance(groups, list):
        raise RuntimeError(f"Field groups tidak ditemukan pada {prompt_filename}")

    slot_index = max(1, int(prompt_index or 1))
    if slot_index > len(groups):
        raise RuntimeError(f"Prompt group index {slot_index} tidak ditemukan di {prompt_filename}")

    group = groups[slot_index - 1]
    if not isinstance(group, dict):
        raise RuntimeError(f"Format group prompt tidak valid pada slot {slot_index}")

    source_image = str(group.get("source_image", "")).strip()
    prompt_text = str(group.get("prompt", "")).strip()

    if not prompt_text:
        raise RuntimeError(f"prompt pada slot {slot_index} kosong.")

    return source_image, prompt_text, "", ""


def process_scene(
    scene_dir: str,
    server: str,
    model_name: str,
    source_image: str,
    prompt: str,
    gemini_model_id: str = "",
):
    prompt_text = str(prompt or "").strip()
    if not prompt_text:
        raise RuntimeError("Prompt edit wajib diisi.")

    source_path = _resolve_source_image(scene_dir, source_image)
    with Image.open(source_path) as im:
        width, height = im.size
    if width <= 0 or height <= 0:
        raise RuntimeError("Ukuran gambar input tidak valid.")

    model_key = str(model_name or MODEL_GEMINI_IMAGE).strip().lower()
    if model_key != MODEL_GEMINI_IMAGE:
        raise RuntimeError("Flux.2 Image Edit sudah dihapus; gunakan Gemini Image Edit atau Qwen Image Edit.")

    output_path = generate_scene_image_edit(
        scene_dir=scene_dir,
        source_image_path=source_path,
        prompt=prompt_text,
        target_width=width,
        target_height=height,
        gemini_model_id=gemini_model_id,
    )
    write_log(f"Gemini image edit selesai: {output_path}")
    return output_path


def main():
    # Project-specific runtime management is performed by the parent workflow.
    parser = argparse.ArgumentParser(description="Generate image edit for one scene")
    parser.add_argument("--server", "-s", default=get_server_address("comfyui"), help="ComfyUI server host:port")
    parser.add_argument("--project", "-p", required=True, help="Nama project di dalam folder api_production")
    parser.add_argument("--scene", "-S", required=True, help="Nama scene, contoh scene_1")
    parser.add_argument("--model", "-m", default=MODEL_GEMINI_IMAGE, help="Model edit image: gemini")
    parser.add_argument("--gemini-model-id", default="", help="Model Gemini image spesifik (opsional)")
    parser.add_argument("--source-image", default="", help="Nama file gambar sumber di root folder scene")
    parser.add_argument("--prompt", default="", help="Prompt edit gambar")
    parser.add_argument("--prompt-file", default="", help="Nama file prompt scene, contoh image_edit_prompt.json")
    parser.add_argument("--prompt-index", type=int, default=1, help="Index group prompt (1-based) untuk file prompt bertipe groups")
    args = parser.parse_args()

    setup_logging()

    scene_dir = Path(PROJECT_ROOT) / "api_production" / str(args.project).strip() / str(args.scene).strip()
    if not scene_dir.exists() or not scene_dir.is_dir():
        write_log(f"Folder scene tidak ditemukan: {scene_dir}", level="error")
        print("Scene folder not found")
        return 1
    if project_uses_llama(scene_dir.parent):
        prepare_project_prompts_for_runtime(
            scene_dir.parent,
            scene_dirs=[scene_dir],
            additional_filenames=["image_edit_prompt.json"],
            log_fn=write_log,
        )

    try:
        source_image = str(args.source_image or "").strip()
        prompt_text = str(args.prompt or "").strip()
        model_name = str(args.model or "").strip()
        gemini_model_id = str(args.gemini_model_id or "").strip()

        if str(args.prompt_file or "").strip():
            slot_source_image, slot_prompt_text, slot_model_name, slot_gemini_model_id = _resolve_prompt_slot(
                str(scene_dir),
                args.prompt_file,
                args.prompt_index,
            )
            if slot_source_image:
                source_image = slot_source_image
            if slot_prompt_text:
                prompt_text = slot_prompt_text
            if slot_model_name:
                model_name = slot_model_name
            if slot_gemini_model_id:
                gemini_model_id = slot_gemini_model_id

        if not model_name:
            model_name = MODEL_GEMINI_IMAGE
        if not source_image:
            raise RuntimeError("Gambar awal belum dipilih.")
        if not prompt_text:
            raise RuntimeError("Prompt edit wajib diisi.")

        output_path = process_scene(
            scene_dir=str(scene_dir),
            server=args.server,
            model_name=model_name,
            source_image=source_image,
            prompt=prompt_text,
            gemini_model_id=gemini_model_id,
        )
        print(f"OK: {output_path}")
        return 0
    except Exception as e:
        write_log(f"Gagal generate image edit: {e}", level="error")
        print(f"Failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
