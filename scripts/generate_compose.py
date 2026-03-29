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

setup_logging()
logger = get_logger(__name__)

PARENT = os.path.dirname(ROOT)
API_PRODUCTION = os.path.join(PARENT, os.path.basename(ROOT), 'api_production')

VIDEO_EXTS = ('.mp4', '.mov', '.webm', '.mkv')
AUDIO_EXTS = ('.m4a', '.wav', '.mp3')
IMAGE_EXTS = ('.jpg', '.jpeg', '.png')

# Background music volume for final merged video (0.0 to 1.0)
BACKGROUND_MUSIC_VOLUME = 0.3


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
            run(
                f'ffmpeg -y -i "{final_video_path}" -i "{looped_wav}" '
                f'-filter_complex "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,'
                f'pan=mono|c0=c0[a0m];'
                f'[1:a]aformat=sample_rates=44100:channel_layouts=stereo,'
                f'pan=mono|c0=0.5*c0+0.5*c1[a1m];'
                f'[a0m][a1m]amix=inputs=2:normalize=0:duration=first[aout]" '
                f'-map 0:v -map "[aout]" -c:v copy -c:a aac -b:a 192k '
                f'-ac 2 -ar 44100 '
                f'-movflags +faststart "{out_tmp}"'
            )
        else:
            run(
                f'ffmpeg -y -i "{final_video_path}" -i "{looped_wav}" '
                f'-filter_complex "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,'
                f'pan=mono|c0=0.5*c0+0.5*c1[mixm];'
                f'[mixm]pan=stereo|c0=c0|c1=c0[aout]" '
                f'-map 0:v -map "[aout]" -c:v copy -c:a aac -b:a 192k -ac 2 -ar 44100 '
                f'-movflags +faststart "{out_tmp}"'
            )
        shutil.copyfile(out_tmp, final_video_path)

    return final_video_path


def _force_dual_mono_audio(final_video_path):
    if not ffprobe_has_audio(final_video_path):
        return final_video_path
    with tempfile.TemporaryDirectory(prefix="dualmono_") as td:
        out_tmp = os.path.join(td, "final_dual_mono.mp4")
        run(
            f'ffmpeg -y -i "{final_video_path}" '
            f'-filter_complex "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,'
            f'pan=stereo|c0=c0|c1=c0[a0]" '
            f'-map 0:v -map "[a0]" -c:v copy -c:a aac -b:a 192k -ac 2 -ar 44100 '
            f'-movflags +faststart "{out_tmp}"'
        )
        shutil.copyfile(out_tmp, final_video_path)
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
        logger.error(proc.stderr.decode('utf-8', errors='ignore'))
        raise RuntimeError('ffmpeg command failed')
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


def concat_videos(video_files, out_path):
    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.txt') as f:
        for p in video_files:
            # escape single quotes
            f.write(f"file '{p.replace("'", "'\\''")}'\n")
        list_path = f.name
    cmd = f'ffmpeg -y -f concat -safe 0 -i "{list_path}" -c copy "{out_path}"'
    try:
        run(cmd)
    finally:
        try:
            os.unlink(list_path)
        except Exception:
            pass


