import datetime
import os
import shutil
import tempfile
import argparse


def make_timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def unique_path(path):
    base = path
    i = 1
    while os.path.exists(path):
        path = f"{base}_{i}"
        i += 1
    return path


def zip_project(source_dir, backup_root, project_name):
    source_dir = os.path.abspath(source_dir)
    backup_root = os.path.abspath(backup_root)

    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"Source folder not found: {source_dir}")

    os.makedirs(backup_root, exist_ok=True)

    final_name = f"{project_name}.zip"
    final_dest = os.path.join(backup_root, final_name)
    if os.path.exists(final_dest):
        os.remove(final_dest)

    archive_base = os.path.splitext(final_dest)[0]
    source_parent = os.path.dirname(source_dir)
    source_name = os.path.basename(source_dir)

    tmp_zip = None
    try:
        with tempfile.TemporaryDirectory(prefix="backup_zip_") as tmp_dir:
            tmp_base = os.path.join(tmp_dir, os.path.basename(archive_base))
            tmp_zip = shutil.make_archive(tmp_base, "zip", root_dir=source_parent, base_dir=source_name)
            shutil.copy2(tmp_zip, final_dest)
    except Exception:
        if tmp_zip and os.path.exists(tmp_zip):
            try:
                os.remove(tmp_zip)
            except Exception:
                pass
        raise

    return final_dest


def main():
    parser = argparse.ArgumentParser(description="Backup satu project api_production menjadi file ZIP")
    parser.add_argument("--project", "-p", required=True, help="Nama project di dalam folder api_production")
    args = parser.parse_args()

    project_name = str(args.project).strip()
    if not project_name:
        print("Error: project name cannot be empty")
        return 2

    source = os.path.join("api_production", project_name)
    backup_dir = "backup_production"

    try:
        dest = zip_project(source, backup_dir, project_name=project_name)
        print(f"OK: zipped project '{project_name}' -> '{dest}'")
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 2
    except Exception as e:
        print(f"Error during backup: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
