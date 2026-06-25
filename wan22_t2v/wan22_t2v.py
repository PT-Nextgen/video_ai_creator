import copy
import json
import os
import random

from scripts import comfyui_api
from logging_config import get_logger, write_log

logger = get_logger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TEMPLATE = os.path.join(ROOT, "api_template")
TEMPLATE_4 = "wan22_t2v_4steps_lora_api.json"
SIZE_OPTIONS = [
    ("368x640", 368, 640),
    ("480x848", 480, 848),
    ("720x1280", 720, 1280),
    ("640x368", 640, 368),
    ("848x480", 848, 480),
    ("1280x720", 1280, 720),
]
DEFAULT_PROMPT = {
    "lora_trigger_words": "",
    "positive_prompt": "",
    "negative_prompt": "",
    "width": 368,
    "height": 640,
    "lora_high_name": "WAN2.2/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors",
    "lora_high_strength": 0,
    "lora_low_name": "WAN2.2/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors",
    "lora_low_strength": 0,
    "lora_high_name_2": "WAN2.2/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors",
    "lora_high_strength_2": 0,
    "lora_low_name_2": "WAN2.2/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors",
    "lora_low_strength_2": 0,
}


def _load_template(name: str) -> dict:
    path = os.path.join(API_TEMPLATE, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _set_text_input(workflow: dict, node_id: str, value: str):
    node = workflow.get(str(node_id))
    if not isinstance(node, dict):
        return False
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return False
    if "text" not in inputs:
        return False
    inputs["text"] = str(value or "")
    return True


def _set_size_inputs(workflow: dict, width: int, height: int):
    node = workflow.get("74")
    if not isinstance(node, dict):
        return
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return
    inputs["width"] = int(width)
    inputs["height"] = int(height)


def _set_length_override(workflow: dict, length: int):
    node = workflow.get("74")
    if not isinstance(node, dict):
        return
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return
    inputs["length"] = int(length)


def _set_lora_node(workflow: dict, node_id: str | None, lora_name: str, strength_value, fallback_strength: float) -> bool:
    if not node_id:
        return False
    node = workflow.get(str(node_id))
    if not isinstance(node, dict):
        return False
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return False
    inputs["lora_name"] = str(lora_name or "")
    try:
        inputs["strength_model"] = float(strength_value)
    except (TypeError, ValueError):
        inputs["strength_model"] = float(fallback_strength)
    return True


def _inject_random_noise_seed(workflow: dict):
    try:
        seed = random.randint(10**15, 10**16 - 1)
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            if "noise_seed" in inputs:
                inputs["noise_seed"] = seed
    except Exception:
        pass
    return workflow


def get_template_name(t2v_prompt: dict | None = None) -> str:
    return TEMPLATE_4


def get_step_template_name(t2v_prompt: dict | None = None) -> str:
    return TEMPLATE_4


def resolve_wan22_i2v_duration(scene_duration) -> int:
    try:
        value = int(float(scene_duration))
    except (TypeError, ValueError):
        value = 10
    if value >= 15:
        return 10
    return 5


def build_workflow(t2v_prompt: dict, scene_meta: dict | None = None, length_override: int | None = None) -> dict:
    t2v_prompt = t2v_prompt if isinstance(t2v_prompt, dict) else {}
    workflow = copy.deepcopy(_load_template(TEMPLATE_4))

    positive_prompt = str(t2v_prompt.get("positive_prompt", DEFAULT_PROMPT["positive_prompt"]))
    negative_prompt = str(t2v_prompt.get("negative_prompt", DEFAULT_PROMPT["negative_prompt"]))
    _set_text_input(workflow, "89", positive_prompt)
    _set_text_input(workflow, "72", negative_prompt)

    try:
        width = int(t2v_prompt.get("width", DEFAULT_PROMPT["width"]))
    except (TypeError, ValueError):
        width = DEFAULT_PROMPT["width"]
    try:
        height = int(t2v_prompt.get("height", DEFAULT_PROMPT["height"]))
    except (TypeError, ValueError):
        height = DEFAULT_PROMPT["height"]
    _set_size_inputs(workflow, width, height)

    if length_override is not None:
        _set_length_override(workflow, int(length_override))

    _set_lora_node(workflow, "114", t2v_prompt.get("lora_high_name", ""), t2v_prompt.get("lora_high_strength", 0), 0)
    _set_lora_node(workflow, "115", t2v_prompt.get("lora_low_name", ""), t2v_prompt.get("lora_low_strength", 0), 0)
    _set_lora_node(workflow, "133", t2v_prompt.get("lora_high_name_2", ""), t2v_prompt.get("lora_high_strength_2", 0), 0)
    _set_lora_node(workflow, "134", t2v_prompt.get("lora_low_name_2", ""), t2v_prompt.get("lora_low_strength_2", 0), 0)

    _inject_random_noise_seed(workflow)
    return workflow


def build_wan_t2v_workflow(
    t2v_prompt: dict,
    scene_meta: dict | None = None,
    length_override: int | None = None,
) -> dict:
    return build_workflow(t2v_prompt, scene_meta=scene_meta, length_override=length_override)


def send_workflow(workflow, server, log_file=None, source_label="in-memory workflow"):
    result = comfyui_api.post_workflow_api(workflow, server)
    if log_file:
        with open(log_file, "a", encoding="utf-8") as log:
            log.write(f"Sent {source_label}\nResult: {json.dumps(result)}\n")
    write_log(f"Sent wan22_t2v workflow for {source_label}: {json.dumps(result)}", extra={"source_label": source_label})
    return result


def prepare_and_send_workflow(scene_dir, server, log_file=None):
    wan_json_path = None
    for fname in ["wan22_t2v_4steps_lora_api.json"]:
        fpath = os.path.join(scene_dir, fname)
        if os.path.exists(fpath):
            wan_json_path = fpath
            break
    if not wan_json_path:
        if log_file:
            with open(log_file, "a", encoding="utf-8") as log:
                log.write(f"No wan22_t2v json found in {scene_dir}\n")
        write_log(f"No wan22_t2v json found in {scene_dir}", level="warning", extra={"scene_dir": scene_dir})
        return None

    with open(wan_json_path, "r", encoding="utf-8") as f:
        wan_json = json.load(f)

    return send_workflow(
        wan_json,
        server,
        log_file=log_file,
        source_label=scene_dir,
    )
