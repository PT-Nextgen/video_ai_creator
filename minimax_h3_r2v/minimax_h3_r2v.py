"""Build an in-memory MiniMax H3 Reference-to-Video workflow.

The adapter starts from ``api_template/minimax_h3_r2v_api.json`` and removes
reference nodes/connections when the corresponding assets are not available.
The source template is never modified and no generated workflow is written to
disk.
"""

from __future__ import annotations

import copy
import json
import os
import random
import subprocess
from collections.abc import Mapping

from scripts import comfyui_api
from logging_config import write_log
from minimax_h3_prompt import empty_ref2va_prompt, serialize_ref2va_prompt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TEMPLATE = os.path.join(ROOT, "api_template")
TEMPLATE = "minimax_h3_r2v_api.json"
MAIN_NODE = "136"
PICTURE_1_NODE = "143"
AUDIO_1_NODE = "153"
MAX_AUDIO_DURATION = 15.0
MAX_DURATION = 15

SIZE_OPTIONS = [
    ("368x640", 368, 640),
    ("480x848", 480, 848),
    ("720x1280", 720, 1280),
    ("640x368", 640, 368),
    ("848x480", 848, 480),
    ("1280x720", 1280, 720),
]

RESOLUTION_MAP = {
    (368, 640): ("9:16 (Portrait Widescreen)", 0.2),
    (480, 848): ("9:16 (Portrait Widescreen)", 0.4),
    (720, 1280): ("9:16 (Portrait Widescreen)", 0.9),
    (640, 368): ("16:9 (Widescreen)", 0.2),
    (848, 480): ("16:9 (Widescreen)", 0.4),
    (1280, 720): ("16:9 (Widescreen)", 0.9),
}

DEFAULT_S2V_ID_PROMPT = {
    "subject_definitions": "<Picture 1> adalah bingkai awal dan referensi visual untuk seluruh video. <Subject 1> adalah wanita dalam <Picture 1>. <Audio 1> adalah rekaman ucapan yang harus digunakan secara utuh untuk suara <Subject 1> (S1).",
    "summary": "[keyframe completion + audio reuse] Buat avatar berbicara sederhana dari <Picture 1>, dengan <Subject 1> mengucapkan audio dari <Audio 1> secara sinkron.",
    "retention_analysis": "<Picture 1> (bingkai awal dan komposisi): fully_preserved - pertahankan tampilan, pose, pencahayaan, latar belakang, dan framing. <Subject 1> (sepanjang video): fully_preserved - pertahankan identitas, wajah, pakaian, dan posisi tubuh. <Audio 1>: fully_copy - gunakan rekaman ucapan lengkap tanpa mengubah isi atau waktunya.",
    "detailed_description": "[Shot 1] Video dimulai tepat dari <Picture 1>. Kamera terkunci dan seluruh komposisi tetap diam. <Subject 1> (S1) tetap pada pose yang sama dan hanya menggerakkan bibir serta mulut seperlunya agar sinkron secara alami dengan ucapan dari <Audio 1>. Setelah seluruh ucapan dalam <Audio 1> selesai, <Subject 1> (S1) berhenti menggerakkan bibir dan tetap diam sampai video berakhir. Jangan tambahkan gerakan kepala, tubuh, tangan, kamera, latar belakang, atau objek lain.",
    "overall_soundscape": "Gunakan hanya rekaman suara asli dari <Audio 1>, tersinkron dengan gerakan bibir <Subject 1> (S1). Setelah <Audio 1> selesai, pertahankan keheningan sampai video berakhir. Jangan tambahkan ambience atau efek suara.",
    "non_diegetic_music": "N/A",
}

