import argparse
import os
import json
import time
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
from scripts.server_config import get_server_address
from scripts.workflow_builders import load_json
from z_image.z_image import (
    build_z_image_workflow,
    get_model_display_name as get_image_model_display_name,
    get_model_key as get_image_model_key,
    send_workflow as send_z_image_workflow,
)
from gemini.gemini_image import MODEL_GEMINI_IMAGE, generate_scene_image, is_gemini_prompt
from wan22_i2v.wan22_i2v import build_wan_workflow, send_workflow as send_wan_workflow
from wan22_s2v.wan22_s2v import (
    DEFAULT_PROMPT as DEFAULT_WAN22_S2V_PROMPT,
    MAX_AUDIO_DURATION as WAN22_S2V_MAX_AUDIO_DURATION,
    build_wan22_s2v_workflow,
    get_audio_duration as get_s2v_audio_duration,
    send_workflow as send_s2v_workflow,
    trim_video_to_speech_duration,
)
from logging_config import setup_logging, get_logger, write_log, RUN_ID
from scripts.generate_caption import apply_caption_to_video
from scripts.generate_compose import compose_scene
from scripts.generate_web_scroll_video import generate_web_scroll_video
from scripts.generate_image_pan_video import generate_image_pan_video
from prompt_localization import prepare_prompt_payload_for_save, read_json_for_runtime, resolve_prompt_payload_for_runtime


