import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from logging_config import setup_logging, get_logger, write_log
from scripts.project_settings import load_project_settings

setup_logging()
logger = get_logger(__name__)

API_PRODUCTION = Path(ROOT) / "api_production"
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
DEFAULT_MODEL_SIZE = "base"
TAG_PATTERN = re.compile(r"\[[^\]]+\]")
ARABIC_UNICODE_NAME = "ARABIC"
CAPTION_BASE_HEIGHT = 640
CAPTION_BASE_FONT_SIZE = 12
CAPTION_FONT_NAME = "Arial"


def list_scene_dirs():
    if not API_PRODUCTION.exists():
        return []
    scenes = []
    for child in API_PRODUCTION.iterdir():
        if child.is_dir() and child.name.startswith("scene_"):
            try:
                scenes.append((int(child.name.split("_", 1)[1]), child))
            except ValueError:
                continue
    scenes.sort(key=lambda item: item[0])
    return [path for _, path in scenes]


def find_latest_file(scene_dir: Path, exts: set[str], prefix: str | None = None):
    items = []
    for child in scene_dir.iterdir():
        if not child.is_file():
            continue
        if child.suffix.lower() not in exts:
            continue
        if prefix and not child.name.startswith(prefix):
            continue
        items.append(child)
    if not items:
        return None
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return items[0]


def find_latest_caption_source_video(scene_dir: Path):
    items = []
    for child in scene_dir.iterdir():
        if not child.is_file():
            continue
        if child.suffix.lower() not in VIDEO_EXTS:
            continue
        if "_captioned" in child.stem.lower():
            continue
        items.append(child)
    if not items:
        return find_latest_file(scene_dir, VIDEO_EXTS)
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return items[0]


