import argparse
import audioop
import os
import sys
import time
import wave
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from logging_config import setup_logging, get_logger, write_log
from scripts.server_config import get_server_address
from scripts.workflow_builders import load_json
from gemini.gemini_tts import (
    GEMINI_VOICE_NAME_BY_CHARACTER,
    process_scene as process_gemini_tts_scene,
    synthesize_with_fallbacks as synthesize_gemini_with_fallbacks,
)
from scripts.elevenlabs_tts import find_elevenlabs_key, process_scene as process_elevenlabs_tts_scene
from scripts.voice_profiles import (
    VOICE_PROVIDER_ELEVENLABS,
    VOICE_PROVIDER_GEMINI,
    resolve_scene_voice_key,
)
from scripts.project_settings import load_project_settings


setup_logging()
logger = get_logger(__name__)

POLL_INTERVAL = 3.0
POLL_TIMEOUT = 600


def _estimate_ratio_boundaries(total_frames: int, text_lengths: list[int]) -> list[int]:
    weights = [max(1, int(v)) for v in text_lengths]
    total_weight = sum(weights)
    if total_weight <= 0:
        return []
    boundaries = []
    cumulative = 0
    for idx in range(len(weights) - 1):
        cumulative += weights[idx]
        boundary = int(round((cumulative / total_weight) * total_frames))
        boundaries.append(max(1, min(total_frames - 1, boundary)))
    return boundaries


def _snap_boundaries_to_silence(
    pcm: bytes,
    channels: int,
    sample_width: int,
    frame_rate: int,
    total_frames: int,
    boundaries: list[int],
) -> list[int]:
    if not boundaries or total_frames <= 0:
        return boundaries
    bytes_per_frame = channels * sample_width
    win_frames = max(1, int(frame_rate * 0.08))  # 80 ms
    step_frames = max(1, int(frame_rate * 0.02))  # 20 ms
    search_frames = max(step_frames, int(frame_rate * 0.7))  # 700 ms around estimated boundary
    min_gap_frames = int(frame_rate * 0.35)  # keep at least 350 ms per segment

    snapped = []
    prev_boundary = 0
    for idx, est in enumerate(boundaries):
        lower_limit = prev_boundary + min_gap_frames
        upper_limit = total_frames - ((len(boundaries) - idx) * min_gap_frames)
        lo = max(lower_limit, est - search_frames)
        hi = min(upper_limit, est + search_frames)
        if lo >= hi:
            candidate = max(lower_limit, min(upper_limit, est))
            snapped.append(candidate)
            prev_boundary = candidate
            continue

        best_boundary = est
        best_rms = None
        pos = lo
        while pos <= hi:
            start = pos * bytes_per_frame
            end = min(len(pcm), (pos + win_frames) * bytes_per_frame)
            frag = pcm[start:end]
            if frag:
                try:
                    rms = audioop.rms(frag, sample_width)
                except Exception:
                    rms = None
                if rms is not None and (best_rms is None or rms < best_rms):
                    best_rms = rms
                    best_boundary = pos
            pos += step_frames

        best_boundary = max(lower_limit, min(upper_limit, best_boundary))
        snapped.append(best_boundary)
        prev_boundary = best_boundary

    return snapped


def _split_wav_by_ratio(in_wav_path: str, out_paths: list[str], text_lengths: list[int]):
    with wave.open(in_wav_path, "rb") as src:
        channels = src.getnchannels()
        sample_width = src.getsampwidth()
        frame_rate = src.getframerate()
        total_frames = src.getnframes()
        all_pcm = src.readframes(total_frames)

    if total_frames <= 0 or not out_paths:
        return False

    bytes_per_frame = channels * sample_width
    boundaries = _estimate_ratio_boundaries(total_frames, text_lengths)
    boundaries = _snap_boundaries_to_silence(
        pcm=all_pcm,
        channels=channels,
        sample_width=sample_width,
        frame_rate=frame_rate,
        total_frames=total_frames,
        boundaries=boundaries,
    )
    segment_edges = [0, *boundaries, total_frames]

    for idx, out_path in enumerate(out_paths):
        start_frame = segment_edges[idx]
        end_frame = segment_edges[idx + 1]
        start_byte = max(0, start_frame * bytes_per_frame)
        end_byte = min(len(all_pcm), end_frame * bytes_per_frame)
        chunk_pcm = all_pcm[start_byte:end_byte]
        chunk_pcm = _trim_segment_silence(
            chunk_pcm,
            channels=channels,
            sample_width=sample_width,
            frame_rate=frame_rate,
            threshold_rms=260,
            window_ms=20,
            keep_pad_ms=40,
        )
        chunk_pcm = _snap_end_to_zero_crossing(
            chunk_pcm,
            channels=channels,
            sample_width=sample_width,
            frame_rate=frame_rate,
            search_ms=30,
        )
        chunk_pcm = _apply_fade_out(
            chunk_pcm,
            channels=channels,
            sample_width=sample_width,
            frame_rate=frame_rate,
            fade_ms=24,
            tail_silence_ms=80,
        )

        with wave.open(out_path, "wb") as dst:
            dst.setnchannels(channels)
            dst.setsampwidth(sample_width)
            dst.setframerate(frame_rate)
            dst.writeframes(chunk_pcm)
    return True


