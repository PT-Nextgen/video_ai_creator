import copy
import json
import os
import random
import subprocess
import tempfile

from scripts import comfyui_api
from logging_config import get_logger, write_log

logger = get_logger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TEMPLATE = os.path.join(ROOT, "api_template")
TEMPLATE_B1 = "wan22_s2v_b1_api.json"
TEMPLATE_B2 = "wan22_s2v_b2_api.json"
TEMPLATE_B3 = "wan22_s2v_b3_api.json"
TEMPLATE_B4 = "wan22_s2v_b4_api.json"
MAX_AUDIO_DURATION = 19.2
SIZE_OPTIONS = [
    ("368x640", 368, 640),
    ("480x848", 480, 848),
    ("720x1280", 720, 1280),
    ("640x368", 640, 368),
    ("848x480", 848, 480),
    ("1280x720", 1280, 720),
]
DEFAULT_PROMPT = {
    "positive_prompt": "This presenter is explaining an audio-related topic and stares into the camera.",
    "negative_prompt": (
        "unnatural body bending, torso twisting, shoulders shifting randomly, floating torso, body stretching or shrinking between frames, "
        "neck elongation, missing neck, spine distortion, arms crossing through body, uneven shoulder height, body flicker, scale inconsistency, "
        "posture warping, unnatural leaning, body vibrating, torso intersecting microphone or logo, jittering position. deformed hands, extra fingers, "
        "missing fingers, finger fusion, bent backward fingers, floating or disconnected hands, hands merging with body or microphone, oversized or "
        "undersized hands, inconsistent hand position between frames, hands appearing or disappearing suddenly, double hands, palm distortion, wrist "
        "twisting unnaturally, jittery finger motion, fingernails flickering. face deformation, asymmetric expression, melted face, mouth jitter, lip "
        "morphing, teeth distortion, lips fusing together, over-wide mouth opening, head wobble, unnatural blinking, flickering eyes, eyes misaligned, "
        "double pupils, eyelids vanishing, mouth desync with emotion, nose distortion, nostril stretching, jaw popping, head turning unnaturally fast, "
        "facial morph between frames, ghosting face, duplicated face overlay, stretched or shrinking head, hair flickering or detaching. flickering "
        "brightness, inconsistent exposure, sudden lighting change, shadow popping, overexposed highlights, underexposed shadows, lighting shifting "
        "direction, unrealistic glow, color banding, inconsistent white balance, color drift, glowing artifacts on skin, over-saturated tones, "
        "inconsistent HDR lighting.frame flicker, motion jitter, ghosting, double exposure, temporal aliasing, inconsistent motion, frame skipping, "
        "motion blur hiding facial features, lagging body parts, warped motion trails, interpolation ghost artifacts, unstable subject position, "
        "camera shake, unintentional zoom or pan, inconsistent focus depth, frame-to-frame brightness variation. extra limbs, duplicated torso, mutated "
        "anatomy, disproportionate body parts, merged geometry, invisible body sections, stretched polygons, low-resolution mesh artifacts, silhouette "
        "flicker, melting texture, glitch noise, non-human facial shape, random artifacts near edges."
    ),
    "width": 480,
    "height": 848,
    "cfg": 2.0,
    "json_api": "auto_by_speech_duration",
}