def load_scene_meta(scene_dir: Path) -> dict:
    meta_path = scene_dir / "scene_meta.json"
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def load_voice_selection(scene_dir: Path) -> dict:
    selection_path = scene_dir / "voice_selection.json"
    if not selection_path.exists():
        return {}
    try:
        return json.loads(selection_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")
    return float(result.stdout.strip())


def ffprobe_size(path: Path) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe video dimensions failed")
    try:
        width, height = [int(value) for value in result.stdout.strip().split("x", 1)]
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Dimensi video tidak valid: {result.stdout.strip()}") from exc
    return width, height


def caption_font_size(height: int | float) -> int:
    """Scale the caption from 12 px at a 640 px video height."""
    try:
        numeric_height = float(height)
    except (TypeError, ValueError):
        numeric_height = CAPTION_BASE_HEIGHT
    return max(1, math.ceil(numeric_height / CAPTION_BASE_HEIGHT * CAPTION_BASE_FONT_SIZE))


def extract_audio_from_video(video_path: Path, output_path: Path):
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg audio extract failed")


def format_srt_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3600000)
    minutes, rem = divmod(rem, 60000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def normalize_caption_text(text: str) -> str:
    text = " ".join(str(text).replace("\n", " ").split())
    return text.strip()


def subtitle_text_direction(text: str) -> str:
    """Wrap Arabic/Hebrew subtitle text in an explicit RTL embedding.

    SRT stores Unicode text in logical order, but subtitle renderers can make
    different decisions when a line contains Arabic, diacritics, punctuation,
    or numbers. The embedding is invisible and keeps the stored text intact
    while forcing the renderer to lay out the line as RTL.
    """
    normalized = normalize_caption_text(text)
    if not normalized:
        return normalized
    if any(ARABIC_UNICODE_NAME in unicodedata.name(char, "") for char in normalized):
        # RLM anchors the line when punctuation/numbers or a neutral glyph
        # appears at either edge; RLE/PDF keeps the whole caption in one RTL
        # embedding without changing the logical Arabic text.
        return f"\u200f\u202b{normalized}\u202c\u200f"
    return normalized


def contains_arabic_text(text: str) -> bool:
    return any(ARABIC_UNICODE_NAME in unicodedata.name(char, "") for char in str(text or ""))


def strip_audio_tags(text: str) -> str:
    return normalize_caption_text(TAG_PATTERN.sub("", text))


def split_caption_text(text: str, max_chars: int = 42, max_words: int = 8):
    text = strip_audio_tags(text)
    if not text:
        return []

    chunks = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        words = sentence.split()
        current = []
        for word in words:
            candidate = " ".join([*current, word]).strip()
            if current and (len(candidate) > max_chars or len(current) >= max_words):
                chunks.append(" ".join(current).strip())
                current = [word]
            else:
                current.append(word)
        if current:
            chunks.append(" ".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def build_caption_entries(transcript_segments, voice_text: str, total_duration: float):
    chunks = split_caption_text(voice_text)
    if not chunks:
        raise RuntimeError("voice_text kosong setelah dibersihkan.")

    speech_start = 0.0
    speech_end = total_duration
    if transcript_segments:
        starts = [float(seg.start) for seg in transcript_segments]
        ends = [float(seg.end) for seg in transcript_segments]
        if starts and ends:
            speech_start = max(0.0, min(starts))
            speech_end = max(speech_start + 0.1, max(ends))

    window = max(0.3, speech_end - speech_start)
    total_chars = sum(max(1, len(chunk)) for chunk in chunks)
    entries = []
    cursor = speech_start
    for index, chunk in enumerate(chunks, start=1):
        weight = max(1, len(chunk)) / total_chars
        duration = window * weight
        start = cursor
        if index == len(chunks):
            end = speech_end
        else:
            end = min(speech_end, start + max(0.7, duration))
        if end <= start:
            end = start + 0.7
        entries.append((index, start, end, chunk))
        cursor = end
    # smooth overlaps/gaps
    normalized_entries = []
    for index, start, end, text in entries:
        start = max(speech_start, start)
        end = max(start + 0.5, end)
        normalized_entries.append((index, start, min(end, speech_end if index == len(entries) else end), text))
    return normalized_entries


def write_srt(entries, output_path: Path):
    lines = []
    for idx, start_seconds, end_seconds, raw_text in entries:
        text = normalize_caption_text(raw_text)
        if not text:
            continue
        text = subtitle_text_direction(text)
        start = max(0.0, float(start_seconds))
        end = max(start + 0.05, float(end_seconds))
        lines.append(
            f"{idx}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}\n"
        )
    if not lines:
        raise RuntimeError("Transkripsi tidak menghasilkan caption yang dapat ditulis.")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def subtitle_filter_path(path: Path) -> str:
    # ffmpeg subtitles filter on Windows needs escaped drive colon and forward slashes.
    value = str(path.resolve()).replace("\\", "/")
    value = value.replace(":", "\\:")
    value = value.replace("'", "\\'")
    return value


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path):
    _, height = ffprobe_size(video_path)
    font_size = caption_font_size(height)
    outline_size = max(1, math.ceil(font_size * 0.12))
    margin_v = max(1, math.ceil(height / CAPTION_BASE_HEIGHT * 20))
    force_style = (
        f"FontName={CAPTION_FONT_NAME},FontSize={font_size},PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,BorderStyle=1,Outline={outline_size},Shadow=0,"
        f"MarginV={margin_v},Alignment=2,Spacing=-0.5"
    )
    vf = f"subtitles='{subtitle_filter_path(srt_path)}':force_style='{force_style}'"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-c:a",
        "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg burn subtitles failed")


def _caption_font(size: int):
    for font_path in (
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\tahoma.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
    ):
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size)
    return ImageFont.load_default()


def _text_measure_kwargs(direction: str | None = None, language: str | None = None):
    kwargs = {}
    if direction:
        kwargs["direction"] = direction
    if language:
        kwargs["language"] = language
    return kwargs


