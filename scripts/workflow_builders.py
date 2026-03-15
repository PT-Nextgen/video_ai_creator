import copy
import json
import os

from edgetts.edgetts import build_edgetts_workflow
from wan22_i2v.wan22_i2v import build_wan_workflow
from z_image.z_image import build_z_image_workflow


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TEMPLATE = os.path.join(ROOT, "api_template")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_template(name):
    return load_json(os.path.join(API_TEMPLATE, name))


def traverse_and_replace(node, replace_map):
    if isinstance(node, dict):
        inputs = node.get("inputs")
        if isinstance(inputs, dict) and "text" in inputs:
            val = inputs["text"]
            if isinstance(val, str) and val in replace_map:
                inputs["text"] = replace_map[val]
        for value in node.values():
            traverse_and_replace(value, replace_map)
    elif isinstance(node, list):
        for item in node:
            traverse_and_replace(item, replace_map)


def replace_any_string_values(node, replace_map):
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, str):
                if value in replace_map:
                    node[key] = replace_map[value]
            else:
                replace_any_string_values(value, replace_map)
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            if isinstance(item, str):
                if item in replace_map:
                    node[idx] = replace_map[item]
            else:
                replace_any_string_values(item, replace_map)
