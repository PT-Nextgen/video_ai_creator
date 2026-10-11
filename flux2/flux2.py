import copy
import json
import os
import random

MODEL_FLUX2 = "flux.2"
TEMPLATE_DEFAULT = "flux2_api.json"
TEMPLATE_LORA = "flux2_lora_api.json"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TEMPLATE = os.path.join(ROOT, "api_template")


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


def is_flux2_prompt(z_prompt: dict | None = None) -> bool:
    z_prompt = z_prompt or {}
    model = str(z_prompt.get("image_model", "")).strip().lower()
    json_api = str(z_prompt.get("json_api", "")).strip().lower()
    return model == MODEL_FLUX2 or json_api in {TEMPLATE_DEFAULT, TEMPLATE_LORA}


def get_model_key(z_prompt: dict | None = None) -> str:
    return MODEL_FLUX2


def supports_negative_prompt(z_prompt: dict | None = None) -> bool:
    return False


def get_template_name(z_prompt: dict | None = None) -> str:
    z_prompt = z_prompt or {}
    return TEMPLATE_LORA if z_prompt.get("use_lora") else TEMPLATE_DEFAULT


def _inject_seed(workflow: dict, z_prompt: dict | None = None):
    try:
        seed_node = "25"
        if seed_node not in workflow or not isinstance(workflow[seed_node], dict):
            workflow[seed_node] = {"inputs": {}}
        if "inputs" not in workflow[seed_node] or not isinstance(workflow[seed_node]["inputs"], dict):
            workflow[seed_node]["inputs"] = {}
        if z_prompt and not z_prompt.get("use_random_seed", True):
            seed = int(z_prompt.get("seed", 1))
        else:
            seed = random.randint(10**15, 10**16 - 1)
        workflow[seed_node]["inputs"]["noise_seed"] = seed
    except Exception:
        pass
    return workflow


def build_workflow(z_prompt: dict) -> dict:
    workflow = copy.deepcopy(_load_template(get_template_name(z_prompt)))
    replace_map = {
        "positive_prompt": z_prompt.get("positive_prompt", ""),
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

    if "47" in workflow and isinstance(workflow["47"], dict):
        inputs = workflow["47"].get("inputs")
        if isinstance(inputs, dict):
            inputs["width"] = width
            inputs["height"] = height
    if "48" in workflow and isinstance(workflow["48"], dict):
        inputs = workflow["48"].get("inputs")
        if isinstance(inputs, dict):
            inputs["width"] = width
            inputs["height"] = height

    lora_node = "82"
    if z_prompt.get("use_lora") and lora_node in workflow and isinstance(workflow[lora_node], dict):
        inputs = workflow[lora_node].get("inputs")
        if isinstance(inputs, dict):
            inputs["lora_name"] = z_prompt.get("lora_name", "")
            try:
                inputs["strength_model"] = float(z_prompt.get("strength_model", 1.0))
            except (TypeError, ValueError):
                inputs["strength_model"] = 1.0

    _inject_seed(workflow, z_prompt)
    return workflow


def build_flux2_workflow(z_prompt: dict) -> dict:
    return build_workflow(z_prompt)
