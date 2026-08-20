import argparse
import copy
import os
import json
import time
import tempfile
from pathlib import Path
from datetime import datetime
import sys

# Ensure project root is on sys.path so local modules are importable
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import glob
import math
import imageio
from PIL import Image

from scripts import comfyui_api
from scripts.runtime_service_controller import RuntimeServiceController, project_uses_llama
from scripts.server_config import get_server_address
from scripts.timeout_config import COMFYUI_WORKFLOW_TIMEOUT_SECONDS, COMFYUI_POLL_INTERVAL_SECONDS
from scripts.workflow_builders import load_json
from z_image.z_image import (
    build_z_image_workflow,
    get_model_display_name as get_image_model_display_name,
    get_model_key as get_image_model_key,
    send_workflow as send_z_image_workflow,
)
from gemini.gemini_image import MODEL_GEMINI_IMAGE, generate_scene_image, is_gemini_prompt
from wan22_i2v.wan22_i2v import (
    DEFAULT_PROMPT as DEFAULT_WAN_PROMPT,
    build_wan_workflow,
    send_workflow as send_wan_workflow,
)
from wan22_t2v.wan22_t2v import (
    DEFAULT_PROMPT as DEFAULT_WAN22_T2V_PROMPT,
    build_wan_t2v_workflow,
    resolve_wan22_i2v_duration,
    send_workflow as send_wan22_t2v_workflow,
)
from wan22_s2v.wan22_s2v import (
    DEFAULT_PROMPT as DEFAULT_WAN22_S2V_PROMPT,
    MAX_AUDIO_DURATION as WAN22_S2V_MAX_AUDIO_DURATION,
    build_wan22_s2v_workflow,
    get_audio_duration as get_s2v_audio_duration,
    send_workflow as send_s2v_workflow,
    trim_video_to_speech_duration,
)
from minimax_h3_t2v.minimax_h3_t2v import (
    DEFAULT_PROMPT as DEFAULT_MINIMAX_H3_T2V_PROMPT,
    build_minimax_h3_t2v_workflow,
    send_workflow as send_minimax_h3_t2v_workflow,
)
from minimax_h3_i2v.minimax_h3_i2v import (
    DEFAULT_PROMPT as DEFAULT_MINIMAX_H3_I2V_PROMPT,
    build_minimax_h3_i2v_workflow,
    send_workflow as send_minimax_h3_i2v_workflow,
)
from minimax_h3_r2v.minimax_h3_r2v import (
    DEFAULT_PROMPT as DEFAULT_MINIMAX_H3_S2V_PROMPT,
    DEFAULT_R2V_PROMPT as DEFAULT_MINIMAX_H3_R2V_PROMPT,
    MAX_AUDIO_DURATION as MINIMAX_H3_S2V_MAX_AUDIO_DURATION,
    MAX_DURATION as MINIMAX_H3_R2V_MAX_DURATION,
    build_minimax_h3_r2v_workflow,
    send_workflow as send_minimax_h3_s2v_workflow,
)
from logging_config import setup_logging, get_logger, write_log, RUN_ID
from scripts.generate_caption import apply_caption_to_video
from scripts.generate_compose import (
    COMFY_AUDIO_SOURCE_DIRNAME,
    COMFY_AUDIO_SOURCE_FILENAME,
    compose_scene,
    ffprobe_duration,
    ffprobe_fps,
    ffprobe_has_audio,
    ffprobe_size,
    run as run_ffmpeg,
)
from scripts.generate_web_scroll_video import generate_web_scroll_video
from scripts.generate_image_pan_video import generate_image_pan_video
from scripts.generate_image_zoom_video import generate_image_zoom_video
from prompt_localization import (
    LORA_TRIGGER_WORDS_FIELD,
    prepare_prompt_payload_for_save,
    prepend_lora_trigger_words,
    read_json_for_runtime,
    resolve_prompt_payload_for_runtime,
    prepare_project_prompts_for_runtime,
)
from scripts.project_settings import load_project_settings


API_PRODUCTION_ROOT = os.path.join(os.path.dirname(__file__), 'api_production')
LOG_FILE = os.path.join(os.path.dirname(__file__), 'content_creation.log')
POLL_INTERVAL = COMFYUI_POLL_INTERVAL_SECONDS
I2V_FPS = 16
WEB_SCROLL_FPS = 16
DEFAULT_WEB_SCROLL_PROMPT = {
    "url": "",
    "width": 368,
    "height": 640,
    "duration_seconds": 5.0,
    "speed": 1,
}
DEFAULT_IMAGE_PAN_PROMPT = {
    "width": 480,
    "height": 848,
    "direction": "from_right",
}
DEFAULT_IMAGE_ZOOM_PROMPT = {
    "width": 480,
    "height": 848,
    "zoom_direction": "in",
    "focal_point": "center",
    "zoom_strength": 1.3,
}
DEFAULT_WAN22_T2V_BATCH_EXTRA_PROMPTS = {
    "groups": [
        {"positive_prompt": "", "negative_prompt": ""},
        {"positive_prompt": "", "negative_prompt": ""},
        {"positive_prompt": "", "negative_prompt": ""},
    ],
}

# initialize logging for the process (idempotent)
setup_logging()
logger = get_logger(__name__)


def _scene_sort_key(name: str):
    if not str(name).startswith("scene_"):
        return (10**9, str(name))
    try:
        return (int(str(name).split("_", 1)[1]), str(name))
    except Exception:
        return (10**9, str(name))


def _read_scene_json(scene_dir, filename, required=False):
    path = os.path.join(scene_dir, filename)
    try:
        return read_json_for_runtime(path, required=required, log_fn=write_log)
    except FileNotFoundError:
        raise
    except Exception as e:
        if filename in {
            'minimax_h3_t2v_prompt.json',
            'minimax_h3_i2v_prompt.json',
            'minimax_h3_s2v_prompt.json',
            'minimax_h3_r2v_prompt.json',
        }:
            # MiniMax must never run with stale English or untranslated
            # fallback text. A runtime translation/validation failure is a
            # hard scene failure and must reach the caller.
            write_log(f"MiniMax prompt runtime validation/translation failed for {path}: {e}", level="error")
            raise RuntimeError(f"MiniMax prompt gagal divalidasi/diterjemahkan: {filename}") from e
        write_log(f"Prompt localization runtime fallback untuk {path}: {e}", level="warning")
        if required:
            # fallback to non-translated prompt text so runtime can still continue
            if not os.path.exists(path):
                raise
            raw_data = load_json(path)
            resolved, _, _ = resolve_prompt_payload_for_runtime(
                filename,
                raw_data,
                translate_fn=lambda text: text,
                log_fn=write_log,
            )
            return resolved
        if not os.path.exists(path):
            return {}
        raw_data = load_json(path)
        resolved, _, _ = resolve_prompt_payload_for_runtime(
            filename,
            raw_data,
            translate_fn=lambda text: text,
            log_fn=write_log,
        )
        return resolved


def _ensure_scene_json(scene_dir, filename, default_data):
    path = os.path.join(scene_dir, filename)
    if os.path.exists(path):
        return
    try:
        payload = prepare_prompt_payload_for_save(filename, default_data, existing_data=None)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        write_log(f"{filename} tidak ditemukan di {scene_dir}; dibuat otomatis dari default.")
    except Exception as e:
        write_log(f"Gagal membuat default {filename} di {scene_dir}: {e}", level="error")


def _extract_last_frame_image(video_path: str, output_path: str):
    reader = imageio.get_reader(video_path)
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
    Image.fromarray(last_frame).convert("RGB").save(output_path)
    return output_path


