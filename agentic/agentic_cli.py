"""CLI entry point for agentic variations."""
import argparse
import sys
from pathlib import Path

ROOT = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from logging_config import setup_logging, write_log
from scripts.server_config import get_server_address
from agentic.agentic_pipeline import (
    run_agentic_execute_for_project,
    run_agentic_for_project,
    run_agentic_generate_for_project,
)


def main():
    parser = argparse.ArgumentParser(description="Jalankan variasi agentic AI untuk project")
    parser.add_argument("--server", "-s", default=get_server_address("comfyui"),
                        help="ComfyUI server host:port")
    parser.add_argument("--project", "-p", required=True,
                        help="Nama project di dalam folder api_production")
    parser.add_argument("--scene", "-S", action='append', default=None,
                        help='Scene name to process (e.g., scene_3). Repeatable.')
    parser.add_argument(
        "--mode",
        choices=["all", "generate", "execute"],
        default="all",
        help="Tahap agentic yang dijalankan",
    )
    args = parser.parse_args()

    # Initialize logging
    setup_logging()

    project_dir = Path(ROOT) / "api_production" / args.project
    if not project_dir.is_dir():
        write_log(f"Project folder tidak ditemukan: {project_dir}", level="error")
        print(f"Project folder not found: {project_dir}")
        return 1

    # Filter scenes if specified
    target_scenes = None
    if args.scene:
        requested = set(args.scene)
        available = {d.name for d in project_dir.iterdir() if d.is_dir() and d.name.startswith("scene_")}
        missing = requested - available
        for m in sorted(missing):
            print(f"Warning: requested scene not found: {m}")
        target_scenes = [s for s in requested if s in available]
        if target_scenes:
            write_log(f"[agentic] Filtered to scenes: {sorted(target_scenes)}")

    try:
        if args.mode == "generate":
            success = run_agentic_generate_for_project(project_dir, target_scenes=target_scenes)
        elif args.mode == "execute":
            success = run_agentic_execute_for_project(project_dir, args.server, target_scenes=target_scenes)
        else:
            success = run_agentic_for_project(project_dir, args.server, target_scenes=target_scenes)
    except Exception as e:
        write_log(f"[agentic] Error: {e}", level="error")
        print(f"Error: {e}")
        return 1

    if success:
        print("Agentic variations completed successfully.")
        return 0
    else:
        print("Agentic variations failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
