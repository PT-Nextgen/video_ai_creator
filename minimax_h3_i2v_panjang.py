"""Shared defaults for the chained MiniMax H3 I2VA scene."""
from __future__ import annotations

import copy

from minimax_h3_i2v.minimax_h3_i2v import DEFAULT_PROMPT as DEFAULT_I2V_PROMPT


SCENE_TYPE = "minimax-h3_i2v-panjang"
PROMPT_FILENAME = "minimax_h3_i2v_panjang_prompt.json"
MAX_PROMPTS = 4


def build_default_prompt() -> dict:
    base = copy.deepcopy(DEFAULT_I2V_PROMPT)
    first_entry = copy.deepcopy(base.pop("positive_prompt"))
    base["continuations"] = 0
    base["prompts"] = [copy.deepcopy(first_entry) for _ in range(MAX_PROMPTS)]
    return base


DEFAULT_PROMPT = build_default_prompt()
