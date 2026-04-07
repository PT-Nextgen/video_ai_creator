import copy
import json
import os

from flux2.flux2 import (
    MODEL_FLUX2,
    MODEL_FLUX2_K9,
    build_flux2_workflow,
    get_model_key as get_flux_model_key,
    get_template_name as get_flux2_template_name,
    is_flux2_prompt,
    supports_negative_prompt as flux_supports_negative_prompt,
)
from gemini.gemini_image import MODEL_GEMINI_IMAGE, MODEL_GEMINI_FLASH_05K, is_gemini_prompt
from scripts import comfyui_api
from logging_config import get_logger, write_log

logger = get_logger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TEMPLATE = os.path.join(ROOT, "api_template")
MODEL_Z_IMAGE_TURBO = "z-image turbo"
IMAGE_MODEL_OPTIONS = [
    (MODEL_Z_IMAGE_TURBO, "Z-Image Turbo"),
    (MODEL_FLUX2, "Flux.2"),
    (MODEL_FLUX2_K9, "Flux.2 Klein 9B"),
    (MODEL_GEMINI_IMAGE, "Gemini"),
]
TEMPLATE_DEFAULT = "z_image_api.json"
TEMPLATE_LORA = "z_image_lora_api.json"
SIZE_OPTIONS = [
    ("368x640", 368, 640),
    ("480x848", 480, 848),
    ("720x1280", 720, 1280),
    ("640x368", 640, 368),
    ("848x480", 848, 480),
    ("1280x720", 1280, 720),
]
DEFAULT_PROMPT = {
    "image_model": MODEL_Z_IMAGE_TURBO,
    "positive_prompt": "",
    "negative_prompt": "",
    "width": 368,
    "height": 640,
    "use_random_seed": True,
    "seed": 1,
    "use_lora": False,
    "lora_name": "",
    "strength_model": 1.0,
    "gemini_model_id": MODEL_GEMINI_FLASH_05K,
    "json_api": TEMPLATE_DEFAULT,
}


def _load_template(name: str) -> dict:
    path = os.path.join(API_TEMPLATE, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _traverse_and_replace(node, replace_map):
    if isinstance(node, dict):
        inputs = node.get("inputs")
        if isinstance(inputs, dict) and "text" in inputs:
            value = inputs["text"]
            if isinstance(value, str) and value in replace_map:
                inputs["text"] = replace_map[value]
        for value in node.values():
            _traverse_and_replace(value, replace_map)
    elif isinstance(node, list):
        for item in node:
            _traverse_and_replace(item, replace_map)


def get_model_key(z_prompt: dict | None = None) -> str:
    if is_gemini_prompt(z_prompt):
        return MODEL_GEMINI_IMAGE
    if is_flux2_prompt(z_prompt):
        return get_flux_model_key(z_prompt)
    return MODEL_Z_IMAGE_TURBO


def get_model_display_name(z_prompt: dict | None = None) -> str:
    model_key = get_model_key(z_prompt)
    for option_key, label in IMAGE_MODEL_OPTIONS:
        if option_key == model_key:
            return label
    return model_key


def supports_negative_prompt(z_prompt: dict | None = None) -> bool:
    model_key = get_model_key(z_prompt)
    if model_key == MODEL_Z_IMAGE_TURBO:
        return True
    if model_key == MODEL_GEMINI_IMAGE:
        return False
    return flux_supports_negative_prompt(z_prompt)


def get_template_name(z_prompt: dict | None = None) -> str:
    z_prompt = z_prompt or {}
    if get_model_key(z_prompt) == MODEL_GEMINI_IMAGE:
        return "gemini_flash_05k"
    if get_model_key(z_prompt) in {MODEL_FLUX2, MODEL_FLUX2_K9}:
        return get_flux2_template_name(z_prompt)
    return TEMPLATE_LORA if z_prompt.get("use_lora") else TEMPLATE_DEFAULT


def build_workflow(z_prompt: dict) -> dict:
    workflow = copy.deepcopy(_load_template(get_template_name(z_prompt)))
    replace_map = {
        "positive_prompt": z_prompt.get("positive_prompt", ""),
        "negative_prompt": z_prompt.get("negative_prompt", ""),
    }
    _traverse_and_replace(workflow, replace_map)

    try:
        width = int(z_prompt.get("width", 368))
    except (TypeError, ValueError):
        width = 368
    try:
        height = int(z_prompt.get("height", 640))
    except (TypeError, ValueError):
        height = 640

    if "13" in workflow and isinstance(workflow["13"], dict):
        inputs = workflow["13"].get("inputs")
        if isinstance(inputs, dict):
            inputs["width"] = width
            inputs["height"] = height
    if z_prompt.get("use_lora") and "30" in workflow and isinstance(workflow["30"], dict):
        inputs = workflow["30"].get("inputs")
        if isinstance(inputs, dict):
            inputs["lora_name"] = z_prompt.get("lora_name", "")
            try:
                inputs["strength_model"] = float(z_prompt.get("strength_model", 1.0))
            except (TypeError, ValueError):
                inputs["strength_model"] = 1.0

    _inject_seed(workflow, z_prompt)

    return workflow


def build_z_image_workflow(z_prompt: dict) -> dict:
    if get_model_key(z_prompt) == MODEL_GEMINI_IMAGE:
        raise RuntimeError("Gemini image model does not use ComfyUI workflow.")
    if get_model_key(z_prompt) in {MODEL_FLUX2, MODEL_FLUX2_K9}:
        return build_flux2_workflow(z_prompt)
    return build_workflow(z_prompt)


def _inject_seed(workflow: dict, z_prompt: dict | None = None):
    """Ensure workflow seed node is set from prompt config."""
    try:
        if "3" not in workflow or not isinstance(workflow["3"], dict):
            workflow["3"] = {"inputs": {}}
        if "inputs" not in workflow["3"] or not isinstance(workflow["3"]["inputs"], dict):
            workflow["3"]["inputs"] = {}
        if z_prompt and not z_prompt.get("use_random_seed", True):
            seed = int(z_prompt.get("seed", 1))
        else:
            import random
            seed = random.randint(10**15, 10**16 - 1)
        workflow["3"]["inputs"]["seed"] = seed
    except Exception:
        pass
    return workflow

def send_workflow(workflow, server, log_file=None, source_label="in-memory workflow", model_name=None):
    result = comfyui_api.post_workflow_api(workflow, server)
    if log_file:
        import json
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write(f"Sent {source_label}\nResult: {json.dumps(result)}\n")
    label = model_name or "image"
    write_log(f"Sent {label} workflow {source_label}: {result}", extra={'source_label': source_label})
    return result


def prepare_and_send_workflow(json_path, server, log_file=None):
    with open(json_path, 'r', encoding='utf-8') as f:
        z_json = json.load(f)
    return send_workflow(
        z_json,
        server,
        log_file=log_file,
        source_label=json_path,
        model_name=get_model_display_name(z_json),
    )




    