DEFAULT_S2V_EN_PROMPT = {
    "subject_definitions": "<Picture 1> is the initial frame and visual reference for the entire video. <Subject 1> is the woman in <Picture 1>. <Audio 1> is the complete speech recording that must be used for <Subject 1> (S1).",
    "summary": "[keyframe completion + audio reuse] Create a simple talking avatar from <Picture 1>, with <Subject 1> speaking the audio from <Audio 1> in sync.",
    "retention_analysis": "<Picture 1> (initial frame and composition): fully_preserved - preserve the appearance, pose, lighting, background, and framing. <Subject 1> (throughout the video): fully_preserved - preserve her identity, face, clothing, and body position. <Audio 1>: fully_copy - use the complete speech recording without changing its content or timing.",
    "detailed_description": "[Shot 1] The video begins exactly from <Picture 1>. The camera is locked and the entire composition remains still. <Subject 1> (S1) stays in the same pose and moves only her lips and mouth as needed to synchronize naturally with the speech from <Audio 1>. After all speech in <Audio 1> has finished, <Subject 1> (S1) stops moving her lips and remains completely still until the video ends. Do not add head, body, hand, camera, background, or object movement.",
    "overall_soundscape": "Use only the original voice recording from <Audio 1>, synchronized with the lip movement of <Subject 1> (S1). After <Audio 1> finishes, maintain silence until the video ends. Do not add ambience or sound effects.",
    "non_diegetic_music": "N/A",
}

DEFAULT_PROMPT = {
    "positive_prompt": {
        "id_old": copy.deepcopy(DEFAULT_S2V_ID_PROMPT),
        "id_new": copy.deepcopy(DEFAULT_S2V_ID_PROMPT),
        "en": copy.deepcopy(DEFAULT_S2V_EN_PROMPT),
    },
    "width": 368,
    "height": 640,
    "fps": 24,
    "lora_name": "MINIMAX-H3/AI-Girl-Fictional.safetensors",
    "lora_strength": 0,
    "lora_name_2": "MINIMAX-H3/AI-Girl-Fictional.safetensors",
    "lora_strength_2": 0,
}

DEFAULT_R2V_PROMPT = {
    "positive_prompt": {
        "id_old": {
            "subject_definitions": "Adegan memiliki subjek utama yang menjadi fokus video.",
            "summary": "Video menampilkan subjek utama dalam adegan sinematik yang koheren.",
            "retention_analysis": "Identitas dan kesinambungan subjek utama dipertahankan sepanjang video.",
            "detailed_description": "[Shot 1] Video dimulai dengan subjek utama dalam komposisi sinematik, lalu bergerak secara alami dengan pencahayaan yang konsisten.",
            "overall_soundscape": "Suasana suara mengikuti lingkungan dan aksi yang terlihat dalam adegan.",
            "non_diegetic_music": "N/A",
        },
        "id_new": {
            "subject_definitions": "Adegan memiliki subjek utama yang menjadi fokus video.",
            "summary": "Video menampilkan subjek utama dalam adegan sinematik yang koheren.",
            "retention_analysis": "Identitas dan kesinambungan subjek utama dipertahankan sepanjang video.",
            "detailed_description": "[Shot 1] Video dimulai dengan subjek utama dalam komposisi sinematik, lalu bergerak secara alami dengan pencahayaan yang konsisten.",
            "overall_soundscape": "Suasana suara mengikuti lingkungan dan aksi yang terlihat dalam adegan.",
            "non_diegetic_music": "N/A",
        },
        "en": {
            "subject_definitions": "The scene contains a primary subject that remains the focus of the video.",
            "summary": "The video presents the primary subject in a coherent cinematic scene.",
            "retention_analysis": "The identity and continuity of the primary subject are preserved throughout the video.",
            "detailed_description": "[Shot 1] The video begins with the primary subject in a cinematic composition, then develops naturally with consistent lighting.",
            "overall_soundscape": "The soundscape follows the environment and visible actions in the scene.",
            "non_diegetic_music": "N/A",
        },
    },
    "width": 368,
    "height": 640,
    "fps": 24,
    "references": {"images": [], "video": "", "audios": []},
    "lora_name": "MINIMAX-H3/AI-Girl-Fictional.safetensors",
    "lora_strength": 0,
    "lora_name_2": "MINIMAX-H3/AI-Girl-Fictional.safetensors",
    "lora_strength_2": 0,
}


