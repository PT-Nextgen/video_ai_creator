"""Fast MiniMax H3 image-to-video workflow adapter."""

from __future__ import annotations

import copy
import json
import os
import random

from minimax_h3.minimax_h3_prompt import (
    I2VA_FIRST_SHOT_VISUAL_EN,
    I2VA_FIRST_SHOT_VISUAL_ID,
    default_structured_prompt,
    ensure_i2va_frame_instructions,
    serialize_structured_prompt,
    structured_prompt_entry,
)
from scripts import comfyui_api
from logging_config import get_logger, write_log

logger = get_logger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TEMPLATE = os.path.join(ROOT, "api_template")
TEMPLATE = "minimax_fasth3_i2v_api.json"
FAST_LAST_FRAME_NODE_ID = "165"

SIZE_OPTIONS = [
    ("368x640", 368, 640),
    ("480x848", 480, 848),
    ("720x1280", 720, 1280),
    ("640x368", 640, 368),
    ("848x480", 848, 480),
    ("1280x720", 1280, 720),
]

_DEFAULT_I2VA_ID_NEW = default_structured_prompt("I2VA")
_DEFAULT_I2VA_ID_NEW["shots"][0]["visual"] = I2VA_FIRST_SHOT_VISUAL_ID
_DEFAULT_I2VA_EN = default_structured_prompt("I2VA")
_DEFAULT_I2VA_EN["shots"][0]["visual"] = I2VA_FIRST_SHOT_VISUAL_EN
DEFAULT_PROMPT = {
    "positive_prompt": structured_prompt_entry(
        "I2VA",
        id_new=_DEFAULT_I2VA_ID_NEW,
        en=_DEFAULT_I2VA_EN,
    ),
    "lora_name": "MINIMAX-H3/AI-Girl-Fictional.safetensors",
    "lora_strength": 0,
    "lora_name_2": "MINIMAX-H3/AI-Girl-Fictional.safetensors",
    "lora_strength_2": 0,
    "width": 368,
    "height": 640,
    "fps": 24,
    "remove_sound": False,
    "fast_mode": True,
}


def _load_template() -> dict:
    with open(os.path.join(API_TEMPLATE, TEMPLATE), "r", encoding="utf-8") as handle:
        return json.load(handle)


def _set_input(workflow: dict, node_id: str, key: str, value) -> bool:
    node = workflow.get(str(node_id))
    if not isinstance(node, dict):
        return False
    inputs = node.get("inputs")
    if not isinstance(inputs, dict) or key not in inputs:
        return False
    inputs[key] = value
    return True


def _set_lora_node(workflow: dict, node_id: str, lora_name: str, strength_value) -> bool:
    node = workflow.get(str(node_id))
    if not isinstance(node, dict):
        return False
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return False
    inputs["lora_name"] = str(lora_name or "")
    try:
        inputs["strength_model"] = float(str(strength_value))
    except (TypeError, ValueError):
        inputs["strength_model"] = 0.0
    return True


def _set_resolution_selector(workflow: dict, width: int, height: int) -> bool:
    node = workflow.get("164")
    if not isinstance(node, dict):
        return False
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return False
    resolution_map = {
        (368, 640): ("9:16 (Portrait Widescreen)", 0.2),
        (480, 848): ("9:16 (Portrait Widescreen)", 0.4),
        (720, 1280): ("9:16 (Portrait Widescreen)", 0.9),
        (640, 368): ("16:9 (Widescreen)", 0.2),
        (848, 480): ("16:9 (Widescreen)", 0.4),
        (1280, 720): ("16:9 (Widescreen)", 0.9),
    }
    aspect_ratio, megapixels = resolution_map.get(
        (int(width), int(height)), resolution_map[(368, 640)]
    )
    inputs["aspect_ratio"] = aspect_ratio
    inputs["megapixels"] = megapixels
    inputs["multiple"] = 32
    return True


def _inject_random_noise_seed(workflow: dict) -> dict:
    seed = random.randint(10**15, 10**16 - 1)
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if isinstance(inputs, dict) and "noise_seed" in inputs:
            inputs["noise_seed"] = seed
    return workflow


def _frame_expression(fps: int = 24) -> str:
    return (
        f"max(5, round(a * {fps})) + "
        f"(5 - (max(5, round(a * {fps})) % 17)) % 17"
    )


def _set_last_frame(workflow: dict, last_frame_uploaded_name: str | None) -> None:
    node = workflow.get("156")
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, dict):
        return
    if last_frame_uploaded_name:
        workflow[FAST_LAST_FRAME_NODE_ID] = {
            "inputs": {"image": str(last_frame_uploaded_name)},
            "class_type": "LoadImage",
            "_meta": {"title": "Load Last Frame"},
        }
        inputs["last_frame"] = [FAST_LAST_FRAME_NODE_ID, 0]
    else:
        workflow.pop(FAST_LAST_FRAME_NODE_ID, None)
        inputs.pop("last_frame", None)


