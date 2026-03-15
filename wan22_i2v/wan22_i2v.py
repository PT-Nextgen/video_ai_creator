import os
import copy
import json
import random
from scripts import comfyui_api
from logging_config import get_logger, write_log

logger = get_logger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TEMPLATE = os.path.join(ROOT, "api_template")
TEMPLATE_20 = "wan22_i2v_api.json"
TEMPLATE_4 = "wan22_i2v_4steps_api.json"
TEMPLATE_20_LORA = "wan22_i2v_lora_api.json"
TEMPLATE_4_LORA = "wan22_i2v_4steps_lora_api.json"
SIZE_OPTIONS = [
    ("368x640", 368, 640),
    ("480x848", 480, 848),
    ("720x1280", 720, 1280),
    ("640x368", 640, 368),
    ("848x480", 848, 480),
    ("1280x720", 1280, 720),
]
STEP_OPTIONS = [
    ("4 langkah", TEMPLATE_4),
    ("20 langkah", TEMPLATE_20),
]
DEFAULT_PROMPT = {
    "positive_prompt_one": "",
    "positive_prompt_two": "",
    "positive_prompt_three": "",
    "positive_prompt_four": "",
    "positive_prompt_five": "",
    "negative_prompt_one": "",
    "negative_prompt_two": "",
    "negative_prompt_three": "",
    "negative_prompt_four": "",
    "negative_prompt_five": "",
    "width": 368,
    "height": 640,
    "use_lora": False,
    "lora_high_name": "",
    "lora_high_strength": 1.0,
    "lora_low_name": "",
    "lora_low_strength": 1.0,
    "json_api": TEMPLATE_4,
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


def _set_wan_loop_total(workflow, value):
    if "167" in workflow and isinstance(workflow["167"], dict):
        inputs = workflow["167"].get("inputs")
        if isinstance(inputs, dict):
            inputs["total"] = value
            return True

    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if isinstance(inputs, dict) and "total" in inputs:
            inputs["total"] = value
            return True
    return False


def get_template_name(wan_prompt: dict | None = None) -> str:
    wan_prompt = wan_prompt or {}
    template_name = wan_prompt.get("json_api", TEMPLATE_20)
    use_lora = bool(wan_prompt.get("use_lora"))
    if template_name in {TEMPLATE_4_LORA, TEMPLATE_4}:
        return TEMPLATE_4_LORA if use_lora else TEMPLATE_4
    if template_name in {TEMPLATE_20_LORA, TEMPLATE_20}:
        return TEMPLATE_20_LORA if use_lora else TEMPLATE_20
    if template_name not in {TEMPLATE_20, TEMPLATE_4, TEMPLATE_20_LORA, TEMPLATE_4_LORA}:
        template_name = TEMPLATE_20
    return template_name


def get_step_template_name(wan_prompt: dict | None = None) -> str:
    wan_prompt = wan_prompt or {}
    template_name = wan_prompt.get("json_api", TEMPLATE_20)
    if template_name in {TEMPLATE_4, TEMPLATE_4_LORA}:
        return TEMPLATE_4
    return TEMPLATE_20


def build_workflow(wan_prompt, scene_meta, uploaded_name=None):
    workflow = copy.deepcopy(_load_template(get_template_name(wan_prompt)))
    replace_map = {}
    for suffix in ["one", "two", "three", "four", "five"]:
        pos_key = f"positive_prompt_{suffix}"
        neg_key = f"negative_prompt_{suffix}"
        replace_map[pos_key] = wan_prompt.get(pos_key, "")
        replace_map[neg_key] = wan_prompt.get(neg_key, "")

    _traverse_and_replace(workflow, replace_map)

    duration_seconds = None
    if isinstance(scene_meta, dict):
        duration_seconds = scene_meta.get("duration_seconds")
    if isinstance(duration_seconds, (int, float)):
        _set_wan_loop_total(workflow, int(duration_seconds / 5))

    if uploaded_name and "97" in workflow and isinstance(workflow["97"], dict):
        inputs = workflow["97"].get("inputs")
        if isinstance(inputs, dict) and "image" in inputs:
            inputs["image"] = uploaded_name

    try:
        width = int(wan_prompt.get("width", 368))
    except (TypeError, ValueError):
        width = 368
    try:
        height = int(wan_prompt.get("height", 640))
    except (TypeError, ValueError):
        height = 640
    if "214" in workflow and isinstance(workflow["214"], dict):
        inputs = workflow["214"].get("inputs")
        if isinstance(inputs, dict):
            inputs["value"] = width
    if "215" in workflow and isinstance(workflow["215"], dict):
        inputs = workflow["215"].get("inputs")
        if isinstance(inputs, dict):
            inputs["value"] = height

    if wan_prompt.get("use_lora"):
        if "264" in workflow and isinstance(workflow["264"], dict):
            inputs = workflow["264"].get("inputs")
            if isinstance(inputs, dict):
                inputs["lora_name"] = wan_prompt.get("lora_high_name", "")
                try:
                    inputs["strength_model"] = float(wan_prompt.get("lora_high_strength", 1.5))
                except (TypeError, ValueError):
                    inputs["strength_model"] = 1.5
        if "265" in workflow and isinstance(workflow["265"], dict):
            inputs = workflow["265"].get("inputs")
            if isinstance(inputs, dict):
                inputs["lora_name"] = wan_prompt.get("lora_low_name", "")
                try:
                    inputs["strength_model"] = float(wan_prompt.get("lora_low_strength", 0.5))
                except (TypeError, ValueError):
                    inputs["strength_model"] = 0.5

    return workflow


def build_wan_workflow(wan_prompt, scene_meta, uploaded_name=None):
    return build_workflow(wan_prompt, scene_meta, uploaded_name=uploaded_name)


def _inject_random_noise_seed(workflow: dict):
    """Ensure workflow has node '86' -> 'inputs' -> 'noise_seed' set to a random 16-digit int."""
    try:
        if '86' not in workflow or not isinstance(workflow['86'], dict):
            workflow['86'] = {'inputs': {}}
        if 'inputs' not in workflow['86'] or not isinstance(workflow['86']['inputs'], dict):
            workflow['86']['inputs'] = {}
        seed = random.randint(10**15, 10**16 - 1)
        workflow['86']['inputs']['noise_seed'] = seed
    except Exception:
        pass
    return workflow

def send_workflow(workflow, uploaded_name, server, log_file=None, source_label="in-memory workflow"):
    workflow = _inject_random_noise_seed(workflow)

    if '97' in workflow and isinstance(workflow['97'], dict):
        inputs = workflow['97'].get('inputs')
        if isinstance(inputs, dict) and 'image' in inputs:
            inputs['image'] = uploaded_name

    result = comfyui_api.post_workflow_api(workflow, server)
    if log_file:
        with open(log_file, 'a', encoding='utf-8') as log:
            log.write(f"Sent {source_label}\nResult: {json.dumps(result)}\n")
    write_log(f"Sent wan22 workflow for {source_label}: {json.dumps(result)}", extra={'source_label': source_label})
    return result


def prepare_and_send_workflow(scene_dir, uploaded_name, server, log_file=None):
    """Find wan22 json in scene_dir, replace node '97'->inputs->image with uploaded_name,
    and send the modified workflow (without overwriting the original file).
    """
    wan_json_path = None
    for fname in ['wan22_i2v_4steps_api.json', 'wan22_i2v_api.json']:
        fpath = os.path.join(scene_dir, fname)
        if os.path.exists(fpath):
            wan_json_path = fpath
            break
    if not wan_json_path:
        if log_file:
            with open(log_file, 'a', encoding='utf-8') as log:
                log.write(f"No wan22 json found in {scene_dir}\n")
        write_log(f"No wan22 json found in {scene_dir}", level='warning', extra={'scene_dir': scene_dir})
        return None

    with open(wan_json_path, 'r', encoding='utf-8') as f:
        wan_json = json.load(f)

    return send_workflow(
        wan_json,
        uploaded_name,
        server,
        log_file=log_file,
        source_label=scene_dir,
    )
