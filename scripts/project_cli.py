import argparse
import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scene_manager_ui import (
    API_PRODUCTION,
    DEFAULT_PROJECT_SETTINGS,
    DEFAULT_Z_IMAGE_PROMPT,
    create_project_on_disk,
    create_scene_in_project,
    list_scene_dirs_in_project,
)

SCENE_TYPE_CHOICES = [
    "wan22_i2v",
    "wan22_t2v_i2v",
    "wan22_s2v",
    "i2v",
    "web_scroll",
    "image_pan",
    "image_zoom",
]
PROJECT_MODEL_CHOICES = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
]
VOICE_PROVIDER_CHOICES = [
    "gemini",
    "elevenlabs",
]


def str_to_bool(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("Gunakan true/false, yes/no, atau 1/0.")


def build_project_settings(args) -> dict:
    settings = copy.deepcopy(DEFAULT_PROJECT_SETTINGS)
    settings["project_description"] = args.description or ""
    settings["video_size"] = {
        "width": int(args.width),
        "height": int(args.height),
    }
    settings["comfyui_server"] = str(args.comfyui_server or settings["comfyui_server"]).strip()
    settings["prompt_generation"] = {
        "provider": "gemini",
        "model": str(args.prompt_generation_model or settings["prompt_generation"]["model"]).strip(),
    }
    settings["translate"] = {
        "provider": "gemini",
        "model": str(args.translate_model or settings["translate"]["model"]).strip(),
    }
    settings["voice"] = {
        "voice_provider": str(args.voice_provider or settings["voice"]["voice_provider"]).strip(),
    }
    settings["caption"] = {
        "generate_caption": bool(args.generate_caption),
    }
    settings["cover"] = copy.deepcopy(DEFAULT_Z_IMAGE_PROMPT)
    settings["cover"]["width"] = int(args.width)
    settings["cover"]["height"] = int(args.height)
    return settings


def command_create_project(args) -> int:
    project_settings = build_project_settings(args)
    project_dir, _saved_settings = create_project_on_disk(
        args.project,
        create_default_scene=bool(args.with_default_scene),
        project_settings=project_settings,
    )
    scene_count = len(list_scene_dirs_in_project(project_dir))
    print(f"Project created: {project_dir}")
    print(f"Scenes created: {scene_count}")
    return 0


def command_create_scene(args) -> int:
    project_dir = API_PRODUCTION / args.project
    scene_dir = create_scene_in_project(
        project_dir,
        scene_type=args.scene_type,
        scene_title=args.title or "",
        scene_description=args.scene_description or "",
        voice_text=args.voice_text or "",
        duration=int(args.duration),
    )
    print(f"Scene created: {scene_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI helper untuk membuat project dan scene dengan jalur yang sama seperti UI."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_project_parser = subparsers.add_parser(
        "create-project",
        help="Buat project baru. Default-nya project kosong tanpa scene.",
    )
    create_project_parser.add_argument("--project", "-p", required=True, help="Nama project di api_production.")
    create_project_parser.add_argument("--description", default="", help="Deskripsi project.")
    create_project_parser.add_argument("--width", type=int, default=480, help="Lebar video project.")
    create_project_parser.add_argument("--height", type=int, default=848, help="Tinggi video project.")
    create_project_parser.add_argument(
        "--comfyui-server",
        default=DEFAULT_PROJECT_SETTINGS["comfyui_server"],
        help="Alamat ComfyUI server, contoh: nextgenserver:8188",
    )
    create_project_parser.add_argument(
        "--prompt-generation-model",
        choices=PROJECT_MODEL_CHOICES,
        default=DEFAULT_PROJECT_SETTINGS["prompt_generation"]["model"],
        help="Model untuk prompt generation project.",
    )
    create_project_parser.add_argument(
        "--translate-model",
        choices=PROJECT_MODEL_CHOICES,
        default=DEFAULT_PROJECT_SETTINGS["translate"]["model"],
        help="Model untuk translate project.",
    )
    create_project_parser.add_argument(
        "--voice-provider",
        choices=VOICE_PROVIDER_CHOICES,
        default=DEFAULT_PROJECT_SETTINGS["voice"]["voice_provider"],
        help="Provider voice default project.",
    )
    create_project_parser.add_argument(
        "--generate-caption",
        type=str_to_bool,
        default=DEFAULT_PROJECT_SETTINGS["caption"]["generate_caption"],
        help="Aktifkan caption otomatis: true/false.",
    )
    create_project_parser.add_argument(
        "--with-default-scene",
        action="store_true",
        help="Ikuti perilaku tombol UI dan buat scene_1 default.",
    )
    create_project_parser.set_defaults(func=command_create_project)

    create_scene_parser = subparsers.add_parser(
        "create-scene",
        help="Tambah scene baru ke project yang sudah ada.",
    )
    create_scene_parser.add_argument("--project", "-p", required=True, help="Nama project di api_production.")
    create_scene_parser.add_argument(
        "--scene-type",
        required=True,
        choices=SCENE_TYPE_CHOICES,
        help="Tipe scene.",
    )
    create_scene_parser.add_argument("--title", default="", help="Judul scene.")
    create_scene_parser.add_argument("--scene-description", default="", help="Deskripsi scene.")
    create_scene_parser.add_argument("--voice-text", default="", help="Voice text scene.")
    create_scene_parser.add_argument("--duration", type=int, default=10, help="Durasi scene dalam detik.")
    create_scene_parser.set_defaults(func=command_create_scene)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