def _concat_video_segments(segment_paths: list[str], output_path: str, *, preserve_audio: bool = False):
    valid_segments = [str(path) for path in segment_paths if str(path or "").strip() and os.path.exists(path)]
    if len(valid_segments) < 2:
        raise RuntimeError("Minimal dua video diperlukan untuk concat.")

    base_fps = max(1, int(round(float(ffprobe_fps(valid_segments[0])))))
    base_width, base_height = ffprobe_size(valid_segments[0])

    with tempfile.TemporaryDirectory(prefix="wan22_concat_") as td:
        normalized_paths = []
        for idx, src in enumerate(valid_segments):
            dst = os.path.join(td, f"norm_{idx:02d}.mp4")
            if preserve_audio and ffprobe_has_audio(src):
                run_ffmpeg(
                    f'ffmpeg -y -i "{src}" '
                    f'-map 0:v:0 -map 0:a:0 '
                    f'-vf "scale={base_width}:{base_height},fps={base_fps}" '
                    f'-af "aresample=44100:async=1:first_pts=0,'
                    f'aformat=sample_rates=44100:channel_layouts=stereo" '
                    f'-c:v libx264 -preset fast -pix_fmt yuv420p '
                    f'-c:a aac -b:a 192k -ac 2 -ar 44100 "{dst}"'
                )
            elif preserve_audio:
                segment_duration = max(0.1, ffprobe_duration(src))
                run_ffmpeg(
                    f'ffmpeg -y -i "{src}" '
                    f'-f lavfi -t {segment_duration:.6f} '
                    f'-i anullsrc=channel_layout=stereo:sample_rate=44100 '
                    f'-map 0:v:0 -map 1:a:0 '
                    f'-vf "scale={base_width}:{base_height},fps={base_fps}" '
                    f'-c:v libx264 -preset fast -pix_fmt yuv420p '
                    f'-c:a aac -b:a 192k -ac 2 -ar 44100 -shortest "{dst}"'
                )
            else:
                run_ffmpeg(
                    f'ffmpeg -y -i "{src}" '
                    f'-vf "scale={base_width}:{base_height},fps={base_fps}" '
                    f'-an -c:v libx264 -preset fast -pix_fmt yuv420p "{dst}"'
                )
            normalized_paths.append(dst)

        if preserve_audio:
            inputs = " ".join(f'-i "{path}"' for path in normalized_paths)
            streams = "".join(
                f'[{index}:v:0][{index}:a:0]'
                for index in range(len(normalized_paths))
            )
            run_ffmpeg(
                f'ffmpeg -y {inputs} '
                f'-filter_complex "{streams}concat=n={len(normalized_paths)}:v=1:a=1[v][a]" '
                f'-map "[v]" -map "[a]" '
                f'-c:v libx264 -preset fast -pix_fmt yuv420p '
                f'-c:a aac -b:a 192k -ac 2 -ar 44100 "{output_path}"'
            )
            return output_path

        list_path = os.path.join(td, "concat_list.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for path in normalized_paths:
                escaped = path.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        try:
            run_ffmpeg(f'ffmpeg -y -f concat -safe 0 -i "{list_path}" -c copy -an "{output_path}"')
        except Exception:
            run_ffmpeg(
                f'ffmpeg -y -f concat -safe 0 -i "{list_path}" '
                f'-c:v libx264 -preset fast -pix_fmt yuv420p -an "{output_path}"'
            )
    return output_path


def _remove_video_audio(video_path: str) -> str:
    """Remove every audio stream from a downloaded ComfyUI video in place."""
    video_path = str(video_path)
    if not os.path.isfile(video_path):
        raise FileNotFoundError(video_path)
    if not ffprobe_has_audio(video_path):
        write_log(f"No embedded audio to remove from {video_path}")
        return video_path

    root, extension = os.path.splitext(video_path)
    temp_path = f"{root}.__remove_sound_tmp__{extension or '.mp4'}"
    try:
        try:
            run_ffmpeg(
                f'ffmpeg -y -i "{video_path}" -map 0:v:0 -an '
                f'-c:v copy -movflags +faststart "{temp_path}"'
            )
        except Exception:
            # Some containers do not support stream-copying with the original
            # muxer. Re-encode video while still guaranteeing no audio stream.
            run_ffmpeg(
                f'ffmpeg -y -i "{video_path}" -map 0:v:0 -an '
                f'-c:v libx264 -preset fast -pix_fmt yuv420p "{temp_path}"'
            )
        if not os.path.isfile(temp_path) or os.path.getsize(temp_path) <= 0:
            raise RuntimeError(f"Audio removal output missing or empty: {temp_path}")
        os.replace(temp_path, video_path)
        if ffprobe_has_audio(video_path):
            raise RuntimeError(f"Audio stream still present after removal: {video_path}")
        write_log(f"Removed embedded ComfyUI audio from downloaded video: {video_path}")
        return video_path
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _invalidate_comfy_audio_source(scene_dir: str):
    """Invalidate a cached Compose audio master after a new video download."""
    source_path = os.path.join(
        str(scene_dir),
        COMFY_AUDIO_SOURCE_DIRNAME,
        COMFY_AUDIO_SOURCE_FILENAME,
    )
    if os.path.isfile(source_path):
        try:
            os.remove(source_path)
            write_log(f"Invalidated stale ComfyUI audio source: {source_path}")
        except OSError as e:
            raise RuntimeError(f"Failed to invalidate ComfyUI audio source: {source_path}: {e}")



def process_scene(scene_dir, server, project_generate_caption=True):
    """Process a single scene directory.

    Steps:
    1. Send `z_image_api.json` to ComfyUI and wait for an image output.
    2. Download the image, upload it back to the server for WAN workflow.
    3. Send WAN workflow and optionally wait/download video output.

    Returns True on success, False on failure.
    """
    # Load scene metadata to decide processing branch
    try:
        scene_meta = _read_scene_json(scene_dir, 'scene_meta.json', required=False)
    except Exception as e:
        write_log(f"Failed to read scene_meta.json for {scene_dir}: {e}")
        return False

    scene_type = scene_meta.get('scene_type', 'wan22_i2v')

    def _safe_error_text(err):
        text = str(err)
        # Keep logs single-line and console-safe on cp1252 terminals.
        text = " ".join(text.splitlines()).strip()
        return text.encode("cp1252", errors="replace").decode("cp1252")

    def _apply_caption_if_enabled(video_path):
        if not bool(project_generate_caption):
            return True
        try:
            return apply_caption_to_video(Path(scene_dir), Path(video_path), overwrite=True)
        except Exception as e:
            write_log(f"Failed to apply caption for {scene_dir}: {e}")
            return False

    def _finalize_scene_success(
        video_path,
        *,
        is_s2v=False,
        preserve_comfy_audio=False,
        compose_audio=True,
        success_message=None,
    ):
        if compose_audio and not _mix_scene_audio_to_video(
            video_path,
            is_s2v=is_s2v,
            preserve_comfy_audio=preserve_comfy_audio,
        ):
            return False
        # The four audio/video scene types below are fully mixed here.  Keep a
        # durable marker so the later project-level compose step can preserve
        # this audio instead of mixing the same scene files a second time.
        if compose_audio and scene_type in {
            'wan22',
            'wan22_i2v',
            'wan22_t2v_i2v',
            'wan22_t2v',
            'minimax-h3_i2v',
            'minimax-h3_t2v_i2v',
        }:
            try:
                meta_path = os.path.join(scene_dir, 'scene_meta.json')
                with open(meta_path, 'r', encoding='utf-8') as meta_file:
                    current_meta = json.load(meta_file)
                current_meta['audio_composed'] = True
                current_meta['audio_composed_video'] = os.path.basename(video_path)
                current_meta['audio_composed_components'] = [
                    'comfyui_audio_if_preserved',
                    'scene_voice',
                    'scene_sound_effect',
                ]
                temp_meta_path = f'{meta_path}.__audio_composed_tmp__'
                with open(temp_meta_path, 'w', encoding='utf-8') as meta_file:
                    json.dump(current_meta, meta_file, ensure_ascii=False, indent=2)
                    meta_file.write('\n')
                os.replace(temp_meta_path, meta_path)
            except Exception as e:
                write_log(f"Failed to mark composed scene audio for {scene_dir}: {e}")
                return False
        if not _apply_caption_if_enabled(video_path):
            return False
        if success_message:
            write_log(success_message)
        return True

    def _mix_scene_audio_to_video(video_path, is_s2v=False, preserve_comfy_audio=False):
        # Mix using the exact compose-scene pipeline, but target only this generated video.
        # S2V keeps embedded speech and excludes standalone speech. MiniMax H3
        # T2V/I2V keeps embedded ComfyUI audio and also includes scene speech.
        tmp_out = os.path.join(scene_dir, "__scene_mix_tmp__.mp4")
        if os.path.exists(tmp_out):
            try:
                os.remove(tmp_out)
            except OSError:
                pass
        try:
            compose_scene(
                scene_dir,
                fps=None,
                speech_volume=0.0 if is_s2v else 1.0,
                video_files=[video_path],
                out_path_override=tmp_out,
                include_video_audio=is_s2v or preserve_comfy_audio,
                include_scene_speech=(not is_s2v),
            )
            if not os.path.exists(tmp_out) or os.path.getsize(tmp_out) <= 0:
                write_log(f"Mixed scene output missing or empty: {tmp_out}")
                return False
            os.replace(tmp_out, video_path)
            return True
        except Exception as e:
            write_log(f"Failed to mix scene audio for {scene_dir}: {e}")
            return False
        finally:
            if os.path.exists(tmp_out):
                try:
                    os.remove(tmp_out)
                except OSError:
                    pass

    def _find_images(sd):
        patterns = ['*.png', '*.jpg', '*.jpeg', '*.webp']
        imgs = []
        # search root folder only
        for p in patterns:
            imgs.extend(glob.glob(os.path.join(sd, p)))
        # normalize and sort
        imgs = sorted(list({os.path.abspath(i): i for i in imgs}.values()))
        return imgs

    def _find_latest_root_image(sd):
        patterns = ['*.png', '*.jpg', '*.jpeg', '*.webp']
        imgs = []
        for p in patterns:
            imgs.extend(glob.glob(os.path.join(sd, p)))
        imgs = [os.path.abspath(i) for i in imgs if os.path.isfile(i)]
        if not imgs:
            return None
        imgs.sort(key=lambda path: os.path.getmtime(path), reverse=True)
        return imgs[0]

    def _find_latest_root_speech(sd):
        patterns = ['speech_*.mp3', 'speech_*.wav', 'speech_*.m4a', 'speech_*.aac', 'speech_*.flac', 'speech_*.ogg']
        items = []
        for p in patterns:
            items.extend(glob.glob(os.path.join(sd, p)))
        items = [os.path.abspath(i) for i in items if os.path.isfile(i)]
        if not items:
            return None
        items.sort(key=lambda path: os.path.getmtime(path), reverse=True)
        return items[0]

    def _upload_to_comfy(path):
        try:
            upload_info = comfyui_api.upload_file(server, path)
            write_log(f"Upload response for {path}: {json.dumps(upload_info)}")
        except Exception as e:
            write_log(f"Upload failed for {path}: {e}")
            return None
        returned_name = None
        for key in ('name', 'filename', 'file'):
            if key in upload_info and upload_info.get(key):
                returned_name = upload_info.get(key)
                break
        if not returned_name and upload_info.get('url'):
            try:
                from urllib.parse import urlparse
                returned_name = os.path.basename(urlparse(upload_info.get('url')).path)
            except Exception:
                returned_name = None
        return returned_name or os.path.basename(path)

    def _upload_to_comfy_audio(path):
        try:
            upload_info = comfyui_api.upload_file(server, path, file_type='audio')
            write_log(f"Upload response for {path}: {json.dumps(upload_info)}")
        except Exception as e:
            write_log(f"Upload failed for {path}: {e}")
            return None
        returned_name = None
        for key in ('name', 'filename', 'file'):
            if key in upload_info and upload_info.get(key):
                returned_name = upload_info.get(key)
                break
        return returned_name or os.path.basename(path)

    def _upload_to_comfy_video(path):
        try:
            upload_info = comfyui_api.upload_file(server, path, file_type='video')
            write_log(f"Upload response for {path}: {json.dumps(upload_info)}")
        except Exception as e:
            write_log(f"Upload failed for {path}: {e}")
            return None
        returned_name = None
        for key in ('name', 'filename', 'file'):
            if key in upload_info and upload_info.get(key):
                returned_name = upload_info.get(key)
                break
        return returned_name or os.path.basename(path)

    def _compose_i2v_video(sd, image_paths, duration_seconds, fps=16, target_w=368, target_h=640):
        # create a simple hold-each-image-for-N-frames video
        n = len(image_paths)
        if n == 0:
            write_log(f"No images provided for i2v in {sd}")
            return None
        total_frames = max(1, int(round((duration_seconds or 1) * fps)))
        per = total_frames // n
        rem = total_frames % n
        video_name = f"i2v_compose_{int(datetime.utcnow().timestamp())}.mp4"
        video_out_path = os.path.join(sd, video_name)
        # ensure each source image is placed onto the target canvas without stretching
        def _ensure_canvas_size(path, target_w=target_w, target_h=target_h):
            # create a resized (fit within target) copy in scene_dir/resized/
            # Behavior: do NOT crop; do NOT stretch. Scale down if larger to fit.
            # Do NOT upscale small images (preserve quality). Then center-pad to target.
            out_dir = os.path.join(sd, 'resized')
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, os.path.basename(path))
            try:
                with Image.open(path) as im:
                    im = im.convert('RGB')
                    w, h = im.size

                    # compute scale factor (no upscaling): scale <= 1.0
                    scale = min(1.0, min(target_w / float(w), target_h / float(h)))
                    new_w = int(round(w * scale))
                    new_h = int(round(h * scale))

                    if (new_w, new_h) != (w, h):
                        im = im.resize((new_w, new_h), resample=Image.LANCZOS)

                    # create canvas and paste centered
                    canvas = Image.new('RGB', (target_w, target_h), (0, 0, 0))
                    paste_x = (target_w - im.width) // 2
                    paste_y = (target_h - im.height) // 2
                    canvas.paste(im, (paste_x, paste_y))
                    canvas.save(out_path, format='PNG')
                return out_path
            except Exception:
                return path

        try:
            writer = imageio.get_writer(video_out_path, fps=fps)
            for i, img_path in enumerate(image_paths):
                safe_path = _ensure_canvas_size(img_path)
                frames_for_img = per + (1 if i < rem else 0)
                img = imageio.imread(safe_path)
                for _ in range(frames_for_img):
                    writer.append_data(img)
            writer.close()
            write_log(f"Wrote i2v composed video to {video_out_path}")
            return video_out_path
        except Exception as e:
            write_log(f"Failed to compose i2v video for {sd}: {e}")
            try:
                writer.close()
            except Exception:
                pass
            return None

    # Branch by scene_type
    if scene_type == 'wan22_t2v_i2v':
        try:
            scene_duration = int(scene_meta.get('duration_seconds', 0))
        except Exception:
            scene_duration = 0
        if scene_duration not in {5, 10, 15}:
            write_log(f"wan22_t2v_i2v scene duration must be 5, 10, or 15 seconds: {scene_duration}")
            return False

        _ensure_scene_json(scene_dir, 'wan22_t2v_prompt.json', DEFAULT_WAN22_T2V_PROMPT)
        _ensure_scene_json(scene_dir, 'wan22_i2v_prompt.json', DEFAULT_WAN_PROMPT)

        try:
            t2v_prompt = _read_scene_json(scene_dir, 'wan22_t2v_prompt.json', required=True)
            t2v_workflow = build_wan_t2v_workflow(t2v_prompt, scene_meta)
        except Exception as e:
            write_log(f"Failed to build wan22_t2v workflow for {scene_dir}: {e}")
            return False

        t2v_result = send_wan22_t2v_workflow(
            t2v_workflow,
            server,
            log_file=LOG_FILE,
            source_label=os.path.join(scene_dir, 'wan22_t2v_prompt.json'),
        )
        if not t2v_result:
            write_log(f"send_wan22_t2v_workflow failed for {scene_dir}")
            return False
        prompt_id = t2v_result.get('prompt_id') or t2v_result.get('id')
        write_log(f"Posted wan22_t2v workflow for {scene_dir}, prompt_id={prompt_id}")
        video_out = None
        if prompt_id:
            video_out = comfyui_api.wait_for_output(server, prompt_id, output_type='video', timeout=COMFYUI_WORKFLOW_TIMEOUT_SECONDS, interval=POLL_INTERVAL)
        if not video_out:
            write_log(f"No T2V video found for {scene_dir} (prompt_id={prompt_id}); stopping run")
            return False
        write_log(f"T2V video output info: {json.dumps(video_out)}")
        video_filename = video_out.get('filename') or video_out.get('name') or video_out.get('file')
        video_subfolder = video_out.get('subfolder')
        video_type = video_out.get('type')
        if not video_filename:
            write_log(f"Cannot determine T2V video filename from output: {json.dumps(video_out)}")
            return False
        video_url = comfyui_api.get_file_url(server, video_filename, subfolder=video_subfolder, type_=video_type)
        t2v_video_out_path = os.path.join(scene_dir, video_filename)
        try:
            comfyui_api.download_file_url(video_url, t2v_video_out_path)
        except Exception as e:
            write_log(f"Failed to download T2V video {video_filename} from {video_url}: {e}")
            return False
        try:
            if not os.path.exists(t2v_video_out_path) or os.path.getsize(t2v_video_out_path) == 0:
                write_log(f"Downloaded T2V file missing or empty: {t2v_video_out_path}")
                return False
        except Exception as e:
            write_log(f"Error checking downloaded T2V file {t2v_video_out_path}: {e}")
            return False

        if scene_duration == 5:
            return _finalize_scene_success(
                t2v_video_out_path,
                is_s2v=False,
                success_message=f"Completed wan22_t2v_i2v T2V-only processing for {scene_dir}",
            )

        last_frame_path = os.path.join(scene_dir, 'wan22_t2v_last_frame.png')
        try:
            _extract_last_frame_image(t2v_video_out_path, last_frame_path)
        except Exception as e:
            write_log(f"Failed to extract last frame from T2V video for {scene_dir}: {e}")
            return False

        try:
            wan_prompt = _read_scene_json(scene_dir, 'wan22_i2v_prompt.json', required=True)
            wan_prompt = copy.deepcopy(wan_prompt) if isinstance(wan_prompt, dict) else {}
            wan_prompt['duration_seconds'] = resolve_wan22_i2v_duration(scene_duration)
        except Exception as e:
            write_log(f"Failed to read wan22_i2v_prompt.json for {scene_dir}: {e}")
            return False

        uploaded_name = _upload_to_comfy(last_frame_path)
        if not uploaded_name:
            write_log(f"Failed to upload extracted last frame for {scene_dir}")
            return False
        try:
            wan_workflow = build_wan_workflow(wan_prompt, scene_meta, uploaded_name=uploaded_name)
        except Exception as e:
            write_log(f"Failed to build wan22_i2v workflow for {scene_dir}: {e}")
            return False
        wan_result = send_wan_workflow(
            wan_workflow,
            uploaded_name,
            server,
            log_file=LOG_FILE,
            source_label=os.path.join(scene_dir, 'wan22_i2v_prompt.json'),
        )
        if not wan_result:
            write_log(f"send_wan_workflow failed for wan22_t2v_i2v in {scene_dir}")
            return False
        prompt_id = wan_result.get('prompt_id') or wan_result.get('id')
        write_log(f"Posted wan22_i2v workflow for {scene_dir}, prompt_id={prompt_id}")
        video_out = None
        if prompt_id:
            video_out = comfyui_api.wait_for_output(server, prompt_id, output_type='video', timeout=COMFYUI_WORKFLOW_TIMEOUT_SECONDS, interval=POLL_INTERVAL)
        if not video_out:
            write_log(f"No WAN22_I2V video found for {scene_dir} (prompt_id={prompt_id}); stopping run")
            return False
        write_log(f"WAN22_I2V video output info: {json.dumps(video_out)}")
        video_filename = video_out.get('filename') or video_out.get('name') or video_out.get('file')
        video_subfolder = video_out.get('subfolder')
        video_type = video_out.get('type')
        if not video_filename:
            write_log(f"Cannot determine WAN22_I2V video filename from output: {json.dumps(video_out)}")
            return False
        video_url = comfyui_api.get_file_url(server, video_filename, subfolder=video_subfolder, type_=video_type)
        i2v_video_out_path = os.path.join(scene_dir, video_filename)
        try:
            comfyui_api.download_file_url(video_url, i2v_video_out_path)
        except Exception as e:
            write_log(f"Failed to download WAN22_I2V video {video_filename} from {video_url}: {e}")
            return False
        try:
            if not os.path.exists(i2v_video_out_path) or os.path.getsize(i2v_video_out_path) == 0:
                write_log(f"Downloaded WAN22_I2V file missing or empty: {i2v_video_out_path}")
                return False
        except Exception as e:
            write_log(f"Error checking downloaded WAN22_I2V file {i2v_video_out_path}: {e}")
            return False
        try:
            concat_tmp_path = os.path.join(scene_dir, "__wan22_t2v_i2v_concat_tmp__.mp4")
            _concat_video_segments([t2v_video_out_path, i2v_video_out_path], concat_tmp_path)
            os.replace(concat_tmp_path, i2v_video_out_path)
            write_log(
                f"Combined wan22_t2v_i2v stages into final video: {i2v_video_out_path} "
                f"(T2V {os.path.basename(t2v_video_out_path)} + I2V {os.path.basename(i2v_video_out_path)})"
            )
        except Exception as e:
            write_log(f"Failed to concat WAN22_T2V + WAN22_I2V for {scene_dir}: {e}")
            return False
        return _finalize_scene_success(
            i2v_video_out_path,
            is_s2v=False,
            success_message=f"Completed processing {scene_dir}",
        )

    if scene_type == 'minimax-h3_t2v_i2v':
        try:
            scene_duration = float(scene_meta.get('duration_seconds', 0))
        except Exception:
            scene_duration = 0
        if not (1.0 <= scene_duration <= 30.0 and scene_duration == round(scene_duration, 1)):
            write_log(
                "minimax-h3_t2v_i2v scene duration must be between 1.0 and 30.0 seconds with at most 1 decimal: "
                f"{scene_duration}"
            )
            return False

        _ensure_scene_json(
            scene_dir,
            'minimax_h3_t2v_prompt.json',
            DEFAULT_MINIMAX_H3_T2V_PROMPT,
        )
        _ensure_scene_json(
            scene_dir,
            'minimax_h3_i2v_prompt.json',
            DEFAULT_MINIMAX_H3_I2V_PROMPT,
        )

        try:
            t2v_prompt = _read_scene_json(
                scene_dir,
                'minimax_h3_t2v_prompt.json',
                required=True,
            )
            t2v_prompt = copy.deepcopy(t2v_prompt) if isinstance(t2v_prompt, dict) else {}
            i2v_prompt = {}
            if scene_duration > 15:
                i2v_prompt = _read_scene_json(
                    scene_dir,
                    'minimax_h3_i2v_prompt.json',
                    required=True,
                )
                i2v_prompt = copy.deepcopy(i2v_prompt) if isinstance(i2v_prompt, dict) else {}

        except Exception as e:
            write_log(f"Failed to read MiniMax H3 prompt files for {scene_dir}: {e}")
            return False

        t2v_duration = scene_duration if scene_duration <= 15 else 15
        try:
            t2v_workflow = build_minimax_h3_t2v_workflow(
                t2v_prompt,
                scene_meta,
                duration_override=t2v_duration,
                fps_override=t2v_prompt.get("fps", 24),
            )
        except Exception as e:
            write_log(f"Failed to build MiniMax H3 T2V workflow for {scene_dir}: {e}")
            return False

        t2v_result = send_minimax_h3_t2v_workflow(
            t2v_workflow,
            server,
            log_file=LOG_FILE,
            source_label=os.path.join(scene_dir, 'minimax_h3_t2v_prompt.json'),
        )
        if not t2v_result:
            write_log(f"send_minimax_h3_t2v_workflow failed for {scene_dir}")
            return False
        prompt_id = t2v_result.get('prompt_id') or t2v_result.get('id')
        write_log(f"Posted MiniMax H3 T2V workflow for {scene_dir}, prompt_id={prompt_id}")
        video_out = None
        if prompt_id:
            video_out = comfyui_api.wait_for_output(
                server,
                prompt_id,
                output_type='video',
                timeout=COMFYUI_WORKFLOW_TIMEOUT_SECONDS,
                interval=POLL_INTERVAL,
            )
        if not video_out:
            write_log(f"No MiniMax H3 T2V video found for {scene_dir} (prompt_id={prompt_id})")
            return False

        video_filename = video_out.get('filename') or video_out.get('name') or video_out.get('file')
        video_subfolder = video_out.get('subfolder')
        video_type = video_out.get('type')
        if not video_filename:
            write_log(f"Cannot determine MiniMax H3 T2V video filename: {json.dumps(video_out)}")
            return False
        video_url = comfyui_api.get_file_url(
            server,
            video_filename,
            subfolder=video_subfolder,
            type_=video_type,
        )
        t2v_video_out_path = os.path.join(scene_dir, video_filename)
        try:
            comfyui_api.download_file_url(video_url, t2v_video_out_path)
            if not os.path.exists(t2v_video_out_path) or os.path.getsize(t2v_video_out_path) == 0:
                write_log(f"Downloaded MiniMax H3 T2V file missing or empty: {t2v_video_out_path}")
                return False
        except Exception as e:
            write_log(f"Failed to download MiniMax H3 T2V video {video_filename}: {e}")
            return False

        if bool(t2v_prompt.get("remove_sound", False)):
            try:
                _remove_video_audio(t2v_video_out_path)
            except Exception as e:
                write_log(f"Failed to remove MiniMax H3 T2V sound for {scene_dir}: {e}")
                return False
        try:
            _invalidate_comfy_audio_source(scene_dir)
        except Exception as e:
            write_log(f"Failed to invalidate old MiniMax H3 T2V audio source for {scene_dir}: {e}")
            return False

        if scene_duration <= 15:
            return _finalize_scene_success(
                t2v_video_out_path,
                is_s2v=False,
                preserve_comfy_audio=not bool(t2v_prompt.get("remove_sound", False)),
                compose_audio=True,
                success_message=(
                    f"Completed minimax-h3_t2v_i2v T2V-only processing for {scene_dir}"
                ),
            )

        last_frame_path = os.path.join(scene_dir, 'minimax_h3_t2v_last_frame.png')
        try:
            _extract_last_frame_image(t2v_video_out_path, last_frame_path)
        except Exception as e:
            write_log(f"Failed to extract MiniMax H3 T2V last frame for {scene_dir}: {e}")
            return False

        uploaded_name = _upload_to_comfy(last_frame_path)
        if not uploaded_name:
            write_log(f"Failed to upload MiniMax H3 T2V last frame for {scene_dir}")
            return False

        i2v_duration = scene_duration - 15
        try:
            i2v_workflow = build_minimax_h3_i2v_workflow(
                i2v_prompt,
                scene_meta,
                uploaded_name=uploaded_name,
                duration_override=i2v_duration,
                fps_override=t2v_prompt.get("fps", 24),
            )
        except Exception as e:
            write_log(f"Failed to build MiniMax H3 I2V workflow for {scene_dir}: {e}")
            return False

        i2v_result = send_minimax_h3_i2v_workflow(
            i2v_workflow,
            uploaded_name,
            server,
            log_file=LOG_FILE,
            source_label=os.path.join(scene_dir, 'minimax_h3_i2v_prompt.json'),
        )
        if not i2v_result:
            write_log(f"send_minimax_h3_i2v_workflow failed for {scene_dir}")
            return False
        prompt_id = i2v_result.get('prompt_id') or i2v_result.get('id')
        write_log(f"Posted MiniMax H3 I2V workflow for {scene_dir}, prompt_id={prompt_id}")
        video_out = None
        if prompt_id:
            video_out = comfyui_api.wait_for_output(
                server,
                prompt_id,
                output_type='video',
                timeout=COMFYUI_WORKFLOW_TIMEOUT_SECONDS,
                interval=POLL_INTERVAL,
            )
        if not video_out:
            write_log(f"No MiniMax H3 I2V video found for {scene_dir} (prompt_id={prompt_id})")
            return False

        video_filename = video_out.get('filename') or video_out.get('name') or video_out.get('file')
        video_subfolder = video_out.get('subfolder')
        video_type = video_out.get('type')
        if not video_filename:
            write_log(f"Cannot determine MiniMax H3 I2V video filename: {json.dumps(video_out)}")
            return False
        video_url = comfyui_api.get_file_url(
            server,
            video_filename,
            subfolder=video_subfolder,
            type_=video_type,
        )
        i2v_video_out_path = os.path.join(scene_dir, video_filename)
        try:
            comfyui_api.download_file_url(video_url, i2v_video_out_path)
            if not os.path.exists(i2v_video_out_path) or os.path.getsize(i2v_video_out_path) == 0:
                write_log(f"Downloaded MiniMax H3 I2V file missing or empty: {i2v_video_out_path}")
                return False
        except Exception as e:
            write_log(f"Failed to download MiniMax H3 I2V video {video_filename}: {e}")
            return False

        if bool(i2v_prompt.get("remove_sound", False)):
            try:
                _remove_video_audio(i2v_video_out_path)
            except Exception as e:
                write_log(f"Failed to remove MiniMax H3 I2V sound for {scene_dir}: {e}")
                return False

        try:
            concat_tmp_path = os.path.join(scene_dir, "__minimax_h3_t2v_i2v_concat_tmp__.mp4")
            _concat_video_segments(
                [t2v_video_out_path, i2v_video_out_path],
                concat_tmp_path,
                preserve_audio=True,
            )
            os.replace(concat_tmp_path, i2v_video_out_path)
            write_log(
                f"Combined MiniMax H3 T2V + I2V stages into final video: {i2v_video_out_path}"
            )
        except Exception as e:
            write_log(f"Failed to concat MiniMax H3 T2V + I2V for {scene_dir}: {e}")
            return False
        try:
            _invalidate_comfy_audio_source(scene_dir)
        except Exception as e:
            write_log(f"Failed to invalidate old MiniMax H3 T2V-I2V audio source for {scene_dir}: {e}")
            return False
        final_remove_sound = bool(
            t2v_prompt.get("remove_sound", False)
            or i2v_prompt.get("remove_sound", False)
        )
        if final_remove_sound:
            try:
                _remove_video_audio(i2v_video_out_path)
            except Exception as e:
                write_log(f"Failed to remove MiniMax H3 T2V-I2V sound after concat for {scene_dir}: {e}")
                return False
        return _finalize_scene_success(
            i2v_video_out_path,
            is_s2v=False,
            preserve_comfy_audio=not final_remove_sound,
            compose_audio=True,
            success_message=f"Completed minimax-h3_t2v_i2v processing for {scene_dir}",
        )

    if scene_type == 'minimax-h3_i2v':
        try:
            scene_duration = float(scene_meta.get('duration_seconds', 0))
        except Exception:
            scene_duration = 0
        if not (1.0 <= scene_duration <= 15.0 and scene_duration == round(scene_duration, 1)):
            write_log(
                "minimax-h3_i2v scene duration must be between 1.0 and 15.0 seconds with at most 1 decimal: "
                f"{scene_duration}"
            )
            return False

        _ensure_scene_json(
            scene_dir,
            'minimax_h3_i2v_prompt.json',
            DEFAULT_MINIMAX_H3_I2V_PROMPT,
        )
        img_path = _find_latest_root_image(scene_dir)
        if not img_path:
            write_log(f"minimax-h3_i2v scene requires at least one input image in root folder {scene_dir}")
            return False
        write_log(f"Using latest root image for minimax-h3_i2v: {img_path}")
        uploaded_name = _upload_to_comfy(img_path)
        if not uploaded_name:
            write_log(f"Failed to upload image for minimax-h3_i2v in {scene_dir}")
            return False
        try:
            i2v_prompt = _read_scene_json(
                scene_dir,
                'minimax_h3_i2v_prompt.json',
                required=True,
            )
            i2v_workflow = build_minimax_h3_i2v_workflow(
                i2v_prompt,
                scene_meta,
                uploaded_name=uploaded_name,
                duration_override=scene_duration,
                fps_override=i2v_prompt.get("fps", 24),
            )
        except Exception as e:
            write_log(f"Failed to build MiniMax H3 I2V workflow for {scene_dir}: {e}")
            return False
        i2v_result = send_minimax_h3_i2v_workflow(
            i2v_workflow,
            uploaded_name,
            server,
            log_file=LOG_FILE,
            source_label=os.path.join(scene_dir, 'minimax_h3_i2v_prompt.json'),
        )
        if not i2v_result:
            write_log(f"send_minimax_h3_i2v_workflow failed for {scene_dir}")
            return False
        prompt_id = i2v_result.get('prompt_id') or i2v_result.get('id')
        write_log(f"Posted MiniMax H3 I2V workflow for {scene_dir}, prompt_id={prompt_id}")
        video_out = None
        if prompt_id:
            video_out = comfyui_api.wait_for_output(
                server,
                prompt_id,
                output_type='video',
                timeout=COMFYUI_WORKFLOW_TIMEOUT_SECONDS,
                interval=POLL_INTERVAL,
            )
        if not video_out:
            write_log(f"No MiniMax H3 I2V video found for {scene_dir} (prompt_id={prompt_id})")
            return False
        video_filename = video_out.get('filename') or video_out.get('name') or video_out.get('file')
        video_subfolder = video_out.get('subfolder')
        video_type = video_out.get('type')
        if not video_filename:
            write_log(f"Cannot determine MiniMax H3 I2V video filename: {json.dumps(video_out)}")
            return False
        video_url = comfyui_api.get_file_url(
            server,
            video_filename,
            subfolder=video_subfolder,
            type_=video_type,
        )
        video_out_path = os.path.join(scene_dir, video_filename)
        try:
            comfyui_api.download_file_url(video_url, video_out_path)
            if not os.path.exists(video_out_path) or os.path.getsize(video_out_path) == 0:
                write_log(f"Downloaded MiniMax H3 I2V file missing or empty: {video_out_path}")
                return False
        except Exception as e:
            write_log(f"Failed to download MiniMax H3 I2V video {video_filename}: {e}")
            return False

        if bool(i2v_prompt.get("remove_sound", False)):
            try:
                _remove_video_audio(video_out_path)
            except Exception as e:
                write_log(f"Failed to remove MiniMax H3 I2V sound for {scene_dir}: {e}")
                return False
        try:
            _invalidate_comfy_audio_source(scene_dir)
        except Exception as e:
            write_log(f"Failed to invalidate old MiniMax H3 I2V audio source for {scene_dir}: {e}")
            return False
        return _finalize_scene_success(
            video_out_path,
            is_s2v=False,
            preserve_comfy_audio=not bool(i2v_prompt.get("remove_sound", False)),
            compose_audio=True,
            success_message=f"Completed minimax-h3_i2v processing for {scene_dir}",
        )

    if scene_type == 'wan22_t2v_batch':
        try:
            scene_duration = int(scene_meta.get('duration_seconds', 0))
        except Exception:
            scene_duration = 0
        if scene_duration not in {5, 10}:
            write_log(f"wan22_t2v_batch scene duration must be 5 or 10 seconds: {scene_duration}")
            return False

        _ensure_scene_json(scene_dir, 'wan22_t2v_prompt.json', DEFAULT_WAN22_T2V_PROMPT)
        _ensure_scene_json(scene_dir, 'wan22_t2v_batch_extra_prompts.json', DEFAULT_WAN22_T2V_BATCH_EXTRA_PROMPTS)

        try:
            t2v_prompt = _read_scene_json(scene_dir, 'wan22_t2v_prompt.json', required=True)
            extra_prompts_data = _read_scene_json(scene_dir, 'wan22_t2v_batch_extra_prompts.json', required=True)
        except Exception as e:
            write_log(f"Failed to read prompt files for {scene_dir}: {e}")
            return False

        # Build list of prompts: main + filled extras
        prompts_to_process = [t2v_prompt]
        groups = extra_prompts_data.get("groups", []) if isinstance(extra_prompts_data, dict) else []
        for group in groups:
            if isinstance(group, dict) and group.get("positive_prompt", "").strip():
                prompts_to_process.append(group)

        total_videos = len(prompts_to_process)
        if total_videos < 1:
            write_log(f"wan22_t2v_batch has no prompts to process in {scene_dir}")
            return False

        # Calculate frames per video: ceil((duration * 16) / total_videos)
        frames_per_video = math.ceil((scene_duration * 16) / total_videos)
        write_log(f"wan22_t2v_batch: {total_videos} videos, {frames_per_video} frames each (duration={scene_duration}s)")

        # Process each prompt sequentially
        video_paths = []
        base_t2v_trigger_words = str(t2v_prompt.get(LORA_TRIGGER_WORDS_FIELD, "")).strip()
        for idx, prompt_data in enumerate(prompts_to_process):
            write_log(f"Processing wan22_t2v_batch video {idx + 1}/{total_videos} for {scene_dir}")
            try:
                # Extra prompts only override the prompt text; inherit the base T2V config
                # so LoRA, size, and other workflow inputs remain valid.
                merged_prompt_data = copy.deepcopy(t2v_prompt)
                if isinstance(prompt_data, dict):
                    merged_prompt_data.update(prompt_data)
                    if prompt_data is not t2v_prompt:
                        merged_prompt_data["positive_prompt"] = prepend_lora_trigger_words(
                            str(prompt_data.get("positive_prompt", "")).strip(),
                            base_t2v_trigger_words,
                        )
                workflow = build_wan_t2v_workflow(merged_prompt_data, scene_meta, length_override=frames_per_video)
            except Exception as e:
                write_log(f"Failed to build wan22_t2v workflow for batch video {idx + 1} in {scene_dir}: {e}")
                return False

            result = send_wan22_t2v_workflow(
                workflow,
                server,
                log_file=LOG_FILE,
                source_label=os.path.join(scene_dir, f'batch_video_{idx + 1}'),
            )
            if not result:
                write_log(f"send_wan22_t2v_workflow failed for batch video {idx + 1} in {scene_dir}")
                return False

            prompt_id = result.get('prompt_id') or result.get('id')
            write_log(f"Posted wan22_t2v_batch video {idx + 1} for {scene_dir}, prompt_id={prompt_id}")

            video_out = None
            if prompt_id:
                video_out = comfyui_api.wait_for_output(server, prompt_id, output_type='video', timeout=COMFYUI_WORKFLOW_TIMEOUT_SECONDS, interval=POLL_INTERVAL)
            if not video_out:
                write_log(f"No video found for batch video {idx + 1} in {scene_dir} (prompt_id={prompt_id}); stopping run")
                return False

            video_filename = video_out.get('filename') or video_out.get('name') or video_out.get('file')
            video_subfolder = video_out.get('subfolder')
            video_type = video_out.get('type')
            if not video_filename:
                write_log(f"Cannot determine video filename from output for batch video {idx + 1}: {json.dumps(video_out)}")
                return False

            video_url = comfyui_api.get_file_url(server, video_filename, subfolder=video_subfolder, type_=video_type)
            video_out_path = os.path.join(scene_dir, f'batch_video_{idx + 1}_{video_filename}')
            try:
                comfyui_api.download_file_url(video_url, video_out_path)
            except Exception as e:
                write_log(f"Failed to download video {video_filename} for batch video {idx + 1}: {e}")
                return False

            if not os.path.exists(video_out_path) or os.path.getsize(video_out_path) == 0:
                write_log(f"Downloaded batch video missing or empty: {video_out_path}")
                return False

            video_paths.append(video_out_path)
            write_log(f"Downloaded batch video {idx + 1}/{total_videos}: {video_out_path}")

        # Concat all videos
        final_video_path = os.path.join(scene_dir, "wan22_t2v_batch_final.mp4")
        if len(video_paths) == 1:
            final_video_path = video_paths[0]
        else:
            concat_tmp_path = os.path.join(scene_dir, "__wan22_t2v_batch_concat_tmp__.mp4")
            try:
                _concat_video_segments(video_paths, concat_tmp_path)
                os.replace(concat_tmp_path, final_video_path)
            except Exception as e:
                write_log(f"Failed to concat wan22_t2v_batch videos for {scene_dir}: {e}")
                return False

        return _finalize_scene_success(
            final_video_path,
            is_s2v=False,
            success_message=f"Completed wan22_t2v_batch processing for {scene_dir} ({total_videos} videos merged)",
        )

    if scene_type in {'wan22', 'wan22_i2v'}:
        img_path = _find_latest_root_image(scene_dir)
        if not img_path:
            write_log(f"{scene_type} scene requires at least one input image in root folder {scene_dir}")
            return False
        write_log(f"Using latest root image for {scene_dir}: {img_path}")
        uploaded_name = _upload_to_comfy(img_path)
        if not uploaded_name:
            write_log(f"Failed to upload image for {scene_type} in {scene_dir}")
            return False
        try:
            wan_prompt = _read_scene_json(scene_dir, 'wan22_i2v_prompt.json', required=True)
            wan_workflow = build_wan_workflow(wan_prompt, scene_meta, uploaded_name=uploaded_name)
        except Exception as e:
            write_log(f"Failed to build wan22 workflow for {scene_dir}: {e}")
            return False
        wan_result = send_wan_workflow(
            wan_workflow,
            uploaded_name,
            server,
            log_file=LOG_FILE,
            source_label=os.path.join(scene_dir, 'wan22_i2v_prompt.json'),
        )
        if not wan_result:
            write_log(f"send_wan_workflow failed for {scene_dir}")
            return False
        prompt_id = wan_result.get('prompt_id') or wan_result.get('id')
        write_log(f"Posted wan22 workflow for {scene_dir}, prompt_id={prompt_id}")
        video_out = None
        if prompt_id:
                video_out = comfyui_api.wait_for_output(server, prompt_id, output_type='video', timeout=COMFYUI_WORKFLOW_TIMEOUT_SECONDS, interval=POLL_INTERVAL)
        if not video_out:
            write_log(f"No video found for {scene_dir} (prompt_id={prompt_id}); stopping run")
            return False
        write_log(f"Video output info: {json.dumps(video_out)}")
        video_filename = video_out.get('filename') or video_out.get('name') or video_out.get('file')
        video_subfolder = video_out.get('subfolder')
        video_type = video_out.get('type')
        if not video_filename:
            write_log(f"Cannot determine video filename from output: {json.dumps(video_out)}")
            return False
        video_url = comfyui_api.get_file_url(server, video_filename, subfolder=video_subfolder, type_=video_type)
        video_out_path = os.path.join(scene_dir, video_filename)
        try:
            comfyui_api.download_file_url(video_url, video_out_path)
        except Exception as e:
            write_log(f"Failed to download video {video_filename} from {video_url}: {e}")
            return False
        try:
            if not os.path.exists(video_out_path) or os.path.getsize(video_out_path) == 0:
                write_log(f"Downloaded file missing or empty: {video_out_path}")
                return False
        except Exception as e:
            write_log(f"Error checking downloaded file {video_out_path}: {e}")
            return False
        return _finalize_scene_success(
            video_out_path,
            is_s2v=False,
            success_message=f"Completed processing {scene_dir}",
        )

    if scene_type == 'wan22_s2v':
        _ensure_scene_json(scene_dir, 'wan22_s2v_prompt.json', DEFAULT_WAN22_S2V_PROMPT)
        img_path = _find_latest_root_image(scene_dir)
        if not img_path:
            write_log(f"wan22_s2v scene requires at least one input image in root folder {scene_dir}")
            return False
        speech_path = _find_latest_root_speech(scene_dir)
        if not speech_path:
            write_log(f"wan22_s2v scene requires at least one speech audio in root folder {scene_dir}")
            return False
        try:
            audio_duration = get_s2v_audio_duration(speech_path)
        except Exception as e:
            write_log(f"Failed to read speech duration for {speech_path}: {e}")
            return False
        if audio_duration >= WAN22_S2V_MAX_AUDIO_DURATION:
            write_log(
                f"wan22_s2v speech duration must be less than {WAN22_S2V_MAX_AUDIO_DURATION} seconds: "
                f"{speech_path} ({audio_duration:.2f}s)"
            )
            return False

        uploaded_image_name = _upload_to_comfy(img_path)
        if not uploaded_image_name:
            write_log(f"Failed to upload image for wan22_s2v in {scene_dir}")
            return False
        uploaded_audio_name = _upload_to_comfy_audio(speech_path)
        if not uploaded_audio_name:
            write_log(f"Failed to upload speech audio for wan22_s2v in {scene_dir}")
            return False
        try:
            s2v_prompt = _read_scene_json(scene_dir, 'wan22_s2v_prompt.json', required=True)
            s2v_workflow = build_wan22_s2v_workflow(
                s2v_prompt,
                uploaded_image_name,
                uploaded_audio_name,
                audio_duration,
            )
        except Exception as e:
            write_log(f"Failed to build wan22_s2v workflow for {scene_dir}: {e}")
            return False
        s2v_result = send_s2v_workflow(
            s2v_workflow,
            server,
            log_file=LOG_FILE,
            source_label=os.path.join(scene_dir, 'wan22_s2v_prompt.json'),
        )
        prompt_id = s2v_result.get('prompt_id') or s2v_result.get('id')
        write_log(f"Posted wan22_s2v workflow for {scene_dir}, prompt_id={prompt_id}")
        video_out = None
        if prompt_id:
            video_out = comfyui_api.wait_for_output(
                server,
                prompt_id,
                output_type='video',
                timeout=COMFYUI_WORKFLOW_TIMEOUT_SECONDS,
                interval=POLL_INTERVAL,
            )
        if not video_out:
            write_log(f"No video found for {scene_dir} (prompt_id={prompt_id}); stopping run")
            return False
        video_filename = video_out.get('filename') or video_out.get('name') or video_out.get('file')
        video_subfolder = video_out.get('subfolder')
        video_type = video_out.get('type')
        if not video_filename:
            write_log(f"Cannot determine video filename from output: {json.dumps(video_out)}")
            return False
        video_url = comfyui_api.get_file_url(server, video_filename, subfolder=video_subfolder, type_=video_type)
        video_out_path = os.path.join(scene_dir, video_filename)
        try:
            comfyui_api.download_file_url(video_url, video_out_path)
        except Exception as e:
            write_log(f"Failed to download video {video_filename} from {video_url}: {e}")
            return False
        try:
            if not os.path.exists(video_out_path) or os.path.getsize(video_out_path) == 0:
                write_log(f"Downloaded file missing or empty: {video_out_path}")
                return False
        except Exception as e:
            write_log(f"Error checking downloaded file {video_out_path}: {e}")
            return False
        try:
            trimmed_duration = trim_video_to_speech_duration(video_out_path, audio_duration, max_extra_frames=4)
            write_log(
                f"Trimmed wan22_s2v video to speech duration for {scene_dir}: "
                f"speech={audio_duration:.3f}s, output={trimmed_duration:.3f}s"
            )
        except Exception as e:
            write_log(f"Failed to trim wan22_s2v video for {scene_dir}: {e}")
            return False
        return _finalize_scene_success(
            video_out_path,
            is_s2v=True,
            success_message=f"Completed processing {scene_dir}",
        )

    if scene_type == 'minimax-h3_r2v':
        _ensure_scene_json(scene_dir, 'minimax_h3_r2v_prompt.json', DEFAULT_MINIMAX_H3_R2V_PROMPT)
        try:
            r2v_prompt = _read_scene_json(scene_dir, 'minimax_h3_r2v_prompt.json', required=True)
            references = r2v_prompt.get('references', {}) if isinstance(r2v_prompt, dict) else {}
            references = references if isinstance(references, dict) else {}
            image_names = [str(value).strip() for value in references.get('images', []) if str(value).strip()][:3]
            audio_names = [str(value).strip() for value in references.get('audios', []) if str(value).strip()][:3]
            video_name = str(references.get('video', '')).strip()
            if not image_names and not audio_names and not video_name:
                raise ValueError('minimal satu reference image, audio, atau video wajib dipilih')
            duration = float(scene_meta.get('duration_seconds', 0))
            if not (1.0 <= duration <= 15.0 and duration == round(duration, 1)):
                raise ValueError('durasi R2V harus antara 1.0 dan 15.0 detik dengan maksimal 1 angka desimal')
            image_paths = [os.path.join(scene_dir, name) for name in image_names]
            audio_paths = [os.path.join(scene_dir, name) for name in audio_names]
            video_path = os.path.join(scene_dir, video_name) if video_name else None
            missing = [path for path in image_paths + audio_paths + ([video_path] if video_path else []) if not os.path.isfile(path)]
            if missing:
                raise FileNotFoundError('reference tidak ditemukan: ' + ', '.join(os.path.basename(path) for path in missing[:3]))
            uploaded_images = [_upload_to_comfy(path) for path in image_paths]
            uploaded_audios = [_upload_to_comfy_audio(path) for path in audio_paths]
            uploaded_video = _upload_to_comfy_video(video_path) if video_path else None
            if any(not value for value in uploaded_images + uploaded_audios) or video_path and not uploaded_video:
                raise RuntimeError('gagal upload satu atau lebih reference R2V ke ComfyUI')
            r2v_workflow = build_minimax_h3_r2v_workflow(
                r2v_prompt,
                scene_meta=scene_meta,
                image_names=uploaded_images,
                audio_names=uploaded_audios,
                video_name=uploaded_video,
                duration_override=duration,
                fps_override=r2v_prompt.get("fps", 24),
            )
            r2v_result = send_minimax_h3_s2v_workflow(
                r2v_workflow,
                server,
                log_file=LOG_FILE,
                source_label=os.path.join(scene_dir, 'minimax_h3_r2v_prompt.json'),
            )
        except Exception as e:
            write_log(f"Failed to build minimax-h3_r2v workflow for {scene_dir}: {e}")
            return False
        prompt_id = r2v_result.get('prompt_id') or r2v_result.get('id')
        write_log(f"Posted minimax-h3_r2v workflow for {scene_dir}, prompt_id={prompt_id}")
        video_out = None
        if prompt_id:
            video_out = comfyui_api.wait_for_output(
                server,
                prompt_id,
                output_type='video',
                timeout=COMFYUI_WORKFLOW_TIMEOUT_SECONDS,
                interval=POLL_INTERVAL,
            )
        if not video_out:
            write_log(f"No MiniMax H3 R2V video found for {scene_dir} (prompt_id={prompt_id}); stopping run")
            return False
        video_filename = video_out.get('filename') or video_out.get('name') or video_out.get('file')
        video_subfolder = video_out.get('subfolder')
        video_type = video_out.get('type')
        if not video_filename:
            write_log(f"Cannot determine video filename from output: {json.dumps(video_out)}")
            return False
        video_url = comfyui_api.get_file_url(server, video_filename, subfolder=video_subfolder, type_=video_type)
        video_out_path = os.path.join(scene_dir, video_filename)
        try:
            comfyui_api.download_file_url(video_url, video_out_path)
        except Exception as e:
            write_log(f"Failed to download video {video_filename} from {video_url}: {e}")
            return False
        if not os.path.exists(video_out_path) or os.path.getsize(video_out_path) == 0:
            write_log(f"Downloaded file missing or empty: {video_out_path}")
            return False
        return _finalize_scene_success(
            video_out_path,
            is_s2v=True,
            success_message=f"Completed processing {scene_dir}",
        )

    if scene_type == 'minimax-h3_s2v':
        _ensure_scene_json(scene_dir, 'minimax_h3_s2v_prompt.json', DEFAULT_MINIMAX_H3_S2V_PROMPT)
        img_path = _find_latest_root_image(scene_dir)
        if not img_path:
            write_log(f"minimax-h3_s2v scene requires at least one input image in root folder {scene_dir}")
            return False
        speech_path = _find_latest_root_speech(scene_dir)
        if not speech_path:
            write_log(f"minimax-h3_s2v scene requires at least one speech audio in root folder {scene_dir}")
            return False
        try:
            audio_duration = get_s2v_audio_duration(speech_path)
        except Exception as e:
            write_log(f"Failed to read speech duration for {speech_path}: {e}")
            return False
        if audio_duration > MINIMAX_H3_S2V_MAX_AUDIO_DURATION:
            write_log(
                f"minimax-h3_s2v speech duration must be at most {MINIMAX_H3_S2V_MAX_AUDIO_DURATION:g} seconds: "
                f"{speech_path} ({audio_duration:.2f}s)"
            )
            return False

        uploaded_image_name = _upload_to_comfy(img_path)
        if not uploaded_image_name:
            write_log(f"Failed to upload image for minimax-h3_s2v in {scene_dir}")
            return False
        uploaded_audio_name = _upload_to_comfy_audio(speech_path)
        if not uploaded_audio_name:
            write_log(f"Failed to upload speech audio for minimax-h3_s2v in {scene_dir}")
            return False
        try:
            s2v_prompt = _read_scene_json(scene_dir, 'minimax_h3_s2v_prompt.json', required=True)
            s2v_workflow = build_minimax_h3_r2v_workflow(
                s2v_prompt,
                scene_meta=scene_meta,
                image_name=uploaded_image_name,
                audio_name=uploaded_audio_name,
                duration_override=audio_duration,
                fps_override=s2v_prompt.get("fps", 24),
                remove_picture_2_reference=True,
                remove_picture_3_reference=True,
                remove_video_1_reference=True,
                remove_audio_2_reference=True,
                remove_audio_3_reference=True,
            )
        except Exception as e:
            write_log(f"Failed to build minimax-h3_s2v workflow for {scene_dir}: {e}")
            return False
        s2v_result = send_minimax_h3_s2v_workflow(
            s2v_workflow,
            server,
            log_file=LOG_FILE,
            source_label=os.path.join(scene_dir, 'minimax_h3_s2v_prompt.json'),
        )
        prompt_id = s2v_result.get('prompt_id') or s2v_result.get('id')
        write_log(f"Posted minimax-h3_s2v workflow for {scene_dir}, prompt_id={prompt_id}")
        video_out = None
        if prompt_id:
            video_out = comfyui_api.wait_for_output(
                server,
                prompt_id,
                output_type='video',
                timeout=COMFYUI_WORKFLOW_TIMEOUT_SECONDS,
                interval=POLL_INTERVAL,
            )
        if not video_out:
            write_log(f"No MiniMax H3 S2V video found for {scene_dir} (prompt_id={prompt_id}); stopping run")
            return False
        video_filename = video_out.get('filename') or video_out.get('name') or video_out.get('file')
        video_subfolder = video_out.get('subfolder')
        video_type = video_out.get('type')
        if not video_filename:
            write_log(f"Cannot determine video filename from output: {json.dumps(video_out)}")
            return False
        video_url = comfyui_api.get_file_url(server, video_filename, subfolder=video_subfolder, type_=video_type)
        video_out_path = os.path.join(scene_dir, video_filename)
        try:
            comfyui_api.download_file_url(video_url, video_out_path)
        except Exception as e:
            write_log(f"Failed to download video {video_filename} from {video_url}: {e}")
            return False
        if not os.path.exists(video_out_path) or os.path.getsize(video_out_path) == 0:
            write_log(f"Downloaded file missing or empty: {video_out_path}")
            return False
        return _finalize_scene_success(
            video_out_path,
            is_s2v=True,
            success_message=f"Completed processing {scene_dir}",
        )

    if scene_type == 'i2v':
        imgs = _find_images(scene_dir)
        if len(imgs) == 0:
            write_log(f"i2v scene requires at least one input image in {scene_dir}; found none")
            return False
        duration_seconds = float(scene_meta.get('duration_seconds', 1))
        z_prompt = _read_scene_json(scene_dir, 'z_image_prompt.json', required=False)
        try:
            i2v_width = int(z_prompt.get('width', 368))
        except (TypeError, ValueError):
            i2v_width = 368
        try:
            i2v_height = int(z_prompt.get('height', 640))
        except (TypeError, ValueError):
            i2v_height = 640
        composed = _compose_i2v_video(
            scene_dir,
            imgs,
            duration_seconds,
            fps=I2V_FPS,
            target_w=i2v_width,
            target_h=i2v_height,
        )
        if not composed:
            write_log(f"Failed to compose i2v video for {scene_dir}")
            return False
        try:
            if not os.path.exists(composed) or os.path.getsize(composed) == 0:
                write_log(f"Composed i2v video missing or empty: {composed}")
                return False
        except Exception as e:
            write_log(f"Error checking composed i2v video {composed}: {e}")
            return False
        return _finalize_scene_success(
            composed,
            is_s2v=False,
            success_message=f"Completed i2v composition for {scene_dir}: {composed}",
        )

    if scene_type == 'web_scroll':
        _ensure_scene_json(scene_dir, 'web_scroll_prompt.json', DEFAULT_WEB_SCROLL_PROMPT)
        try:
            web_prompt = _read_scene_json(scene_dir, 'web_scroll_prompt.json', required=True)
        except Exception as e:
            write_log(f"Failed to read web_scroll_prompt.json for {scene_dir}: {e}")
            return False
        web_url = str(web_prompt.get('url', '')).strip()
        web_width = int(web_prompt.get('width', 368))
        web_height = int(web_prompt.get('height', 640))
        try:
            web_duration = float(web_prompt.get('duration_seconds', 5.0))
        except (TypeError, ValueError):
            web_duration = 5.0
        web_speed = int(web_prompt.get('speed', 1))
        composed = None
        last_error = None
        for attempt in range(1, 4):
            try:
                composed = generate_web_scroll_video(
                    scene_dir=scene_dir,
                    url=web_url,
                    width=web_width,
                    height=web_height,
                    duration_seconds=web_duration,
                    speed=web_speed,
                    fps=WEB_SCROLL_FPS,
                    capture_mode='stable_pan',
                )
                last_error = None
                break
            except Exception as e:
                last_error = e
                write_log(f"web_scroll attempt {attempt}/3 failed for {scene_dir}: {_safe_error_text(e)}")
                if attempt < 3:
                    time.sleep(1.0 * attempt)
        if last_error is not None or not composed:
            write_log(f"Failed to generate web_scroll video for {scene_dir}: {_safe_error_text(last_error)}")
            return False
        try:
            if not os.path.exists(composed) or os.path.getsize(composed) == 0:
                write_log(f"Composed web_scroll video missing or empty: {composed}")
                return False
        except Exception as e:
            write_log(f"Error checking composed web_scroll video {composed}: {e}")
            return False
        return _finalize_scene_success(
            composed,
            is_s2v=False,
            success_message=f"Completed web_scroll composition for {scene_dir}: {composed}",
        )

    if scene_type == 'image_pan':
        _ensure_scene_json(scene_dir, 'image_pan_prompt.json', DEFAULT_IMAGE_PAN_PROMPT)
        try:
            pan_prompt = _read_scene_json(scene_dir, 'image_pan_prompt.json', required=True)
        except Exception as e:
            write_log(f"Failed to read image_pan_prompt.json for {scene_dir}: {e}")
            return False
        img_path = _find_latest_root_image(scene_dir)
        if not img_path:
            write_log(f"image_pan scene requires at least one input image in root folder {scene_dir}")
            return False
        try:
            pan_width = int(pan_prompt.get('width', 480))
            pan_height = int(pan_prompt.get('height', 848))
            pan_duration = float(scene_meta.get('duration_seconds', 5.0))
            pan_direction = str(pan_prompt.get('direction', 'from_right')).strip() or 'from_right'
        except Exception as e:
            write_log(f"Invalid image_pan prompt value for {scene_dir}: {e}")
            return False
        if pan_duration <= 0:
            write_log(f"Invalid scene duration for image_pan in {scene_dir}: {pan_duration}")
            return False
        composed = None
        last_error = None
        for attempt in range(1, 4):
            try:
                composed = generate_image_pan_video(
                    scene_dir=scene_dir,
                    image_path=img_path,
                    width=pan_width,
                    height=pan_height,
                    duration_seconds=pan_duration,
                    direction=pan_direction,
                    fps=I2V_FPS,
                    capture_mode='stable_pan',
                )
                last_error = None
                break
            except Exception as e:
                last_error = e
                write_log(f"image_pan attempt {attempt}/3 failed for {scene_dir}: {_safe_error_text(e)}")
                if attempt < 3:
                    time.sleep(1.0 * attempt)
        if last_error is not None or not composed:
            write_log(f"Failed to generate image_pan video for {scene_dir}: {_safe_error_text(last_error)}")
            return False
        try:
            if not os.path.exists(composed) or os.path.getsize(composed) == 0:
                write_log(f"Composed image_pan video missing or empty: {composed}")
                return False
        except Exception as e:
            write_log(f"Error checking composed image_pan video {composed}: {e}")
            return False
        return _finalize_scene_success(
            composed,
            is_s2v=False,
            success_message=f"Completed image_pan composition for {scene_dir}: {composed}",
        )

    if scene_type == 'image_zoom':
        _ensure_scene_json(scene_dir, 'image_zoom_prompt.json', DEFAULT_IMAGE_ZOOM_PROMPT)
        try:
            zoom_prompt = _read_scene_json(scene_dir, 'image_zoom_prompt.json', required=True)
        except Exception as e:
            write_log(f"Failed to read image_zoom_prompt.json for {scene_dir}: {e}")
            return False
        img_path = _find_latest_root_image(scene_dir)
        if not img_path:
            write_log(f"image_zoom scene requires at least one input image in root folder {scene_dir}")
            return False
        try:
            zoom_width = int(zoom_prompt.get('width', 480))
            zoom_height = int(zoom_prompt.get('height', 848))
            zoom_duration = float(scene_meta.get('duration_seconds', 5.0))
            zoom_direction = str(zoom_prompt.get('zoom_direction', 'in')).strip() or 'in'
            zoom_focal = str(zoom_prompt.get('focal_point', 'center')).strip() or 'center'
            zoom_strength = float(zoom_prompt.get('zoom_strength', 1.3))
        except Exception as e:
            write_log(f"Invalid image_zoom prompt value for {scene_dir}: {e}")
            return False
        if zoom_duration <= 0:
            write_log(f"Invalid scene duration for image_zoom in {scene_dir}: {zoom_duration}")
            return False
        composed = None
        last_error = None
        for attempt in range(1, 4):
            try:
                composed = generate_image_zoom_video(
                    scene_dir=scene_dir,
                    image_path=img_path,
                    width=zoom_width,
                    height=zoom_height,
                    duration_seconds=zoom_duration,
                    zoom_direction=zoom_direction,
                    focal_point=zoom_focal,
                    zoom_strength=zoom_strength,
                    fps=I2V_FPS,
                    capture_mode='stable_pan',
                )
                last_error = None
                break
            except Exception as e:
                last_error = e
                write_log(f"image_zoom attempt {attempt}/3 failed for {scene_dir}: {_safe_error_text(e)}")
                if attempt < 3:
                    time.sleep(1.0 * attempt)
        if last_error is not None or not composed:
            write_log(f"Failed to generate image_zoom video for {scene_dir}: {_safe_error_text(last_error)}")
            return False
        try:
            if not os.path.exists(composed) or os.path.getsize(composed) == 0:
                write_log(f"Composed image_zoom video missing or empty: {composed}")
                return False
        except Exception as e:
            write_log(f"Error checking composed image_zoom video {composed}: {e}")
            return False
        return _finalize_scene_success(
            composed,
            is_s2v=False,
            success_message=f"Completed image_zoom composition for {scene_dir}: {composed}",
        )

    write_log(f"Unsupported scene_type `{scene_type}` for {scene_dir}.")
    return False


