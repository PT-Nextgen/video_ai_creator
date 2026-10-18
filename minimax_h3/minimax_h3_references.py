"""Reference-image resolution shared by MiniMax runtime and prompt generation.

The UI must describe to the LLM the same files that the ComfyUI workflow will
receive.  Keeping the small amount of path/frame resolution logic here avoids
the UI inventing a different "latest" or stage-frame rule.
"""

from __future__ import annotations

import os
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def find_latest_root_image(scene_dir: str | os.PathLike) -> str | None:
    """Return the newest direct image in a scene directory, by mtime."""
    root = Path(scene_dir).resolve()
    if not root.is_dir():
        return None
    images = [
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    if not images:
        return None
    images.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return str(images[0].resolve())


def extract_last_frame_image(video_path: str | os.PathLike, output_path: str | os.PathLike) -> str:
    """Extract and persist the last video frame using the runtime's method."""
    import imageio
    from PIL import Image

    reader = imageio.get_reader(str(video_path))
    last_frame = None
    try:
        for frame in reader:
            last_frame = frame
    finally:
        try:
            reader.close()
        except Exception:
            pass
    if last_frame is None:
        raise RuntimeError(f"Tidak ada frame yang bisa diekstrak dari video: {video_path}")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(last_frame).convert("RGB").save(destination)
    return str(destination.resolve())


def extract_first_frame_image(video_path: str | os.PathLike, output_path: str | os.PathLike) -> str:
    """Extract and persist the first video frame using the runtime's method."""
    import imageio
    from PIL import Image

    reader = imageio.get_reader(str(video_path))
    try:
        first_frame = reader.get_data(0)
    except Exception as exc:
        raise RuntimeError(f"Tidak ada frame pertama yang bisa diekstrak dari video: {video_path}") from exc
    finally:
        try:
            reader.close()
        except Exception:
            pass
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(first_frame).convert("RGB").save(destination)
    return str(destination.resolve())


def ensure_stage_last_frame(scene_dir: str | os.PathLike, stage_number: int) -> str | None:
    """Return a persisted last frame for an earlier long-I2V stage.

    A frame saved by the runtime is preferred.  If only the segment exists,
    create the same frame filename from that segment before returning it.
    """
    root = Path(scene_dir).resolve()
    try:
        stage = int(stage_number)
    except (TypeError, ValueError):
        return None
    if stage <= 0:
        return None
    frame_path = root / f"minimax_h3_i2v_panjang_frame_{stage}.png"
    if frame_path.is_file() and frame_path.stat().st_size > 0:
        return str(frame_path)
    segment_path = root / f"minimax_h3_i2v_panjang_segment_{stage}.mp4"
    if not segment_path.is_file() or segment_path.stat().st_size <= 0:
        return None
    try:
        return extract_last_frame_image(segment_path, frame_path)
    except Exception:
        return None


def _safe_scene_path(scene_dir: Path, name: str) -> Path | None:
    candidate = (scene_dir / str(name or "").strip()).resolve()
    try:
        candidate.relative_to(scene_dir)
    except ValueError:
        return None
    return candidate


def resolve_stage_reference_path(
    scene_dir: str | os.PathLike,
    reference: dict | None,
    stage_number: int,
) -> str | None:
    """Resolve one configured long-I2V reference exactly as the runtime does."""
    root = Path(scene_dir).resolve()
    value = reference if isinstance(reference, dict) else {}
    source = str(value.get("source", "none") or "none").strip().lower()
    if source in {"", "none"}:
        return None
    if source == "scene":
        path = _safe_scene_path(root, value.get("name", ""))
        return str(path) if path and path.is_file() else None
    if source == "stage_last":
        try:
            source_stage = int(value.get("stage", 0))
        except (TypeError, ValueError):
            return None
        if not 1 <= source_stage < int(stage_number):
            return None
        return ensure_stage_last_frame(root, source_stage)
    return None


def resolve_long_i2v_prompt_images(
    scene_dir: str | os.PathLike,
    stage_references: list[dict] | None,
    stage_number: int,
) -> list[str]:
    """Return first-frame then optional last-frame paths in ComfyUI order."""
    stage = int(stage_number)
    configured = stage_references if isinstance(stage_references, list) else []
    if not configured:
        first = (
            find_latest_root_image(scene_dir)
            if stage == 1
            else ensure_stage_last_frame(scene_dir, stage - 1)
        )
        return [first] if first else []
    entry = configured[stage - 1] if 0 < stage <= len(configured) else {}
    entry = entry if isinstance(entry, dict) else {}
    first = resolve_stage_reference_path(scene_dir, entry.get("first"), stage)
    if not first:
        return []
    paths = [first]
    last_reference = entry.get("last") if isinstance(entry.get("last"), dict) else {}
    last_source = str(last_reference.get("source", "none") or "none").strip().lower()
    if last_source not in {"", "none"}:
        last = resolve_stage_reference_path(scene_dir, last_reference, stage)
        if not last:
            return []
        paths.append(last)
    return paths
