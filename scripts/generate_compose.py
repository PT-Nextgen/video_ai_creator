import os
import sys
import json
import subprocess
import shlex
import tempfile
import argparse
import random
import shutil
from pathlib import Path
import math

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency
    Image = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from logging_config import setup_logging, get_logger
from prompt_localization import read_json_for_runtime, resolve_prompt_payload_for_runtime
from scripts.project_settings import load_project_settings

setup_logging()
logger = get_logger(__name__)

PARENT = os.path.dirname(ROOT)
API_PRODUCTION = None

VIDEO_EXTS = ('.mp4', '.mov', '.webm', '.mkv')
AUDIO_EXTS = ('.m4a', '.wav', '.mp3')
IMAGE_EXTS = ('.jpg', '.jpeg', '.png')
COMFY_AUDIO_SOURCE_DIRNAME = '.comfy_audio_source'
COMFY_AUDIO_SOURCE_FILENAME = 'audio.wav'

# Background music volume for final merged video (0.0 to 1.0)
BACKGROUND_MUSIC_VOLUME = 0.3
UPSCALE_FACTORS = {
    "none": 1.0,
    "1.5x": 1.5,
    "2x": 2.0,
}


def _load_scene_meta_runtime(scene_dir: str) -> dict:
    meta_path = os.path.join(scene_dir, "scene_meta.json")
    if not os.path.exists(meta_path):
        return {}
    try:
        return read_json_for_runtime(meta_path, required=True, log_fn=lambda msg: logger.info(msg))
    except Exception as e:
        logger.warning("Prompt localization fallback for %s: %s", meta_path, e)
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                raw_meta = json.load(f)
            resolved_meta, _, _ = resolve_prompt_payload_for_runtime(
                "scene_meta.json",
                raw_meta,
                translate_fn=lambda text: text,
            )
            return resolved_meta
        except Exception:
            return {}


def _safe_filename_segment(text: str) -> str:
    text = str(text or "")
    # Replace Windows-forbidden filename chars and control chars.
    forbidden = '<>:"/\\|?*'
    cleaned = ''.join('_' if (ch in forbidden or ord(ch) < 32) else ch for ch in text)
    cleaned = '_'.join(cleaned.split())
    return cleaned.strip('._') or "untitled"


def _find_first_cover_image(cover_dir: str, temp_dir: str):
    if not os.path.isdir(cover_dir):
        return None
    files = sorted(
        [
            os.path.join(cover_dir, f)
            for f in os.listdir(cover_dir)
            if os.path.isfile(os.path.join(cover_dir, f))
        ]
    )
    if not files:
        return None
    # Accept "any" image-like file by validating with Pillow when available.
    if Image is not None:
        for fp in files:
            try:
                with Image.open(fp) as im:
                    out_path = os.path.join(temp_dir, "cover_input.png")
                    im.convert("RGB").save(out_path, format="PNG")
                    return out_path
            except Exception:
                continue
    # Fallback: use common image extensions directly.
    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
    for fp in files:
        if os.path.splitext(fp)[1].lower() in exts:
            return fp
    return None


def _create_cover_clip(cover_image_path, dst, fps, width, height):
    duration = max(1.0 / max(float(fps), 1.0), 2.0 / max(float(fps), 1.0))  # exactly 2 frames target
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}"
    )
    run(
        f'ffmpeg -y -loop 1 -i "{cover_image_path}" '
        f'-f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 '
        f'-t {duration:.6f} -vf "{vf}" '
        f'-c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 192k "{dst}"'
    )


