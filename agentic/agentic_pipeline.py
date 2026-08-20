"""Agentic pipeline orchestration.

Tahap 1: Generate konfigurasi variasi
1. LLM generate file JSON variasi
2. Simpan hasil ke folder variasiN/

Tahap 2: Eksekusi variasi
1. Cari folder variasi yang belum punya status.done
2. Copy isi variasi ke root scene
3. Jalankan generate image / main.py
4. Copy hasil root kembali ke folder variasi
5. Buat status.done
6. Cleanup media di root
"""
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import re
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

VENV_PYTHON = Path(ROOT) / ".venv" / "Scripts" / "python.exe"

from logging_config import write_log
from scripts.project_settings import load_project_settings
from scripts.server_config import load_server_config
from scripts.runtime_service_controller import RuntimeServiceController, project_uses_llama
from prompt_localization import prepare_project_prompts_for_runtime
from agentic.agentic_config import load_agentic_config
from agentic.agentic_llm import expected_output_files, generate_variations


VARIATION_DIR_PATTERN = re.compile(r"^variasi_?\d+$", re.IGNORECASE)
STATUS_DONE_FILENAME = "status.done"
STATUS_FAILED_FILENAME = "status.failed"
VARIATION_FAIL_FILENAME = "variasi_gagal.txt"


def _run_script(
    script_path: Path,
    args: list[str],
    cwd: Path | None = None,
    timeout: int | None = None,
) -> bool:
    """Run a Python script as a subprocess. Returns True on success."""
    python_executable = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
    cmd = [str(python_executable), str(script_path)] + args
    timeout_label = "call-managed" if timeout is None else f"{int(timeout)}s"
    write_log(f"[agentic] Running (timeout={timeout_label}): {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=None if timeout is None else int(timeout),
        )
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                write_log(f"[agentic] {line}")
        if result.stderr:
            for line in result.stderr.strip().split("\n"):
                write_log(f"[agentic] STDERR: {line}", level="warning")
        write_log(f"[agentic] Script selesai: {script_path.name} (exit={result.returncode})")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        write_log(
            f"[agentic] Script timeout setelah {int(timeout)} detik: {script_path.name}",
            level="error",
        )
        return False
    except Exception as e:
        write_log(f"[agentic] Script error: {script_path.name}: {e}", level="error")
        return False


def _copy_dir_contents(src: Path, dst: Path, exclude_status_done: bool = False) -> bool:
    """Copy scene contents from src to dst, excluding nested variation folders."""
    try:
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            if item.resolve() == dst.resolve():
                continue
            if item.is_dir() and VARIATION_DIR_PATTERN.match(item.name.strip()):
                continue
            if exclude_status_done and item.is_file() and item.name == STATUS_DONE_FILENAME:
                continue
            target = dst / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        return True
    except Exception as e:
        write_log(f"[agentic] Copy error {src} -> {dst}: {e}", level="error")
        return False


