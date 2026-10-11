import copy
import json
import os
import random
import copy

from minimax_h3.minimax_h3_prompt import default_structured_prompt, serialize_structured_prompt, structured_prompt_entry

from scripts import comfyui_api
from logging_config import get_logger, write_log

logger = get_logger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TEMPLATE = os.path.join(ROOT, "api_template")
TEMPLATE = "minimax_h3_t2v_api.json"
SPECIAL_UNET_MODEL = "MINIMAX-H3/10eros_max_h3_8step_turbo_beta6_int8.safetensors"

SIZE_OPTIONS = [
    ("368x640", 368, 640),
    ("480x848", 480, 848),
    ("544x960", 544, 960),
    ("608x1056", 608, 1056),
    ("640x1152", 640, 1152),
    ("672x1216", 672, 1216),
    ("720x1280", 720, 1280),
    ("768x1344", 768, 1344),
    ("640x368", 640, 368),
    ("848x480", 848, 480),
    ("960x544", 960, 544),
    ("1056x608", 1056, 608),
    ("1152x640", 1152, 640),
    ("1216x672", 1216, 672),
    ("1280x720", 1280, 720),
    ("1344x768", 1344, 768),
]

DEFAULT_H3_CACHE = {
    "steps": 20,
    "reuse_threshold": 0.05,
    "start_percent": 0.15,
    "end_percent": 0.90,
    "max_steps": 1,
}

DEFAULT_PROMPT = {
    "positive_prompt": structured_prompt_entry(
        "T2VA",
        id_new=default_structured_prompt("T2VA"),
        en=default_structured_prompt("T2VA"),
    ),
    "lora_name": "MINIMAX-H3/AI-Girl-Fictional.safetensors",
    "lora_strength": 0,
    "lora_name_2": "MINIMAX-H3/AI-Girl-Fictional.safetensors",
    "lora_strength_2": 0,
    "width": 368,
    "height": 640,
    "fps": 24,
    "remove_sound": False,
    "fast_mode": False,
    "special_mode": False,
    "h3_cache_enabled": True,
    "h3_cache": copy.deepcopy(DEFAULT_H3_CACHE),
}


def _h3_cache_values(prompt: dict) -> dict:
    raw = prompt.get("h3_cache") if isinstance(prompt, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    values = {}
    specs = {
        "steps": (int, 4, 50),
        "reuse_threshold": (float, 0.0, 0.5),
        "start_percent": (float, 0.0, 1.0),
        "end_percent": (float, 0.0, 1.0),
        "max_steps": (int, 1, 3),
    }
    for key, (converter, minimum, maximum) in specs.items():
        value = raw[key] if key in raw else DEFAULT_H3_CACHE[key]
        if isinstance(value, str) and not value.strip():
            raise ValueError(f"H3 Cache {key} wajib diisi")
        try:
            parsed = converter(value)
        except (TypeError, ValueError):
            raise ValueError(f"H3 Cache {key} tidak valid") from None
        if converter is int and isinstance(value, float) and not value.is_integer():
            raise ValueError(f"H3 Cache {key} harus integer")
        if not minimum <= parsed <= maximum:
            raise ValueError(f"H3 Cache {key} di luar rentang")
        values[key] = parsed
    return values


def _apply_h3_cache(workflow: dict, prompt: dict) -> None:
    values = _h3_cache_values(prompt)
    # Steps adalah parameter sampler terpisah dari node H3 Cache dan selalu
    # diterapkan, termasuk saat node cache dinonaktifkan.
    _set_input(workflow, "124", "steps", values["steps"])
    if not bool(prompt.get("h3_cache_enabled", True)):
        workflow.pop("137", None)
        _set_input(workflow, "136", "model", ["127", 0])
        return
    _set_input(workflow, "137", "reuse_threshold", values["reuse_threshold"])
    _set_input(workflow, "137", "start_percent", values["start_percent"])
    _set_input(workflow, "137", "end_percent", values["end_percent"])
    _set_input(workflow, "137", "max_steps", values["max_steps"])


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


def _set_lora_node(workflow: dict, node_id: str, lora_name: str, strength_value) -> bool:
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
        inputs["strength_model"] = 0.0
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
        (544, 960): ("9:16 (Portrait Widescreen)", 0.5),
        (608, 1056): ("9:16 (Portrait Widescreen)", 0.6),
        (640, 1152): ("9:16 (Portrait Widescreen)", 0.7),
        (672, 1216): ("9:16 (Portrait Widescreen)", 0.8),
        (720, 1280): ("9:16 (Portrait Widescreen)", 0.9),
        (768, 1344): ("9:16 (Portrait Widescreen)", 0.98),
        (640, 368): ("16:9 (Widescreen)", 0.2),
        (848, 480): ("16:9 (Widescreen)", 0.4),
        (960, 544): ("16:9 (Widescreen)", 0.5),
        (1056, 608): ("16:9 (Widescreen)", 0.6),
        (1152, 640): ("16:9 (Widescreen)", 0.7),
        (1216, 672): ("16:9 (Widescreen)", 0.8),
        (1280, 720): ("16:9 (Widescreen)", 0.9),
        (1344, 768): ("16:9 (Widescreen)", 0.98),
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
    fps_override: int | None = None,
) -> dict:
    prompt = t2v_prompt if isinstance(t2v_prompt, dict) else {}
    if bool(prompt.get("fast_mode", False)) and bool(prompt.get("special_mode", False)):
        raise ValueError("Mode Cepat dan Mode Khusus MiniMax H3 tidak boleh aktif bersamaan.")
    workflow = copy.deepcopy(_load_template())
    if bool(prompt.get("special_mode", False)):
        _set_input(workflow, "127", "unet_name", SPECIAL_UNET_MODEL)

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
    # MiniMax H3 hanya mendukung/menjalankan workflow pada 24 FPS.
    fps = 24
    _set_input(workflow, "130", "fps", fps)
    frame_expression = (
        f"max(5, round(a * {fps})) + "
        f"(5 - (max(5, round(a * {fps})) % 17)) % 17"
    )
    _set_input(workflow, "132", "expression", frame_expression)

    _set_lora_node(
        workflow,
        "135",
        prompt.get("lora_name", DEFAULT_PROMPT["lora_name"]),
        prompt.get("lora_strength", DEFAULT_PROMPT["lora_strength"]),
    )
    _set_lora_node(
        workflow,
        "136",
        prompt.get("lora_name_2", DEFAULT_PROMPT["lora_name_2"]),
        prompt.get("lora_strength_2", DEFAULT_PROMPT["lora_strength_2"]),
    )
    _apply_h3_cache(workflow, prompt)
    return _inject_random_noise_seed(workflow)


def build_minimax_h3_t2v_workflow(
    t2v_prompt: dict,
    scene_meta: dict | None = None,
    duration_override: int | float | None = None,
    fps_override: int | None = None,
) -> dict:
    return build_workflow(
        t2v_prompt,
        scene_meta=scene_meta,
        duration_override=duration_override,
        fps_override=fps_override,
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
