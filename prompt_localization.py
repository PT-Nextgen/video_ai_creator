import copy
import json
import os
import ast
from dataclasses import dataclass
from typing import Callable

import requests

from gemini.gemini_image import find_gemini_key


PROMPT_TOP_LEVEL_FIELDS = {
    "scene_meta.json": ["sound_prompt"],
    "z_image_prompt.json": ["positive_prompt", "negative_prompt"],
    "wan22_i2v_prompt.json": [
        "positive_prompt_one",
        "negative_prompt_one",
        "positive_prompt_two",
        "negative_prompt_two",
        "positive_prompt_three",
        "negative_prompt_three",
    ],
    "wan22_s2v_prompt.json": ["positive_prompt", "negative_prompt"],
    "cover_prompt.json": ["positive_prompt", "negative_prompt"],
}

GROUP_PROMPT_FIELDS = {
    "z_image_extra_prompts.json": ["positive_prompt", "negative_prompt"],
    "image_edit_prompt.json": ["prompt"],
}


@dataclass
class I18NPrompt:
    id_old: str
    id_new: str
    en: str


class GeminiPromptTranslator:
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name
        self.api_key = find_gemini_key()
        self._cache: dict[str, str] = {}

    def translate_to_english(self, text: str) -> str:
        text = _clean_text(text)
        if not text:
            return ""
        if text in self._cache:
            return self._cache[text]
        if not self.api_key:
            raise RuntimeError(
                "Gemini API key tidak ditemukan. Tambahkan GEMINIKEY / GEMINI_API_KEY / GOOGLE_API_KEY di keys.cfg."
            )

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
            f"?key={self.api_key}"
        )
        instruction = (
            "Translate the following prompt to natural English for AI generation.\n"
            "Preserve intent, style, and detail.\n"
            "Return only the translated text without extra explanation."
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": instruction},
                        {"text": text},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
            },
        }

        response = requests.post(url, json=payload, timeout=60)
        if response.status_code >= 400:
            raise RuntimeError(f"Gemini translate error {response.status_code}: {response.text[:600]}")

        translated = _extract_text_from_gemini_response(response.json())
        translated = _clean_text(translated)
        if not translated:
            translated = text
        self._cache[text] = translated
        return translated


def _clean_text(value) -> str:
    return str(value or "").strip()


def _maybe_parse_prompt_object_string(value):
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    if not (text.startswith("{") and text.endswith("}")):
        return value
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return value