def _wrap_caption_text(
    draw,
    text: str,
    font,
    max_width: int,
    direction: str | None = None,
    language: str | None = None,
) -> str:
    words = normalize_caption_text(text).split()
    if not words:
        return ""
    lines = []
    current = ""
    measure_kwargs = _text_measure_kwargs(direction, language)
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=font,
            **measure_kwargs,
        )
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def _caption_overlay(text: str, width: int, height: int, output_path: Path):
    """Render one caption with Pillow so Arabic and non-Arabic use identical pixels."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    wrapped_text, draw_kwargs, font, stroke_width, spacing, bottom_margin = _caption_draw_spec(
        draw, text, width, height
    )
    draw.multiline_text(
        (width // 2, height - bottom_margin),
        wrapped_text,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0, 255),
        anchor="mm",
        align="center",
        spacing=spacing,
        **draw_kwargs,
    )
    image.save(output_path, format="PNG")


def _caption_draw_spec(draw, text: str, width: int, height: int):
    """Return the exact Pillow layout parameters used by full and cropped overlays."""
    text = normalize_caption_text(text)
    is_arabic = contains_arabic_text(text)
    direction = "rtl" if is_arabic else None
    language = "ar" if is_arabic else None
    font_size = caption_font_size(height)
    margin = max(1, math.ceil(width / CAPTION_BASE_HEIGHT * 20))
    font = _caption_font(font_size)
    stroke_width = max(1, math.ceil(font_size * 0.12))
    wrapped_text = _wrap_caption_text(
        draw,
        text,
        font,
        max(1, width - (margin * 2)),
        direction=direction,
        language=language,
    )
    draw_kwargs = _text_measure_kwargs(direction, language)
    spacing = max(1, math.ceil(font_size * 0.15))
    bottom_margin = max(1, math.ceil(height / CAPTION_BASE_HEIGHT * 20))
    return wrapped_text, draw_kwargs, font, stroke_width, spacing, bottom_margin


def _caption_band_height(entries, width: int, height: int) -> int:
    """Find the smallest transparent band that can contain all caption text."""
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    required_height = 1
    for _, _, _, raw_text in entries:
        text = normalize_caption_text(raw_text)
        if not text:
            continue
        wrapped_text, draw_kwargs, font, stroke_width, spacing, bottom_margin = _caption_draw_spec(
            draw, text, width, height
        )
        bbox = draw.multiline_textbbox(
            (width // 2, 0),
            wrapped_text,
            font=font,
            stroke_width=stroke_width,
            anchor="mm",
            align="center",
            spacing=spacing,
            **draw_kwargs,
        )
        # The cropped band is positioned at y=video_height-band_height.  Using
        # the same anchor and bottom margin keeps the text at the same absolute
        # coordinates as the previous full-frame Pillow overlay.
        required_height = max(required_height, math.ceil(bottom_margin - bbox[1] + 2))
    return min(height, max(required_height, 4))


def _caption_band_overlay(
    text: str,
    width: int,
    video_height: int,
    band_height: int,
    output_path: Path,
):
    """Render one caption into a narrow transparent band instead of Full HD."""
    image = Image.new("RGBA", (width, band_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    wrapped_text, draw_kwargs, font, stroke_width, spacing, bottom_margin = _caption_draw_spec(
        draw, text, width, video_height
    )
    draw.multiline_text(
        (width // 2, band_height - bottom_margin),
        wrapped_text,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0, 255),
        anchor="mm",
        align="center",
        spacing=spacing,
        **draw_kwargs,
    )
    image.save(output_path, format="PNG")


def _concat_file_path(path: Path) -> str:
    """Escape one Windows path for an FFmpeg concat demuxer list."""
    return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")


def _overlay_caption_entries(video_path: Path, entries, output_path: Path):
    """Overlay all captions through one narrow Pillow subtitle layer.

    Each caption is rendered at the same pixel size as before, but only the
    bottom caption band is stored.  FFmpeg then receives one alpha video input
    and performs one overlay instead of one Full HD looped input per caption.
    """
    width, height = ffprobe_size(video_path)
    duration = ffprobe_duration(video_path)
    if duration <= 0:
        raise RuntimeError("Durasi video caption tidak valid.")
    normalized_entries = []
    for index, start, end, raw_text in entries:
        text = normalize_caption_text(raw_text)
        start = max(0.0, min(float(start), duration))
        end = max(start, min(float(end), duration))
        if text and end > start:
            normalized_entries.append((int(index), start, end, text))
    if not normalized_entries:
        raise RuntimeError("Caption tidak menghasilkan overlay.")
    normalized_entries.sort(key=lambda item: (item[1], item[2], item[0]))

    temp_dir = Path(tempfile.mkdtemp(prefix="caption_overlay_", dir=str(output_path.parent)))
    try:
        band_height = _caption_band_height(normalized_entries, width, height)
        blank_path = temp_dir / "blank.png"
        Image.new("RGBA", (width, band_height), (0, 0, 0, 0)).save(blank_path, format="PNG")

        caption_files = []
        for file_index, (_, _, _, text) in enumerate(normalized_entries):
            caption_path = temp_dir / f"caption_{file_index:04d}.png"
            _caption_band_overlay(text, width, height, band_height, caption_path)
            caption_files.append(caption_path)

        # Build one timed RGBA stream.  The list contains only a blank band or
        # one caption band at any point in time, so the final filter graph has a
        # single overlay input regardless of the number of captions.
        segments = []
        cursor = 0.0
        for caption_item, caption_path in zip(normalized_entries, caption_files):
            _, start, end, _ = caption_item
            if start > cursor:
                segments.append((blank_path, start - cursor))
            visible_start = max(start, cursor)
            if end > visible_start:
                segments.append((caption_path, end - visible_start))
            cursor = max(cursor, end)
        if cursor < duration:
            segments.append((blank_path, duration - cursor))
        if not segments:
            raise RuntimeError("Caption tidak menghasilkan layer bertiming.")

        concat_list = temp_dir / "caption_layer.txt"
        concat_lines = []
        for image_path, segment_duration in segments:
            concat_lines.append(f"file '{_concat_file_path(image_path)}'")
            concat_lines.append(f"duration {segment_duration:.6f}")
        # concat demuxer applies the last duration only when the last file is
        # repeated, otherwise its duration is guessed as one frame.
        concat_lines.append(f"file '{_concat_file_path(segments[-1][0])}'")
        concat_list.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

        layer_path = temp_dir / "caption_layer.mov"
        layer_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-an", "-fps_mode", "vfr", "-c:v", "qtrle", "-pix_fmt", "argb",
            "-t", f"{duration:.6f}", str(layer_path),
        ]
        layer_result = subprocess.run(layer_cmd, capture_output=True, text=True, check=False)
        if layer_result.returncode != 0:
            raise RuntimeError(layer_result.stderr.strip() or "ffmpeg caption layer failed")

        filter_complex = "[0:v][1:v]overlay=0:H-h:format=auto:eof_action=repeat[v]"
        cmd = ["ffmpeg", "-y", "-i", str(video_path), "-i", str(layer_path)]
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", "-t", f"{duration:.6f}", str(output_path),
        ])
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "ffmpeg caption overlay failed")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _arabic_caption_overlay(text: str, width: int, height: int, output_path: Path):
    """Compatibility wrapper for callers that still use the old Arabic helper."""
    _caption_overlay(text, width, height, output_path)


def _overlay_arabic_caption_entries(video_path: Path, entries, output_path: Path):
    """Compatibility wrapper; the unified renderer also shapes Arabic with Pillow."""
    _overlay_caption_entries(video_path, entries, output_path)


def burn_arabic_subtitles(video_path: Path, entries, output_path: Path):
    """Burn a batch containing only Arabic captions."""
    _overlay_caption_entries(video_path, entries, output_path)


def burn_mixed_subtitles(video_path: Path, entries, output_path: Path):
    """Burn mixed Arabic/non-Arabic captions with the same Pillow renderer."""
    _overlay_caption_entries(video_path, entries, output_path)


def transcribe_audio(audio_path: Path, model_size: str):
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        raise RuntimeError("faster-whisper belum terpasang; install dulu dari requirements.txt") from e

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        str(audio_path),
        language="id",
        vad_filter=True,
        beam_size=5,
    )
    return list(segments)

def is_caption_enabled(scene_dir: Path, scene_meta: dict) -> bool:
    project_dir = Path(scene_dir).parent
    project_settings = load_project_settings(project_dir)
    return bool(project_settings.get("caption", {}).get("generate_caption", True))


def _caption_voice_text(scene_dir: Path, scene_meta: dict) -> str:
    voice_selection = load_voice_selection(scene_dir)
    return str(
        voice_selection.get("selected_voice_text")
        or scene_meta.get("voice_text", "")
    ).strip()


def build_caption_entries_for_scene(
    scene_dir: Path,
    video_path: Path,
    model_size: str = DEFAULT_MODEL_SIZE,
    audio_path: Path | None = None,
):
    """Build timed entries without burning them into the video.

    The caller can later offset/retime these entries and burn them once onto
    the final composed video.  ``audio_path`` is used by compose-song so the
    timing follows the exact audio chunk placed on the final timeline.
    """
    scene_dir = Path(scene_dir)
    video_path = Path(video_path)
    scene_meta = load_scene_meta(scene_dir)
    if not video_path.exists():
        raise RuntimeError(f"Video untuk caption tidak ditemukan: {video_path}")

    voice_text = _caption_voice_text(scene_dir, scene_meta)
    if not strip_audio_tags(voice_text):
        return []

    selected_audio = Path(audio_path) if audio_path else None
    if selected_audio is None or not selected_audio.exists():
        voice_selection = load_voice_selection(scene_dir)
        selected_filename = str(voice_selection.get("selected_filename", "")).strip()
        selected_audio = scene_dir / selected_filename if selected_filename else None
        selected_audio = selected_audio if selected_audio and selected_audio.exists() else None
    speech_audio = selected_audio or find_latest_file(scene_dir, AUDIO_EXTS, prefix="speech_")
    temp_audio = None
    try:
        audio_source = speech_audio
        if audio_source is None:
            temp_audio = scene_dir / "_caption_temp_audio.wav"
            extract_audio_from_video(video_path, temp_audio)
            audio_source = temp_audio
        duration = ffprobe_duration(audio_source)
        if duration <= 0:
            raise RuntimeError(f"Durasi audio untuk caption tidak valid di {scene_dir}.")
        transcript_segments = transcribe_audio(audio_source, model_size=model_size)
        return build_caption_entries(transcript_segments, voice_text, duration)
    finally:
        if temp_audio and temp_audio.exists():
            try:
                temp_audio.unlink()
            except OSError:
                pass


def burn_caption_entries(video_path: Path, entries, output_path: Path):
    """Burn already-timed entries using the final video's dimensions."""
    video_path = Path(video_path)
    output_path = Path(output_path)
    if not entries:
        raise RuntimeError("Tidak ada entry caption untuk dibakar.")
    _overlay_caption_entries(video_path, entries, output_path)
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"Video caption hasil burn kosong atau gagal dibuat: {output_path}")


