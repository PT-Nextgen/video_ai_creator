import copy
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TEMPLATE = os.path.join(ROOT, "api_template")
TEMPLATE_NAME = "edgetts-api.json"


def _load_template(name: str) -> dict:
    path = os.path.join(API_TEMPLATE, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _replace_any_string_values(node, replace_map):
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, str):
                if value in replace_map:
                    node[key] = replace_map[value]
            else:
                _replace_any_string_values(value, replace_map)
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            if isinstance(item, str):
                if item in replace_map:
                    node[idx] = replace_map[item]
            else:
                _replace_any_string_values(item, replace_map)


def get_template_name(scene_meta: dict | None = None) -> str:
    return TEMPLATE_NAME


def build_workflow(scene_meta: dict) -> dict:
    workflow = copy.deepcopy(_load_template(TEMPLATE_NAME))
    replace_map = {
        "voice_text": scene_meta.get("voice_text", ""),
        "edgetts_voice_id": scene_meta.get("edgetts_voice_id", ""),
    }
    _replace_any_string_values(workflow, replace_map)
    return workflow


def build_edgetts_workflow(scene_meta: dict) -> dict:
    return build_workflow(scene_meta)