def main():
    parser = argparse.ArgumentParser(description="Run content creation workflow via ComfyUI")
    parser.add_argument("--server", "-s", default=get_server_address("comfyui"), help="ComfyUI server host:port")
    parser.add_argument("--project", "-p", required=True, help="Nama project di dalam folder api_production")
    parser.add_argument("--scene", "-S", action='append', help='Scene name to process (e.g., scene_3). Repeatable to specify multiple scenes')
    parser.add_argument("--loop", "-L", type=int, default=1, help='Number of times to loop over the selected scenes (default: 1)')
    args = parser.parse_args()

    project_dir = os.path.join(API_PRODUCTION_ROOT, str(args.project).strip())
    if not os.path.isdir(project_dir):
        write_log(f"Project folder tidak ditemukan: {project_dir}")
        print(f"Project folder not found: {project_dir}")
        return 1
    try:
        project_settings = load_project_settings(Path(project_dir))
    except Exception as e:
        write_log(f"Gagal membaca project_settings.json: {e}")
        print(f"Gagal membaca project_settings.json: {e}")
        return 1
    project_generate_caption = bool(project_settings.get("caption", {}).get("generate_caption", True))
    scenes = sorted([d for d in os.listdir(project_dir) if d.startswith('scene_')], key=_scene_sort_key)

    # If user provided specific scenes, filter available scenes
    if args.scene:
        requested = set(args.scene)
        available = set(scenes)
        missing = requested - available
        for m in sorted(missing):
            print('Warning: requested scene not found:', m)
        scenes = [s for s in scenes if s in requested]
    if not scenes:
        write_log("Tidak ada scene yang cocok untuk diproses.")
        print("No matching scenes found")
        return 1

    # Validate loop count
    loop_count = int(args.loop or 1)
    if loop_count < 1:
        print('Loop count must be >= 1')
        return 1

    manage_runtime = project_uses_llama(project_dir)
    runtime_controller = RuntimeServiceController.from_config() if manage_runtime else None
    if runtime_controller is not None:
        write_log(f"[runtime] Pra-lokalisasi prompt project sebelum switch ComfyUI: {project_dir}")
        prepare_project_prompts_for_runtime(
            project_dir,
            scene_dirs=[os.path.join(project_dir, scene) for scene in scenes],
            log_fn=write_log,
        )
        runtime_controller.ensure_comfyui(reason=f"main.py project={args.project}")
    for loop_idx in range(loop_count):
        if loop_count > 1:
            print(f"Starting loop {loop_idx+1}/{loop_count}")
        for scene in scenes:
            scene_dir = os.path.join(project_dir, scene)
            print(f"Processing {scene_dir}")
            ok = process_scene(scene_dir, args.server, project_generate_caption=project_generate_caption)
            if not ok:
                write_log(f"Stopping run due to failure processing {scene}")
                print(f"Stopped due to failure in {scene}")
                return 1
    # Pertahankan service terakhir yang diperlukan. Jangan switch balik
    # otomatis ke Llama setelah workflow selesai.
    return 0



if __name__ == "__main__":
    sys.exit(main())