def apply_caption_to_video(scene_dir: Path, video_path: Path, model_size: str = DEFAULT_MODEL_SIZE, overwrite: bool = True):
    scene_meta = load_scene_meta(scene_dir)
    if not is_caption_enabled(scene_dir, scene_meta):
        write_log(f"Caption dinonaktifkan untuk {scene_dir}, melewati proses caption.", level="info")
        return True

    video_path = Path(video_path)
    if not video_path.exists():
        write_log(f"Video untuk caption tidak ditemukan: {video_path}", level="error")
        return False

    try:
        caption_entries = build_caption_entries_for_scene(scene_dir, video_path, model_size=model_size)
        if not caption_entries:
            write_log(f"Tidak ada voice_text yang valid untuk caption di {scene_dir}.", level="error")
            return False

        if overwrite:
            output_path = video_path.with_name(f"{video_path.stem}.__caption_tmp__.mp4")
        else:
            output_path = video_path.with_name(f"{video_path.stem}_captioned.mp4")
        burn_caption_entries(video_path, caption_entries, output_path)
        if not output_path.exists() or output_path.stat().st_size <= 0:
            write_log(f"Video caption hasil burn kosong atau gagal dibuat: {output_path}", level="error")
            return False
        if overwrite:
            original_path = video_path
            backup_path = video_path.with_name(f"{video_path.stem}.__pre_caption__.bak{video_path.suffix}")
            try:
                if backup_path.exists():
                    backup_path.unlink()
                original_path.replace(backup_path)
                output_path.replace(original_path)
                if backup_path.exists():
                    backup_path.unlink()
                final_path = original_path
            except Exception as e:
                write_log(f"Gagal menimpa video asli dengan caption untuk {scene_dir}: {e}", level="error")
                return False
        else:
            final_path = output_path
        write_log(f"Berhasil membuat video caption untuk {scene_dir}: {final_path}")
        return True
    except Exception as e:
        write_log(f"Gagal membuat caption untuk {scene_dir}: {e}", level="error")
        return False