API_PRODUCTION_ROOT = os.path.join(os.path.dirname(__file__), 'api_production')
LOG_FILE = os.path.join(os.path.dirname(__file__), 'content_creation.log')
POLL_INTERVAL = 10.0
POLL_TIMEOUT = 600
WAN22_S2V_POLL_TIMEOUT = 2400
I2V_FPS = 16
WEB_SCROLL_FPS = 16
DEFAULT_WEB_SCROLL_PROMPT = {
    "url": "",
    "width": 368,
    "height": 640,
    "duration_seconds": 5.0,
    "speed": 1,
    "capture_mode": "stable_pan",
}
DEFAULT_IMAGE_PAN_PROMPT = {
    "width": 480,
    "height": 848,
    "direction": "from_right",
    "capture_mode": "stable_pan",
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



def process_scene(scene_dir, server):
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

    scene_type = scene_meta.get('scene_type', 'default')

    def _safe_error_text(err):
        text = str(err)
        # Keep logs single-line and console-safe on cp1252 terminals.
        text = " ".join(text.splitlines()).strip()
        return text.encode("cp1252", errors="replace").decode("cp1252")

    def _apply_caption_if_enabled(video_path):
        if not scene_meta.get("generate_caption", True):
            return True
        try:
            return apply_caption_to_video(Path(scene_dir), Path(video_path), overwrite=True)
        except Exception as e:
            write_log(f"Failed to apply caption for {scene_dir}: {e}")
            return False

    def _mix_scene_audio_to_video(video_path, is_s2v=False):
        # Mix using the exact compose-scene pipeline, but target only this generated video.
        # For s2v, keep the original video speech and only mix sound effects.
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
                include_video_audio=is_s2v,
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
            video_out = comfyui_api.wait_for_output(server, prompt_id, output_type='video', timeout=POLL_TIMEOUT, interval=POLL_INTERVAL)
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
        if not _mix_scene_audio_to_video(video_out_path, is_s2v=False):
            return False
        if not _apply_caption_if_enabled(video_out_path):
            return False
        write_log(f"Completed processing {scene_dir}")
        return True

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
                timeout=WAN22_S2V_POLL_TIMEOUT,
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
        if not _mix_scene_audio_to_video(video_out_path, is_s2v=True):
            return False
        if not _apply_caption_if_enabled(video_out_path):
            return False
        write_log(f"Completed processing {scene_dir}")
        return True

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
        if not _mix_scene_audio_to_video(composed, is_s2v=False):
            return False
        if not _apply_caption_if_enabled(composed):
            return False
        write_log(f"Completed i2v composition for {scene_dir}: {composed}")
        return True

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
        web_capture_mode = str(web_prompt.get('capture_mode', 'stable_pan')).strip() or 'stable_pan'
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
                    capture_mode=web_capture_mode,
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
        if not _mix_scene_audio_to_video(composed, is_s2v=False):
            return False
        if not _apply_caption_if_enabled(composed):
            return False
        write_log(f"Completed web_scroll composition for {scene_dir}: {composed}")
        return True

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
            pan_capture_mode = str(pan_prompt.get('capture_mode', 'stable_pan')).strip() or 'stable_pan'
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
                    capture_mode=pan_capture_mode,
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
        if not _mix_scene_audio_to_video(composed, is_s2v=False):
            return False
        if not _apply_caption_if_enabled(composed):
            return False
        write_log(f"Completed image_pan composition for {scene_dir}: {composed}")
        return True

    # default behavior: create initial image -> upload -> wan22 prompt -> wait/download video
    try:
        z_prompt = _read_scene_json(scene_dir, 'z_image_prompt.json', required=True)
        image_model_name = get_image_model_display_name(z_prompt)
    except Exception as e:
        write_log(f"Failed to read z_image prompt for {scene_dir}: {e}")
        return False

    image_out_path = None
    if is_gemini_prompt(z_prompt) or get_image_model_key(z_prompt) == MODEL_GEMINI_IMAGE:
        try:
            image_out_path = generate_scene_image(scene_dir, z_prompt)
        except Exception as e:
            write_log(f"Failed to generate Gemini image for {scene_dir}: {e}")
            return False
        if not image_out_path or not os.path.exists(image_out_path):
            write_log(f"Gemini image not found for {scene_dir}: {image_out_path}")
            return False
        if os.path.getsize(image_out_path) == 0:
            write_log(f"Gemini image is empty for {scene_dir}: {image_out_path}")
            return False
        write_log(f"Generated {image_model_name} image for {scene_dir}: {image_out_path}")
    else:
        try:
            z_workflow = build_z_image_workflow(z_prompt)
        except Exception as e:
            write_log(f"Failed to build z_image workflow for {scene_dir}: {e}")
            return False

        z_result = send_z_image_workflow(
            z_workflow,
            server,
            log_file=LOG_FILE,
            source_label=os.path.join(scene_dir, 'z_image_prompt.json'),
            model_name=image_model_name,
        )
        prompt_id = z_result.get('prompt_id') or z_result.get('id')
        write_log(f"Posted {image_model_name} workflow for {scene_dir}, prompt_id={prompt_id}")
        try:
            hist = comfyui_api.get_history_for_prompt(server, prompt_id)
            write_log(f"History for prompt_id={prompt_id}: {json.dumps(hist)}")
        except Exception as e:
            write_log(f"Failed to fetch history for prompt_id={prompt_id}: {e}")

        image_out = None
        if prompt_id:
            image_out = comfyui_api.wait_for_output(server, prompt_id, output_type='image', timeout=POLL_TIMEOUT, interval=POLL_INTERVAL)

        if not image_out:
            write_log(f"No image found for {scene_dir} (prompt_id={prompt_id}); stopping run")
            return False

        write_log(f"Image output info: {json.dumps(image_out)}")
        image_filename = image_out.get('filename') or image_out.get('name') or image_out.get('file')
        image_subfolder = image_out.get('subfolder')
        image_type = image_out.get('type')

        if not image_filename:
            write_log(f"Cannot determine image filename from output: {json.dumps(image_out)}")
            return False

        image_url = comfyui_api.get_file_url(server, image_filename, subfolder=image_subfolder, type_=image_type)
        image_out_path = os.path.join(scene_dir, image_filename)
        try:
            comfyui_api.download_file_url(image_url, image_out_path)
        except Exception as e:
            write_log(f"Failed to download image {image_filename} from {image_url}: {e}")
            return False

        try:
            if not os.path.exists(image_out_path) or os.path.getsize(image_out_path) == 0:
                write_log(f"Downloaded file missing or empty: {image_out_path}")
                return False
        except Exception as e:
            write_log(f"Error checking downloaded file {image_out_path}: {e}")
            return False

    try:
        upload_info = comfyui_api.upload_file(server, image_out_path)
        write_log(f"Upload response for {image_out_path}: {json.dumps(upload_info)}")
    except Exception as e:
        write_log(f"Upload failed for {image_out_path}: {e}")
        return False

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

    if returned_name and returned_name != image_filename:
        new_local_path = os.path.join(scene_dir, returned_name)
        try:
            os.replace(image_out_path, new_local_path)
            image_out_path = new_local_path
            uploaded_name = returned_name
            write_log(f"Local file renamed to match server: {returned_name}")
        except Exception as e:
            uploaded_name = returned_name
            write_log(f"Failed to rename local file to {returned_name}: {e} -- Using server-side name for workflow.")
    else:
        uploaded_name = returned_name or image_filename

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
    prompt_id = wan_result.get('prompt_id') or wan_result.get('id')
    write_log(f"Posted wan22 workflow for {scene_dir}, prompt_id={prompt_id}")

    try:
        wan_hist = comfyui_api.get_history_for_prompt(server, prompt_id)
        write_log(f"WAN history for prompt_id={prompt_id}: {json.dumps(wan_hist)}")
    except Exception as e:
        write_log(f"Failed to fetch WAN history for prompt_id={prompt_id}: {e}")

    video_out = None
    if prompt_id:
        video_out = comfyui_api.wait_for_output(server, prompt_id, output_type='video', timeout=POLL_TIMEOUT, interval=POLL_INTERVAL)

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

    if not _mix_scene_audio_to_video(video_out_path, is_s2v=False):
        return False
    if not _apply_caption_if_enabled(video_out_path):
        return False

    write_log(f"Completed processing {scene_dir}")
    return True


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

    for loop_idx in range(loop_count):
        if loop_count > 1:
            print(f"Starting loop {loop_idx+1}/{loop_count}")
        for scene in scenes:
            scene_dir = os.path.join(project_dir, scene)
            print(f"Processing {scene_dir}")
            ok = process_scene(scene_dir, args.server)
            if not ok:
                write_log(f"Stopping run due to failure processing {scene}")
                print(f"Stopped due to failure in {scene}")
                return 1
    return 0



if __name__ == "__main__":
    sys.exit(main())
