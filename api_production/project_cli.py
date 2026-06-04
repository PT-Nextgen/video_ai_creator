from pathlib import Path
import sys


def main() -> int:
    launcher_dir = Path(__file__).resolve().parent
    if launcher_dir.name != "api_production":
        raise RuntimeError("Launcher ini harus berada di folder api_production.")

    current_dir = Path.cwd().resolve()
    if current_dir != launcher_dir:
        raise RuntimeError(
            "Launcher ini harus dijalankan dari folder api_production. "
            f"Current directory: {current_dir}"
        )

    repo_root = launcher_dir.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from scripts.project_cli import main as project_cli_main

    return int(project_cli_main())


if __name__ == "__main__":
    raise SystemExit(main())