def ensure_video_fps_size_and_length(src, dst, fps, width, height, target_duration):
    # Check if any transformation is needed
    src_fps = ffprobe_fps(src)
    src_w, src_h = ffprobe_size(src)
    dur = ffprobe_duration(src)
    
    needs_fps = abs(src_fps - fps) > 0.1
    needs_size = src_w != width or src_h != height
    needs_pad = target_duration - dur > 0.01
    
    if not needs_fps and not needs_size and not needs_pad:
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
    
    # Need full transformation (scale/fps/pad) - use high bitrate to preserve quality
    pad = max(0.0, target_duration - dur)
    pad_filter = f',tpad=stop_mode=clone:stop_duration={pad}' if pad > 0.001 else ''
    
    cmd = (
        f'ffmpeg -y -i "{src}" -vf "scale={width}:{height},fps={fps}{pad_filter}" '
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
):
    files = sorted(os.listdir(scene_dir))
    if video_files is None:
        videos = [os.path.join(scene_dir, f) for f in files if f.lower().endswith(VIDEO_EXTS)]
    else:
        videos = [os.path.abspath(v) for v in video_files if os.path.isfile(v)]
    all_audios = [os.path.join(scene_dir, f) for f in files if f.lower().endswith(AUDIO_EXTS)]

    meta_path = os.path.join(scene_dir, 'scene_meta.json')
    try:
        meta = json.load(open(meta_path, 'r', encoding='utf-8')) if os.path.exists(meta_path) else {}
    except Exception:
        meta = {}

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

    selected_audios = []
    if latest_speech:
        selected_audios.append(latest_speech)
    for snd_path in sound_vols.keys():
        if snd_path not in selected_audios:
            selected_audios.append(snd_path)
    audios = selected_audios

    video_durations = [ffprobe_duration(v) for v in videos]
    audio_durations = [ffprobe_duration(a) for a in audios]
    max_video_dur = max(video_durations) if video_durations else 0
    max_audio_dur = max(audio_durations) if audio_durations else 0
    target_dur = max(max_video_dur, max_audio_dur)
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
        target_fps = ffprobe_fps(base_video)
        target_w, target_h = ffprobe_size(base_video)
        if fps:
            target_fps = fps
        video_normalized = os.path.join(tmpdir, 'video_norm.mp4')
        ensure_video_fps_size_and_length(base_video, video_normalized, target_fps, target_w, target_h, target_dur)
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
    speech_keys = ('elevenlabs', 'edgetts', 'voice', 'tts')
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
    try:
        meta = json.load(open(os.path.join(scene_dir, 'scene_meta.json'), 'r', encoding='utf-8'))
        scene_title = meta.get('scene_title', '')
    except Exception:
        pass
    if out_path_override:
        out_path = str(out_path_override)
    else:
        safe_title = _safe_filename_segment(scene_title)
        out_name = f"Scene_{num}_{safe_title}.mp4"
        # Output directly to combined directory
        combined_dir = os.path.join(API_PRODUCTION, 'combined')
        os.makedirs(combined_dir, exist_ok=True)
        out_path = os.path.join(combined_dir, out_name)

    # Force stable audio timestamps and duration; this helps downstream transcoders (e.g., Clipchamp/WhatsApp)
    cmd = (
        f'ffmpeg -y -i "{video_normalized}" -i "{mixed_audio}" '
        f'-map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k '
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


def export_scene_video_to_combined(scene_dir):
    latest_video = _get_latest_scene_video(scene_dir)
    if not latest_video:
        logger.warning('No video found in %s, skipping export', scene_dir)
        return None

    scene_name = os.path.basename(scene_dir)
    num = scene_name.split('_')[-1]
    scene_title = ''
    try:
        meta = json.load(open(os.path.join(scene_dir, 'scene_meta.json'), 'r', encoding='utf-8'))
        scene_title = meta.get('scene_title', '')
    except Exception:
        pass

    safe_title = _safe_filename_segment(scene_title)
    out_name = f"Scene_{num}_{safe_title}.mp4"
    combined_dir = os.path.join(API_PRODUCTION, 'combined')
    os.makedirs(combined_dir, exist_ok=True)
    out_path = os.path.join(combined_dir, out_name)
    shutil.copyfile(latest_video, out_path)
    logger.info('Exported scene video: %s -> %s', latest_video, out_path)
    return out_path


def normalize_video(src, dst, fps, width, height):
    # Simple re-encode with standard settings
    cmd = (
        f'ffmpeg -y -i "{src}" -vf "scale={width}:{height},fps={fps}" '
        f'-c:v libx264 -preset fast -pix_fmt yuv420p -c:a aac -b:a 192k "{dst}"'
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


def merge_combined_videos(selected_scene_nums=None, music_file=None, music_volume=BACKGROUND_MUSIC_VOLUME):
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

    with tempfile.TemporaryDirectory(prefix='merge_') as td:
        # Master fps and size from first video
        master_fps = ffprobe_fps(videos[0])
        master_w, master_h = ffprobe_size(videos[0])
        cover_dir = os.path.join(API_PRODUCTION, 'cover')
        cover_src = _find_first_cover_image(cover_dir, td)
        cover_clip = None
        if cover_src:
            cover_clip = os.path.join(td, "cover_intro.mp4")
            _create_cover_clip(cover_src, cover_clip, master_fps, master_w, master_h)

        # Check if all videos already have same fps/resolution
        all_same = True
        for v in videos[1:]:
            if ffprobe_fps(v) != master_fps or ffprobe_size(v) != (master_w, master_h):
                all_same = False
                break
        # If cover intro exists, safest path is normalize+reencode merge.
        if cover_clip:
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
                f.write(f"file '{vp.replace("'", "'\\''")}'\n")

        final_out = os.path.join(combined_dir, 'combined_all.mp4')
        if all_same:
            run(
                f'ffmpeg -y -f concat -safe 0 -i "{list_path}" '
                f'-c copy -movflags +faststart "{final_out}"'
            )
        else:
            run(
                f'ffmpeg -y -f concat -safe 0 -i "{list_path}" '
                f'-c:v libx264 -preset fast -pix_fmt yuv420p '
                f'-c:a aac -b:a 192k -movflags +faststart "{final_out}"'
            )

    if music_file:
        _mix_background_music(final_out, music_file, music_volume)
    _force_dual_mono_audio(final_out)

    logger.info('Final merged video: %s', final_out)
    return final_out


def main(specific_scenes=None, speech_volume=1.0, no_final_merge=False, music_file=None, music_volume=BACKGROUND_MUSIC_VOLUME):
    if not os.path.exists(API_PRODUCTION):
        print('api_production folder not found:', API_PRODUCTION)
        return
    
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
            try:
                if os.path.exists(scene_meta_path):
                    with open(scene_meta_path, 'r', encoding='utf-8') as f:
                        scene_meta = json.load(f)
                        scene_type = str(scene_meta.get('scene_type', '') or '').strip().lower()
            except Exception:
                scene_type = ''

            # Keep s2v speech from generated video and mix only scene sounds.
            is_s2v = scene_type == 'wan22_s2v'
            compose_scene(
                scene_dir,
                speech_volume=0.0 if is_s2v else speech_volume,
                include_video_audio=is_s2v,
            )
        except Exception as e:
            logger.error('Failed to compose %s: %s', scene_dir, e)
    # After collecting, merge videos in combined (unless quick mode is requested)
    if no_final_merge:
        logger.info('Skip final merge because --no-final-merge is enabled.')
        return
    try:
        if specific_scenes:
            selected_nums = [scene.split('_')[-1] for scene in specific_scenes]
            merge_combined_videos(
                selected_scene_nums=selected_nums,
                music_file=music_file,
                music_volume=music_volume,
            )
        else:
            merge_combined_videos(
                music_file=music_file,
                music_volume=music_volume,
            )
    except Exception as e:
        logger.error('Failed to merge combined videos: %s', e)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compose videos and audio per scene')
    parser.add_argument('--scene', '-s', action='append', help='Scene to process (repeatable)')
    parser.add_argument('--speech-volume', type=float, default=1.0, help='Global multiplier for detected speech audio files (can be >1)')
    parser.add_argument('--no-final-merge', action='store_true', help='Only export scene videos to combined folder, skip combined_all.mp4 merge')
    parser.add_argument('--music-file', default='', help='Optional background music file path for final combined video')
    parser.add_argument('--music-volume', type=float, default=BACKGROUND_MUSIC_VOLUME, help='Background music volume in range 0.0 to 2.0')
    args = parser.parse_args()
    music_volume = max(0.0, min(2.0, float(args.music_volume)))
    main(
        specific_scenes=args.scene,
        speech_volume=args.speech_volume,
        no_final_merge=args.no_final_merge,
        music_file=str(args.music_file or '').strip() or None,
        music_volume=music_volume,
    )