def _load_template(name: str = TEMPLATE) -> dict:
    path = os.path.join(API_TEMPLATE, name)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def get_audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", audio_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe gagal membaca durasi audio: {result.stderr.strip()}")
    return float(result.stdout.strip())


def _remove_node(workflow: dict, node_id: str) -> bool:
    return workflow.pop(str(node_id), None) is not None


def _remove_input(workflow: dict, node_id: str, input_name: str) -> bool:
    node = workflow.get(str(node_id))
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, dict):
        return False
    return inputs.pop(input_name, None) is not None


def remove_picture_2(workflow: dict) -> dict:
    """Remove Picture 2 node 144 and ``ref_image_1`` from node 136."""
    _remove_node(workflow, "144")
    _remove_input(workflow, MAIN_NODE, "ref_images.ref_image_1")
    return workflow


def remove_picture_1(workflow: dict) -> dict:
    """Remove Picture 1 node 143 and ``ref_image_0`` from node 136."""
    _remove_node(workflow, PICTURE_1_NODE)
    _remove_input(workflow, MAIN_NODE, "ref_images.ref_image_0")
    return workflow


def remove_picture_3(workflow: dict) -> dict:
    """Remove Picture 3 node 151 and ``ref_image_2`` from node 136."""
    _remove_node(workflow, "151")
    _remove_input(workflow, MAIN_NODE, "ref_images.ref_image_2")
    return workflow


def remove_video_1(workflow: dict) -> dict:
    """Remove Video 1 and both its video and synchronized-audio connections."""
    _remove_node(workflow, "152")
    _remove_input(workflow, MAIN_NODE, "ref_videos.ref_video_0")
    _remove_input(workflow, MAIN_NODE, "ref_video_audios.ref_video_audio_0")
    return workflow


def remove_audio_1(workflow: dict) -> dict:
    """Remove Audio 1 node 153 and ``ref_audio_0`` from node 136."""
    _remove_node(workflow, "153")
    _remove_input(workflow, MAIN_NODE, "ref_audios.ref_audio_0")
    return workflow


def remove_audio_2(workflow: dict) -> dict:
    """Remove Audio 2 node 154 and ``ref_audio_1`` from node 136."""
    _remove_node(workflow, "154")
    _remove_input(workflow, MAIN_NODE, "ref_audios.ref_audio_1")
    return workflow


def remove_audio_3(workflow: dict) -> dict:
    """Remove Audio 3 node 155 and ``ref_audio_2`` from node 136."""
    _remove_node(workflow, "155")
    _remove_input(workflow, MAIN_NODE, "ref_audios.ref_audio_2")
    return workflow


def remove_references(
    workflow: dict,
    *,
    remove_picture_2_reference: bool = False,
    remove_picture_3_reference: bool = False,
    remove_video_1_reference: bool = False,
    remove_audio_1_reference: bool = False,
    remove_audio_2_reference: bool = False,
    remove_audio_3_reference: bool = False,
    remove_picture_1_reference: bool = False,
) -> dict:
    """Remove selected R2V assets from an existing in-memory workflow."""
    if remove_picture_1_reference:
        remove_picture_1(workflow)
    if remove_picture_2_reference:
        remove_picture_2(workflow)
    if remove_picture_3_reference:
        remove_picture_3(workflow)
    if remove_video_1_reference:
        remove_video_1(workflow)
    if remove_audio_1_reference:
        remove_audio_1(workflow)
    if remove_audio_2_reference:
        remove_audio_2(workflow)
    if remove_audio_3_reference:
        remove_audio_3(workflow)
    return workflow


def _set_resolution_selector(workflow: dict, width: int, height: int) -> bool:
    node = workflow.get("115")
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, dict):
        return False
    aspect_ratio, megapixels = RESOLUTION_MAP.get(
        (int(width), int(height)),
        RESOLUTION_MAP[(368, 640)],
    )
    inputs["aspect_ratio"] = aspect_ratio
    inputs["megapixels"] = megapixels
    inputs["multiple"] = 32
    return True