def _find_silence_runs(
    pcm: bytes,
    channels: int,
    sample_width: int,
    frame_rate: int,
    threshold_rms: int = 260,
    window_ms: int = 20,
):
    bytes_per_frame = channels * sample_width
    win_frames = max(1, int(frame_rate * (window_ms / 1000.0)))
    total_frames = len(pcm) // bytes_per_frame
    runs = []
    in_run = False
    run_start = 0
    pos = 0
    while pos < total_frames:
        start = pos * bytes_per_frame
        end = min(len(pcm), (pos + win_frames) * bytes_per_frame)
        frag = pcm[start:end]
        if not frag:
            break
        try:
            rms = audioop.rms(frag, sample_width)
        except Exception:
            rms = 10**9
        is_silent = rms <= threshold_rms
        if is_silent and not in_run:
            in_run = True
            run_start = pos
        elif not is_silent and in_run:
            in_run = False
            runs.append((run_start, pos))
        pos += win_frames
    if in_run:
        runs.append((run_start, total_frames))
    return runs


def _trim_segment_silence(
    segment_pcm: bytes,
    channels: int,
    sample_width: int,
    frame_rate: int,
    threshold_rms: int = 260,
    window_ms: int = 20,
    keep_pad_ms: int = 60,
):
    bytes_per_frame = channels * sample_width
    win_frames = max(1, int(frame_rate * (window_ms / 1000.0)))
    keep_pad_frames = max(0, int(frame_rate * (keep_pad_ms / 1000.0)))
    total_frames = len(segment_pcm) // bytes_per_frame
    if total_frames <= 0:
        return segment_pcm

    first_voice = 0
    last_voice = total_frames

    pos = 0
    while pos < total_frames:
        start = pos * bytes_per_frame
        end = min(len(segment_pcm), (pos + win_frames) * bytes_per_frame)
        frag = segment_pcm[start:end]
        if not frag:
            break
        try:
            rms = audioop.rms(frag, sample_width)
        except Exception:
            rms = 0
        if rms > threshold_rms:
            first_voice = pos
            break
        pos += win_frames

    pos = total_frames
    while pos > 0:
        s = max(0, pos - win_frames)
        start = s * bytes_per_frame
        end = min(len(segment_pcm), pos * bytes_per_frame)
        frag = segment_pcm[start:end]
        if not frag:
            break
        try:
            rms = audioop.rms(frag, sample_width)
        except Exception:
            rms = 0
        if rms > threshold_rms:
            last_voice = pos
            break
        pos -= win_frames

    first_voice = max(0, first_voice - keep_pad_frames)
    last_voice = min(total_frames, last_voice + keep_pad_frames)
    if last_voice <= first_voice:
        return segment_pcm
    return segment_pcm[first_voice * bytes_per_frame:last_voice * bytes_per_frame]


def _snap_end_to_zero_crossing(
    pcm: bytes,
    channels: int,
    sample_width: int,
    frame_rate: int,
    search_ms: int = 30,
):
    if sample_width != 2 or channels <= 0:
        return pcm
    bytes_per_frame = channels * sample_width
    total_frames = len(pcm) // bytes_per_frame
    if total_frames <= 2:
        return pcm

    search_frames = max(1, int(frame_rate * (search_ms / 1000.0)))
    start_frame = max(1, total_frames - search_frames)
    best_cut_frame = total_frames
    min_abs_val = None

    for f in range(start_frame, total_frames):
        byte_pos = f * bytes_per_frame
        sample_bytes = pcm[byte_pos:byte_pos + 2]
        if len(sample_bytes) < 2:
            continue
        sample_val = int.from_bytes(sample_bytes, byteorder="little", signed=True)
        abs_val = abs(sample_val)
        if min_abs_val is None or abs_val < min_abs_val:
            min_abs_val = abs_val
            best_cut_frame = f
            if abs_val == 0:
                break

    cut_bytes = max(bytes_per_frame, min(len(pcm), best_cut_frame * bytes_per_frame))
    return pcm[:cut_bytes]


