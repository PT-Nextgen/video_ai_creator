"""Upscale marked root-scene video outputs through the GAN ComfyUI workflow."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logging_config import get_logger, setup_logging, write_log
from scripts import comfyui_api
from scripts.runtime_service_controller import RuntimeServiceController, project_uses_llama
from scripts.server_config import get_server_address
from scripts.timeout_config import COMFYUI_POLL_INTERVAL_SECONDS, COMFYUI_WORKFLOW_TIMEOUT_SECONDS


setup_logging()
logger = get_logger(__name__)

TEMPLATE_PATH = ROOT / "api_template" / "gan_upscaler_api.json"
API_PRODUCTION_ROOT = ROOT / "api_production"
OUTPUT_FILENAME = "gan_upscaled_2x.mp4"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}


def _scene_sort_key(path: Path):
    name = path.name.lower()
    try:
        return (0, int(name.split("_", 1)[1]))
    except (IndexError, ValueError):
        return (1, name)


def _load_template() -> dict:
    with TEMPLATE_PATH.open("r", encoding="utf-8") as handle:
        workflow = json.load(handle)
    if not isinstance(workflow, dict):
        raise ValueError(f"Template GAN bukan object JSON: {TEMPLATE_PATH}")
    return workflow


def _latest_root_video(scene_dir: Path) -> Path | None:
    videos = [
        path
        for path in scene_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in VIDEO_EXTENSIONS
        and path.name.lower() != OUTPUT_FILENAME.lower()
    ]
    if not videos:
        return None
    return max(videos, key=lambda path: (path.stat().st_mtime, path.name.lower()))


def _uploaded_name(upload_info: dict, fallback: Path) -> str:
    if isinstance(upload_info, dict):
        for key in ("name", "filename", "file"):
            value = str(upload_info.get(key, "")).strip()
            if value:
                return value
    return fallback.name


def _upload_video(server: str, source: Path) -> str:
    response = comfyui_api.upload_file(server, str(source), file_type="video")
    name = _uploaded_name(response, source)
    write_log(f"[gan-upscale] Upload video berhasil: {source.name} -> {name}")
    return name


def _build_workflow(uploaded_name: str) -> dict:
    workflow = _load_template()
    node = workflow.get("9")
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, dict):
        raise ValueError("Node 9 LoadVideo tidak memiliki inputs yang valid")
    inputs["file"] = uploaded_name
    return workflow


def _output_filename(video_output: dict) -> str:
    if not isinstance(video_output, dict):
        return ""
    for key in ("filename", "name", "file"):
        value = str(video_output.get(key, "")).strip()
        if value:
            return value
    return ""


def upscale_scene(scene_dir: Path, server: str) -> bool:
    meta_path = scene_dir / "scene_meta.json"
    try:
        with meta_path.open("r", encoding="utf-8") as handle:
            meta = json.load(handle)
    except Exception as exc:
        write_log(f"[gan-upscale] {scene_dir.name}: gagal membaca scene_meta.json: {exc}", level="error")
        return False

    if not bool(meta.get("upscale", False)):
        write_log(f"[gan-upscale] {scene_dir.name}: upscale=false, dilewati")
        return True

    source = _latest_root_video(scene_dir)
    if source is None:
        write_log(f"[gan-upscale] {scene_dir.name}: video output root tidak ditemukan", level="error")
        return False

    write_log(f"[gan-upscale] {scene_dir.name}: mulai, sumber={source.name}")
    try:
        uploaded_name = _upload_video(server, source)
        workflow = _build_workflow(uploaded_name)
        result = comfyui_api.post_workflow_api(workflow, server)
        prompt_id = result.get("prompt_id") or result.get("id") if isinstance(result, dict) else None
        write_log(f"[gan-upscale] {scene_dir.name}: workflow dikirim, prompt_id={prompt_id}")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI tidak mengembalikan prompt_id: {result}")

        video_output = comfyui_api.wait_for_output(
            server,
            prompt_id,
            output_type="video",
            timeout=COMFYUI_WORKFLOW_TIMEOUT_SECONDS,
            interval=COMFYUI_POLL_INTERVAL_SECONDS,
        )
        output_name = _output_filename(video_output)
        if not output_name:
            raise RuntimeError("Output video GAN tidak ditemukan")
        video_url = comfyui_api.get_file_url(
            server,
            output_name,
            subfolder=video_output.get("subfolder"),
            type_=video_output.get("type"),
        )

        final_path = scene_dir / OUTPUT_FILENAME
        temporary_path = scene_dir / f".{OUTPUT_FILENAME}.download.tmp"
        try:
            comfyui_api.download_file_url(video_url, str(temporary_path))
            if not temporary_path.is_file() or temporary_path.stat().st_size <= 0:
                raise RuntimeError(f"Download hasil GAN kosong: {temporary_path}")
            os.replace(temporary_path, final_path)
        finally:
            if temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass
        write_log(f"[gan-upscale] {scene_dir.name}: selesai, hasil={final_path.name}")
        return True
    except Exception as exc:
        logger.error("[gan-upscale] %s gagal: %s", scene_dir.name, exc)
        write_log(f"[gan-upscale] {scene_dir.name}: gagal: {exc}", level="error")
        return False


def run(project: str, server: str, selected_scenes: list[str] | None = None) -> int:
    project_dir = (API_PRODUCTION_ROOT / str(project).strip()).resolve()
    if not project_dir.is_dir():
        write_log(f"[gan-upscale] Project tidak ditemukan: {project_dir}", level="error")
        return 1

    scene_dirs = sorted(
        [path for path in project_dir.iterdir() if path.is_dir() and path.name.lower().startswith("scene_")],
        key=_scene_sort_key,
    )
    if selected_scenes:
        wanted = {str(value).strip().lower() for value in selected_scenes}
        scene_dirs = [path for path in scene_dirs if path.name.lower() in wanted]
    if not scene_dirs:
        write_log(f"[gan-upscale] Tidak ada scene yang cocok pada {project_dir}", level="error")
        return 1

    if project_uses_llama(project_dir):
        controller = RuntimeServiceController.from_config()
        write_log("[gan-upscale] Project memakai Llama; memastikan ComfyUI aktif")
        controller.ensure_comfyui(reason=f"GAN upscale project={project}")
    else:
        write_log("[gan-upscale] Project memakai Gemini; switch runtime tidak diperlukan")

    for scene_dir in scene_dirs:
        if not upscale_scene(scene_dir, server):
            write_log(f"[gan-upscale] Proses dihentikan setelah gagal pada {scene_dir.name}", level="error")
            return 1
    write_log(f"[gan-upscale] Semua scene selesai diproses: {project_dir.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GAN upscale video output root scene yang memiliki upscale=true")
    parser.add_argument("--project", "-p", required=True, help="Nama project di dalam api_production")
    parser.add_argument("--server", "-s", default=get_server_address("comfyui"), help="Server ComfyUI host:port")
    parser.add_argument("--scene", "-S", action="append", help="Scene tertentu; dapat diulang")
    args = parser.parse_args()
    return run(args.project, args.server, args.scene)


if __name__ == "__main__":
    raise SystemExit(main())