def _set_duration(workflow: dict, duration) -> bool:
    node = workflow.get("132")
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, dict):
        return False
    try:
        inputs["value"] = float(duration)
    except (TypeError, ValueError):
        inputs["value"] = 5.0
    return True


def _set_asset(workflow: dict, node_id: str, input_name: str, value) -> bool:
    node = workflow.get(str(node_id))
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, dict) or not value:
        return False
    inputs[input_name] = str(value)
    return True


def _set_input(workflow: dict, node_id: str, key: str, value) -> bool:
    node = workflow.get(str(node_id))
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, dict) or key not in inputs:
        return False
    inputs[key] = value
    return True


def _inject_random_noise_seed(workflow: dict):
    seed = random.randint(10**15, 10**16 - 1)
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if isinstance(inputs, dict) and "noise_seed" in inputs:
            inputs["noise_seed"] = seed
    return workflow


def _prompt_text(prompt) -> str:
    if isinstance(prompt, str):
        return prompt
    if not isinstance(prompt, Mapping):
        return ""
    if isinstance(prompt.get("prompt"), str):
        return prompt["prompt"]
    positive = prompt.get("positive_prompt")
    if isinstance(positive, str):
        return positive
    if isinstance(positive, Mapping):
        for key in ("en", "id_new", "id_old"):
            value = positive.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, Mapping):
                return serialize_ref2va_prompt(value)
    return ""


def _set_prompt(workflow: dict, prompt) -> bool:
    node = workflow.get(MAIN_NODE)
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, dict):
        return False
    inputs["prompt"] = _prompt_text(prompt)
    return True


def _set_lora_node(workflow: dict, node_id: str, lora_name: str, strength_value) -> bool:
    node = workflow.get(str(node_id))
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, dict):
        return False
    inputs["lora_name"] = str(lora_name or "")
    try:
        inputs["strength_model"] = float(strength_value)
    except (TypeError, ValueError):
        inputs["strength_model"] = 0.0
    return True