def _apply_fade_out(
    pcm: bytes,
    channels: int,
    sample_width: int,
    frame_rate: int,
    fade_ms: int = 12,
    tail_silence_ms: int = 60,
):
    if sample_width != 2 or channels <= 0:
        return pcm
    bytes_per_frame = channels * sample_width
    total_frames = len(pcm) // bytes_per_frame
    if total_frames <= 2:
        return pcm

    fade_frames = max(1, int(frame_rate * (fade_ms / 1000.0)))
    fade_frames = min(fade_frames, total_frames - 1)
    if fade_frames <= 0:
        return pcm

    out = bytearray(pcm)
    start_fade = total_frames - fade_frames
    for i in range(fade_frames):
        frame_idx = start_fade + i
        gain = 0.0 if fade_frames <= 1 else (fade_frames - 1 - i) / (fade_frames - 1)
        frame_offset = frame_idx * bytes_per_frame
        for ch in range(channels):
            s_off = frame_offset + (ch * sample_width)
            sample_val = int.from_bytes(out[s_off:s_off + 2], byteorder="little", signed=True)
            scaled = int(round(sample_val * gain))
            if scaled > 32767:
                scaled = 32767
            elif scaled < -32768:
                scaled = -32768
            out[s_off:s_off + 2] = int(scaled).to_bytes(2, byteorder="little", signed=True)

    silence_frames = max(0, int(frame_rate * (tail_silence_ms / 1000.0)))
    if silence_frames:
        out.extend(b"\x00" * silence_frames * bytes_per_frame)
    return bytes(out)


def _split_wav_by_long_silence(
    in_wav_path: str,
    out_paths: list[str],
    text_lengths: list[int] | None = None,
    expected_pause_seconds: float = 3.0,
):
    with wave.open(in_wav_path, "rb") as src:
        channels = src.getnchannels()
        sample_width = src.getsampwidth()
        frame_rate = src.getframerate()
        total_frames = src.getnframes()
        all_pcm = src.readframes(total_frames)

    if total_frames <= 0 or not out_paths:
        return False

    need_boundaries = len(out_paths) - 1
    if need_boundaries <= 0:
        need_boundaries = 0

    silence_runs = _find_silence_runs(
        pcm=all_pcm,
        channels=channels,
        sample_width=sample_width,
        frame_rate=frame_rate,
        threshold_rms=260,
        window_ms=20,
    )

    min_pause_frames = int(frame_rate * max(2.2, expected_pause_seconds * 0.72))
    eligible = []
    for s, e in silence_runs:
        dur = e - s
        if dur >= min_pause_frames:
            center = (s + e) // 2
            eligible.append((s, e, dur, center))

    if len(eligible) < need_boundaries:
        return False

    boundaries = []
    if need_boundaries > 0:
        # Prioritize the longest silence runs first (the inserted scene separators
        # should be the most dominant silences), then map to expected boundaries.
        strongest = sorted(eligible, key=lambda item: item[2], reverse=True)[:need_boundaries]
        strongest = sorted(strongest, key=lambda item: item[3])

        if text_lengths and len(text_lengths) == len(out_paths):
            ratio_targets = _estimate_ratio_boundaries(total_frames, text_lengths)
            chosen = []
            remaining = strongest[:]
            for target in ratio_targets[:need_boundaries]:
                best_idx = None
                best_dist = None
                for idx, item in enumerate(remaining):
                    center = item[3]
                    dist = abs(center - target)
                    if best_dist is None or dist < best_dist:
                        best_dist = dist
                        best_idx = idx
                if best_idx is None:
                    return False
                chosen.append(remaining.pop(best_idx))
            boundaries = sorted([item[3] for item in chosen])
        else:
            boundaries = [item[3] for item in strongest]

    bytes_per_frame = channels * sample_width
    edges = [0, *boundaries, total_frames]
    for idx, out_path in enumerate(out_paths):
        start_frame = edges[idx]
        end_frame = edges[idx + 1]
        start_byte = max(0, start_frame * bytes_per_frame)
        end_byte = min(len(all_pcm), end_frame * bytes_per_frame)
        chunk_pcm = all_pcm[start_byte:end_byte]
        chunk_pcm = _trim_segment_silence(
            chunk_pcm,
            channels=channels,
            sample_width=sample_width,
            frame_rate=frame_rate,
            threshold_rms=260,
            window_ms=20,
            keep_pad_ms=60,
        )
        chunk_pcm = _snap_end_to_zero_crossing(
            chunk_pcm,
            channels=channels,
            sample_width=sample_width,
            frame_rate=frame_rate,
            search_ms=30,
        )
        chunk_pcm = _apply_fade_out(
            chunk_pcm,
            channels=channels,
            sample_width=sample_width,
            frame_rate=frame_rate,
            fade_ms=24,
            tail_silence_ms=80,
        )
        with wave.open(out_path, "wb") as dst:
            dst.setnchannels(channels)
            dst.setsampwidth(sample_width)
            dst.setframerate(frame_rate)
            dst.writeframes(chunk_pcm)
    return True