def _extract_text_from_gemini_response(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    for cand in candidates:
        content = cand.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            text = part.get("text")
            if text:
                return str(text)
    return ""


def _normalize_prompt_entry(value) -> I18NPrompt:
    value = _maybe_parse_prompt_object_string(value)
    if isinstance(value, dict) and any(key in value for key in ("id_old", "id_new", "en")):
        old_raw = _maybe_parse_prompt_object_string(value.get("id_old"))
        new_raw = _maybe_parse_prompt_object_string(value.get("id_new"))
        en_raw = _maybe_parse_prompt_object_string(value.get("en"))

        if isinstance(old_raw, dict):
            old_raw = _normalize_prompt_entry(old_raw).id_new
        if isinstance(new_raw, dict):
            new_raw = _normalize_prompt_entry(new_raw).id_new
        if isinstance(en_raw, dict):
            en_raw = _normalize_prompt_entry(en_raw).en or _normalize_prompt_entry(en_raw).id_new

        old_text = _clean_text(old_raw)
        new_text = _clean_text(new_raw)
        en_text = _clean_text(en_raw)
        if not old_text:
            old_text = en_text or new_text
        if not en_text and new_text and old_text == new_text:
            en_text = new_text
        return I18NPrompt(id_old=old_text, id_new=new_text, en=en_text)
    text = _clean_text(value)
    return I18NPrompt(id_old=text, id_new=text, en=text)


def _prompt_entry_for_save(existing_value, new_value) -> dict:
    existing = _normalize_prompt_entry(existing_value)
    new_text = _normalize_prompt_entry(new_value).id_new
    old_text = existing.id_old if existing.id_old else new_text
    return {"id_old": old_text, "id_new": new_text, "en": existing.en}


def _prompt_entry_for_runtime(
    existing_value,
    translate_fn: Callable[[str], str],
    log_fn: Callable[[str], None] | None = None,
) -> tuple[dict, str, bool]:
    existing = _normalize_prompt_entry(existing_value)
    changed = not isinstance(existing_value, dict)
    should_translate = bool(existing.id_new) and (existing.id_old != existing.id_new or not existing.en)
    if should_translate:
        try:
            existing.en = _clean_text(translate_fn(existing.id_new))
            existing.id_old = existing.id_new
            changed = True
        except Exception as e:
            existing.en = ""
            if log_fn:
                log_fn(f"Gagal translate prompt ke Inggris, fallback ke teks terbaru: {e}")
    if not existing.id_new:
        runtime_text = ""
    else:
        runtime_text = existing.en or existing.id_new
    normalized = {"id_old": existing.id_old, "id_new": existing.id_new, "en": existing.en}
    if isinstance(existing_value, dict) and existing_value != normalized:
        changed = True
    return normalized, runtime_text, changed


def _top_level_fields_for(filename: str) -> list[str]:
    return PROMPT_TOP_LEVEL_FIELDS.get(str(filename or ""), [])


def _group_fields_for(filename: str) -> list[str]:
    return GROUP_PROMPT_FIELDS.get(str(filename or ""), [])


def _get_group_item(groups_value, index: int):
    if isinstance(groups_value, list) and 0 <= index < len(groups_value) and isinstance(groups_value[index], dict):
        return groups_value[index]
    return {}


def convert_prompt_payload_for_ui(filename: str, data: dict) -> dict:
    result = copy.deepcopy(data or {})
    for key in _top_level_fields_for(filename):
        result[key] = _normalize_prompt_entry(result.get(key)).id_new

    group_fields = _group_fields_for(filename)
    if group_fields:
        groups = result.get("groups")
        if isinstance(groups, list):
            for idx, item in enumerate(groups):
                if not isinstance(item, dict):
                    continue
                for key in group_fields:
                    item[key] = _normalize_prompt_entry(item.get(key)).id_new
                groups[idx] = item
            result["groups"] = groups
    return result


def prepare_prompt_payload_for_save(filename: str, data: dict, existing_data: dict | None = None) -> dict:
    result = copy.deepcopy(data or {})
    existing = existing_data if isinstance(existing_data, dict) else {}

    for key in _top_level_fields_for(filename):
        result[key] = _prompt_entry_for_save(existing.get(key), result.get(key))

    group_fields = _group_fields_for(filename)
    if group_fields:
        groups = result.get("groups")
        existing_groups = existing.get("groups")
        if isinstance(groups, list):
            new_groups = []
            for idx, item in enumerate(groups):
                item = dict(item) if isinstance(item, dict) else {}
                existing_item = _get_group_item(existing_groups, idx)
                for key in group_fields:
                    item[key] = _prompt_entry_for_save(existing_item.get(key), item.get(key))
                new_groups.append(item)
            result["groups"] = new_groups
    return result


def resolve_prompt_payload_for_runtime(
    filename: str,
    data: dict,
    translate_fn: Callable[[str], str],
    log_fn: Callable[[str], None] | None = None,
) -> tuple[dict, dict, bool]:
    source = copy.deepcopy(data or {})
    resolved = copy.deepcopy(source)
    stored = copy.deepcopy(source)
    changed = False

    for key in _top_level_fields_for(filename):
        entry_value = source.get(key)
        stored_entry, runtime_text, entry_changed = _prompt_entry_for_runtime(entry_value, translate_fn, log_fn=log_fn)
        stored[key] = stored_entry
        resolved[key] = runtime_text
        changed = changed or entry_changed

    group_fields = _group_fields_for(filename)
    if group_fields:
        groups = source.get("groups")
        if isinstance(groups, list):
            stored_groups = []
            resolved_groups = []
            for item in groups:
                src_item = dict(item) if isinstance(item, dict) else {}
                out_stored_item = dict(src_item)
                out_resolved_item = dict(src_item)
                for key in group_fields:
                    stored_entry, runtime_text, entry_changed = _prompt_entry_for_runtime(
                        src_item.get(key),
                        translate_fn,
                        log_fn=log_fn,
                    )
                    out_stored_item[key] = stored_entry
                    out_resolved_item[key] = runtime_text
                    changed = changed or entry_changed
                stored_groups.append(out_stored_item)
                resolved_groups.append(out_resolved_item)
            stored["groups"] = stored_groups
            resolved["groups"] = resolved_groups

    return resolved, stored, changed


def _read_json_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_file(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_json_for_runtime(
    path: str,
    required: bool = False,
    persist_updates: bool = True,
    log_fn: Callable[[str], None] | None = None,
) -> dict:
    if not os.path.exists(path):
        if required:
            raise FileNotFoundError(path)
        return {}

    source = _read_json_file(path)
    filename = os.path.basename(path)
    translator = GeminiPromptTranslator()
    resolved, stored, changed = resolve_prompt_payload_for_runtime(
        filename,
        source,
        translate_fn=translator.translate_to_english,
        log_fn=log_fn,
    )
    if changed and persist_updates:
        _write_json_file(path, stored)
        if log_fn:
            log_fn(f"Prompt localization diperbarui: {path}")
    return resolved