def build_workflow(
    prompt=None,
    scene_meta: dict | None = None,
    width: int | None = None,
    height: int | None = None,
    duration_override: int | float | None = None,
    fps_override: int | None = None,
    image_name: str | None = None,
    audio_name: str | None = None,
    image_names: list[str] | None = None,
    audio_names: list[str] | None = None,
    video_name: str | None = None,
    **remove_options,
) -> dict:
    """Return a configured R2V workflow in memory.

    ``remove_options`` accepts the keyword flags documented by
    :func:`remove_references`. Unknown flags are rejected to avoid silently
    keeping or deleting the wrong reference.
    """
    allowed = {
        "remove_picture_1_reference",
        "remove_picture_2_reference",
        "remove_picture_3_reference",
        "remove_video_1_reference",
        "remove_audio_1_reference",
        "remove_audio_2_reference",
        "remove_audio_3_reference",
    }
    unknown = set(remove_options) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise TypeError(f"Unknown R2V reference removal option(s): {names}")

    workflow = copy.deepcopy(_load_template())
    _set_prompt(workflow, prompt)

    # New R2V callers provide compact lists. The legacy image_name/audio_name
    # arguments remain supported for the existing MiniMax H3 S2V scene.
    if image_names is None:
        image_names = [image_name] if image_name else []
    if audio_names is None:
        audio_names = [audio_name] if audio_name else []
    image_names = [str(value).strip() for value in image_names[:3] if str(value or "").strip()]
    audio_names = [str(value).strip() for value in audio_names[:3] if str(value or "").strip()]
    video_name = str(video_name or "").strip()

    source = prompt if isinstance(prompt, Mapping) else {}
    if width is None:
        width = source.get("width", 368) if isinstance(source, Mapping) else 368
    if height is None:
        height = source.get("height", 640) if isinstance(source, Mapping) else 640
    try:
        width = int(width)
    except (TypeError, ValueError):
        width = 368
    try:
        height = int(height)
    except (TypeError, ValueError):
        height = 640
    _set_resolution_selector(workflow, width, height)

    duration = duration_override
    if duration is None and isinstance(scene_meta, dict):
        duration = scene_meta.get("duration_seconds")
    if duration is None and isinstance(source, Mapping):
        duration = source.get("duration_seconds", source.get("duration"))
    _set_duration(workflow, 5 if duration is None else duration)
    fps = fps_override if fps_override is not None else source.get("fps", 24)
    try:
        fps = int(fps)
    except (TypeError, ValueError):
        fps = 24
    _set_input(workflow, "130", "fps", fps)
    frame_expression = (
        f"max(5, round(a * {fps})) + "
        f"(5 - (max(5, round(a * {fps})) % 17)) % 17"
    )
    _set_input(workflow, "131", "expression", frame_expression)

    picture_nodes = (PICTURE_1_NODE, "144", "151")
    audio_nodes = (AUDIO_1_NODE, "154", "155")
    for index, node_id in enumerate(picture_nodes):
        if index < len(image_names):
            _set_asset(workflow, node_id, "image", image_names[index])
        else:
            remove_references(workflow, **{f"remove_picture_{index + 1}_reference": True})
    if video_name:
        _set_asset(workflow, "152", "video", video_name)
    else:
        remove_video_1(workflow)
    for index, node_id in enumerate(audio_nodes):
        if index < len(audio_names):
            _set_asset(workflow, node_id, "audio", audio_names[index])
        else:
            remove_references(workflow, **{f"remove_audio_{index + 1}_reference": True})

    workflow = remove_references(workflow, **remove_options)
    _set_lora_node(
        workflow,
        "156",
        source.get("lora_name", DEFAULT_PROMPT["lora_name"]),
        source.get("lora_strength", DEFAULT_PROMPT["lora_strength"]),
    )
    _set_lora_node(
        workflow,
        "157",
        source.get("lora_name_2", DEFAULT_PROMPT["lora_name_2"]),
        source.get("lora_strength_2", DEFAULT_PROMPT["lora_strength_2"]),
    )
    return _inject_random_noise_seed(workflow)


def build_minimax_h3_r2v_workflow(
    prompt=None,
    scene_meta: dict | None = None,
    width: int | None = None,
    height: int | None = None,
    duration_override: int | float | None = None,
    fps_override: int | None = None,
    image_name: str | None = None,
    audio_name: str | None = None,
    image_names: list[str] | None = None,
    audio_names: list[str] | None = None,
    video_name: str | None = None,
    **remove_options,
) -> dict:
    """Named adapter entry point matching the other MiniMax H3 modules."""
    return build_workflow(
        prompt,
        scene_meta=scene_meta,
        width=width,
        height=height,
        duration_override=duration_override,
        fps_override=fps_override,
        image_name=image_name,
        audio_name=audio_name,
        image_names=image_names,
        audio_names=audio_names,
        video_name=video_name,
        **remove_options,
    )


def get_template_name(prompt: dict | None = None) -> str:
    return TEMPLATE


def get_step_template_name(prompt: dict | None = None) -> str:
    return TEMPLATE


def send_workflow(workflow, server, log_file=None, source_label="in-memory workflow"):
    """Send an already-built in-memory workflow to ComfyUI."""
    prompt = ""
    main_node = workflow.get(MAIN_NODE) if isinstance(workflow, dict) else None
    if isinstance(main_node, dict):
        prompt = main_node.get("inputs", {}).get("prompt", "")
    message = f"Prompt MiniMax H3 R2V dikirim ke ComfyUI untuk {source_label}:\n{prompt}"
    write_log(message, extra={"source_label": source_label})
    result = comfyui_api.post_workflow_api(workflow, server)
    write_log(
        f"Sent minimax_h3_r2v workflow for {source_label}: {json.dumps(result)}",
        extra={"source_label": source_label},
    )
    if log_file:
        with open(log_file, "a", encoding="utf-8") as handle:
            handle.write(message + "\n")
            handle.write(f"Result: {json.dumps(result)}\n")
    return result
