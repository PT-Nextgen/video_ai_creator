import argparse
import json
import os
import sys
from pathlib import Path

from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in os.sys.path:
    os.sys.path.insert(0, PROJECT_ROOT)

from flux2.flux2 import MODEL_FLUX2, build_flux2_edit_workflow
from gemini.gemini_image import MODEL_GEMINI_IMAGE, generate_scene_image_edit
from logging_config import setup_logging, write_log
from scripts import comfyui_api
from scripts.server_config import get_server_address

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _extract_uploaded_name(upload_info: dict, fallback_name: str) -> str:
    for key in ("name", "filename", "file"):
        value = str(upload_info.get(key, "")).strip()
        if value:
            return value
    return fallback_name


def _download_comfy_image(server: str, image_out: dict, output_dir: str) -> str:
    image_filename = image_out.get("filename") or image_out.get("name") or image_out.get("file")
    image_subfolder = image_out.get("subfolder")
    image_type = image_out.get("type")
    if not image_filename:
        raise RuntimeError(f"Tidak bisa membaca filename output image: {json.dumps(image_out)}")
    image_url = comfyui_api.get_file_url(server, image_filename, subfolder=image_subfolder, type_=image_type)
    output_path = os.path.join(output_dir, image_filename)
    comfyui_api.download_file_url(image_url, output_path)
    if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError(f"File hasil download kosong/tidak ada: {output_path}")
    return output_path


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

    model_key = str(model_name or MODEL_FLUX2).strip().lower()
    if model_key == MODEL_GEMINI_IMAGE:
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

    upload_info = comfyui_api.upload_file(server, source_path, file_type="image")
    uploaded_name = _extract_uploaded_name(upload_info, os.path.basename(source_path))
    workflow = build_flux2_edit_workflow(
        source_image_name=uploaded_name,
        prompt=prompt_text,
        width=width,
        height=height,
    )
    result = comfyui_api.post_workflow_api(workflow, server)
    prompt_id = result.get("prompt_id") or result.get("id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI tidak mengembalikan prompt_id: {json.dumps(result)}")
    write_log(f"Flux2 edit workflow terkirim, prompt_id={prompt_id}")

    image_out = comfyui_api.wait_for_output(server, prompt_id, output_type="image", timeout=900, interval=2.0)
    if not image_out:
        raise RuntimeError(f"Output image tidak ditemukan (prompt_id={prompt_id})")
    output_path = _download_comfy_image(server, image_out, scene_dir)
    write_log(f"Flux2 image edit selesai: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate image edit for one scene")
    parser.add_argument("--server", "-s", default=get_server_address("comfyui"), help="ComfyUI server host:port")
    parser.add_argument("--project", "-p", required=True, help="Nama project di dalam folder api_production")
    parser.add_argument("--scene", "-S", required=True, help="Nama scene, contoh scene_1")
    parser.add_argument("--model", "-m", default=MODEL_FLUX2, help="Model edit image: flux.2 atau gemini")
    parser.add_argument("--gemini-model-id", default="", help="Model Gemini image spesifik (opsional)")
    parser.add_argument("--source-image", required=True, help="Nama file gambar sumber di root folder scene")
    parser.add_argument("--prompt", required=True, help="Prompt edit gambar")
    args = parser.parse_args()

    setup_logging()

    scene_dir = Path(PROJECT_ROOT) / "api_production" / str(args.project).strip() / str(args.scene).strip()
    if not scene_dir.exists() or not scene_dir.is_dir():
        write_log(f"Folder scene tidak ditemukan: {scene_dir}", level="error")
        print("Scene folder not found")
        return 1

    try:
        output_path = process_scene(
            scene_dir=str(scene_dir),
            server=args.server,
            model_name=args.model,
            source_image=args.source_image,
            prompt=args.prompt,
            gemini_model_id=args.gemini_model_id,
        )
        print(f"OK: {output_path}")
        return 0
    except Exception as e:
        write_log(f"Gagal generate image edit: {e}", level="error")
        print(f"Failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
