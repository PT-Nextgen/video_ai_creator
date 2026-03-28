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


def zip_and_rename(source_dir, backup_root, zip_name=None):
    source_dir = os.path.abspath(source_dir)
    backup_root = os.path.abspath(backup_root)

    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"Source folder not found: {source_dir}")

    os.makedirs(backup_root, exist_ok=True)

    if zip_name:
        final_name = zip_name.strip()
        if not final_name.lower().endswith(".zip"):
            final_name = f"{final_name}.zip"
    else:
        ts = make_timestamp()
        final_name = f"api_production_{ts}.zip"

    final_dest = os.path.join(backup_root, final_name)
    final_dest = unique_path(final_dest)

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
    parser = argparse.ArgumentParser(description="Backup api_production menjadi file ZIP")
    parser.add_argument("--zip-name", default="", help="Nama file zip output (opsional, .zip akan ditambahkan jika belum ada)")
    args = parser.parse_args()

    # Fixed source and backup folder names
    source = "api_production"
    backup_dir = "backup_production"

    try:
        dest = zip_and_rename(source, backup_dir, zip_name=args.zip_name)
        print(f"OK: zipped '{source}' -> '{dest}'")
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 2
    except Exception as e:
        print(f"Error during backup: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