def _build_looped_music_track(music_path, dst_wav_path, target_duration, volume):
    music_dur = ffprobe_duration(music_path)
    if music_dur <= 0:
        raise RuntimeError(f"Invalid music duration: {music_path}")
    reps = max(1, int(math.ceil(target_duration / music_dur)))

    with tempfile.TemporaryDirectory(prefix="musicseg_") as td:
        seg_paths = []
        remaining = float(target_duration)
        for i in range(reps):
            seg_len = min(music_dur, remaining)
            if seg_len <= 0.001:
                break
            fade_dur = min(0.5, max(0.0, seg_len))
            fade_start = max(0.0, seg_len - fade_dur)
            seg_path = os.path.join(td, f"seg_{i:03d}.wav")
            run(
                f'ffmpeg -y -i "{music_path}" -t {seg_len:.6f} '
                f'-af "volume={volume},afade=t=out:st={fade_start:.6f}:d={fade_dur:.6f}" '
                f'-ac 2 -ar 44100 -c:a pcm_s16le "{seg_path}"'
            )
            seg_paths.append(seg_path)
            remaining -= seg_len

        if not seg_paths:
            raise RuntimeError("No music segment generated")

        list_path = os.path.join(td, "segments.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for p in seg_paths:
                safe_p = p.replace("'", "'\\''")
                f.write(f"file '{safe_p}'\n")
        run(f'ffmpeg -y -f concat -safe 0 -i "{list_path}" -ac 2 -ar 44100 -c:a pcm_s16le "{dst_wav_path}"')


def _mix_background_music(final_video_path, music_path, music_volume):
    if not music_path or not os.path.isfile(music_path):
        return final_video_path

    try:
        volume = float(music_volume)
    except Exception:
        volume = BACKGROUND_MUSIC_VOLUME
    volume = max(0.0, min(2.0, volume))

    target_duration = ffprobe_duration(final_video_path)
    if target_duration <= 0:
        return final_video_path

    with tempfile.TemporaryDirectory(prefix="musicmix_") as td:
        looped_wav = os.path.join(td, "music_looped.wav")
        _build_looped_music_track(music_path, looped_wav, target_duration, volume)

        out_tmp = os.path.join(td, "final_with_music.mp4")
        if ffprobe_has_audio(final_video_path):
            # Keep original speech track as-is, only scale music by selected volume.
            run(
                f'ffmpeg -y -i "{final_video_path}" -i "{looped_wav}" '
                f'-filter_complex "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];'
                f'[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a1];'
                f'[a0][a1]amix=inputs=2:normalize=0:duration=first[aout]" '
                f'-map 0:v -map "[aout]" -c:v copy -c:a aac -b:a 192k '
                f'-ac 2 -ar 44100 '
                f'-movflags +faststart "{out_tmp}"'
            )
        else:
            run(
                f'ffmpeg -y -i "{final_video_path}" -i "{looped_wav}" '
                f'-filter_complex "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[aout]" '
                f'-map 0:v -map "[aout]" -c:v copy -c:a aac -b:a 192k -ac 2 -ar 44100 '
                f'-movflags +faststart "{out_tmp}"'
            )
        shutil.copyfile(out_tmp, final_video_path)

    return final_video_path


def _force_dual_mono_audio(final_video_path):
    # Intentionally no-op to preserve original speech loudness/channel balance.
    return final_video_path


def _scene_sort_key(name: str):
    if not str(name).startswith("scene_"):
        return (10**9, str(name))
    try:
        return (int(str(name).split("_", 1)[1]), str(name))
    except Exception:
        return (10**9, str(name))


def _safe_remove_file(path):
    try:
        os.remove(path)
        return True
    except PermissionError:
        logger.warning('File is locked, skip remove: %s', path)
        return False
    except FileNotFoundError:
        return True
    except Exception as e:
        logger.warning('Failed to remove file %s: %s', path, e)
        return False


def _safe_clean_combined_dir(combined_dir, delete_all=True, scene_nums=None):
    os.makedirs(combined_dir, exist_ok=True)
    for f in os.listdir(combined_dir):
        fp = os.path.join(combined_dir, f)
        if not os.path.isfile(fp):
            continue
        if delete_all:
            _safe_remove_file(fp)
            continue
        if scene_nums:
            for scene_num in scene_nums:
                if f.startswith(f'Scene_{scene_num}_') and f.lower().endswith('.mp4'):
                    _safe_remove_file(fp)
                    break


def run(cmd):
    logger.debug('Run: %s', cmd)
    proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        logger.error('Command failed: %s', cmd)
        stderr_text = proc.stderr.decode('utf-8', errors='ignore')
        if stderr_text:
            logger.error(stderr_text)
        raise RuntimeError(f'ffmpeg command failed: {stderr_text[:500]}')
    return proc.stdout


def ffprobe_duration(path):
    cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{path}"'
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
        return float(out.decode().strip())
    except Exception:
        return 0.0


def ffprobe_fps(path):
    # Try avg_frame_rate, fallback to r_frame_rate
    cmd = (
        f'ffprobe -v error -select_streams v:0 '
        f'-show_entries stream=avg_frame_rate,r_frame_rate '
        f'-of default=noprint_wrappers=1 "{path}"'
    )
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
        # Parse lines like avg_frame_rate=30000/1001
        rate = None
        for line in out.splitlines():
            if 'avg_frame_rate=' in line:
                rate = line.split('=')[1].strip()
                break
        if not rate:
            for line in out.splitlines():
                if 'r_frame_rate=' in line:
                    rate = line.split('=')[1].strip()
                    break
        if rate and '/' in rate:
            num, den = rate.split('/')
            num = float(num)
            den = float(den)
            if den != 0:
                return round(num / den)
        elif rate:
            return float(rate)
    except Exception:
        pass
    return 24.0


def ffprobe_size(path):
    cmd = (
        f'ffprobe -v error -select_streams v:0 '
        f'-show_entries stream=width,height '
        f'-of csv=p=0 "{path}"'
    )
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
        if out:
            parts = out.split(',')
            if len(parts) >= 2:
                return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 1280, 720


def ffprobe_has_audio(path):
    cmd = (
        f'ffprobe -v error -select_streams a:0 '
        f'-show_entries stream=index -of csv=p=0 "{path}"'
    )
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
        return bool(out)
    except Exception:
        return False


def ffprobe_audio_signature(path):
    """Return the primary audio stream parameters used for concat safety."""
    cmd = (
        f'ffprobe -v error -select_streams a:0 '
        f'-show_entries stream=codec_name,sample_rate,channels,channel_layout '
        f'-of json "{path}"'
    )
    try:
        raw = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
        payload = json.loads(raw.decode("utf-8", errors="ignore"))
        streams = payload.get("streams") if isinstance(payload, dict) else None
        stream = streams[0] if isinstance(streams, list) and streams else None
        if not isinstance(stream, dict):
            return None
        return (
            str(stream.get("codec_name") or ""),
            str(stream.get("sample_rate") or ""),
            str(stream.get("channels") or ""),
            str(stream.get("channel_layout") or ""),
        )
    except Exception:
        return None


def _clear_directory_contents(directory: str):
    if not os.path.isdir(directory):
        return
    for name in os.listdir(directory):
        target = os.path.join(directory, name)
        try:
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
        except Exception as e:
            logger.warning("Failed to clear %s: %s", target, e)


def _scaled_dimension(value: int, factor: float) -> int:
    scaled = max(2, int(round(float(value) * float(factor))))
    if scaled % 2 != 0:
        scaled += 1
    return scaled


def upscale_video(src_path: str, dst_path: str, scale_factor: float) -> str:
    src_path = os.path.abspath(str(src_path))
    dst_path = os.path.abspath(str(dst_path))
    factor = float(scale_factor)
    if factor <= 1.0:
        raise ValueError("scale_factor harus lebih besar dari 1.0")
    width, height = ffprobe_size(src_path)
    out_width = _scaled_dimension(width, factor)
    out_height = _scaled_dimension(height, factor)

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    tmp_output = dst_path if os.path.abspath(dst_path) != os.path.abspath(src_path) else f"{dst_path}.tmp.mp4"
    run(
        f'ffmpeg -y -i "{src_path}" '
        f'-vf "scale={out_width}:{out_height}:flags=lanczos" '
        f'-c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p '
        f'-c:a aac -b:a 192k -movflags +faststart "{tmp_output}"'
    )
    if tmp_output != dst_path:
        os.replace(tmp_output, dst_path)
    logger.info("Upscaled video written to %s", dst_path)
    return dst_path


def concat_videos(video_files, out_path):
    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.txt') as f:
        for p in video_files:
            # escape single quotes
            escaped = p.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
        list_path = f.name
    cmd = f'ffmpeg -y -f concat -safe 0 -i "{list_path}" -c copy "{out_path}"'
    try:
        run(cmd)
    finally:
        try:
            os.unlink(list_path)
        except Exception:
            pass


def concat_videos_reencode(video_files, out_path):
    """Concat audio/video through the concat filter to reset per-file timestamps."""
    if not video_files:
        raise ValueError("Minimal satu video diperlukan untuk concat.")
    inputs = " ".join(f'-i "{path}"' for path in video_files)
    streams = "".join(f"[{index}:v:0][{index}:a:0]" for index in range(len(video_files)))
    filter_complex = f'{streams}concat=n={len(video_files)}:v=1:a=1[v][a]'
    run(
        f'ffmpeg -y {inputs} -filter_complex "{filter_complex}" '
        f'-map "[v]" -map "[a]" -c:v libx264 -preset fast -pix_fmt yuv420p '
        f'-c:a aac -b:a 192k -ac 2 -ar 44100 -movflags +faststart "{out_path}"'
    )


def concat_videos_only_reencode(video_files, out_path):
    """Concat video streams only; audio is supplied separately by Compose Lagu."""
    if not video_files:
        raise ValueError("Minimal satu video diperlukan untuk concat.")
    inputs = " ".join(f'-i "{path}"' for path in video_files)
    streams = "".join(f"[{index}:v:0]" for index in range(len(video_files)))
    filter_complex = f'{streams}concat=n={len(video_files)}:v=1:a=0[v]'
    run(
        f'ffmpeg -y {inputs} -filter_complex "{filter_complex}" '
        f'-map "[v]" -an -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
        f'-fps_mode:v vfr -enc_time_base:v 1:1000000 -video_track_timescale 1000000 '
        f'-movflags +faststart "{out_path}"'
    )


def retime_video_only_to_duration(src_path, dst_path, target_duration):
    """Make a scene video occupy exactly the duration of its audio chunk."""
    source_duration = max(ffprobe_duration(src_path), 0.001)
    retime = float(target_duration) / source_duration
    run(
        f'ffmpeg -y -i "{src_path}" -map 0:v:0 -an '
        f'-vf "setpts=PTS*{retime:.12f}" -t {float(target_duration):.6f} '
        f'-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
        f'-fps_mode:v vfr -enc_time_base:v 1:1000000 -video_track_timescale 1000000 '
        f'"{dst_path}"'
    )


def build_song_audio_from_scenes(scene_dirs, out_path):
    """Decode and concatenate speech chunks as one continuous audio master."""
    chunk_paths = []
    for scene_dir in scene_dirs:
        candidates = [
            os.path.join(scene_dir, name)
            for name in os.listdir(scene_dir)
            if name.lower().startswith('speech_chunk_')
            and name.lower().endswith(AUDIO_EXTS)
        ]
        candidates.sort()
        if candidates:
            chunk_paths.append(candidates[0])

    if not chunk_paths:
        raise RuntimeError('Compose Lagu membutuhkan speech_chunk audio pada setiap scene.')
    if len(chunk_paths) != len(scene_dirs):
        raise RuntimeError(
            f'Compose Lagu menemukan {len(chunk_paths)} speech chunk untuk '
            f'{len(scene_dirs)} scene.'
        )

    inputs = ' '.join(f'-i "{path}"' for path in chunk_paths)
    streams = ''.join(
        f'[{index}:a:0]aresample=44100:async=0:first_pts=0, '
        f'asetpts=PTS-STARTPTS[a{index}];'
        for index in range(len(chunk_paths))
    )
    concat_inputs = ''.join(f'[a{index}]' for index in range(len(chunk_paths)))
    filter_complex = (
        f'{streams}{concat_inputs}concat=n={len(chunk_paths)}:v=0:a=1,'
        'aresample=44100:async=0:first_pts=0,aformat=sample_rates=44100:channel_layouts=stereo[a]'
    )
    run(
        f'ffmpeg -y {inputs} -filter_complex "{filter_complex}" '
        f'-map "[a]" -c:a pcm_s16le "{out_path}"'
    )
    return chunk_paths


def trim_video_to_exact_duration(src_path, dst_path, duration, fps=None):
    """Trim an S2V video while retaining its embedded audio track."""
    audio_map = "-map 0:a:0" if ffprobe_has_audio(src_path) else "-map -0:a"
    video_filter = "setpts=PTS-STARTPTS"
    if fps and float(fps) > 0:
        frame_count = max(1, math.ceil(float(duration) * float(fps) - 1e-6))
        source_frame_duration = frame_count / float(fps)
        retime = float(duration) / max(source_frame_duration, 1e-6)
        video_filter = f"trim=end_frame={frame_count},setpts=(PTS-STARTPTS)*{retime:.12f}"
    run(
        f'ffmpeg -y -i "{src_path}" -t {float(duration):.6f} '
        f'-map 0:v:0 {audio_map} -vf "{video_filter}" '
        f'-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
        f'-fps_mode:v vfr -enc_time_base:v 1:1000000 -video_track_timescale 1000000 '
        f'-c:a aac -b:a 192k -ac 2 -ar 44100 '
        f'-avoid_negative_ts make_zero "{dst_path}"'
    )


def ensure_video_fps_size_and_length(
    src,
    dst,
    fps,
    width,
    height,
    target_duration,
    preserve_audio=False,
    precise_timing=False,
):
    # Check if any transformation is needed
    src_fps = ffprobe_fps(src)
    src_w, src_h = ffprobe_size(src)
    dur = ffprobe_duration(src)
    
    needs_fps = abs(src_fps - fps) > 0.1
    needs_size = src_w != width or src_h != height
    needs_pad = target_duration - dur > 0.01
    needs_trim = dur - target_duration > 0.01
    
    if not needs_fps and not needs_size and not needs_pad and not needs_trim:
        # Perfect match - copy without re-encoding
        shutil.copyfile(src, dst)
        logger.debug('Video already perfect, using direct copy: %s', src)
        return
    
    if not needs_fps and not needs_size and needs_pad:
        # Only need duration padding - use tpad to clone last frame and re-encode
        # This is more reliable than concat for seamless visual result
        pad = target_duration - dur
        pad_filter = f',tpad=stop_mode=clone:stop_duration={pad}' if pad > 0.001 else ''
        cmd = (
            f'ffmpeg -y -i "{src}" -vf "fps={fps}{pad_filter}" '
            f'-c:v libx264 -b:v 2M -preset fast -pix_fmt yuv420p -an "{dst}"'
        )
        run(cmd)
        logger.debug('Extended video duration using tpad re-encode: %s', src)
        return

    if not needs_fps and not needs_size and needs_trim:
        audio_args = ""
        if preserve_audio and ffprobe_has_audio(src):
            audio_args = '-map 0:a:0 -c:a aac -b:a 192k -ac 2 -ar 44100'
        else:
            audio_args = '-an'
        retime = target_duration / max(dur, 1e-6)
        precision_args = ''
        if precise_timing:
            precision_args = '-fps_mode:v vfr -enc_time_base:v 1:1000000 -video_track_timescale 1000000 '
        cmd = (
            f'ffmpeg -y -i "{src}" -vf "setpts=PTS*{retime:.12f}" '
            f'{precision_args}-t {target_duration:.6f} -map 0:v:0 {audio_args} '
            f'-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p "{dst}"'
        )
        run(cmd)
        logger.debug('Retimed video to exact target duration: %s', src)
        return
    
    # Need full transformation (scale/fps/pad) - use high bitrate to preserve quality
    pad = max(0.0, target_duration - dur)
    pad_filter = f',tpad=stop_mode=clone:stop_duration={pad}' if pad > 0.001 else ''
    
    fit_filter = (
        f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2'
    )
    cmd = (
        f'ffmpeg -y -i "{src}" -vf "{fit_filter},fps={fps}{pad_filter}" '
        f'-c:v libx264 -b:v 2M -preset fast -pix_fmt yuv420p -an "{dst}"'
    )
    run(cmd)
    logger.debug('Full video transformation applied: %s', src)


def create_silent_video(dst, fps, width, height, duration):
    cmd = (
        f'ffmpeg -y -f lavfi -i color=size={width}x{height}:rate={fps}:color=000000 '
        f'-t {duration} -c:v libx264 -pix_fmt yuv420p "{dst}"'
    )
    run(cmd)


def pad_audio_to_duration(src, dst, target_duration):
    dur = ffprobe_duration(src)
    pad = max(0.0, target_duration - dur)
    if pad < 0.01:
        # No padding needed - copy directly
        shutil.copyfile(src, dst)
        return
    # Simple padding with silence
    cmd = (
        f'ffmpeg -y -i "{src}" -af "apad=pad_dur={pad}" '
        f'-c:a pcm_s16le "{dst}"'
    )
    run(cmd)


def create_black_clip_with_silence(dst, fps, width, height, duration):
    # Create black video and silent audio, then mux together as mp4 (aac)
    with tempfile.TemporaryDirectory() as td:
        vpath = os.path.join(td, 'black.mp4')
        apath = os.path.join(td, 'silent.wav')
        run(
            f'ffmpeg -y -f lavfi -i color=size={width}x{height}:rate={fps}:color=000000 '
            f'-t {duration} -c:v libx264 -pix_fmt yuv420p "{vpath}"'
        )
        run(
            f'ffmpeg -y -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 '
            f'-t {duration} -c:a pcm_s16le "{apath}"'
        )
        run(
            f'ffmpeg -y -i "{vpath}" -i "{apath}" -map 0:v -map 1:a '
            f'-c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 192k "{dst}"'
        )


def build_audio_mix_cmd(inputs, volumes, target_audio_path):
    # Build per-input volume filters then amix; this ensures only specified prompt audios are scaled
    parts = []
    for p in inputs:
        parts.append(f'-i "{p}"')
    input_str = ' '.join(parts)

    filter_parts = []
    labeled_streams = []
    for i, p in enumerate(inputs):
        vol = volumes.get(p, 1.0)
        try:
            vol = float(vol)
        except Exception:
            vol = 1.0
        filter_parts.append(f'[{i}:a]volume={vol}[a{i}]')
        labeled_streams.append(f'[a{i}]')

    num = len(inputs)
    amix = f"{''.join(labeled_streams)}amix=inputs={num}:normalize=0[aout]"
    filter_complex = ';'.join(filter_parts + [amix])
    cmd = f'ffmpeg -y {input_str} -filter_complex "{filter_complex}" -map "[aout]" -c:a pcm_s16le "{target_audio_path}"'
    return cmd


def compose_scene(
    scene_dir,
    fps=None,
    speech_volume=1.0,
    video_files=None,
    out_path_override=None,
    include_video_audio=False,
    include_scene_speech=None,
    embedded_audio_source=None,
    compose_song=False,
    trim_s2v_extra_frames=False,
    project_video_size=None,
):
    files = sorted(os.listdir(scene_dir))
    if video_files is None:
        videos = [os.path.join(scene_dir, f) for f in files if f.lower().endswith(VIDEO_EXTS)]
    else:
        videos = [os.path.abspath(v) for v in video_files if os.path.isfile(v)]
    all_audios = [os.path.join(scene_dir, f) for f in files if f.lower().endswith(AUDIO_EXTS)]

    meta = _load_scene_meta_runtime(scene_dir)

    # Select only intended audio sources:
    # - latest speech_* file
    # - sound files mapped from sound_prompt
    latest_speech = None
    speech_candidates = [a for a in all_audios if os.path.basename(a).lower().startswith('speech_')]
    if speech_candidates:
        speech_candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        latest_speech = speech_candidates[0]

    sound_prompt = str(meta.get('sound_prompt', '') or '')
    sound_volume = str(meta.get('sound_volume', '') or '')
    prompts = [p.strip() for p in sound_prompt.split(',') if p.strip()]
    vols = [s.strip() for s in sound_volume.split(',') if s.strip()]

    sound_vols = {}
    for i, p in enumerate(prompts):
        prompt_name = p.replace(' ', '_')
        v = 1.0
        if i < len(vols):
            try:
                v = float(vols[i])
            except Exception:
                v = 1.0
        for f in files:
            if not f.lower().endswith(AUDIO_EXTS):
                continue
            fname_no_ext = os.path.splitext(f)[0].lower()
            if fname_no_ext == prompt_name.lower():
                full_path = os.path.join(scene_dir, f)
                sound_vols[full_path] = v
                logger.debug('Found sound prompt file: %s with volume %s', full_path, v)

    if include_scene_speech is None:
        # Backward-compatible default: embedded S2V speech replaces the
        # standalone speech file, while ordinary scenes use scene speech.
        include_scene_speech = not include_video_audio

    selected_audios = []
    if latest_speech and include_scene_speech:
        selected_audios.append(latest_speech)
    for snd_path in sound_vols.keys():
        if snd_path not in selected_audios:
            selected_audios.append(snd_path)
    audios = selected_audios
    embedded_audio_source = str(embedded_audio_source or '').strip()
    has_embedded_audio_source = bool(
        embedded_audio_source and os.path.isfile(embedded_audio_source)
    )

    video_durations = [ffprobe_duration(v) for v in videos]
    audio_durations = [ffprobe_duration(a) for a in audios]
    if has_embedded_audio_source:
        audio_durations.append(ffprobe_duration(embedded_audio_source))
    max_video_dur = max(video_durations) if video_durations else 0
    max_audio_dur = max(audio_durations) if audio_durations else 0
    target_dur = max(max_video_dur, max_audio_dur)
    if compose_song and trim_s2v_extra_frames and latest_speech:
        # WAN22 S2V may contain up to four extra frames. Song compose uses
        # the original speech chunk as the exact scene duration. MiniMax H3
        # S2V already follows the audio duration and must not use this trim.
        target_dur = ffprobe_duration(latest_speech)
    if target_dur < 0.1:
        logger.warning('No media duration found in %s, skipping', scene_dir)
        return None

    tmpdir = tempfile.mkdtemp(prefix='compose_')
    base_video = None
    # Determine target fps and size from first available video
    target_fps = None
    target_w, target_h = 1280, 720
    if videos:
        if len(videos) == 1:
            base_video = videos[0]
        else:
            concat_path = os.path.join(tmpdir, 'concat.mp4')
            concat_videos(videos, concat_path)
            base_video = concat_path
        if compose_song and trim_s2v_extra_frames and latest_speech and len(videos) == 1:
            exact_path = os.path.join(tmpdir, 's2v_exact_duration.mp4')
            trim_video_to_exact_duration(base_video, exact_path, target_dur, ffprobe_fps(base_video))
            base_video = exact_path
        target_fps = ffprobe_fps(base_video)
        if isinstance(project_video_size, (tuple, list)) and len(project_video_size) == 2:
            try:
                target_w, target_h = int(project_video_size[0]), int(project_video_size[1])
            except (TypeError, ValueError):
                target_w, target_h = ffprobe_size(base_video)
        else:
            target_w, target_h = ffprobe_size(base_video)
        if fps:
            target_fps = fps
        video_normalized = os.path.join(tmpdir, 'video_norm.mp4')
        ensure_video_fps_size_and_length(
            base_video,
            video_normalized,
            target_fps,
            target_w,
            target_h,
            target_dur,
            preserve_audio=include_video_audio,
            precise_timing=compose_song,
        )
    else:
        if not fps:
            target_fps = 24
        else:
            target_fps = fps
        video_normalized = os.path.join(tmpdir, 'video_norm.mp4')
        create_silent_video(video_normalized, target_fps, target_w, target_h, target_dur)

    # collect only actual audio files for mixing (do not use video file unless it has audio)
    audio_inputs = []
    volumes = {}

    padded_audio_inputs = []
    # Determine speech candidates by filename patterns
    speech_keys = ('voice', 'tts')
    for idx, a in enumerate(audios):
        vol = sound_vols.get(a, 1.0)
        # detect likely speech files by filename
        bname = os.path.basename(a).lower()
        is_speech = any(k in bname for k in speech_keys)
        if is_speech and speech_volume is not None:
            try:
                vol = float(vol) * float(speech_volume)
            except Exception:
                vol = float(vol)
        padded_path = os.path.join(tmpdir, f'padded_audio_{idx}.wav')
        pad_audio_to_duration(a, padded_path, target_dur)
        padded_audio_inputs.append(padded_path)
        volumes[padded_path] = vol
        logger.info('Audio file: %s -> volume: %s%s', os.path.basename(a), vol, ' (speech)' if is_speech else '')

    audio_inputs = padded_audio_inputs

    if has_embedded_audio_source:
        padded_embedded_audio = os.path.join(tmpdir, 'padded_embedded_audio.wav')
        pad_audio_to_duration(embedded_audio_source, padded_embedded_audio, target_dur)
        audio_inputs.append(padded_embedded_audio)
        volumes[padded_embedded_audio] = 1.0

    if include_video_audio and ffprobe_has_audio(video_normalized):
        base_audio_path = os.path.join(tmpdir, 'base_video_audio.wav')
        extract_cmd = f'ffmpeg -y -i "{video_normalized}" -vn -acodec pcm_s16le "{base_audio_path}"'
        run(extract_cmd)
        padded_base_audio = os.path.join(tmpdir, 'padded_base_audio.wav')
        pad_audio_to_duration(base_audio_path, padded_base_audio, target_dur)
        audio_inputs.append(padded_base_audio)
        volumes[padded_base_audio] = 1.0

    if not audio_inputs:
        silent_path = os.path.join(tmpdir, 'silent.wav')
        cmd = f'ffmpeg -y -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t {target_dur} -c:a pcm_s16le "{silent_path}"'
        run(cmd)
        audio_inputs = [silent_path]
        volumes[silent_path] = 1.0

    mixed_audio = os.path.join(tmpdir, 'mixed.wav')
    mix_cmd = build_audio_mix_cmd(audio_inputs, volumes, mixed_audio)
    run(mix_cmd)

    scene_name = os.path.basename(scene_dir)
    num = scene_name.split('_')[-1]
    scene_title = ''
    meta_for_title = _load_scene_meta_runtime(scene_dir)
    scene_title = meta_for_title.get('scene_title', '')
    if out_path_override:
        out_path = str(out_path_override)
    else:
        safe_title = _safe_filename_segment(scene_title)
        out_name = f"Scene_{num}_{safe_title}.mp4"
        # Output directly to combined directory
        if not API_PRODUCTION:
            raise RuntimeError("Project root belum diset untuk compose.")
        combined_dir = os.path.join(API_PRODUCTION, 'combined')
        os.makedirs(combined_dir, exist_ok=True)
        out_path = os.path.join(combined_dir, out_name)

    # Force stable audio timestamps and duration; this helps downstream transcoders (e.g., Clipchamp/WhatsApp)
    video_codec = (
        '-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p'
        if compose_song
        else '-c:v copy'
    )
    cmd = (
        f'ffmpeg -y -i "{video_normalized}" -i "{mixed_audio}" '
        f'-map 0:v -map 1:a {video_codec} -c:a aac -b:a 192k '
        f'-af "aresample=async=1:first_pts=0" -t {target_dur:.6f} -movflags +faststart "{out_path}"'
    )
    run(cmd)

    try:
        for fn in os.listdir(tmpdir):
            os.remove(os.path.join(tmpdir, fn))
        os.rmdir(tmpdir)
    except Exception:
        pass

    logger.info('Composed scene output: %s', out_path)
    return out_path


def _get_latest_scene_video(scene_dir):
    files = sorted(os.listdir(scene_dir))
    videos = [os.path.join(scene_dir, f) for f in files if f.lower().endswith(VIDEO_EXTS)]
    if not videos:
        return None
    videos.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return videos[0]


def _prepare_comfy_audio_source(scene_dir, video_path):
    """Create the pristine ComfyUI audio cache when Compose first needs it.

    Generated MiniMax videos remain untouched in the scene root. The cache is
    created only when Compose needs it, preventing the generation step from
    replacing the original downloaded video with a mixed scene output.
    """
    source_dir = os.path.join(scene_dir, COMFY_AUDIO_SOURCE_DIRNAME)
    source_path = os.path.join(source_dir, COMFY_AUDIO_SOURCE_FILENAME)
    if not video_path or not os.path.isfile(video_path) or not ffprobe_has_audio(video_path):
        if os.path.isfile(source_path):
            _safe_remove_file(source_path)
        return None
    if os.path.isfile(source_path):
        return source_path

    os.makedirs(source_dir, exist_ok=True)
    temp_path = os.path.join(source_dir, 'audio.tmp.wav')
    try:
        run(
            f'ffmpeg -y -i "{video_path}" -vn '
            f'-af "aresample=44100:async=0:first_pts=0,'
            f'aformat=sample_rates=44100:channel_layouts=stereo" '
            f'-c:a pcm_s16le -ac 2 -ar 44100 "{temp_path}"'
        )
        if not os.path.isfile(temp_path) or os.path.getsize(temp_path) <= 0:
            raise RuntimeError(f'ComfyUI audio source missing or empty: {temp_path}')
        os.replace(temp_path, source_path)
        logger.info('Prepared ComfyUI audio source for Compose: %s', source_path)
        return source_path
    finally:
        if os.path.isfile(temp_path):
            _safe_remove_file(temp_path)


def export_scene_video_to_combined(scene_dir):
    latest_video = _get_latest_scene_video(scene_dir)
    if not latest_video:
        logger.warning('No video found in %s, skipping export', scene_dir)
        return None

    scene_name = os.path.basename(scene_dir)
    num = scene_name.split('_')[-1]
    scene_title = ''
    meta = _load_scene_meta_runtime(scene_dir)
    scene_title = meta.get('scene_title', '')

    safe_title = _safe_filename_segment(scene_title)
    out_name = f"Scene_{num}_{safe_title}.mp4"
    if not API_PRODUCTION:
        raise RuntimeError("Project root belum diset untuk export scene.")
    combined_dir = os.path.join(API_PRODUCTION, 'combined')
    os.makedirs(combined_dir, exist_ok=True)
    out_path = os.path.join(combined_dir, out_name)
    shutil.copyfile(latest_video, out_path)
    logger.info('Exported scene video: %s -> %s', latest_video, out_path)
    return out_path


def normalize_video(src, dst, fps, width, height):
    # Re-encode with fixed video settings and guaranteed stereo AAC audio.
    # If source has no audio stream, add silent audio so concat remains stable.
    fit_filter = (
        f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2'
    )
    if ffprobe_has_audio(src):
        cmd = (
            f'ffmpeg -y -i "{src}" -vf "{fit_filter},fps={fps}" '
            f'-af "aresample=async=1:first_pts=0,aformat=sample_rates=44100:channel_layouts=stereo" '
            f'-c:v libx264 -preset fast -pix_fmt yuv420p '
            f'-c:a aac -b:a 192k -ac 2 -ar 44100 "{dst}"'
        )
    else:
        duration = max(0.1, ffprobe_duration(src))
        cmd = (
            f'ffmpeg -y -i "{src}" '
            f'-f lavfi -t {duration:.6f} -i anullsrc=channel_layout=stereo:sample_rate=44100 '
            f'-vf "{fit_filter},fps={fps}" '
            f'-map 0:v:0 -map 1:a:0 '
            f'-c:v libx264 -preset fast -pix_fmt yuv420p '
            f'-c:a aac -b:a 192k -ac 2 -ar 44100 -shortest "{dst}"'
        )
    run(cmd)


def image_to_clip(img_path, dst, fps, width, height, duration):
    vf = f'scale={width}:{height}:force_original_aspect_ratio=decrease,' \
         f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black'
    run(
        f'ffmpeg -y -loop 1 -t {duration} -framerate {fps} -i "{img_path}" '
        f'-vf "{vf}" -c:v libx264 -pix_fmt yuv420p -shortest "{dst}"'
    )
    # add silent audio
    with tempfile.TemporaryDirectory() as td:
        apath = os.path.join(td, 'silent.wav')
        run(
            f'ffmpeg -y -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 '
            f'-t {duration} -c:a pcm_s16le "{apath}"'
        )
        run(
            f'ffmpeg -y -i "{dst}" -i "{apath}" -map 0:v -map 1:a '
            f'-c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 192k "{dst}.tmp"'
        )
        os.replace(f'{dst}.tmp', dst)


def merge_combined_videos(selected_scene_nums=None, music_file=None, music_volume=BACKGROUND_MUSIC_VOLUME, upscale_factor=1.0, compose_song=False, project_video_size=None):
    if not API_PRODUCTION:
        raise RuntimeError("Project root belum diset untuk merge.")
    combined_dir = os.path.join(API_PRODUCTION, 'combined')
    if not os.path.isdir(combined_dir):
        logger.warning('Combined directory not found: %s', combined_dir)
        return None
    files = sorted(os.listdir(combined_dir))
    # Only include per-scene outputs to avoid re-merging previous combined outputs
    videos = [
        os.path.join(combined_dir, f)
        for f in files
        if f.lower().endswith(VIDEO_EXTS) and f.startswith('Scene_')
    ]
    if selected_scene_nums:
        selected = {str(n) for n in selected_scene_nums}
        filtered = []
        for vp in videos:
            bn = os.path.basename(vp)
            parts = bn.split('_')
            if len(parts) >= 2 and parts[1] in selected:
                filtered.append(vp)
        videos = filtered
    if not videos:
        logger.warning('No videos in combined to merge.')
        return None

    # Sort by scene number if available in filename
    def scene_key(p):
        bn = os.path.basename(p)
        num = None
        try:
            # Expect names like Scene_1_...
            parts = bn.split('_')
            if len(parts) >= 2:
                num = int(parts[1])
        except Exception:
            num = None
        # Ensure consistent sortable type: tuple of (num or big, name)
        return (num if isinstance(num, int) else 999999, bn)
    videos.sort(key=scene_key)

    song_scene_dirs = []
    if compose_song:
        for video_path in videos:
            try:
                scene_num = int(os.path.basename(video_path).split('_')[1])
            except (IndexError, ValueError):
                song_scene_dirs = []
                break
            scene_dir = os.path.join(API_PRODUCTION, f'scene_{scene_num}')
            if not os.path.isdir(scene_dir):
                song_scene_dirs = []
                break
            song_scene_dirs.append(scene_dir)

    with tempfile.TemporaryDirectory(prefix='merge_') as td:
        # Master fps and size from first video
        master_fps = ffprobe_fps(videos[0])
        if isinstance(project_video_size, (tuple, list)) and len(project_video_size) == 2:
            try:
                master_w, master_h = int(project_video_size[0]), int(project_video_size[1])
            except (TypeError, ValueError):
                master_w, master_h = ffprobe_size(videos[0])
        else:
            master_w, master_h = ffprobe_size(videos[0])
        cover_dir = os.path.join(API_PRODUCTION, 'cover')
        cover_src = _find_first_cover_image(cover_dir, td)
        cover_clip = None
        if cover_src:
            cover_clip = os.path.join(td, "cover_intro.mp4")
            _create_cover_clip(cover_src, cover_clip, master_fps, master_w, master_h)

        # Check if all videos already have compatible video and audio streams.
        # Concatenating AAC streams with different sample rates/channel layouts
        # using -c copy creates a mid-stream codec configuration change. The
        # resulting file may look valid to ffprobe but fail when decoded later
        # by the background-music mix.
        all_same = True
        master_audio_signature = ffprobe_audio_signature(videos[0])
        for v in videos[1:]:
            if (
                ffprobe_fps(v) != master_fps
                or ffprobe_size(v) != (master_w, master_h)
                or ffprobe_audio_signature(v) != master_audio_signature
            ):
                all_same = False
                break
        # If cover intro exists, safest path is normalize+reencode merge.
        if cover_clip:
            all_same = False
        if compose_song:
            # Re-encode normalized audio/video before concat so separate AAC
            # encoder priming does not create gaps at scene boundaries.
            all_same = False

        norm_paths = []
        if all_same:
            norm_paths = [v for v in videos]
        else:
            if cover_clip:
                norm_cover = os.path.join(td, 'norm_cover.mp4')
                normalize_video(cover_clip, norm_cover, master_fps, master_w, master_h)
                norm_paths.append(norm_cover)
            for i, v in enumerate(videos):
                dst = os.path.join(td, f'norm_{i:03d}.mp4')
                normalize_video(v, dst, master_fps, master_w, master_h)
                norm_paths.append(dst)
        if all_same and cover_clip:
            norm_paths = [cover_clip] + norm_paths

        list_path = os.path.join(td, 'concat_list.txt')
        with open(list_path, 'w', encoding='utf-8') as f:
            for vp in norm_paths:
                escaped_vp = vp.replace("'", "'\\''")
                f.write(f"file '{escaped_vp}'\n")

        final_out = os.path.join(combined_dir, 'combined_all.mp4')
        if os.path.exists(final_out):
            _safe_remove_file(final_out)

        if compose_song and song_scene_dirs:
            # Audio is the master timeline. Each video scene is retimed to
            # its original speech chunk before the video-only concat, so a
            # video frame can never insert silence at a scene boundary.
            song_audio = os.path.join(td, 'song_audio_master.wav')
            chunk_paths = build_song_audio_from_scenes(song_scene_dirs, song_audio)
            song_video_paths = []
            for index, (video_path, chunk_path) in enumerate(zip(norm_paths, chunk_paths)):
                retimed_path = os.path.join(td, f'song_video_{index:03d}.mp4')
                retime_video_only_to_duration(
                    video_path,
                    retimed_path,
                    ffprobe_duration(chunk_path),
                )
                song_video_paths.append(retimed_path)

            song_video = os.path.join(td, 'song_video_only.mp4')
            concat_videos_only_reencode(song_video_paths, song_video)
            song_duration = ffprobe_duration(song_audio)
            video_gap = song_duration - ffprobe_duration(song_video)
            if video_gap > 0.001:
                # The last encoded frame duration is not always included in
                # the container duration. Hold that frame until audio ends.
                video_mux_args = (
                    f'-vf "tpad=stop_mode=clone:stop_duration={video_gap + 0.05:.6f}" '
                    '-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p '
                )
            else:
                video_mux_args = '-c:v copy '
            run(
                f'ffmpeg -y -i "{song_video}" -i "{song_audio}" '
                f'-map 0:v:0 -map 1:a:0 -t {song_duration:.6f} '
                f'{video_mux_args}-c:a aac -b:a 192k -ac 2 -ar 44100 '
                f'-af "aresample=async=0:first_pts=0" -movflags +faststart "{final_out}"'
            )
        elif compose_song:
            # Keep the prior compose-song path for projects that do not use
            # the standard scene_N/speech_chunk_NN layout.
            concat_videos_reencode(norm_paths, final_out)
        elif all_same:
            try:
                run(
                    f'ffmpeg -y -f concat -safe 0 -i "{list_path}" '
                    f'-c copy -movflags +faststart "{final_out}"'
                )
            except Exception as e:
                logger.warning('Concat copy failed, fallback to re-encode merge: %s', e)
                # Build fully normalized clips (with guaranteed audio), then concat re-encode.
                norm_paths = []
                for i, v in enumerate(videos):
                    dst = os.path.join(td, f'norm_fallback_{i:03d}.mp4')
                    normalize_video(v, dst, master_fps, master_w, master_h)
                    norm_paths.append(dst)
                fallback_list = os.path.join(td, 'concat_list_fallback.txt')
                with open(fallback_list, 'w', encoding='utf-8') as f2:
                    for vp in norm_paths:
                        escaped_vp = vp.replace("'", "'\\''")
                        f2.write(f"file '{escaped_vp}'\n")
                run(
                    f'ffmpeg -y -f concat -safe 0 -i "{fallback_list}" '
                    f'-c:v libx264 -preset fast -pix_fmt yuv420p '
                    f'-c:a aac -b:a 192k -ac 2 -ar 44100 -movflags +faststart "{final_out}"'
                )
        else:
            run(
                f'ffmpeg -y -f concat -safe 0 -i "{list_path}" '
                f'-c:v libx264 -preset fast -pix_fmt yuv420p '
                f'-c:a aac -b:a 192k -ac 2 -ar 44100 -movflags +faststart "{final_out}"'
            )

    if music_file:
        _mix_background_music(final_out, music_file, music_volume)
    _force_dual_mono_audio(final_out)
    if float(upscale_factor) > 1.0:
        upscale_video(
            final_out,
            final_out,
            float(upscale_factor),
        )

    logger.info('Final merged video: %s', final_out)
    return final_out


def main(project_name, specific_scenes=None, speech_volume=1.0, no_final_merge=False, music_file=None, music_volume=BACKGROUND_MUSIC_VOLUME, upscale_factor=1.0, compose_song=False):
    global API_PRODUCTION
    API_PRODUCTION = os.path.join(ROOT, 'api_production', str(project_name).strip())
    if not os.path.exists(API_PRODUCTION):
        print('Project folder not found:', API_PRODUCTION)
        return 1
    try:
        project_settings = load_project_settings(Path(API_PRODUCTION))
        video_size = project_settings.get('video_size', {})
        project_video_size = (
            int(video_size.get('width', 480)),
            int(video_size.get('height', 848)),
        )
        if project_video_size[0] <= 0 or project_video_size[1] <= 0:
            raise ValueError('Ukuran video project harus lebih besar dari nol.')
    except Exception as e:
        logger.warning('Gagal membaca ukuran video project; memakai ukuran default 480x848: %s', e)
        project_video_size = (480, 848)
    
    # Clean combined folder before starting
    combined_dir = os.path.join(API_PRODUCTION, 'combined')
    
    if specific_scenes:
        # Only delete specific scene files in combined folder
        scene_nums = [scene.split('_')[-1] for scene in specific_scenes]
        _safe_clean_combined_dir(combined_dir, delete_all=False, scene_nums=scene_nums)
    else:
        # Clean entire combined folder when processing all scenes (lock-tolerant)
        _safe_clean_combined_dir(combined_dir, delete_all=True)
    
    scenes = sorted([d for d in os.listdir(API_PRODUCTION) if d.startswith('scene_')], key=_scene_sort_key)
    if specific_scenes:
        scenes = [s for s in scenes if s in specific_scenes]
    for scene in scenes:
        scene_dir = os.path.join(API_PRODUCTION, scene)
        print('Collecting', scene_dir)
        try:
            scene_meta_path = os.path.join(scene_dir, 'scene_meta.json')
            scene_type = ''
            scene_meta = {}
            try:
                if os.path.exists(scene_meta_path):
                    scene_meta = _load_scene_meta_runtime(scene_dir)
                    scene_type = str(scene_meta.get('scene_type', '') or '').strip().lower()
            except Exception:
                scene_type = ''

            # S2V keeps embedded speech and excludes standalone scene speech.
            # MiniMax H3 T2V/I2V keeps its original ComfyUI audio and combines
            # that source with standalone scene speech and sound effects.
            is_wan22_s2v = scene_type == 'wan22_s2v'
            is_s2v = scene_type in {'wan22_s2v', 'minimax-h3_s2v', 'minimax-h3_r2v'}
            is_minimax_h3_av = scene_type in {
                'minimax-h3_i2v',
                'minimax-h3_t2v_i2v',
            }
            audio_composed = bool(scene_meta.get('audio_composed', False))

            # WAN I2V/T2V and MiniMax H3 I2V/T2V-I2V already contain the
            # complete scene mix produced during scene execution.  Export the
            # existing video unchanged; calling compose_scene here would add
            # the same voice and sound-effect files for a second time.
            if audio_composed and scene_type in {
                'wan22',
                'wan22_i2v',
                'wan22_t2v_i2v',
                'wan22_t2v',
                'minimax-h3_i2v',
                'minimax-h3_t2v_i2v',
            }:
                export_scene_video_to_combined(scene_dir)
                continue
            selected_video_files = None
            embedded_audio_source = None
            include_video_audio = is_s2v
            include_scene_speech = not is_s2v
            if scene_type in {'minimax-h3_s2v', 'minimax-h3_r2v'}:
                # A MiniMax scene represents one final generation. Older
                # downloaded outputs in the root must not be concatenated.
                latest_video = _get_latest_scene_video(scene_dir)
                selected_video_files = [latest_video] if latest_video else []
            if is_minimax_h3_av:
                latest_video = _get_latest_scene_video(scene_dir)
                selected_video_files = [latest_video] if latest_video else []
                embedded_audio_source = _prepare_comfy_audio_source(scene_dir, latest_video)
                if embedded_audio_source:
                    # Rebuild from the raw ComfyUI audio master and add scene
                    # speech/sound without touching the root video.
                    include_video_audio = False
                    include_scene_speech = True
                else:
                    # Hapus Sound=true scenes have no embedded audio. Keep
                    # scene speech/sound enabled; if an old legacy video still
                    # has audio and extraction failed, preserve it without a
                    # second speech mix.
                    has_root_audio = bool(latest_video and ffprobe_has_audio(latest_video))
                    include_video_audio = has_root_audio
                    include_scene_speech = not has_root_audio
                    if has_root_audio:
                        logger.warning(
                            'Could not prepare MiniMax H3 ComfyUI audio master in %s; '
                            'preserving existing root-video audio as fallback.',
                            scene_dir,
                        )
            compose_scene(
                scene_dir,
                speech_volume=0.0 if is_s2v else speech_volume,
                video_files=selected_video_files,
                include_video_audio=include_video_audio,
                include_scene_speech=include_scene_speech,
                embedded_audio_source=embedded_audio_source,
                compose_song=compose_song,
                trim_s2v_extra_frames=is_wan22_s2v,
                project_video_size=project_video_size,
            )
        except Exception as e:
            logger.error('Failed to compose %s: %s', scene_dir, e)
    # After collecting, merge videos in combined (unless quick mode is requested)
    if no_final_merge:
        logger.info('Skip final merge because --no-final-merge is enabled.')
        return 0
    try:
        if specific_scenes:
            selected_nums = [scene.split('_')[-1] for scene in specific_scenes]
            merge_combined_videos(
                selected_scene_nums=selected_nums,
                music_file=music_file,
                music_volume=music_volume,
                upscale_factor=upscale_factor,
                compose_song=compose_song,
                project_video_size=project_video_size,
            )
        else:
            merge_combined_videos(
                music_file=music_file,
                music_volume=music_volume,
                upscale_factor=upscale_factor,
                compose_song=compose_song,
                project_video_size=project_video_size,
            )
    except Exception as e:
        logger.error('Failed to merge combined videos: %s', e)
        return 1
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compose videos and audio per scene')
    parser.add_argument('--project', '-p', required=True, help='Nama project di dalam folder api_production')
    parser.add_argument('--scene', '-s', action='append', help='Scene to process (repeatable)')
    parser.add_argument('--speech-volume', type=float, default=1.0, help='Global multiplier for detected speech audio files (can be >1)')
    parser.add_argument('--no-final-merge', action='store_true', help='Only export scene videos to combined folder, skip combined_all.mp4 merge')
    parser.add_argument('--music-file', default='', help='Optional background music file path for final combined video')
    parser.add_argument('--music-volume', type=float, default=BACKGROUND_MUSIC_VOLUME, help='Background music volume in range 0.0 to 2.0')
    parser.add_argument('--upscale-factor', type=float, default=1.0, help='Optional final upscale factor, e.g. 1.5 or 2.0')
    parser.add_argument(
        '--compose-song',
        action='store_true',
        help='Use speech chunks as the song timeline; only WAN22 S2V discards its extra frames.',
    )
    args = parser.parse_args()
    music_volume = max(0.0, min(2.0, float(args.music_volume)))
    raise SystemExit(main(
        project_name=args.project,
        specific_scenes=args.scene,
        speech_volume=args.speech_volume,
        no_final_merge=args.no_final_merge,
        music_file=str(args.music_file or '').strip() or None,
        music_volume=music_volume,
        upscale_factor=float(args.upscale_factor or 1.0),
        compose_song=bool(args.compose_song),
    ))