def _generate_and_split_gemini_scene_group(project_dir: str, voice_key: str, scene_items: list[dict], logger_obj):
    if not scene_items:
        return True

    if len(scene_items) == 1:
        item = scene_items[0]
        return process_gemini_tts_scene(item["scene_dir"], logger=logger_obj, write_log=write_log)

    voice_name = GEMINI_VOICE_NAME_BY_CHARACTER.get(voice_key, "Kore")
    combined_parts = []
    separator_text = "SCENEBREAKTOKEN"
    preamble = (
        "Bacakan seluruh transcript sampai selesai tanpa berhenti di tengah. "
        "Setiap kali menemukan token SCENEBREAKTOKEN, diam selama kira-kira 3 detik, "
        "jangan ucapkan tokennya, lalu lanjutkan ke bagian berikutnya."
    )
    for idx, item in enumerate(scene_items, start=1):
        combined_parts.append(item["text"])
        if idx < len(scene_items):
            combined_parts.append(separator_text)
    combined_text = preamble + "\n\n" + "\n\n".join(combined_parts)

    try:
        audio_bytes = synthesize_gemini_with_fallbacks(
            combined_text,
            voice_key,
            voice_name,
            logger=logger_obj,
            write_log=write_log,
        )
    except Exception as e:
        write_log(f"Gemini TTS gabungan gagal untuk voice `{voice_key}`: {e}", level="error")
        if logger_obj:
            logger_obj.error("Gemini combined TTS failed for %s: %s", voice_key, e)
        return False
    if not audio_bytes:
        write_log(f"Gemini TTS gabungan voice `{voice_key}` mengembalikan audio kosong.", level="error")
        return False

    combined_dir = os.path.join(project_dir, "voice_combined")
    os.makedirs(combined_dir, exist_ok=True)
    timestamp = int(time.time())
    tmp_wav = os.path.join(combined_dir, f"speech_gemini_combined_{voice_key}_{timestamp}.wav")
    try:
        with wave.open(tmp_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(audio_bytes)
    except Exception as e:
        write_log(f"Gagal menyimpan audio gabungan Gemini voice `{voice_key}`: {e}", level="error")
        return False

    out_paths = [
        os.path.join(item["scene_dir"], f"speech_gemini_tts_{timestamp}.wav")
        for item in scene_items
    ]
    lengths = [len(item["text"]) for item in scene_items]

    ok = False
    try:
        ok = _split_wav_by_long_silence(
            tmp_wav,
            out_paths,
            text_lengths=lengths,
            expected_pause_seconds=3.0,
        )
        if not ok:
            write_log(
                f"Deteksi jeda panjang gagal untuk voice `{voice_key}`, batalkan mode konsisten dan fallback ke mode per-scene.",
                level="warning",
            )
            return False
    finally:
        pass

    if not ok:
        write_log(f"Gagal membagi audio Gemini gabungan voice `{voice_key}` ke tiap scene.", level="error")
        return False

    for item, out_path in zip(scene_items, out_paths):
        write_log(f"Gemini konsisten voice `{voice_key}`: voice scene {item['scene']} tersimpan di {out_path}")
    write_log(f"Gemini konsisten voice `{voice_key}`: audio gabungan tersimpan di {tmp_wav}")
    return True


def _process_gemini_all_scenes_consistent(project_dir: str, scenes: list[str], logger_obj):
    scene_items = []
    for scene in scenes:
        scene_dir = os.path.join(project_dir, scene)
        meta_path = os.path.join(scene_dir, "scene_meta.json")
        if not os.path.exists(meta_path):
            continue
        try:
            meta = load_json(meta_path)
        except Exception as e:
            write_log(f"Gagal membaca {meta_path}: {e}")
            continue
        text = str(meta.get("voice_text", "")).strip()
        if not text:
            continue
        voice_key = resolve_scene_voice_key(meta)
        scene_items.append({
            "scene": scene,
            "scene_dir": scene_dir,
            "text": text,
            "voice_key": voice_key,
        })

    if not scene_items:
        write_log("Mode Gemini konsisten: tidak ada scene dengan voice_text untuk diproses.", level="error")
        return False

    grouped_items = {}
    for item in scene_items:
        grouped_items.setdefault(item["voice_key"], []).append(item)

    write_log(
        "Mode Gemini konsisten: memproses batch per voice_character: "
        + ", ".join(f"{key}={len(items)} scene" for key, items in grouped_items.items())
    )

    for voice_key, items in grouped_items.items():
        ok = _generate_and_split_gemini_scene_group(project_dir, voice_key, items, logger_obj)
        if not ok:
            return False
    return True


def _scene_sort_key(name: str):
    if not str(name).startswith("scene_"):
        return (10**9, str(name))
    try:
        return (int(str(name).split("_", 1)[1]), str(name))
    except Exception:
        return (10**9, str(name))


def main(project_name, specific_scenes=None, comfyui_server=None):
    project_dir = os.path.join(ROOT, "api_production", str(project_name).strip())
    if not os.path.exists(project_dir):
        print("Project folder not found:", project_dir)
        return 1
    try:
        project_settings = load_project_settings(Path(project_dir))
    except Exception as e:
        write_log(f"Gagal membaca project_settings.json: {e}", level="error")
        return 1
    voice_cfg = project_settings.get("voice", {}) if isinstance(project_settings, dict) else {}
    voice_provider = str(voice_cfg.get("voice_provider", VOICE_PROVIDER_GEMINI)).strip().lower()
    elevenlabs_key = None
    if voice_provider == VOICE_PROVIDER_ELEVENLABS:
        elevenlabs_key = find_elevenlabs_key()
        if not elevenlabs_key:
            write_log("Mode voice project adalah ElevenLabs, tetapi ELEVENLABSKEY tidak ditemukan di keys.cfg.", level="error")
            return 1

    scenes = sorted([d for d in os.listdir(project_dir) if d.startswith("scene_")], key=_scene_sort_key)
    if specific_scenes:
        scenes = [s for s in scenes if s in specific_scenes]
    if not scenes:
        write_log("Tidak ada scene yang cocok untuk diproses.")
        return 1

    had_error = False
    processed_count = 0

    if voice_provider == VOICE_PROVIDER_GEMINI and not specific_scenes and len(scenes) > 1:
        print("Processing all scenes with Gemini consistent mode")
        ok = _process_gemini_all_scenes_consistent(project_dir, scenes, logger)
        if ok:
            return 0
        write_log("Fallback ke mode per-scene karena mode Gemini konsisten gagal.", level="warning")

    for scene in scenes:
        scene_dir = os.path.join(project_dir, scene)
        meta_path = os.path.join(scene_dir, "scene_meta.json")
        if not os.path.exists(meta_path):
            logger.debug("No scene_meta.json in %s", scene_dir)
            continue
        try:
            meta = load_json(meta_path)
        except Exception as e:
            write_log(f"Gagal membaca {meta_path}: {e}")
            had_error = True
            continue

        print("Processing", scene_dir)
        processed_count += 1
        if voice_provider == VOICE_PROVIDER_ELEVENLABS:
            ok = process_elevenlabs_tts_scene(scene_dir, api_key=elevenlabs_key, logger=logger, write_log=write_log)
            if not ok:
                write_log(f"Gagal membuat voice ElevenLabs untuk {scene}.")
                had_error = True
        else:
            ok = process_gemini_tts_scene(scene_dir, logger=logger, write_log=write_log)
            if not ok:
                write_log(f"Gagal membuat voice Gemini TTS untuk {scene}.")
                had_error = True

    if processed_count == 0:
        write_log("Tidak ada scene yang bisa diproses untuk Gemini TTS.")
        return 1
    return 1 if had_error else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate voice untuk scene berdasarkan provider voice global project")
    parser.add_argument("--project", "-p", required=True, help="Nama project di dalam folder api_production")
    parser.add_argument("--scene", "-s", action="append", help="Scene yang diproses (repeatable)")
    parser.add_argument("--server", default=get_server_address("comfyui"), help="Argumen kompatibilitas lama (tidak dipakai).")
    args = parser.parse_args()
    sys.exit(main(project_name=args.project, specific_scenes=args.scene, comfyui_server=args.server))
