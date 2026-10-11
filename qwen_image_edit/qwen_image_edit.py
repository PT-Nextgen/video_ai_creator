import copy
import json
import os
import random

from scripts import comfyui_api
from logging_config import get_logger, write_log


logger = get_logger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TEMPLATE = os.path.join(ROOT, "api_template")
TEMPLATE = "qwen_2_1_edit_api.json"
MAX_REFERENCE_IMAGES = 10
TEXT_ENCODE_NODE = "510"
LATENT_NODE = "505"
SAMPLER_NODE = "507"
REFERENCE_NODE_START = 470

SIZE_OPTIONS = [
    ("368x640", 368, 640),
    ("480x848", 480, 848),
    ("720x1280", 720, 1280),
    ("640x368", 640, 368),
    ("848x480", 848, 480),
    ("1280x720", 1280, 720),
]

DEFAULT_PROMPT = {
    "images": ["" for _ in range(MAX_REFERENCE_IMAGES)],
    "width": 368,
    "height": 640,
    "use_random_seed": True,
    "seed": 1,
    "number_of_edits": 1,
    "prompt_images": ["" for _ in range(MAX_REFERENCE_IMAGES)],
    "prompt_instruction": "",
    "positive_prompt": "",
    "negative_prompt": "",
}


def _load_template() -> dict:
    with open(os.path.join(API_TEMPLATE, TEMPLATE), "r", encoding="utf-8") as file:
        return json.load(file)


def _prompt_text(value) -> str:
    if isinstance(value, dict):
        for key in ("en", "id_new", "id_old"):
            text = str(value.get(key, "") or "").strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


def _set_node_input(workflow: dict, node_id: str, key: str, value):
    node = workflow.get(node_id)
    if not isinstance(node, dict):
        node = {"inputs": {}, "class_type": ""}
        workflow[node_id] = node
    inputs = node.setdefault("inputs", {})
    if not isinstance(inputs, dict):
        inputs = {}
        node["inputs"] = inputs
    inputs[key] = value


def _set_reference_images(workflow: dict, image_names) -> None:
    """Inject only selected reference images into TextEncodeQwenImage21.

    Empty dropdowns intentionally remove both the LoadImage node and the
    corresponding autogrow input. This allows sparse selections such as
    image_1 and image_4 without inventing placeholder files.
    """
    values = list(image_names or [])
    for slot in range(1, MAX_REFERENCE_IMAGES + 1):
        node_id = str(REFERENCE_NODE_START + slot - 1)
        input_key = f"images.image_{slot}"
        workflow.pop(node_id, None)
        encoder = workflow.get(TEXT_ENCODE_NODE)
        if isinstance(encoder, dict) and isinstance(encoder.get("inputs"), dict):
            encoder["inputs"].pop(input_key, None)

        image_name = str(values[slot - 1] if slot - 1 < len(values) else "").strip()
        if not image_name:
            continue
        workflow[node_id] = {
            "inputs": {"image": image_name},
            "class_type": "LoadImage",
            "_meta": {"title": f"Load Reference Image {slot}"},
        }
        _set_node_input(workflow, TEXT_ENCODE_NODE, input_key, [node_id, 0])


def _set_seed(workflow: dict, prompt: dict | None) -> int:
    prompt = prompt if isinstance(prompt, dict) else {}
    use_random = bool(prompt.get("use_random_seed", True))
    if use_random:
        seed = random.randint(10**15, 10**16 - 1)
    else:
        try:
            seed = int(prompt.get("seed", 1))
        except (TypeError, ValueError):
            seed = 1
        if seed <= 0:
            seed = 1
    _set_node_input(workflow, SAMPLER_NODE, "seed", seed)
    return seed


def build_workflow(prompt: dict, uploaded_images=None) -> dict:
    prompt = prompt if isinstance(prompt, dict) else {}
    workflow = copy.deepcopy(_load_template())
    _set_node_input(workflow, TEXT_ENCODE_NODE, "prompt", _prompt_text(prompt.get("positive_prompt", "")))
    _set_node_input(workflow, TEXT_ENCODE_NODE, "negative_prompt", _prompt_text(prompt.get("negative_prompt", "")))

    try:
        width = int(prompt.get("width", DEFAULT_PROMPT["width"]))
    except (TypeError, ValueError):
        width = DEFAULT_PROMPT["width"]
    try:
        height = int(prompt.get("height", DEFAULT_PROMPT["height"]))
    except (TypeError, ValueError):
        height = DEFAULT_PROMPT["height"]
    _set_node_input(workflow, LATENT_NODE, "width", max(1, width))
    _set_node_input(workflow, LATENT_NODE, "height", max(1, height))

    image_names = uploaded_images if uploaded_images is not None else prompt.get("images", [])
    _set_reference_images(workflow, image_names)
    _set_seed(workflow, prompt)
    return workflow


def build_qwen_image_edit_workflow(prompt: dict, uploaded_images=None) -> dict:
    return build_workflow(prompt, uploaded_images=uploaded_images)


def send_workflow(prompt: dict, server: str, uploaded_images=None):
    workflow = build_workflow(prompt, uploaded_images=uploaded_images)
    write_log(
        "Qwen Image Edit workflow: "
        f"size={workflow[LATENT_NODE]['inputs'].get('width')}x{workflow[LATENT_NODE]['inputs'].get('height')}, "
        f"references={sum(1 for key in workflow.get(TEXT_ENCODE_NODE, {}).get('inputs', {}) if key.startswith('images.image_'))}"
    )
    return comfyui_api.post_workflow_api(workflow, server)
