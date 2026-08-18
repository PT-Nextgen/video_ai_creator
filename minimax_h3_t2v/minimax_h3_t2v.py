import copy
import json
import os
import random

from minimax_h3_prompt import default_structured_prompt, serialize_structured_prompt, structured_prompt_entry

from scripts import comfyui_api
from logging_config import get_logger, write_log

logger = get_logger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TEMPLATE = os.path.join(ROOT, "api_template")
TEMPLATE = "minimax_h3_t2v_api.json"
TURBO_LORA_NAME = "MINIMAX-H3/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
TURBO_LORA_NODE_ID = "137"

SIZE_OPTIONS = [
    ("368x640", 368, 640),
    ("480x848", 480, 848),
    ("720x1280", 720, 1280),
    ("640x368", 640, 368),
    ("848x480", 848, 480),
    ("1280x720", 1280, 720),
]

DEFAULT_PROMPT = {
    "positive_prompt": structured_prompt_entry(
        "T2VA",
        id_new=default_structured_prompt("T2VA"),
        en=default_structured_prompt("T2VA"),
    ),
    "lora_name": "MINIMAX-H3/AI-Girl-Fictional.safetensors",
    "lora_strength": 0,
    "turbo": False,
    "width": 368,
    "height": 640,
    "remove_sound": False,
}


def _load_template(name: str = TEMPLATE) -> dict:
    path = os.path.join(API_TEMPLATE, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _set_input(workflow: dict, node_id: str, key: str, value) -> bool:
    node = workflow.get(str(node_id))
    if not isinstance(node, dict):
        return False
    inputs = node.get("inputs")
    if not isinstance(inputs, dict) or key not in inputs:
        return False
    inputs[key] = value
    return True


def _set_lora_node(workflow: dict, lora_name: str, strength_value) -> bool:
    node = workflow.get("135")
    if not isinstance(node, dict):
        return False
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return False
    inputs["lora_name"] = str(lora_name or "")
    try:
        inputs["strength_model"] = float(strength_value)
    except (TypeError, ValueError):
        inputs["strength_model"] = 0.0
    return True


def _apply_turbo_distillation(workflow: dict, enabled: bool) -> bool:
    """Insert the optional 8-step distillation LoRA before the regular T2V LoRA."""
    if not enabled:
        return False

    base_lora = workflow.get("135")
    if not isinstance(base_lora, dict) or not isinstance(base_lora.get("inputs"), dict):
        return False

    turbo_lora = copy.deepcopy(base_lora)
    turbo_inputs = turbo_lora["inputs"]
    turbo_inputs["lora_name"] = TURBO_LORA_NAME
    turbo_inputs["strength_model"] = 1
    turbo_inputs["model"] = ["127", 0]
    turbo_lora.setdefault("_meta", {})["title"] = "Load Turbo LoRA"
    workflow[TURBO_LORA_NODE_ID] = turbo_lora

    base_lora["inputs"]["model"] = [TURBO_LORA_NODE_ID, 0]
    scheduler = workflow.get("124")
    if isinstance(scheduler, dict) and isinstance(scheduler.get("inputs"), dict):
        scheduler["inputs"]["steps"] = 8
    return True


def _set_resolution_selector(workflow: dict, width: int, height: int) -> bool:
    node = workflow.get("115")
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
        (int(width), int(height)),
        resolution_map[(368, 640)],
    )
    inputs["aspect_ratio"] = aspect_ratio
    inputs["megapixels"] = megapixels
    inputs["multiple"] = 32
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


def get_template_name(prompt: dict | None = None) -> str:
    return TEMPLATE


def get_step_template_name(prompt: dict | None = None) -> str:
    return TEMPLATE


def build_workflow(
    t2v_prompt: dict,
    scene_meta: dict | None = None,
    duration_override: int | float | None = None,
    turbo_enabled: bool = False,
) -> dict:
    prompt = t2v_prompt if isinstance(t2v_prompt, dict) else {}
    workflow = copy.deepcopy(_load_template())

    positive_value = prompt.get("positive_prompt", DEFAULT_PROMPT["positive_prompt"])
    if isinstance(positive_value, dict) and isinstance(positive_value.get("en"), dict):
        positive_prompt = serialize_structured_prompt(positive_value["en"])
    else:
        positive_prompt = str(positive_value or "")
    _set_input(workflow, "131", "prompt", positive_prompt)

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
    _set_input(workflow, "133", "value", duration)

    _set_lora_node(
        workflow,
        prompt.get("lora_name", DEFAULT_PROMPT["lora_name"]),
        prompt.get("lora_strength", DEFAULT_PROMPT["lora_strength"]),
    )
    _apply_turbo_distillation(workflow, bool(turbo_enabled))
    return _inject_random_noise_seed(workflow)


def build_minimax_h3_t2v_workflow(
    t2v_prompt: dict,
    scene_meta: dict | None = None,
    duration_override: int | float | None = None,
    turbo_enabled: bool = False,
) -> dict:
    return build_workflow(
        t2v_prompt,
        scene_meta=scene_meta,
        duration_override=duration_override,
        turbo_enabled=turbo_enabled,
    )


def send_workflow(workflow, server, log_file=None, source_label="in-memory workflow"):
    prompt_logs = []
    for node_id, node in (workflow or {}).items():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if isinstance(inputs, dict) and "prompt" in inputs:
            prompt_logs.append(f"node={node_id}\n{inputs.get('prompt', '')}")
    prompt_message = (
        f"Prompt MiniMax H3 T2V dikirim ke ComfyUI untuk {source_label}:\n"
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
        f"Sent minimax_h3_t2v workflow for {source_label}: {json.dumps(result)}",
        extra={"source_label": source_label},
    )
    return result
