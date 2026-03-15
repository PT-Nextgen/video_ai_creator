import datetime
import os
import shutil


def make_timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def unique_path(path):
    base = path
    i = 1
    while os.path.exists(path):
        path = f"{base}_{i}"
        i += 1
    return path


def copy_and_rename(source_dir, backup_root):
    source_dir = os.path.abspath(source_dir)
    backup_root = os.path.abspath(backup_root)

    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"Source folder not found: {source_dir}")

    os.makedirs(backup_root, exist_ok=True)

    ts = make_timestamp()
    tmp_name = f"api_production_copy_{ts}"
    tmp_dest = os.path.join(backup_root, tmp_name)
    final_name = f"api_production_{ts}"
    final_dest = os.path.join(backup_root, final_name)

    # Ensure unique final name if already present
    final_dest = unique_path(final_dest)

    try:
        shutil.copytree(source_dir, tmp_dest)
        os.replace(tmp_dest, final_dest)
    except Exception:
        # clean up partial copy if exists
        if os.path.exists(tmp_dest):
            try:
                shutil.rmtree(tmp_dest)
            except Exception:
                pass
        raise

    return final_dest


def main():
    # Fixed source and backup folder names (no CLI args)
    source = "api_production"
    backup_dir = "backup_production"

    try:
        dest = copy_and_rename(source, backup_dir)
        print(f"OK: copied '{source}' -> '{dest}'")
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 2
    except Exception as e:
        print(f"Error during backup: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