def process_scene(scene_dir: Path, model_size: str = DEFAULT_MODEL_SIZE):
    latest_video = find_latest_caption_source_video(scene_dir)
    if not latest_video:
        write_log(f"Tidak ada video di {scene_dir}.", level="error")
        return False
    return apply_caption_to_video(scene_dir, latest_video, model_size=model_size, overwrite=False)


def main(specific_scenes=None, model_size: str = DEFAULT_MODEL_SIZE):
    if not API_PRODUCTION.exists():
        print("api_production folder not found:", API_PRODUCTION)
        return 1

    scenes = list_scene_dirs()
    if specific_scenes:
        requested = set(specific_scenes)
        scenes = [scene for scene in scenes if scene.name in requested]
    if not scenes:
        write_log("Tidak ada scene yang cocok untuk generate caption.", level="error")
        return 1

    had_error = False
    for scene_dir in scenes:
        print("Processing", scene_dir)
        if not process_scene(scene_dir, model_size=model_size):
            had_error = True
    return 1 if had_error else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate caption ke video terbaru per scene dengan faster-whisper")
    parser.add_argument("--scene", "-s", action="append", help="Scene yang diproses (repeatable)")
    parser.add_argument("--model", default=DEFAULT_MODEL_SIZE, help="Model faster-whisper untuk CPU, misalnya base atau small")
    args = parser.parse_args()
    sys.exit(main(specific_scenes=args.scene, model_size=args.model))