def _write_scene_meta(scene_dir: Path, scene_meta: dict) -> bool:
    """Write the authoritative scene metadata without leaving a partial JSON file."""
    meta_path = Path(scene_dir) / "scene_meta.json"
    temp_path = meta_path.with_name(f"{meta_path.name}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(scene_meta, f, ensure_ascii=False, indent=2)
            f.write("\n")
        temp_path.replace(meta_path)
        return True
    except Exception as e:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        write_log(f"[agentic] Gagal menulis scene_meta.json: {e}", level="error")
        return False


def _copy_scene_baseline_files(src: Path, dst: Path) -> bool:
    """Copy non-media baseline scene files so a variation folder is self-contained."""
    try:
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            if item.resolve() == dst.resolve():
                continue
            if item.is_dir() and VARIATION_DIR_PATTERN.match(item.name.strip()):
                continue
            if item.is_file() and item.name == STATUS_DONE_FILENAME:
                continue
            if item.is_file() and item.suffix.lower() in {".png", ".mp4", ".jpg", ".jpeg", ".webp", ".mov", ".avi", ".mkv", ".webm"}:
                continue
            target = dst / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        return True
    except Exception as e:
        write_log(f"[agentic] Copy baseline error {src} -> {dst}: {e}", level="error")
        return False


def _extract_numeric_suffix(name: str) -> int | None:
    match = re.search(r"(\d+)$", str(name).strip())
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _record_variation_failure(project_dir: Path, scene_dir: Path, variation_dir: Path, message: str) -> bool:
    """Append a failure record to project-root variasi_gagal.txt."""
    project_dir = Path(project_dir)
    scene_dir = Path(scene_dir)
    variation_dir = Path(variation_dir)
    timestamp = datetime.now().isoformat(timespec="seconds")
    scene_number = _extract_numeric_suffix(scene_dir.name)
    variation_number = _extract_numeric_suffix(variation_dir.name)
    fail_path = project_dir / VARIATION_FAIL_FILENAME
    line = (
        f"[{timestamp}] scene={scene_dir.name}"
        + (f" (no {scene_number})" if scene_number is not None else "")
        + f", variasi={variation_dir.name}"
        + (f" (no {variation_number})" if variation_number is not None else "")
        + f" - {message}\n"
    )
    try:
        with fail_path.open("a", encoding="utf-8") as f:
            f.write(line)
        return True
    except Exception as e:
        write_log(f"[agentic] Gagal tulis {fail_path.name}: {e}", level="error")
        return False


def _write_variation_failure_marker(variation_dir: Path, message: str) -> bool:
    """Mark a diagnostic variation folder as failed without making it executable."""
    variation_dir = Path(variation_dir)
    try:
        variation_dir.mkdir(parents=True, exist_ok=True)
        (variation_dir / STATUS_FAILED_FILENAME).write_text(
            f"{message}\n",
            encoding="utf-8",
        )
        return True
    except Exception as e:
        write_log(
            f"[agentic] Gagal menulis {STATUS_FAILED_FILENAME} di {variation_dir}: {e}",
            level="error",
        )
        return False


def _delete_media_files(
    scene_dir: Path,
    preserve_images: bool = False,
    preserve_names: set[str] | None = None,
) -> int:
    """Delete generated media while retaining explicitly required references."""
    count = 0
    # Standalone MiniMax H3 I2V accepts png/jpg/jpeg/webp root references. When
    # image generation is disabled, all of those references must survive the
    # per-variation cleanup; only generated videos are removed.
    extensions = ["*.mp4"] if preserve_images else ["*.mp4", "*.png"]
    preserve_names = {str(name).strip() for name in (preserve_names or set()) if str(name).strip()}
    for ext in extensions:
        for f in glob.glob(str(scene_dir / ext)):
            if Path(f).name in preserve_names:
                continue
            try:
                os.remove(f)
                count += 1
            except Exception as e:
                write_log(f"[agentic] Failed to delete {f}: {e}", level="warning")
    return count


def _existing_variation_dirs(scene_dir: Path) -> list[Path]:
    dirs = []
    for item in scene_dir.iterdir():
        if item.is_dir() and VARIATION_DIR_PATTERN.match(item.name.strip()):
            if (item / STATUS_FAILED_FILENAME).is_file():
                continue
            dirs.append(item)
    return sorted(
        dirs,
        key=lambda d: int(re.search(r"(\d+)$", d.name).group(1)) if re.search(r"(\d+)$", d.name) else 999999,
    )


def _pending_variation_dirs(scene_dir: Path) -> list[Path]:
    """Return every variation that has not completed, independent of Agentic count."""
    return [
        variation_dir
        for variation_dir in _existing_variation_dirs(scene_dir)
        if not (variation_dir / STATUS_DONE_FILENAME).is_file()
        and not (variation_dir / STATUS_FAILED_FILENAME).is_file()
    ]


def _existing_variation_indices(scene_dir: Path) -> list[int]:
    indices = []
    for item in _existing_variation_dirs(scene_dir):
        digits_match = re.search(r"(\d+)$", item.name.strip())
        if not digits_match:
            continue
        try:
            indices.append(int(digits_match.group(1)))
        except ValueError:
            continue
    return sorted(set(indices))


def _next_variation_index(scene_dir: Path) -> int:
    indices = _existing_variation_indices(scene_dir)
    return (indices[-1] + 1) if indices else 1


def _sanitize_output_filename(filename: str) -> str | None:
    raw = str(filename or "").strip()
    if not raw:
        return None
    normalized = Path(raw)
    if normalized.is_absolute():
        return None
    parts = normalized.parts
    if any(part in ("..", ".", "") for part in parts):
        return None
    if len(parts) != 1:
        return None
    safe_name = normalized.name
    return safe_name if safe_name == raw else None


def _find_latest_image(scene_dir: Path) -> str | None:
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.webp"]
    imgs = []
    for pattern in patterns:
        imgs.extend(glob.glob(str(scene_dir / pattern)))
    imgs = [os.path.abspath(path) for path in imgs if os.path.isfile(path)]
    if not imgs:
        return None
    imgs.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    return imgs[0]


def _generate_initial_image(scene_dir: Path, project_name: str, server: str) -> bool:
    script = Path(ROOT) / "scripts" / "generate_initial_image.py"
    args = ["--project", project_name, "--scene", scene_dir.name, "--server", server]
    return _run_script(script, args, cwd=scene_dir)


def _generate_extra_images(scene_dir: Path, project_name: str, server: str) -> bool:
    script = Path(ROOT) / "scripts" / "generate_initial_image.py"
    extra_path = scene_dir / "z_image_extra_prompts.json"
    if not extra_path.exists():
        write_log("[agentic] z_image_extra_prompts.json tidak ditemukan, skip extra images")
        return True

    try:
        with extra_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        write_log("[agentic] Gagal baca z_image_extra_prompts.json, skip extra images")
        return True

    groups = data.get("groups", [])
    if not groups:
        return True

    for idx, group in enumerate(groups, start=1):
        positive = str(group.get("positive_prompt", "")).strip()
        if not positive or positive == "{}":
            write_log(f"[agentic] Slot extra {idx} kosong, skip")
            continue
        args = [
            "--project", project_name,
            "--scene", scene_dir.name,
            "--server", server,
            "--prompt-file", "z_image_extra_prompts.json",
            "--prompt-index", str(idx),
        ]
        if not _run_script(script, args, cwd=scene_dir):
            write_log(f"[agentic] Extra image slot {idx} gagal", level="error")
            return False
    return True


def _generate_image_edits(scene_dir: Path, project_name: str, server: str) -> bool:
    script = Path(ROOT) / "scripts" / "generate_image_edit.py"
    edit_path = scene_dir / "image_edit_prompt.json"
    if not edit_path.exists():
        write_log("[agentic] image_edit_prompt.json tidak ditemukan, skip image edits")
        return True

    try:
        with edit_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        write_log("[agentic] Gagal baca image_edit_prompt.json, skip image edits")
        return True

    groups = data.get("groups", [])
    if not groups:
        return True

    for idx, group in enumerate(groups, start=1):
        prompt_val = group.get("prompt", "")
        if isinstance(prompt_val, dict):
            positive = str(prompt_val.get("id_new", "")).strip() or str(prompt_val.get("en", "")).strip()
        else:
            positive = str(prompt_val).strip()
        if not positive:
            write_log(f"[agentic] Slot edit {idx} kosong, skip")
            continue

        source_image = str(group.get("source_image", "")).strip()
        if not source_image:
            latest = _find_latest_image(scene_dir)
            if latest:
                source_image = os.path.basename(latest)
            else:
                write_log(f"[agentic] Tidak ada gambar untuk slot edit {idx}, skip")
                continue

        args = [
            "--project", project_name,
            "--scene", scene_dir.name,
            "--server", server,
            "--prompt-file", "image_edit_prompt.json",
            "--prompt-index", str(idx),
            "--source-image", source_image,
        ]
        if not _run_script(script, args, cwd=scene_dir):
            write_log(f"[agentic] Image edit slot {idx} gagal", level="error")
            return False
    return True


def _process_scene_with_main(scene_dir: Path, project_name: str, server: str) -> bool:
    main_script = Path(ROOT) / "main.py"
    args = ["--project", project_name, "--scene", scene_dir.name, "--server", server]
    scene_meta = _load_scene_meta(scene_dir) or {}
    scene_type = str(scene_meta.get("scene_type", "")).strip()
    return _run_script(main_script, args, cwd=scene_dir, timeout=None)


def _load_scene_meta(scene_dir: Path) -> dict | None:
    meta_path = scene_dir / "scene_meta.json"
    if not meta_path.exists():
        write_log(f"[agentic] {scene_dir.name}: scene_meta.json tidak ditemukan", level="error")
        return None
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        write_log(f"[agentic] {scene_dir.name}: Gagal baca scene_meta.json: {e}", level="error")
        return None


def _variation_dir_name(index: int) -> str:
    return f"variasi{index}"


def _write_variation_payloads(
    variation_dir: Path,
    variations: dict,
    allowed_output_files: set[str],
) -> bool:
    variation_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in variations.items():
        safe_filename = _sanitize_output_filename(filename)
        if not safe_filename:
            write_log(f"[agentic] {variation_dir.name}: Nama file output tidak aman: {filename!r}", level="error")
            return False
        if safe_filename not in allowed_output_files:
            write_log(
                f"[agentic] {variation_dir.name}: File output tidak diizinkan: {safe_filename}",
                level="error",
            )
            return False
        try:
            with (variation_dir / safe_filename).open("w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
            write_log(f"[agentic] {variation_dir.name}: Written {safe_filename}")
        except Exception as e:
            write_log(f"[agentic] {variation_dir.name}: Gagal tulis {safe_filename}: {e}", level="error")
            return False
    return True


def _write_variation_prompt_logs(
    variation_dir: Path,
    input_prompt_text: str,
    output_prompt_text: str,
) -> bool:
    variation_dir.mkdir(parents=True, exist_ok=True)
    files_to_write = {
        "input-prompt.txt": str(input_prompt_text or ""),
        "output-prompt.txt": str(output_prompt_text or ""),
    }
    for filename, content in files_to_write.items():
        try:
            (variation_dir / filename).write_text(content, encoding="utf-8")
            write_log(f"[agentic] {variation_dir.name}: Written {filename}")
        except Exception as e:
            write_log(f"[agentic] {variation_dir.name}: Gagal tulis {filename}: {e}", level="error")
            return False
    return True


def generate_variation_configs_for_scene(
    scene_dir: Path,
    project_name: str,
    all_scenes_meta: list[dict],
) -> bool:
    scene_dir = Path(scene_dir)
    agentic_config = load_agentic_config(scene_dir)
    number_of_variations = int(agentic_config.get("number_of_variations", 0))
    if number_of_variations <= 0:
        write_log(f"[agentic] {scene_dir.name}: number_of_variations=0, skip generate")
        return True

    scene_meta = _load_scene_meta(scene_dir)
    if scene_meta is None:
        return False
    scene_type = str(scene_meta.get("scene_type", "wan22_i2v")).strip()

    try:
        project_settings = load_project_settings(scene_dir.parent)
    except Exception as e:
        write_log(f"[agentic] {project_name}: Gagal baca project_settings.json: {e}", level="error")
        return False

    project_prompt_config = project_settings.get("prompt_generation", {})
    project_provider = str(project_prompt_config.get("provider", "gemini")).strip().lower() if isinstance(project_prompt_config, dict) else "gemini"
    server_config = load_server_config()
    if project_provider == "llama.cpp":
        model_name = str(server_config.get("prompt_generation", {}).get("model", "")).strip()
    else:
        model_name = str(server_config.get("translate", {}).get("model", "")).strip()
    allowed_output_files = set(expected_output_files(scene_type, agentic_config))
    start_variation_index = _next_variation_index(scene_dir)

    write_log(
        f"[agentic] {scene_dir.name}: Generate {number_of_variations} konfigurasi variasi "
        f"(type={scene_type}, start=variasi{start_variation_index})"
    )

    generated_count = 0
    skipped_count = 0
    for offset in range(number_of_variations):
        # Reserve a diagnostic folder before the LLM call so the exact input
        # prompt remains inspectable even when generation fails. A failed
        # folder is marked with status.failed and is ignored by execution.
        variation_index = start_variation_index + generated_count
        variation_dir = scene_dir / _variation_dir_name(variation_index)
        variation_dir.mkdir(parents=True, exist_ok=True)
        (variation_dir / STATUS_FAILED_FILENAME).unlink(missing_ok=True)
        write_log(f"[agentic] {scene_dir.name}/{variation_dir.name}: Generate JSON variasi")
        variations, input_prompt_text, output_prompt_text = generate_variations(
            scene_dir=scene_dir,
            scene_type=scene_type,
            agentic_config=agentic_config,
            project_settings=project_settings,
            all_scenes_meta=all_scenes_meta,
            model_name=model_name,
            current_variation_index=variation_index,
        )
        if not _write_variation_prompt_logs(variation_dir, input_prompt_text, output_prompt_text):
            _write_variation_failure_marker(variation_dir, "Gagal menyimpan log prompt Agentic.")
            return False
        if not variations:
            skipped_count += 1
            write_log(f"[agentic] {scene_dir.name}/{variation_dir.name}: Gagal generate, skip", level="warning")
            _write_variation_failure_marker(
                variation_dir,
                "LLM gagal membuat variasi prompt setelah 3 percobaan.",
            )
            _record_variation_failure(
                scene_dir.parent,
                scene_dir,
                variation_dir,
                "LLM gagal membuat variasi prompt setelah 3 percobaan.",
            )
            continue
        if not _copy_scene_baseline_files(scene_dir, variation_dir):
            _write_variation_failure_marker(variation_dir, "Gagal menyalin baseline scene ke folder variasi.")
            return False
        if not _write_variation_payloads(variation_dir, variations, allowed_output_files):
            _write_variation_failure_marker(variation_dir, "Gagal menyimpan payload JSON variasi.")
            return False
        generated_count += 1

    write_log(
        f"[agentic] {scene_dir.name}: Selesai generate konfigurasi "
        f"(berhasil={generated_count}, skip={skipped_count}, total={number_of_variations})"
    )
    if generated_count == 0:
        write_log(
            f"[agentic] {scene_dir.name}: Tidak ada konfigurasi variasi yang berhasil dibuat.",
            level="error",
        )
        return False
    return True


def execute_variations_for_scene(scene_dir: Path, project_name: str, server: str) -> bool:
    scene_dir = Path(scene_dir)
    agentic_config = load_agentic_config(scene_dir)
    scene_meta = _load_scene_meta(scene_dir)
    if scene_meta is None:
        return False

    scene_type = str(scene_meta.get("scene_type", "wan22_i2v")).strip()
    create_initial_image = bool(agentic_config.get("create_initial_image", True))
    image_extra_mode = str(agentic_config.get("image_extra_mode", "image_extra")).strip()
    if scene_type in {"wan22_t2v_i2v", "minimax-h3_t2v_i2v", "minimax-h3_r2v"}:
        create_initial_image = False

    pending_variations = _pending_variation_dirs(scene_dir)
    if not pending_variations:
        write_log(f"[agentic] {scene_dir.name}: Tidak ada variasi yang perlu dieksekusi")
        return True

    write_log(
        f"[agentic] {scene_dir.name}: Eksekusi {len(pending_variations)} variasi pending"
    )
    preserve_root_images = scene_type == "minimax-h3_i2v" and not create_initial_image
    preserve_root_reference_media = scene_type == "minimax-h3_r2v"
    r2v_reference_names: set[str] = set()
    if preserve_root_reference_media:
        try:
            r2v_prompt = json.loads((scene_dir / "minimax_h3_r2v_prompt.json").read_text(encoding="utf-8"))
            references = r2v_prompt.get("references", {}) if isinstance(r2v_prompt, dict) else {}
            r2v_reference_names.update(str(name).strip() for name in references.get("images", []) if str(name).strip())
            r2v_reference_names.update(str(name).strip() for name in references.get("audios", []) if str(name).strip())
            video_name = str(references.get("video", "") or "").strip()
            if video_name:
                r2v_reference_names.add(video_name)
        except Exception as e:
            write_log(f"[agentic] {scene_dir.name}: gagal membaca referensi R2V untuk cleanup: {e}", level="warning")

    for variation_dir in pending_variations:
        write_log(f"\n{'=' * 60}")
        write_log(f"[agentic] {scene_dir.name}: === eksekusi {variation_dir.name} ===")
        write_log(f"{'=' * 60}")

        deleted_before = _delete_media_files(
            scene_dir,
            preserve_images=preserve_root_images,
            preserve_names=r2v_reference_names if preserve_root_reference_media else None,
        )
        if deleted_before:
            write_log(f"[agentic] {scene_dir.name}/{variation_dir.name}: Cleanup awal root, hapus {deleted_before} media")

        # scene_meta.json di root adalah metadata authoritative setelah voice approval.
        # Variation lama dapat membawa salinan voice_text sebelum voice terakhir dipilih;
        # jangan biarkan salinan tersebut menimpa metadata root sebelum main.py berjalan.
        authoritative_scene_meta = _load_scene_meta(scene_dir)
        if authoritative_scene_meta is None:
            write_log(f"[agentic] {scene_dir.name}: scene_meta.json root tidak valid", level="error")
            return False

        if not _copy_dir_contents(variation_dir, scene_dir, exclude_status_done=True):
            write_log(f"[agentic] {scene_dir.name}/{variation_dir.name}: Gagal copy variasi ke root", level="error")
            return False
        if not _write_scene_meta(scene_dir, authoritative_scene_meta):
            return False

        if create_initial_image:
            if not _generate_initial_image(scene_dir, project_name, server):
                write_log(f"[agentic] {scene_dir.name}/{variation_dir.name}: Gagal generate initial image", level="error")
                return False

        if scene_type == "i2v":
            if image_extra_mode == "image_extra":
                if not _generate_extra_images(scene_dir, project_name, server):
                    write_log(f"[agentic] {scene_dir.name}/{variation_dir.name}: Gagal generate extra images", level="error")
                    return False
            elif image_extra_mode == "image_edit":
                if not _generate_image_edits(scene_dir, project_name, server):
                    write_log(f"[agentic] {scene_dir.name}/{variation_dir.name}: Gagal generate image edits", level="error")
                    return False

        if not _process_scene_with_main(scene_dir, project_name, server):
            write_log(f"[agentic] {scene_dir.name}/{variation_dir.name}: Gagal proses scene (main.py)", level="error")
            return False

        if not _copy_dir_contents(scene_dir, variation_dir):
            write_log(f"[agentic] {scene_dir.name}/{variation_dir.name}: Gagal copy hasil root ke variasi", level="error")
            return False

        try:
            (variation_dir / STATUS_DONE_FILENAME).write_text("done\n", encoding="utf-8")
        except Exception as e:
            write_log(f"[agentic] {scene_dir.name}/{variation_dir.name}: Gagal tulis status.done: {e}", level="error")
            return False

        deleted_after = _delete_media_files(
            scene_dir,
            preserve_images=preserve_root_images,
            preserve_names=r2v_reference_names if preserve_root_reference_media else None,
        )
        write_log(f"[agentic] {scene_dir.name}/{variation_dir.name}: Selesai, hapus {deleted_after} media dari root")

    write_log(f"[agentic] {scene_dir.name}: Selesai eksekusi semua variasi pending")
    return True


def _collect_scene_dirs(project_dir: Path, target_scenes: list[str] | None = None) -> list[Path]:
    raw_scene_dirs = sorted(
        [d for d in project_dir.iterdir() if d.is_dir() and d.name.startswith("scene_")],
        key=lambda d: int(d.name.split("_", 1)[1]) if d.name[6:].isdigit() else 999999,
    )
    if target_scenes:
        return [d for d in raw_scene_dirs if d.name in target_scenes]
    return raw_scene_dirs


def _collect_all_scenes_meta(scene_dirs: list[Path]) -> list[dict]:
    metas = []
    for scene_dir in scene_dirs:
        meta_path = scene_dir / "scene_meta.json"
        if meta_path.exists():
            try:
                with meta_path.open("r", encoding="utf-8") as f:
                    metas.append(json.load(f))
                continue
            except Exception:
                pass
        metas.append({"scene_title": scene_dir.name})
    return metas


def run_agentic_generate_for_project(project_dir: Path, target_scenes: list[str] | None = None) -> bool:
    if project_uses_llama(project_dir):
        RuntimeServiceController.from_config().ensure_llama(reason="agentic generate konfigurasi")
    project_dir = Path(project_dir)
    scene_dirs = _collect_scene_dirs(project_dir, target_scenes=target_scenes)
    all_scenes_meta = _collect_all_scenes_meta(scene_dirs)
    project_name = project_dir.name

    write_log(f"\n{'=' * 60}")
    write_log(f"[agentic] Project: {project_name}")
    write_log(f"[agentic] Mode: generate-config")
    write_log(f"[agentic] Scenes: {len(scene_dirs)}")
    write_log(f"{'=' * 60}\n")

    for scene_dir in scene_dirs:
        if load_agentic_config(scene_dir).get("number_of_variations", 0) <= 0:
            write_log(f"[agentic] {scene_dir.name}: number_of_variations=0, skip generate")
            continue
        if not generate_variation_configs_for_scene(scene_dir, project_name, all_scenes_meta):
            write_log(f"[agentic] Project {project_name}: Gagal generate di {scene_dir.name}", level="error")
            return False

    write_log(f"\n[agentic] Project {project_name}: Selesai generate konfigurasi variasi")
    return True


def run_agentic_execute_for_project(project_dir: Path, server: str, target_scenes: list[str] | None = None) -> bool:
    project_dir = Path(project_dir)
    scene_dirs = _collect_scene_dirs(project_dir, target_scenes=target_scenes)
    manage_runtime = project_uses_llama(project_dir)
    controller = RuntimeServiceController.from_config() if manage_runtime else None
    if controller is not None:
        write_log(f"[runtime] Pra-lokalisasi prompt Agentic sebelum switch ComfyUI: {project_dir}")
        prepare_project_prompts_for_runtime(project_dir, scene_dirs=scene_dirs, log_fn=write_log)
        controller.ensure_comfyui(reason="agentic execute variasi")
    previous_keep_comfyui = os.environ.get("VIDEO_AI_KEEP_COMFYUI")
    os.environ["VIDEO_AI_KEEP_COMFYUI"] = "1"
    project_name = project_dir.name

    write_log(f"\n{'=' * 60}")
    write_log(f"[agentic] Project: {project_name}")
    write_log(f"[agentic] Mode: execute")
    write_log(f"[agentic] Scenes: {len(scene_dirs)}")
    write_log(f"[agentic] Server: {server}")
    write_log(f"{'=' * 60}\n")

    try:
        for scene_dir in scene_dirs:
            if not execute_variations_for_scene(scene_dir, project_name, server):
                write_log(f"[agentic] Project {project_name}: Gagal execute di {scene_dir.name}", level="error")
                return False
        write_log(f"\n[agentic] Project {project_name}: Selesai execute variasi")
        return True
    finally:
        if previous_keep_comfyui is None:
            os.environ.pop("VIDEO_AI_KEEP_COMFYUI", None)
        else:
            os.environ["VIDEO_AI_KEEP_COMFYUI"] = previous_keep_comfyui
        # Jangan switch balik ke Llama setelah execute variasi selesai.
        # ComfyUI masih menjadi service yang dibutuhkan untuk workflow/output
        # berikutnya; switch ke Llama hanya dilakukan oleh operasi LLM yang
        # memerlukannya.


def run_agentic_for_project(project_dir: Path, server: str, target_scenes: list[str] | None = None) -> bool:
    """Backward-compatible full run: generate config first, then execute."""
    if not run_agentic_generate_for_project(project_dir, target_scenes=target_scenes):
        return False
    return run_agentic_execute_for_project(project_dir, server, target_scenes=target_scenes)