def _load_template(name: str) -> dict:
    path = os.path.join(API_TEMPLATE, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_audio_duration(audio_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe gagal membaca durasi audio: {result.stderr.strip()}")
    return float(result.stdout.strip())


def get_video_duration(video_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe gagal membaca durasi video: {result.stderr.strip()}")
    return float(result.stdout.strip())


def get_video_fps(video_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=avg_frame_rate,r_frame_rate",
        "-of",
        "default=noprint_wrappers=1",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe gagal membaca fps video: {result.stderr.strip()}")
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        _, value = line.split("=", 1)
        value = value.strip()
        if not value or value == "0/0":
            continue
        if "/" in value:
            num, den = value.split("/", 1)
            try:
                num_f = float(num)
                den_f = float(den)
            except ValueError:
                continue
            if den_f != 0:
                return num_f / den_f
        else:
            try:
                return float(value)
            except ValueError:
                continue
    return 24.0


def get_template_name(audio_duration: float) -> str:
    if audio_duration >= MAX_AUDIO_DURATION:
        raise ValueError(f"Durasi audio speech WAN22 S2V harus kurang dari {MAX_AUDIO_DURATION} detik.")
    if audio_duration < 4.8:
        return TEMPLATE_B1
    if audio_duration < 9.6:
        return TEMPLATE_B2
    if audio_duration < 14.4:
        return TEMPLATE_B3
    return TEMPLATE_B4


def build_workflow(s2v_prompt: dict, image_name: str, audio_name: str, audio_duration: float) -> dict:
    workflow = copy.deepcopy(_load_template(get_template_name(audio_duration)))

    if "6" in workflow and isinstance(workflow["6"], dict):
        inputs = workflow["6"].get("inputs")
        if isinstance(inputs, dict):
            inputs["text"] = s2v_prompt.get("positive_prompt", DEFAULT_PROMPT["positive_prompt"])

    if "7" in workflow and isinstance(workflow["7"], dict):
        inputs = workflow["7"].get("inputs")
        if isinstance(inputs, dict):
            inputs["text"] = s2v_prompt.get("negative_prompt", DEFAULT_PROMPT["negative_prompt"])

    try:
        width = int(s2v_prompt.get("width", DEFAULT_PROMPT["width"]))
    except (TypeError, ValueError):
        width = DEFAULT_PROMPT["width"]
    try:
        height = int(s2v_prompt.get("height", DEFAULT_PROMPT["height"]))
    except (TypeError, ValueError):
        height = DEFAULT_PROMPT["height"]

    if "93" in workflow and isinstance(workflow["93"], dict):
        inputs = workflow["93"].get("inputs")
        if isinstance(inputs, dict):
            inputs["width"] = width
            inputs["height"] = height

    try:
        cfg_value = float(s2v_prompt.get("cfg", DEFAULT_PROMPT["cfg"]))
    except (TypeError, ValueError):
        cfg_value = DEFAULT_PROMPT["cfg"]
    cfg_value = max(1.0, min(6.0, cfg_value))
    if "105" in workflow and isinstance(workflow["105"], dict):
        inputs = workflow["105"].get("inputs")
        if isinstance(inputs, dict):
            inputs["value"] = cfg_value

    if "52" in workflow and isinstance(workflow["52"], dict):
        inputs = workflow["52"].get("inputs")
        if isinstance(inputs, dict):
            inputs["image"] = image_name

    if "58" in workflow and isinstance(workflow["58"], dict):
        inputs = workflow["58"].get("inputs")
        if isinstance(inputs, dict):
            inputs["audio"] = audio_name
            if "audioUI" in inputs:
                inputs["audioUI"] = f"/api/view?filename={audio_name}&type=input&subfolder=&rand={random.random()}"

    if "3" in workflow and isinstance(workflow["3"], dict):
        inputs = workflow["3"].get("inputs")
        if isinstance(inputs, dict):
            inputs["seed"] = random.randint(10**15, 10**16 - 1)

    return workflow


def build_wan22_s2v_workflow(s2v_prompt: dict, image_name: str, audio_name: str, audio_duration: float) -> dict:
    return build_workflow(s2v_prompt, image_name, audio_name, audio_duration)


def trim_video_to_speech_duration(video_path: str, speech_duration: float, max_extra_frames: int = 4) -> float:
    video_duration = get_video_duration(video_path)
    fps = get_video_fps(video_path)
    if fps <= 0:
        fps = 24.0
    extra_seconds = max_extra_frames / fps
    target_duration = min(video_duration, speech_duration + min(extra_seconds, max(0.0, video_duration - speech_duration)))
    # Skip tiny/no-op trims.
    if target_duration <= 0 or video_duration - target_duration < 0.001:
        return video_duration

    temp_dir = os.path.dirname(os.path.abspath(video_path)) or None
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=os.path.splitext(video_path)[1],
        dir=temp_dir,
    ) as tmp:
        temp_path = tmp.name
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-t",
            f"{target_duration:.6f}",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            temp_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg gagal memotong video: {result.stderr.strip()}")
        os.replace(temp_path, video_path)
        return target_duration
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def send_workflow(workflow, server, log_file=None, source_label="in-memory workflow"):
    result = comfyui_api.post_workflow_api(workflow, server)
    if log_file:
        with open(log_file, "a", encoding="utf-8") as log:
            log.write(f"Sent {source_label}\nResult: {json.dumps(result)}\n")
    write_log(f"Sent wan22_s2v workflow {source_label}: {json.dumps(result)}", extra={"source_label": source_label})
    return result