def get_template_name(prompt: dict | None = None) -> str:
    return TEMPLATE


def get_step_template_name(prompt: dict | None = None) -> str:
    return TEMPLATE


def build_workflow(
    i2v_prompt: dict,
    scene_meta: dict | None = None,
    uploaded_name: str | None = None,
    duration_override: int | float | None = None,
    fps_override: int | None = None,
    last_frame_uploaded_name: str | None = None,
) -> dict:
    prompt = i2v_prompt if isinstance(i2v_prompt, dict) else {}
    workflow = copy.deepcopy(_load_template())

    try:
        width = int(prompt.get("width", DEFAULT_PROMPT["width"]))
    except (TypeError, ValueError):
        width = DEFAULT_PROMPT["width"]
    try:
        height = int(prompt.get("height", DEFAULT_PROMPT["height"]))
    except (TypeError, ValueError):
        height = DEFAULT_PROMPT["height"]
    _set_resolution_selector(workflow, width, height)

    duration = duration_override
    if duration is None and isinstance(scene_meta, dict):
        duration = scene_meta.get("duration_seconds")
    if duration is None:
        duration = 5
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = 5.0

    positive_value = prompt.get("positive_prompt", DEFAULT_PROMPT["positive_prompt"])
    if isinstance(positive_value, dict):
        positive_value = ensure_i2va_frame_instructions(
            positive_value,
            duration,
            include_last_frame=bool(last_frame_uploaded_name),
        )
    if isinstance(positive_value, dict) and isinstance(positive_value.get("en"), dict):
        positive_prompt = serialize_structured_prompt(positive_value["en"])
    else:
        positive_prompt = str(positive_value or "")
    _set_input(workflow, "156", "prompt", positive_prompt)

    _set_input(workflow, "158", "value", duration)
    fps = 24
    _set_input(workflow, "155", "fps", fps)
    _set_input(workflow, "157", "expression", _frame_expression(fps))

    if uploaded_name:
        _set_input(workflow, "136", "image", str(uploaded_name))
    _set_last_frame(workflow, last_frame_uploaded_name)

    # Preserve the existing semantic mapping: lora_name is LoRA 1 and
    # lora_name_2 is LoRA 2. LoRA 2 is upstream in the FastH3 graph.
    _set_lora_node(
        workflow,
        "163",
        prompt.get("lora_name", DEFAULT_PROMPT["lora_name"]),
        prompt.get("lora_strength", DEFAULT_PROMPT["lora_strength"]),
    )
    _set_lora_node(
        workflow,
        "162",
        prompt.get("lora_name_2", DEFAULT_PROMPT["lora_name_2"]),
        prompt.get("lora_strength_2", DEFAULT_PROMPT["lora_strength_2"]),
    )
    return _inject_random_noise_seed(workflow)


def build_minimax_h3fast_i2v_workflow(
    i2v_prompt: dict,
    scene_meta: dict | None = None,
    uploaded_name: str | None = None,
    duration_override: int | float | None = None,
    fps_override: int | None = None,
    last_frame_uploaded_name: str | None = None,
) -> dict:
    return build_workflow(
        i2v_prompt,
        scene_meta=scene_meta,
        uploaded_name=uploaded_name,
        duration_override=duration_override,
        fps_override=fps_override,
        last_frame_uploaded_name=last_frame_uploaded_name,
    )


def send_workflow(
    workflow,
    uploaded_name,
    server,
    log_file=None,
    source_label="in-memory workflow",
    last_frame_uploaded_name=None,
):
    if uploaded_name:
        _set_input(workflow, "136", "image", str(uploaded_name))
    _set_last_frame(workflow, last_frame_uploaded_name)

    prompt_logs = []
    for node_id, node in (workflow or {}).items():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if isinstance(inputs, dict) and "prompt" in inputs:
            prompt_logs.append(f"node={node_id}\n{inputs.get('prompt', '')}")
    prompt_message = (
        f"Prompt MiniMax FastH3 I2V dikirim ke ComfyUI untuk {source_label}:\n"
        + ("\n\n".join(prompt_logs) or "(prompt node tidak ditemukan)")
    )
    write_log(prompt_message, extra={"source_label": source_label})
    if log_file:
        with open(log_file, "a", encoding="utf-8") as log:
            log.write(prompt_message + "\n")
    result = comfyui_api.post_workflow_api(workflow, server)
    if log_file:
        with open(log_file, "a", encoding="utf-8") as log:
            log.write(f"Sent {source_label}\nResult: {json.dumps(result)}\n")
    write_log(
        f"Sent minimax_fast_h3_i2v workflow for {source_label}: {json.dumps(result)}",
        extra={"source_label": source_label},
    )
    return result
