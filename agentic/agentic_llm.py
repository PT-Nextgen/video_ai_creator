"""Gemini text-only API and prompt builder for agentic variations."""
import copy
import json
import re
import time
from pathlib import Path

import requests

from logging_config import write_log
from gemini.gemini_image import find_gemini_key
from minimax_h3_i2v.minimax_h3_i2v import is_valid_minimax_h3_i2v_prompt
from prompt_localization import get_prompt_translator, prepare_prompt_payload_for_save
from minimax_h3_prompt import (
    REF2VA_SECTION_KEYS,
    validate_ref2va_prompt,
    validate_ref2va_reference_tokens,
    validate_structured_prompt,
)

LOCAL_PROMPT_PROVIDER = "llama.cpp"
LEGACY_LOCAL_PROMPT_PROVIDER = "ollama"
DEFAULT_LOCAL_PROMPT_HOST = "nextgenserver"
DEFAULT_LOCAL_PROMPT_PORT = 8080


# ---------------------------------------------------------------------------
# Gemini text-only API
# ---------------------------------------------------------------------------

def call_gemini_text(
    prompt: str,
    model_name: str = "gemini-3.1-flash-lite",
    api_key: str | None = None,
    timeout: int = 120,
    response_mime_type: str | None = None,
    response_json_schema: dict | None = None,
) -> str:
    """Call Gemini API with text-only response (no images).

    Returns the translated/generated text from the model.
    Raises RuntimeError on failure.
    """
    if not api_key:
        api_key = find_gemini_key()
    if not api_key:
        raise RuntimeError(
            "Gemini API key tidak ditemukan. Tambahkan GEMINIKEY / GEMINI_API_KEY / GOOGLE_API_KEY di keys.cfg."
        )

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        f"?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["TEXT"],
        },
    }
    if response_mime_type:
        payload["generationConfig"]["responseMimeType"] = str(response_mime_type).strip()
    if isinstance(response_json_schema, dict) and response_json_schema:
        payload["generationConfig"]["responseJsonSchema"] = response_json_schema

    start_time = time.perf_counter()
    resp = requests.post(url, json=payload, timeout=timeout)
    elapsed = time.perf_counter() - start_time

    if resp.status_code >= 400:
        write_log(
            f"[gemini] text generation gagal | model={model_name} | elapsed={elapsed:.3f}s | "
            f"status={resp.status_code} | error={resp.text[:600]}",
            level="error",
        )
        raise RuntimeError(f"Gemini error {resp.status_code}: {resp.text[:600]}")

    result = resp.json()
    text = _extract_text_from_gemini_response(result)
    if not text:
        write_log(
            f"[gemini] text generation gagal — response tanpa teks | model={model_name} | elapsed={elapsed:.3f}s",
            level="error",
        )
        raise RuntimeError(f"Gemini response has no text data: {json.dumps(result)[:500]}")

    write_log(
        f"[gemini] text generation sukses | model={model_name} | elapsed={elapsed:.3f}s"
    )
    return _clean_text(text)


def call_llama_cpp_text(
    prompt: str,
    model_name: str,
    host: str = DEFAULT_LOCAL_PROMPT_HOST,
    port: int = DEFAULT_LOCAL_PROMPT_PORT,
    timeout: int = 120,
    response_format: str | dict | None = None,
) -> str:
    """Call llama.cpp text API with OpenAI-compatible fallback endpoints."""
    host = str(host or "").strip() or "nextgenserver"
    base_url = host if host.startswith(("http://", "https://")) else f"http://{host}"
    server_base_url = f"{base_url.rstrip('/')}:{int(port)}"
    attempts = [
        (
            f"{server_base_url}/v1/chat/completions",
            {
                "model": str(model_name or "").strip(),
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                **(
                    {"response_format": {"type": "json_object"}}
                    if response_format
                    else {}
                ),
            },
            _extract_best_openai_compatible_text,
        ),
        (
            f"{server_base_url}/completion",
            {
                "prompt": prompt,
            },
            _extract_best_llama_cpp_completion_text,
        ),
        (
            f"{server_base_url}/api/generate",
            {
                "model": str(model_name or "").strip(),
                "prompt": prompt,
                "stream": False,
                **({"format": response_format} if response_format else {}),
            },
            _extract_best_ollama_text,
        ),
    ]
    start_time = time.perf_counter()
    errors: list[str] = []
    prefer_json = bool(response_format)
    for url, payload, extractor in attempts:
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            errors.append(f"{url} -> {exc}")
            continue
        if resp.status_code >= 400:
            errors.append(f"{url} -> HTTP {resp.status_code}: {resp.text[:240]}")
            continue
        result = resp.json()
        text = extractor(result, prefer_json=prefer_json)
        if not text:
            errors.append(f"{url} -> response tanpa teks")
            continue
        elapsed = time.perf_counter() - start_time
        write_log(
            f"[{LOCAL_PROMPT_PROVIDER}] text generation sukses | model={model_name} | host={host} | "
            f"port={port} | elapsed={elapsed:.3f}s | endpoint={url}"
        )
        return _clean_text(text)

    elapsed = time.perf_counter() - start_time
    write_log(
        f"[{LOCAL_PROMPT_PROVIDER}] text generation gagal | model={model_name} | host={host} | port={port} | "
        f"elapsed={elapsed:.3f}s | error={' || '.join(errors[:3])}",
        level="error",
    )
    raise RuntimeError(f"llama.cpp error: {' || '.join(errors[:3])}")


def _extract_text_from_gemini_response(response_json: dict) -> str:
    """Extract text from a Gemini API response."""
    candidates = response_json.get("candidates") or []
    for cand in candidates:
        content = cand.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""


def _extract_json_text_candidate(text: str) -> str:
    text = _clean_text(text)
    if not text:
        return ""
    try:
        json.loads(text)
        return text
    except Exception:
        pass
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if match:
        candidate = _clean_text(match.group(1))
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        candidate = _clean_text(text[brace_start:brace_end + 1])
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    return ""


def _extract_best_ollama_text(result: dict, prefer_json: bool = False) -> str:
    candidates: list[str] = []

    def add_candidate(value):
        if not isinstance(value, str):
            return
        text = _clean_text(value)
        if text and text not in candidates:
            candidates.append(text)

    add_candidate(result.get("response", ""))
    message = result.get("message")
    if isinstance(message, dict):
        add_candidate(message.get("content", ""))
    add_candidate(result.get("thinking", ""))

    response_text = _clean_text(result.get("response", ""))
    thinking_text = _clean_text(result.get("thinking", ""))
    if response_text and thinking_text:
        add_candidate(f"{response_text}\n{thinking_text}")
        add_candidate(f"{thinking_text}\n{response_text}")

    if prefer_json:
        for candidate in candidates:
            json_candidate = _extract_json_text_candidate(candidate)
            if json_candidate:
                return json_candidate
    return candidates[0] if candidates else ""


def _extract_best_openai_compatible_text(result: dict, prefer_json: bool = False) -> str:
    candidates: list[str] = []

    def add_candidate(value):
        if isinstance(value, str):
            text = _clean_text(value)
            if text and text not in candidates:
                candidates.append(text)
        elif isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            if parts:
                add_candidate("\n".join(parts))

    for choice in result.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        add_candidate(choice.get("text", ""))
        message = choice.get("message")
        if isinstance(message, dict):
            add_candidate(message.get("content", ""))
        delta = choice.get("delta")
        if isinstance(delta, dict):
            add_candidate(delta.get("content", ""))

    if prefer_json:
        for candidate in candidates:
            json_candidate = _extract_json_text_candidate(candidate)
            if json_candidate:
                return json_candidate
    return candidates[0] if candidates else ""


def _extract_best_llama_cpp_completion_text(result: dict, prefer_json: bool = False) -> str:
    candidates: list[str] = []
    for key in ("content", "completion", "response"):
        value = result.get(key)
        if isinstance(value, str):
            text = _clean_text(value)
            if text and text not in candidates:
                candidates.append(text)
    if prefer_json:
        for candidate in candidates:
            json_candidate = _extract_json_text_candidate(candidate)
            if json_candidate:
                return json_candidate
    return candidates[0] if candidates else ""


def _clean_text(text: str) -> str:
    """Clean up extracted text."""
    if not text:
        return ""
    # Remove markdown code block wrappers if present
    text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n?\s*```$', '', text, flags=re.MULTILINE)
    return text.strip()


# ---------------------------------------------------------------------------
# File reading helpers
# ---------------------------------------------------------------------------

def _read_json_file(path: Path) -> dict | None:
    """Read a JSON file, return None if not found."""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _normalize_schema_template(filename: str, data: dict | None) -> dict | None:
    """Normalize legacy file payloads into the schema we want to enforce."""
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    if filename == "image_edit_prompt.json":
        normalized.pop("image_model", None)
        normalized.pop("gemini_model_id", None)
    if filename in {
        "z_image_prompt.json",
        "wan22_i2v_prompt.json",
        "wan22_t2v_prompt.json",
        "minimax_h3_t2v_prompt.json",
        "minimax_h3_i2v_prompt.json",
        "minimax_h3_s2v_prompt.json",
        "wan22_s2v_prompt.json",
        "z_image_extra_prompts.json",
        "wan22_t2v_batch_extra_prompts.json",
    }:
        # Older scene files may still contain plain prompt strings. Convert
        # them before constructing the Agentic schema so every generated
        # variation is forced to use id_old/id_new/en objects.
        normalized = prepare_prompt_payload_for_save(filename, normalized)
    return normalized


MINIMAX_AGENTIC_SCENE_TYPES = {"minimax-h3_i2v", "minimax-h3_t2v_i2v", "minimax-h3_s2v", "minimax-h3_r2v"}
MINIMAX_AGENTIC_PROMPT_FILES = {
    "minimax_h3_t2v_prompt.json",
    "minimax_h3_i2v_prompt.json",
    "minimax_h3_s2v_prompt.json",
    "minimax_h3_r2v_prompt.json",
}


def _minimax_agentic_llm_template(filename: str, payload: dict) -> dict:
    """Expose only positive_prompt.en to the LLM for MiniMax prompt files."""
    if filename not in MINIMAX_AGENTIC_PROMPT_FILES:
        return copy.deepcopy(payload)
    positive_prompt = payload.get("positive_prompt")
    en = positive_prompt.get("en") if isinstance(positive_prompt, dict) else None
    # Non-prompt fields are intentionally omitted from the LLM schema. They
    # are restored deterministically from the input payload after validation,
    # so model-generated LoRA/size changes can never consume retry attempts.
    return {
        "positive_prompt": {
            "en": copy.deepcopy(en) if isinstance(en, dict) else {},
        }
    }


def _variation_sort_key(path: Path):
    digits = "".join(ch for ch in path.name if ch.isdigit())
    try:
        return int(digits)
    except Exception:
        return 999999


def _existing_variation_dirs(scene_dir: Path) -> list[Path]:
    if not scene_dir.exists():
        return []
    return sorted(
        [
            child
            for child in scene_dir.iterdir()
            if child.is_dir() and child.name.lower().startswith("variasi")
        ],
        key=_variation_sort_key,
    )


def _collect_existing_variation_payloads(
    scene_dir: Path,
    output_files: list[str],
    max_variation_index: int | None = None,
) -> list[tuple[str, dict[str, dict]]]:
    collected: list[tuple[str, dict[str, dict]]] = []
    for variation_dir in _existing_variation_dirs(scene_dir):
        digits_match = re.search(r"(\d+)$", variation_dir.name.strip())
        variation_index = int(digits_match.group(1)) if digits_match else 999999
        if max_variation_index is not None and variation_index >= max_variation_index:
            continue
        payloads: dict[str, dict] = {}
        for filename in output_files:
            payload = _normalize_schema_template(filename, _read_json_file(variation_dir / filename))
            if isinstance(payload, dict):
                payloads[filename] = payload
        if payloads:
            collected.append((variation_dir.name, payloads))
    return collected


def _prune_to_prompt_only(value, path_parts: tuple[str, ...] = ()):
    if isinstance(value, dict):
        if PROMPT_VALUE_KEYS.issubset({str(key) for key in value.keys()}):
            pruned = {}
            for key in ("id_old", "id_new", "en"):
                if key in value:
                    pruned[key] = value.get(key)
            return pruned
        pruned = {}
        for key, child in value.items():
            child_path = path_parts + (str(key),)
            child_value = _prune_to_prompt_only(child, child_path)
            if child_value is None:
                continue
            if isinstance(child_value, dict) and not child_value:
                continue
            if isinstance(child_value, list) and not child_value:
                continue
            pruned[key] = child_value
        return pruned
    if isinstance(value, list):
        pruned_list = []
        for index, item in enumerate(value):
            child_value = _prune_to_prompt_only(item, path_parts + (f"[{index}]",))
            if child_value is None:
                continue
            if isinstance(child_value, dict) and not child_value:
                continue
            if isinstance(child_value, list) and not child_value:
                continue
            pruned_list.append(child_value)
        return pruned_list
    if _is_prompt_path(path_parts):
        return value
    return None


def _blank_prompt_fields(value, path_parts: tuple[str, ...] = ()):
    if isinstance(value, dict):
        if PROMPT_VALUE_KEYS.issubset({str(key) for key in value.keys()}):
            result = {}
            for key, child in value.items():
                if key in {"id_old", "id_new"}:
                    result[key] = ""
                elif key == "en" and isinstance(child, dict):
                    result[key] = _blank_prompt_fields(child, path_parts + (str(key),))
                else:
                    result[key] = _blank_prompt_fields(child, path_parts + (str(key),))
            return result
        return {
            key: _blank_prompt_fields(child, path_parts + (str(key),))
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [
            _blank_prompt_fields(item, path_parts + (f"[{index}]",))
            for index, item in enumerate(value)
        ]
    if _is_prompt_path(path_parts):
        return ""
    return value


def _read_md_file(path: Path) -> str:
    """Read a markdown file, return empty string if not found."""
    if not path.exists():
        return ""
    try:
        with path.open("r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _json_schema_from_template(value):
    """Build a JSON Schema object from a template payload."""
    if isinstance(value, dict):
        properties = {}
        required = []
        for key, child in value.items():
            properties[str(key)] = _json_schema_from_template(child)
            required.append(str(key))
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
    if isinstance(value, list):
        if not value:
            return {
                "type": "array",
                "items": {},
            }
        item_schemas = [_json_schema_from_template(item) for item in value]
        first_schema = item_schemas[0]
        same_items = all(schema == first_schema for schema in item_schemas[1:])
        schema = {
            "type": "array",
            "minItems": len(value),
            "maxItems": len(value),
        }
        if same_items:
            schema["items"] = first_schema
        else:
            schema["prefixItems"] = item_schemas
            schema["items"] = False
        return schema
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if value is None:
        return {"type": "null"}
    return {"type": "string"}


def _allow_minimax_multishot(schema: dict):
    """Allow Agentic MiniMax schemas to expand the template shot array."""
    if not isinstance(schema, dict):
        return
    properties = schema.get("properties")
    if isinstance(properties, dict):
        shots = properties.get("shots")
        if isinstance(shots, dict) and shots.get("type") == "array":
            shots["minItems"] = 1
            shots.pop("maxItems", None)
        for child in properties.values():
            _allow_minimax_multishot(child)
    items = schema.get("items")
    if isinstance(items, dict):
        _allow_minimax_multishot(items)
    prefix_items = schema.get("prefixItems")
    if isinstance(prefix_items, list):
        for child in prefix_items:
            _allow_minimax_multishot(child)


def _minimax_structured_en_schema(mode: str) -> dict:
    """Return an explicit schema even when the source scene has no shots yet."""
    mode = "I2VA" if str(mode).upper() == "I2VA" else "T2VA"
    shot_properties = {
        "shot_id": {"type": "string"},
        "start": {"type": "number"},
        "end": {"type": "number"},
        "visual": {"type": "string"},
        "action": {"type": "string"},
        "camera": {"type": "string"},
        "dialogue": {"type": "string"},
        "diegetic_sound": {"type": "string"},
    }
    properties = {
        "mode": {"type": "string", "enum": [mode]},
        "shots": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": shot_properties,
                "required": list(shot_properties.keys()),
                "additionalProperties": False,
            },
        },
        "overall_soundscape": {"type": "string"},
        "non_diegetic_music": {"type": "string"},
    }
    required = ["mode", "shots", "overall_soundscape", "non_diegetic_music"]
    if mode == "I2VA":
        reference_properties = {
            "picture": {"type": "string", "enum": ["Picture 1"]},
            "source": {"type": "string", "enum": ["[Shot 1]"]},
            "time": {"type": "number", "enum": [0.0]},
            "instruction": {"type": "string", "enum": ["fully referenced"]},
        }
        properties["reference"] = {
            "type": "object",
            "properties": reference_properties,
            "required": list(reference_properties.keys()),
            "additionalProperties": False,
        }
        required.append("reference")
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _apply_minimax_structured_schema(filename: str, file_schema: dict):
    """Apply the canonical T2VA, I2VA, or Ref2VA response schema."""
    if filename not in MINIMAX_AGENTIC_PROMPT_FILES:
        return
    try:
        en_parent = file_schema["properties"]["positive_prompt"]["properties"]
    except (KeyError, TypeError):
        return
    if filename in {"minimax_h3_s2v_prompt.json", "minimax_h3_r2v_prompt.json"}:
        properties = {key: {"type": "string"} for key in REF2VA_SECTION_KEYS}
        en_parent["en"] = {
            "type": "object",
            "properties": properties,
            "required": list(REF2VA_SECTION_KEYS),
            "additionalProperties": False,
        }
        return
    mode = "I2VA" if filename.endswith("i2v_prompt.json") else "T2VA"
    en_parent["en"] = _minimax_structured_en_schema(mode)


def build_agentic_output_schema(
    scene_dir: Path,
    scene_type: str,
    agentic_config: dict,
) -> dict:
    """Build the structured-output JSON schema for agentic LLM responses."""
    scene_dir = Path(scene_dir)
    properties = {}
    required = []
    for filename in _get_scene_type_outputs(scene_type, agentic_config):
        template_path = scene_dir / filename
        template_payload = _normalize_schema_template(filename, _read_json_file(template_path))
        if not isinstance(template_payload, dict):
            continue
        if scene_type in MINIMAX_AGENTIC_SCENE_TYPES:
            template_payload = _minimax_agentic_llm_template(filename, template_payload)
        properties[filename] = _json_schema_from_template(template_payload)
        _apply_minimax_structured_schema(filename, properties[filename])
        if scene_type in {"minimax-h3_i2v", "minimax-h3_t2v_i2v"} and filename.startswith("minimax_h3_"):
            _allow_minimax_multishot(properties[filename])
        required.append(filename)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    try:
        with path.open("r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

AGENT_SKILLS_DIR = Path(__file__).parent.parent / "api_production" / "AGENT-SKILLS"

SCENE_TYPE_FILES = {
    # (json_files, md_files)
    "wan22_i2v": (
        ["z_image_prompt.json", "wan22_i2v_prompt.json"],
        [
            "SCENE-GENERAL.md",
            "SCENE-WAN22-I2V.md",
            "TEXT-TO-IMAGE.md",
            "IMAGE-TO-VIDEO.md",
            "IMAGE-PROMPT.md",
            "IMAGE-TO-VIDEO-PROMPT.md",
        ],
    ),
    "wan22_t2v_i2v": (
        ["wan22_t2v_prompt.json", "wan22_i2v_prompt.json"],
        [
            "SCENE-GENERAL.md",
            "SCENE-WAN22-T2V-I2V.md",
            "TEXT-TO-VIDEO.md",
            "TEXT-TO-VIDEO-PROMPT.md",
            "IMAGE-TO-VIDEO-PROMPT.md",
        ],
    ),
    "minimax-h3_t2v_i2v": (
        ["minimax_h3_t2v_prompt.json", "minimax_h3_i2v_prompt.json"],
        [
            "SCENE-GENERAL.md",
            "SCENE-MINIMAX-H3-T2V-I2V.md",
            "MINIMAX-H3/SKILL.md",
            "MINIMAX-H3/references/base-en.txt",
        ],
    ),
    "minimax-h3_i2v": (
        ["z_image_prompt.json", "minimax_h3_i2v_prompt.json"],
        [
            "SCENE-GENERAL.md",
            "SCENE-MINIMAX-H3-I2V.md",
            "TEXT-TO-IMAGE.md",
            "IMAGE-PROMPT.md",
            "MINIMAX-H3/SKILL.md",
            "MINIMAX-H3/references/base-en.txt",
        ],
    ),
    "minimax-h3_s2v": (
        ["z_image_prompt.json", "minimax_h3_s2v_prompt.json"],
        [
            "SCENE-GENERAL.md",
            "SCENE-MINIMAX-H3-S2V.md",
            "TEXT-TO-IMAGE.md",
            "IMAGE-PROMPT.md",
            "MINIMAX-H3/SKILL.md",
            "MINIMAX-H3/references/ref-en.txt",
        ],
    ),
    "minimax-h3_r2v": (
        ["minimax_h3_r2v_prompt.json"],
        [
            "SCENE-GENERAL.md",
            "SCENE-MINIMAX-H3-S2V.md",
            "MINIMAX-H3/SKILL.md",
            "MINIMAX-H3/references/ref-en.txt",
        ],
    ),
    "wan22_t2v_batch": (
        ["wan22_t2v_prompt.json", "wan22_t2v_batch_extra_prompts.json"],
        [
            "SCENE-GENERAL.md",
            "SCENE-WAN22-T2V-BATCH.md",
            "TEXT-TO-VIDEO-BATCH.md",
            "TEXT-TO-VIDEO-PROMPT.md",
        ],
    ),
    "wan22_s2v": (
        ["wan22_s2v_prompt.json", "z_image_prompt.json"],
        [
            "SCENE-GENERAL.md",
            "SCENE-WAN22-S2V.md",
            "TEXT-TO-IMAGE.md",
            "IMAGE-SOUND-TO-VIDEO.md",
            "IMAGE-PROMPT.md",
            "IMAGE-TO-VIDEO-PROMPT.md",
        ],
    ),
    "i2v": (
        ["z_image_prompt.json"],
        [
            "SCENE-GENERAL.md",
            "SCENE-I2V.md",
            "TEXT-TO-IMAGE.md",
            "IMAGE-PROMPT.md",
        ],
    ),
    "image_pan": (
        ["z_image_prompt.json"],
        [
            "SCENE-GENERAL.md",
            "SCENE-IMAGE-PAN.md",
            "TEXT-TO-IMAGE.md",
            "IMAGE-PROMPT.md",
        ],
    ),
    "image_zoom": (
        ["z_image_prompt.json"],
        [
            "SCENE-GENERAL.md",
            "SCENE-IMAGE-ZOOM.md",
            "TEXT-TO-IMAGE.md",
            "IMAGE-PROMPT.md",
        ],
    ),
}

# Output files that LLM should produce for each scene type
SCENE_TYPE_OUTPUTS = {
    "wan22_i2v": ["z_image_prompt.json", "wan22_i2v_prompt.json"],
    "wan22_t2v_i2v": ["wan22_t2v_prompt.json", "wan22_i2v_prompt.json"],
    "minimax-h3_t2v_i2v": ["minimax_h3_t2v_prompt.json", "minimax_h3_i2v_prompt.json"],
    "minimax-h3_i2v": ["z_image_prompt.json", "minimax_h3_i2v_prompt.json"],
    "minimax-h3_s2v": ["z_image_prompt.json", "minimax_h3_s2v_prompt.json"],
    "minimax-h3_r2v": ["minimax_h3_r2v_prompt.json"],
    "wan22_t2v_batch": ["wan22_t2v_prompt.json", "wan22_t2v_batch_extra_prompts.json"],
    "wan22_s2v": ["wan22_s2v_prompt.json", "z_image_prompt.json"],
    "i2v": ["z_image_prompt.json"],
    "image_pan": ["z_image_prompt.json"],
    "image_zoom": ["z_image_prompt.json"],
}

PROMPT_VALUE_KEYS = {"id_old", "id_new", "en"}
STRICT_NON_EMPTY_AGENTIC_PROMPT_FILES = {
    "wan22_t2v_prompt.json",
    "wan22_i2v_prompt.json",
    "minimax_h3_t2v_prompt.json",
    "minimax_h3_i2v_prompt.json",
    "minimax_h3_s2v_prompt.json",
    "minimax_h3_r2v_prompt.json",
    "z_image_prompt.json",
    "z_image_extra_prompts.json",
    "wan22_t2v_batch_extra_prompts.json",
}


def _get_scene_type_outputs(scene_type: str, agentic_config: dict) -> list[str]:
    """Get the list of output JSON files for a scene type."""
    outputs = list(SCENE_TYPE_OUTPUTS.get(scene_type, []))

    # wan22_s2v with create_initial_image=false → only wan22_s2v_prompt.json
    if scene_type == "wan22_s2v" and not agentic_config.get("create_initial_image", True):
        outputs = ["wan22_s2v_prompt.json"]

    # i2v with image_extra → add z_image_extra_prompts.json
    if scene_type == "i2v":
        mode = agentic_config.get("image_extra_mode", "image_extra")
        if mode == "image_extra":
            outputs.append("z_image_extra_prompts.json")
        elif mode == "image_edit":
            outputs.append("image_edit_prompt.json")

    return outputs


def _get_scene_type_input_files(scene_type: str, agentic_config: dict) -> list[str]:
    """Get the list of input JSON files for a scene type."""
    json_files, _ = SCENE_TYPE_FILES.get(scene_type, ([], []))
    json_files = list(json_files)

    # wan22_s2v with create_initial_image=false → skip z_image_prompt.json
    if scene_type == "wan22_s2v" and not agentic_config.get("create_initial_image", True):
        json_files = [f for f in json_files if f != "z_image_prompt.json"]

    # i2v with image_edit → replace z_image_extra_prompts.json with image_edit_prompt.json
    if scene_type == "i2v":
        mode = agentic_config.get("image_extra_mode", "image_extra")
        if mode == "image_extra":
            if "z_image_extra_prompts.json" not in json_files:
                json_files.append("z_image_extra_prompts.json")
        elif mode == "image_edit":
            if "image_edit_prompt.json" not in json_files:
                json_files.append("image_edit_prompt.json")

    return json_files


def _get_scene_type_md_files(scene_type: str, agentic_config: dict) -> list[str]:
    """Get the list of input MD files for a scene type."""
    _, md_files = SCENE_TYPE_FILES.get(scene_type, ([], []))
    md_files = list(md_files)

    # i2v with image_extra → add note about extra images
    if scene_type == "i2v":
        mode = agentic_config.get("image_extra_mode", "image_extra")
        if mode == "image_extra":
            md_files.append("__NOTE_IMAGE_EXTRA__")
        elif mode == "image_edit":
            md_files.append("__NOTE_IMAGE_EDIT__")

    # wan22_s2v with create_initial_image=false → add note
    if scene_type == "wan22_s2v" and not agentic_config.get("create_initial_image", True):
        md_files.append("__NOTE_NO_INITIAL_IMAGE__")

    return md_files


def build_agentic_prompt(
    scene_dir: Path,
    scene_type: str,
    agentic_config: dict,
    project_settings: dict,
    all_scenes_meta: list[dict],
    current_variation_index: int | None = None,
) -> str:
    """Build the full prompt to send to Gemini for generating variations.

    Returns a single string prompt containing:
    1. Project description
    2. All scenes context (title, description, voice_text)
    3. Current scene details
    4. Special command
    5. Input JSON files content
    6. Reference MD files content
    7. Existing variation JSONs for anti-duplication guidance
    8. Instructions for output format
    """
    scene_dir = Path(scene_dir)
    lines = []

    # ---- Part 1: Project Description ----
    project_desc = project_settings.get("project_description", "")
    lines.append("=" * 60)
    lines.append("PROYEK VIDEO")
    lines.append("=" * 60)
    if project_desc:
        lines.append(f"Deskripsi project: {project_desc}")
    else:
        lines.append("(Tidak ada deskripsi project)")
    lines.append("")

    # ---- Part 2: All Scenes Context ----
    lines.append("=" * 60)
    lines.append("DAFTAR SEMUA SCENE DALAM PROYEK")
    lines.append("=" * 60)
    if all_scenes_meta:
        for meta in all_scenes_meta:
            title = meta.get("scene_title", "")
            desc = meta.get("scene_description", "")
            voice = meta.get("voice_text", "")
            stype = meta.get("scene_type", "")
            lines.append(f"\n  Scene: {title}")
            lines.append(f"  Tipe: {stype}")
            lines.append(f"  Deskripsi: {desc}")
            lines.append(f"  Voice text: {voice}")
    else:
        lines.append("(Tidak ada data scene)")
    lines.append("")

    # ---- Part 3: Current Scene Details ----
    current_meta_path = scene_dir / "scene_meta.json"
    current_meta = _read_json_file(current_meta_path) or {}
    title = current_meta.get("scene_title", "")
    desc = current_meta.get("scene_description", "")
    voice = current_meta.get("voice_text", "")
    duration = current_meta.get("duration_seconds", "")

    lines.append("=" * 60)
    lines.append(f"SCENE YANG AKAN DIVARIASIKAN")
    lines.append("=" * 60)
    lines.append(f"Scene: {title}")
    lines.append(f"Tipe: {scene_type}")
    lines.append(f"Deskripsi: {desc}")
    lines.append(f"Voice text: {voice}")
    if duration:
        lines.append(f"Durasi: {duration} detik")
    lines.append("")

    # ---- Part 4: Input JSON Files ----
    json_files = _get_scene_type_input_files(scene_type, agentic_config)
    if json_files:
        lines.append("=" * 60)
        lines.append("FILE KONFIGURASI YANG HARUS DIVARIASIKAN")
        lines.append("=" * 60)
        for jf in json_files:
            jpath = scene_dir / jf
            content = _normalize_schema_template(jf, _read_json_file(jpath))
            if content is not None:
                lines.append(f"\n--- {jf} ---")
                lines.append(json.dumps(_blank_prompt_fields(content), ensure_ascii=False, indent=2))
        lines.append("")

    # ---- Part 6: Reference MD Files ----
    lines.append("=" * 60)
    lines.append("PANDUAN REFERENSI")
    lines.append("=" * 60)

    def append_md_group(title: str, files: list[str], extra_note: str | None = None):
        lines.append(f"\n{title}")
        if extra_note:
            lines.append(extra_note)
        for mf in files:
            md_path = AGENT_SKILLS_DIR / mf
            content = _read_md_file(md_path)
            if content:
                lines.append("")
                lines.append(f"REFERENCE MARKDOWN FILE: {mf}")
                lines.append(content)

    if scene_type == "wan22_i2v":
        append_md_group(
            "1. Scene wan22_i2v",
            [
                "SCENE-GENERAL.md",
                "SCENE-WAN22-I2V.md",
                "TEXT-TO-IMAGE.md",
                "IMAGE-TO-VIDEO.md",
                "IMAGE-PROMPT.md",
                "IMAGE-TO-VIDEO-PROMPT.md",
            ],
        )
    elif scene_type == "wan22_t2v_i2v":
        append_md_group(
            "2. Scene wan22_t2v_i2v",
            [
                "SCENE-GENERAL.md",
                "SCENE-WAN22-T2V-I2V.md",
                "TEXT-TO-VIDEO.md",
                "TEXT-TO-VIDEO-PROMPT.md",
                "IMAGE-TO-VIDEO-PROMPT.md",
            ],
        )
    elif scene_type == "minimax-h3_t2v_i2v":
        append_md_group(
            "2. Scene minimax-h3_t2v_i2v",
            [
                "SCENE-GENERAL.md",
                "SCENE-MINIMAX-H3-T2V-I2V.md",
                "MINIMAX-H3/SKILL.md",
                "MINIMAX-H3/references/base-en.txt",
            ],
            "CATATAN: T2VA dipakai untuk durasi 1/5/10/15 detik. Untuk 20/25/30 detik, T2VA berjalan 15 detik lalu I2VA melanjutkan dari frame terakhir T2VA.",
        )
    elif scene_type == "minimax-h3_i2v":
        append_md_group(
            "3. Scene minimax-h3_i2v",
            [
                "SCENE-GENERAL.md",
                "SCENE-MINIMAX-H3-I2V.md",
                "TEXT-TO-IMAGE.md",
                "IMAGE-PROMPT.md",
                "MINIMAX-H3/SKILL.md",
                "MINIMAX-H3/references/base-en.txt",
            ],
            "CATATAN: scene ini memakai gambar terbaru di root scene sebagai Picture 1 untuk workflow MiniMax H3 I2VA; durasi hanya 1, 5, 10, atau 15 detik.",
        )
    elif scene_type == "minimax-h3_r2v":
        r2v_references = {}
        try:
            r2v_payload = _read_json_file(scene_dir / "minimax_h3_r2v_prompt.json")
            r2v_references = r2v_payload.get("references", {}) if isinstance(r2v_payload, dict) else {}
        except Exception:
            r2v_references = {}
        r2v_references = r2v_references if isinstance(r2v_references, dict) else {}
        active_images = [str(value).strip() for value in r2v_references.get("images", []) if str(value).strip()][:3]
        active_audios = [str(value).strip() for value in r2v_references.get("audios", []) if str(value).strip()][:3]
        active_video = str(r2v_references.get("video", "") or "").strip()
        append_md_group(
            "3. Scene minimax-h3_r2v",
            [
                "SCENE-GENERAL.md",
                "SCENE-MINIMAX-H3-S2V.md",
                "MINIMAX-H3/SKILL.md",
                "MINIMAX-H3/references/ref-en.txt",
            ],
            "CATATAN: scene R2V memakai kombinasi dinamis maksimal 3 Picture, 1 Video, dan 3 Audio. "
            "Gunakan hanya token reference yang tercantum pada konfigurasi input, dengan penomoran tiap kategori berurutan. "
            "Minimal satu reference wajib dipakai. Durasi scene hanya 1, 5, 10, atau 15 detik. "
            "Jangan membuat atau mengubah image awal.",
        )
        lines.extend([
            "ACTIVE R2V REFERENCE MANIFEST:",
            f"Picture references: {', '.join(f'<Picture {i + 1}>' for i, _ in enumerate(active_images)) or 'none'}",
            f"Video references: {'<Video 1>' if active_video else 'none'}",
            f"Audio references: {', '.join(f'<Audio {i + 1}>' for i, _ in enumerate(active_audios)) or 'none'}",
            "STRICT RULE: use only the active Picture, Video, and Audio tokens listed in this manifest.",
            "Do not invent, rename, or renumber a Picture, Video, or Audio token. If a category is none, do not mention it.",
            "Non-reference semantic tokens such as <Subject N>, <Shot N>, <d>, </d>, and speaker IDs are allowed.",
            "Keep every active reference token exactly unchanged across all six Ref2VA sections.",
        ])
    elif scene_type == "wan22_t2v_batch":
        append_md_group(
            "2. Scene wan22_t2v_batch",
            [
                "SCENE-GENERAL.md",
                "SCENE-WAN22-T2V-BATCH.md",
                "TEXT-TO-VIDEO-BATCH.md",
                "TEXT-TO-VIDEO-PROMPT.md",
            ],
            "CATATAN: scene ini hanya memakai T2V utama dan 3 slot Prompt Tambahan; tidak ada tahap I2V.",
        )
    elif scene_type == "wan22_s2v":
        if agentic_config.get("create_initial_image", True):
            append_md_group(
                "3. Scene wan22_s2v",
                [
                    "SCENE-GENERAL.md",
                    "SCENE-WAN22-S2V.md",
                    "TEXT-TO-IMAGE.md",
                    "IMAGE-SOUND-TO-VIDEO.md",
                    "IMAGE-PROMPT.md",
                    "IMAGE-TO-VIDEO-PROMPT.md",
                ],
            )
        else:
            append_md_group(
                "3. Scene wan22_s2v",
                [
                    "SCENE-GENERAL.md",
                    "SCENE-WAN22-S2V.md",
                    "IMAGE-SOUND-TO-VIDEO.md",
                    "IMAGE-TO-VIDEO-PROMPT.md",
                ],
                "CATATAN: image awal tidak divariasikan.",
            )
    elif scene_type == "i2v":
        image_extra_mode = str(agentic_config.get("image_extra_mode", "image_extra")).strip()
        if image_extra_mode == "image_extra":
            append_md_group(
                "4. Scene i2v",
                [
                    "SCENE-GENERAL.md",
                    "SCENE-I2V.md",
                    "TEXT-TO-IMAGE.md",
                    "IMAGE-PROMPT.md",
                ],
                "CATATAN: image awal tambahan dibuat dengan memakai metode image extra.",
            )
        else:
            append_md_group(
                "4. Scene i2v",
                [
                    "SCENE-GENERAL.md",
                    "SCENE-I2V.md",
                    "TEXT-TO-IMAGE.md",
                    "IMAGE-PROMPT.md",
                ],
                "CATATAN: image awal tambahan dibuat dengan memakai metode image edit.",
            )
    elif scene_type == "image_pan":
        append_md_group(
            "5. Scene image_pan",
            [
                "SCENE-GENERAL.md",
                "SCENE-IMAGE-PAN.md",
                "TEXT-TO-IMAGE.md",
                "IMAGE-PROMPT.md",
            ],
        )
    elif scene_type == "image_zoom":
        append_md_group(
            "6. Scene image_zoom",
            [
                "SCENE-GENERAL.md",
                "SCENE-IMAGE-ZOOM.md",
                "TEXT-TO-IMAGE.md",
                "IMAGE-PROMPT.md",
            ],
        )
    lines.append("")

    # ---- Part 7: Existing Variation Outputs ----
    output_files = _get_scene_type_outputs(scene_type, agentic_config)
    existing_variations = _collect_existing_variation_payloads(
        scene_dir,
        output_files,
        max_variation_index=current_variation_index,
    )
    lines.append("=" * 60)
    lines.append("VARIASI YANG SUDAH DIBUAT SEBELUMNYA")
    lines.append("=" * 60)
    if existing_variations:
        lines.append(
            "Berikut adalah isi JSON dari variasi yang sudah dibuat sebelumnya. "
            "Gunakan semuanya sebagai pembanding agar variasi baru TIDAK SAMA dengan variasi yang sudah ada."
        )
        for variation_name, payloads in existing_variations:
            lines.append(f"\n--- {variation_name} ---")
            for filename in output_files:
                payload = payloads.get(filename)
                if isinstance(payload, dict):
                    prompt_only = _prune_to_prompt_only(payload)
                    if prompt_only is None:
                        continue
                    if isinstance(prompt_only, dict) and not prompt_only:
                        continue
                    lines.append(f"\n### {filename}")
                    lines.append(json.dumps(prompt_only, ensure_ascii=False, indent=2))
    else:
        lines.append("(Belum ada variasi sebelumnya untuk scene ini)")
    lines.append("")

    # Repeat the active manifest after all reference documents and previous
    # variations so illustrative examples can never override the live scene
    # configuration in the model's final instruction context.
    if scene_type == "minimax-h3_r2v":
        lines.extend([
            "FINAL ACTIVE R2V MANIFEST — HIGHEST PRIORITY:",
            f"Picture tokens allowed: {', '.join(f'<Picture {i + 1}>' for i, _ in enumerate(active_images)) or 'none'}",
            f"Video tokens allowed: {'<Video 1>' if active_video else 'none'}",
            f"Audio tokens allowed: {', '.join(f'<Audio {i + 1}>' for i, _ in enumerate(active_audios)) or 'none'}",
            "Any <Picture N>, <Video N>, or <Audio N> not listed above is forbidden, even if it appears in a reference document or an older variation.",
            "<Subject N>, <Shot N>, <d>, </d>, and speaker IDs are semantic tokens and remain allowed.",
            "Apply this final manifest before producing the JSON response.",
            "",
        ])

    # ---- Part 8: Special Command ----
    special = agentic_config.get("special_command", "")
    lines.append("=" * 60)
    lines.append("PERINTAH KHUSUS")
    lines.append("=" * 60)
    if special:
        lines.append(special)
    else:
        lines.append("(Tidak ada perintah khusus)")
    lines.append("")

    # ---- Part 9: Output Instructions ----
    lines.append("=" * 60)
    lines.append("OUTPUT YANG DIHASILKAN")
    lines.append("=" * 60)
    lines.append("Anda harus mengembalikan output dalam format JSON object root dengan key file berikut:")
    for of in output_files:
        lines.append(f'- {of}')
    lines.append("")
    if scene_type in MINIMAX_AGENTIC_SCENE_TYPES:
        lines.append(
            "Ikuti schema respons di bawah. Untuk file MiniMax, schema sengaja diringkas "
            "agar positive_prompt hanya memiliki field en."
        )
    else:
        lines.append("Struktur setiap file output HARUS sama persis dengan file input aslinya.")
    lines.append("Gunakan schema contoh berikut sebagai acuan langsung:")
    for of in output_files:
        template_path = scene_dir / of
        template_payload = _normalize_schema_template(of, _read_json_file(template_path))
        if template_payload is not None:
            if scene_type in MINIMAX_AGENTIC_SCENE_TYPES:
                template_payload = _minimax_agentic_llm_template(of, template_payload)
            lines.append(f"\n--- SCHEMA WAJIB {of} ---")
            lines.append(json.dumps(_blank_prompt_fields(template_payload), ensure_ascii=False, indent=2))
    lines.append("")

    if scene_type in MINIMAX_AGENTIC_SCENE_TYPES:
        lines.append(
            "KHUSUS file minimax_h3_*_prompt.json: LLM hanya boleh mengisi "
            "positive_prompt.en sebagai object JSON nested berbahasa Inggris. "
            "Jangan mengembalikan positive_prompt.id_new atau positive_prompt.id_old. "
            "Pipeline akan menerjemahkan setiap field teks en menjadi id_new, mempertahankan "
            "key/array/angka/timing/reference, lalu menyalin id_new ke id_old.\n"
        )
        lines.append(
            "File output MiniMax harus mengikuti schema respons ringkas yang ditampilkan di atas. "
            "Field non-prompt tetap sama dengan input. File non-MiniMax tetap mengikuti aturan bilingual normal.\n"
        )
    else:
        lines.append(
            "Setiap file JSON harus memiliki struktur yang sama dengan file aslinya, "
            "hanya saja field prompt (id_new, id_old, en) diisi dengan prompt baru yang sudah divariasikan.\n"
        )

    if scene_type in MINIMAX_AGENTIC_SCENE_TYPES:
        lines.append(
            "Aturan untuk field prompt:\n"
            "- Pada file minimax_h3_*_prompt.json, isi HANYA object JSON `positive_prompt.en` dalam bahasa Inggris\n"
            "- Jangan tulis key `id_new` atau `id_old` pada file MiniMax; pipeline yang akan membuat keduanya\n"
            "- Pada file non-MiniMax seperti z_image_prompt.json, tetap isi `id_new`, `id_old`, dan `en` sesuai schema\n"
            "- Jangan mengganti nama key, menambah key baru, atau menghapus key yang diwajibkan schema respons\n"
            "- Prompt harus mengikuti panduan, kreatif, detail, sesuai konteks, dan berbeda dari semua variasi sebelumnya\n"
            "- Jangan mengulang komposisi, angle, urutan edit, framing, visual emphasis, atau wording secara identik\n"
        )
        if scene_type in {"minimax-h3_i2v", "minimax-h3_t2v_i2v"}:
            lines.append(
                "- `shots[].shot_id` WAJIB berupa string `Shot 1`, `Shot 2`, dan seterusnya; jangan memakai angka JSON\n"
                "- Untuk I2VA, `reference` WAJIB persis: picture=`Picture 1`, source=`[Shot 1]`, time=0.0, instruction=`fully referenced`\n"
            )
        elif scene_type in {"minimax-h3_s2v", "minimax-h3_r2v"}:
            lines.append(
                "- Ref2VA WAJIB berisi tepat enam string: subject_definitions, summary, retention_analysis, "
                "detailed_description, overall_soundscape, dan non_diegetic_music\n"
                "- Gunakan hanya token reference yang tersedia pada konfigurasi scene; nomor tiap kategori harus berurutan mulai dari 1\n"
                "- Batasi aturan ini hanya untuk token <Picture N>, <Video N>, dan <Audio N>; token semantik seperti <Subject N>, <Shot N>, <d>, </d>, dan speaker IDs tetap boleh digunakan\n"
            )
    else:
        lines.append(
            "Aturan untuk field prompt:\n"
            "- Field `id_new` dan `id_old` isinya sama dan dalam bahasa Indonesia\n"
            "- Field `en` berisi versi bahasa Inggris\n"
            "- Jangan mengganti nama key, jangan menambah key baru, dan jangan menghapus key yang sudah ada\n"
            "- Jangan mengubah struktur list/dict, termasuk `groups` harus tetap bernama `groups`\n"
            "- Prompt harus mengikuti panduan yang diberikan di atas\n"
            "- Buat prompt yang kreatif, detail, dan sesuai dengan konteks project serta scene\n"
            "- Bandingkan dengan semua variasi sebelumnya yang diberikan di atas, lalu pastikan isi JSON output ini bervariasi dan tidak sama dengan variasi yang sudah ada sebelumnya\n"
            "- Jangan mengulang komposisi, angle, urutan edit, framing, visual emphasis, atau wording prompt secara identik dengan variasi sebelumnya\n"
        )

    lines.append(
        "PENTING: Kembalikan HANYA JSON valid tanpa teks tambahan di luar JSON. "
        "Jangan sertakan penjelasan atau markdown selain blok JSON."
    )
    lines.append("")

    return "\n".join(lines)


def parse_llm_json_response(response_text: str) -> dict | None:
    """Parse the JSON response from Gemini LLM.

    Tries to extract JSON from the response text, handling potential
    markdown code blocks and surrounding text.
    """
    text = response_text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding the first { ... } block
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass

    write_log(f"Gagal parse JSON dari LLM response (length={len(text)})")
    return None


def _is_prompt_path(path_parts: tuple[str, ...]) -> bool:
    """Return True if the current path points to a prompt field."""
    if not path_parts:
        return False
    current_key = str(path_parts[-1]).strip().lower()
    if "prompt" in current_key:
        return True
    # Nested structured MiniMax leaves such as
    # positive_prompt.en.overall_soundscape are prompt content too. Skip the
    # first path component because it is the filename (which may itself contain
    # the word "prompt") and must not make fields such as LoRA editable.
    for ancestor_key in path_parts[1:-1]:
        if "prompt" in str(ancestor_key).strip().lower():
            return True
    if current_key in PROMPT_VALUE_KEYS:
        for parent_key in reversed(path_parts[:-1]):
            parent_text = str(parent_key).strip().lower()
            if "prompt" in parent_text:
                return True
    return False


def _validate_output_structure_and_changes(
    input_value,
    output_value,
    path_parts: tuple[str, ...],
    errors: list[str],
):
    """Validate that output keeps the same schema and only changes prompt fields."""
    path_text = ".".join(path_parts) if path_parts else "<root>"

    if isinstance(input_value, dict):
        if not isinstance(output_value, dict):
            errors.append(f"{path_text}: output harus berupa object/dict")
            return
        input_keys = list(input_value.keys())
        output_keys = list(output_value.keys())
        if set(input_keys) != set(output_keys):
            errors.append(
                f"{path_text}: kumpulan key output harus sama persis dengan input "
                f"(input={input_keys}, output={output_keys})"
            )
            return
        for key in input_keys:
            _validate_output_structure_and_changes(
                input_value[key],
                output_value[key],
                path_parts + (str(key),),
                errors,
            )
        return

    if isinstance(input_value, list):
        if not isinstance(output_value, list):
            errors.append(f"{path_text}: output harus berupa array/list")
            return
        if path_text.endswith("positive_prompt.en.shots"):
            for index, item_out in enumerate(output_value):
                if not isinstance(item_out, dict):
                    errors.append(f"{path_text}[{index}]: setiap shot harus berupa object")
            return
        if len(input_value) != len(output_value):
            errors.append(
                f"{path_text}: panjang list harus sama (input={len(input_value)}, output={len(output_value)})"
            )
            return
        for index, (item_in, item_out) in enumerate(zip(input_value, output_value)):
            _validate_output_structure_and_changes(
                item_in,
                item_out,
                path_parts + (f"[{index}]",),
                errors,
            )
        return

    if type(output_value) is not type(input_value):
        errors.append(
            f"{path_text}: tipe data berubah dari {type(input_value).__name__} ke {type(output_value).__name__}"
        )
        return

    if not _is_prompt_path(path_parts) and input_value != output_value:
        errors.append(
            f"{path_text}: field non-prompt tidak boleh berubah "
            f"(input={input_value!r}, output={output_value!r})"
        )


def _validate_output_structure(
    input_value,
    output_value,
    path_parts: tuple[str, ...],
    errors: list[str],
):
    """Validate only schema/shape equality between input and output."""
    path_text = ".".join(path_parts) if path_parts else "<root>"

    if isinstance(input_value, dict):
        if not isinstance(output_value, dict):
            errors.append(f"{path_text}: output harus berupa object/dict")
            return
        input_keys = list(input_value.keys())
        output_keys = list(output_value.keys())
        if set(input_keys) != set(output_keys):
            errors.append(
                f"{path_text}: kumpulan key output harus sama persis dengan input "
                f"(input={input_keys}, output={output_keys})"
            )
            return
        for key in input_keys:
            _validate_output_structure(
                input_value[key],
                output_value[key],
                path_parts + (str(key),),
                errors,
            )
        return

    if isinstance(input_value, list):
        if not isinstance(output_value, list):
            errors.append(f"{path_text}: output harus berupa array/list")
            return
        if path_text.endswith("positive_prompt.en.shots"):
            for index, item_out in enumerate(output_value):
                if not isinstance(item_out, dict):
                    errors.append(f"{path_text}[{index}]: setiap shot harus berupa object")
            return
        if len(input_value) != len(output_value):
            errors.append(
                f"{path_text}: panjang list harus sama (input={len(input_value)}, output={len(output_value)})"
            )
            return
        for index, (item_in, item_out) in enumerate(zip(input_value, output_value)):
            _validate_output_structure(
                item_in,
                item_out,
                path_parts + (f"[{index}]",),
                errors,
            )
        return

    if type(output_value) is not type(input_value):
        errors.append(
            f"{path_text}: tipe data berubah dari {type(input_value).__name__} ke {type(output_value).__name__}"
        )


def _validate_non_empty_prompt_triplets(
    filename: str,
    value,
    path_parts: tuple[str, ...],
    errors: list[str],
):
    """Reject agentic prompt outputs when any required bilingual field is empty."""
    if filename not in STRICT_NON_EMPTY_AGENTIC_PROMPT_FILES:
        return

    if isinstance(value, dict):
        dict_keys = {str(key) for key in value.keys()}
        if PROMPT_VALUE_KEYS.issubset(dict_keys):
            missing_keys = [
                key for key in ("id_old", "id_new", "en")
                if not _clean_text(str(value.get(key, "")))
            ]
            if missing_keys:
                path_text = ".".join(path_parts) if path_parts else filename
                errors.append(
                    f"{path_text}: field prompt bilingual tidak boleh kosong "
                    f"(kosong={missing_keys})"
                )
            return

        for key, child in value.items():
            _validate_non_empty_prompt_triplets(
                filename,
                child,
                path_parts + (str(key),),
                errors,
            )
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_non_empty_prompt_triplets(
                filename,
                item,
                path_parts + (f"[{index}]",),
                errors,
            )


def _validate_minimax_h3_i2v_prompt_format(
    filename: str,
    value,
    errors: list[str],
):
    """Require the exact first-frame alignment and core I2VA sections."""
    if filename in {"minimax_h3_s2v_prompt.json", "minimax_h3_r2v_prompt.json"}:
        positive_prompt = value.get("positive_prompt") if isinstance(value, dict) else None
        en = positive_prompt.get("en") if isinstance(positive_prompt, dict) else None
        if isinstance(en, dict):
            errors.extend(f"{filename}: {error}" for error in validate_ref2va_prompt(en))
        return
    if filename not in {"minimax_h3_t2v_prompt.json", "minimax_h3_i2v_prompt.json"}:
        return
    if not isinstance(value, dict):
        return
    positive_prompt = value.get("positive_prompt")
    if not isinstance(positive_prompt, dict):
        return
    mode = "I2VA" if filename.endswith("i2v_prompt.json") else "T2VA"
    errors.extend(f"{filename}: {error}" for error in validate_structured_prompt(positive_prompt, expected_mode=mode))


def _canonicalize_minimax_structured_en(value: dict, mode: str) -> dict:
    """Canonicalize structural MiniMax control fields before validation."""
    mode = "I2VA" if str(mode).upper() == "I2VA" else "T2VA"
    result = copy.deepcopy(value)
    result["mode"] = mode
    shots = result.get("shots")
    if isinstance(shots, list):
        for index, shot in enumerate(shots, start=1):
            if not isinstance(shot, dict):
                continue
            shot_id = shot.get("shot_id")
            if isinstance(shot_id, (int, float)) and not isinstance(shot_id, bool):
                shot["shot_id"] = f"Shot {int(shot_id)}"
            elif isinstance(shot_id, str) and shot_id.strip().isdigit():
                shot["shot_id"] = f"Shot {int(shot_id.strip())}"
            elif not isinstance(shot_id, str) or not shot_id.strip():
                shot["shot_id"] = f"Shot {index}"
    if mode == "I2VA":
        result["reference"] = {
            "picture": "Picture 1",
            "source": "[Shot 1]",
            "time": 0.0,
            "instruction": "fully referenced",
        }
    else:
        result.pop("reference", None)
    return result


def _normalize_minimax_agentic_output(
    scene_dir: Path,
    filename: str,
    input_payload: dict,
    output_payload: dict,
) -> tuple[dict | None, list[str]]:
    """Expand an en-only MiniMax LLM response into the stored bilingual triplet."""
    errors: list[str] = []
    output_payload = copy.deepcopy(output_payload)
    if filename in {"minimax_h3_t2v_prompt.json", "minimax_h3_i2v_prompt.json"}:
        mode = "I2VA" if filename.endswith("i2v_prompt.json") else "T2VA"
        positive_prompt = output_payload.get("positive_prompt")
        en = positive_prompt.get("en") if isinstance(positive_prompt, dict) else None
        if isinstance(en, dict):
            positive_prompt["en"] = _canonicalize_minimax_structured_en(en, mode)
    llm_template = _minimax_agentic_llm_template(filename, input_payload)
    _validate_output_structure_and_changes(
        llm_template,
        output_payload,
        (filename,),
        errors,
    )
    if errors:
        return None, errors

    positive_prompt = output_payload.get("positive_prompt")
    en = positive_prompt.get("en") if isinstance(positive_prompt, dict) else None
    if not isinstance(en, dict):
        return None, [f"{filename}.positive_prompt.en harus berupa object JSON."]

    if filename in {"minimax_h3_s2v_prompt.json", "minimax_h3_r2v_prompt.json"}:
        format_errors = validate_ref2va_prompt(en)
        if format_errors:
            return None, [f"{filename}: {error}" for error in format_errors]
        if filename == "minimax_h3_r2v_prompt.json":
            references = input_payload.get("references", {}) if isinstance(input_payload, dict) else {}
            token_errors = validate_ref2va_reference_tokens(
                en,
                image_count=len(references.get("images", [])) if isinstance(references, dict) else 0,
                audio_count=len(references.get("audios", [])) if isinstance(references, dict) else 0,
                has_video=bool(references.get("video")) if isinstance(references, dict) else False,
            )
            if token_errors:
                return None, [f"{filename}: {error}" for error in token_errors]
        try:
            translator = get_prompt_translator(project_dir=Path(scene_dir).parent)
            id_new = translator.translate_ref2va_prompt_to_indonesian(en)
        except Exception as exc:
            return None, [f"{filename}: gagal menerjemahkan en per field ke id_new: {exc}"]
    else:
        mode = "I2VA" if filename.endswith("i2v_prompt.json") else "T2VA"
        probe = {"id_old": copy.deepcopy(en), "id_new": copy.deepcopy(en), "en": copy.deepcopy(en)}
        format_errors = validate_structured_prompt(probe, expected_mode=mode)
        if format_errors:
            return None, [f"{filename}: {error}" for error in format_errors]
        try:
            translator = get_prompt_translator(project_dir=Path(scene_dir).parent)
            id_new = translator.translate_structured_prompt_to_indonesian(en, mode=mode)
        except Exception as exc:
            return None, [f"{filename}: gagal menerjemahkan en per field ke id_new: {exc}"]

    result = copy.deepcopy(input_payload)
    original_entry = input_payload.get("positive_prompt")
    entry_keys = list(original_entry.keys()) if isinstance(original_entry, dict) else ["id_old", "id_new", "en"]
    expanded_entry = {}
    for key in entry_keys:
        if key == "id_old":
            expanded_entry[key] = copy.deepcopy(id_new)
        elif key == "id_new":
            expanded_entry[key] = copy.deepcopy(id_new)
        elif key == "en":
            expanded_entry[key] = copy.deepcopy(en)
        elif isinstance(original_entry, dict):
            expanded_entry[key] = copy.deepcopy(original_entry.get(key))
    for required_key, required_value in (
        ("id_old", id_new),
        ("id_new", id_new),
        ("en", en),
    ):
        if required_key not in expanded_entry:
            expanded_entry[required_key] = copy.deepcopy(required_value)
    result["positive_prompt"] = expanded_entry
    return result, []

def _normalize_output_against_input(
    input_value,
    output_value,
    path_parts: tuple[str, ...],
):
    """Keep schema identical and only take prompt-field values from LLM output."""
    if isinstance(input_value, dict):
        dict_keys = {str(key) for key in input_value.keys()}
        if PROMPT_VALUE_KEYS.issubset(dict_keys):
            output_dict = output_value if isinstance(output_value, dict) else {}
            id_old = _clean_text(output_dict.get("id_old", ""))
            id_new = _clean_text(output_dict.get("id_new", ""))
            en_value = output_dict.get("en", "")
            en = en_value if isinstance(en_value, dict) else _clean_text(en_value)
            en_fallback = "" if isinstance(en, dict) else en

            if not id_new:
                id_new = id_old or en_fallback
            if not id_old:
                id_old = id_new or en_fallback
            if id_new and id_old != id_new:
                id_old = id_new
            if not id_new and id_old:
                id_new = id_old

            normalized = {}
            for key in input_value.keys():
                if key == "id_old":
                    normalized[key] = id_old
                elif key == "id_new":
                    normalized[key] = id_new
                elif key == "en":
                    normalized[key] = en
                else:
                    normalized[key] = _normalize_output_against_input(
                        input_value[key],
                        output_dict.get(key),
                        path_parts + (str(key),),
                    )
            return normalized

        normalized = {}
        for key in input_value.keys():
            normalized[key] = _normalize_output_against_input(
                input_value[key],
                output_value[key],
                path_parts + (str(key),),
            )
        return normalized

    if isinstance(input_value, list):
        if not input_value and path_parts[-2:] == ("en", "shots"):
            return copy.deepcopy(output_value) if isinstance(output_value, list) else []
        return [
            _normalize_output_against_input(item_in, item_out, path_parts + (f"[{index}]",))
            for index, (item_in, item_out) in enumerate(zip(input_value, output_value))
        ]

    if _is_prompt_path(path_parts):
        return output_value
    return input_value


def validate_llm_variations(
    scene_dir: Path,
    scene_type: str,
    agentic_config: dict,
    variations: dict,
) -> list[str]:
    """Validate LLM JSON output against input schema and allowed prompt-only changes."""
    scene_dir = Path(scene_dir)
    errors: list[str] = []

    if not isinstance(variations, dict):
        return ["Root output LLM harus berupa object JSON."]

    expected_files = _get_scene_type_outputs(scene_type, agentic_config)
    actual_files = list(variations.keys())
    if sorted(actual_files) != sorted(expected_files):
        errors.append(
            f"File output LLM harus sama dengan yang diharapkan "
            f"(expected={expected_files}, actual={actual_files})"
        )
        return errors

    for filename in expected_files:
        output_payload = variations.get(filename)
        if not isinstance(output_payload, dict):
            errors.append(f"{filename}: output harus berupa JSON object.")
            continue

        input_path = scene_dir / filename
        input_payload = _normalize_schema_template(filename, _read_json_file(input_path))
        if input_payload is None:
            errors.append(f"{filename}: file input pembanding tidak ditemukan atau tidak valid.")
            continue

        if scene_type in MINIMAX_AGENTIC_SCENE_TYPES and filename in MINIMAX_AGENTIC_PROMPT_FILES:
            llm_template = _minimax_agentic_llm_template(filename, input_payload)
            _validate_output_structure_and_changes(
                llm_template,
                output_payload,
                (filename,),
                errors,
            )
            positive_prompt = output_payload.get("positive_prompt")
            en = positive_prompt.get("en") if isinstance(positive_prompt, dict) else None
            if isinstance(en, dict):
                if filename in {"minimax_h3_s2v_prompt.json", "minimax_h3_r2v_prompt.json"}:
                    errors.extend(f"{filename}: {error}" for error in validate_ref2va_prompt(en))
                else:
                    mode = "I2VA" if filename.endswith("i2v_prompt.json") else "T2VA"
                    probe = {"id_old": en, "id_new": en, "en": en}
                    errors.extend(f"{filename}: {error}" for error in validate_structured_prompt(probe, expected_mode=mode))
            else:
                errors.append(f"{filename}.positive_prompt.en harus berupa object JSON.")
            continue

        _validate_output_structure_and_changes(
            input_payload,
            output_payload,
            (filename,),
            errors,
        )
        format_errors: list[str] = []
        _validate_minimax_h3_i2v_prompt_format(filename, output_payload, format_errors)
        if format_errors:
            errors.extend(format_errors)

    return errors


def normalize_llm_variations(
    scene_dir: Path,
    scene_type: str,
    agentic_config: dict,
    variations: dict,
) -> tuple[dict | None, list[str]]:
    """Normalize LLM output onto input templates while preserving schema."""
    scene_dir = Path(scene_dir)
    errors: list[str] = []
    normalized: dict[str, dict] = {}

    if not isinstance(variations, dict):
        return None, ["Root output LLM harus berupa object JSON."]

    expected_files = _get_scene_type_outputs(scene_type, agentic_config)
    actual_files = list(variations.keys())
    if sorted(actual_files) != sorted(expected_files):
        errors.append(
            f"File output LLM harus sama dengan yang diharapkan "
            f"(expected={expected_files}, actual={actual_files})"
        )
        return None, errors

    for filename in expected_files:
        output_payload = variations.get(filename)
        if not isinstance(output_payload, dict):
            errors.append(f"{filename}: output harus berupa JSON object.")
            continue

        input_path = scene_dir / filename
        input_payload = _normalize_schema_template(filename, _read_json_file(input_path))
        if input_payload is None:
            errors.append(f"{filename}: file input pembanding tidak ditemukan atau tidak valid.")
            continue

        if scene_type in MINIMAX_AGENTIC_SCENE_TYPES and filename in MINIMAX_AGENTIC_PROMPT_FILES:
            minimax_output, minimax_errors = _normalize_minimax_agentic_output(
                scene_dir,
                filename,
                input_payload,
                output_payload,
            )
            if minimax_errors:
                errors.extend(minimax_errors)
                continue
            normalized[filename] = minimax_output
            continue

        structure_errors: list[str] = []
        _validate_output_structure(input_payload, output_payload, (filename,), structure_errors)
        if structure_errors:
            errors.extend(structure_errors)
            continue

        prompt_triplet_errors: list[str] = []
        _validate_non_empty_prompt_triplets(
            filename,
            output_payload,
            (filename,),
            prompt_triplet_errors,
        )
        if prompt_triplet_errors:
            errors.extend(prompt_triplet_errors)
            continue

        format_errors: list[str] = []
        _validate_minimax_h3_i2v_prompt_format(filename, output_payload, format_errors)
        if format_errors:
            errors.extend(format_errors)
            continue

        normalized[filename] = _normalize_output_against_input(
            input_payload,
            output_payload,
            (filename,),
        )

    if errors:
        return None, errors
    return normalized, []


def generate_variations(
    scene_dir: Path,
    scene_type: str,
    agentic_config: dict,
    project_settings: dict,
    all_scenes_meta: list[dict],
    model_name: str | None = None,
    current_variation_index: int | None = None,
) -> tuple[dict[str, str] | None, str, str]:
    """Generate prompt variations using Gemini LLM.

    Returns a tuple:
    - dict mapping filename -> JSON content for each output file, or None on failure
    - input prompt text sent to the LLM
    - raw output text received from the LLM (latest attempt)
    """
    scene_dir = Path(scene_dir)

    pg = project_settings.get("prompt_generation", {})
    provider = str(pg.get("provider", "gemini")).strip().lower() or "gemini"
    if provider == LEGACY_LOCAL_PROMPT_PROVIDER:
        provider = LOCAL_PROMPT_PROVIDER
    if provider not in {"gemini", LOCAL_PROMPT_PROVIDER}:
        provider = "gemini"

    # Determine model
    if not model_name:
        model_name = str(pg.get("model", "gemini-3.1-flash-lite")).strip()
    if not model_name:
        model_name = "gemini-3.1-flash-lite"
    local_host = str(pg.get("host", DEFAULT_LOCAL_PROMPT_HOST)).strip() or DEFAULT_LOCAL_PROMPT_HOST
    try:
        local_port = int(pg.get("port", DEFAULT_LOCAL_PROMPT_PORT))
    except (TypeError, ValueError):
        local_port = DEFAULT_LOCAL_PROMPT_PORT
    # Build prompt
    prompt = build_agentic_prompt(
        scene_dir=scene_dir,
        scene_type=scene_type,
        agentic_config=agentic_config,
        project_settings=project_settings,
        all_scenes_meta=all_scenes_meta,
        current_variation_index=current_variation_index,
    )
    output_schema = build_agentic_output_schema(scene_dir, scene_type, agentic_config)
    latest_response_text = ""

    write_log(f"[agentic] Memulai LLM variation untuk {scene_dir} (provider={provider}, model={model_name})")

    # Call Gemini with retry
    max_retries = 3
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            if provider == LOCAL_PROMPT_PROVIDER:
                response_text = call_llama_cpp_text(
                    prompt,
                    model_name=model_name,
                    host=local_host,
                    port=local_port,
                    response_format=output_schema,
                )
            else:
                response_text = call_gemini_text(
                    prompt,
                    model_name=model_name,
                    response_mime_type="application/json",
                    response_json_schema=output_schema,
                )
            latest_response_text = str(response_text or "")
            write_log(f"[agentic] LLM response diterima (attempt {attempt})")

            # Parse JSON
            parsed = parse_llm_json_response(response_text)
            if parsed and isinstance(parsed, dict):
                normalized, validation_errors = normalize_llm_variations(
                    scene_dir, scene_type, agentic_config, parsed
                )
                if validation_errors:
                    for error in validation_errors:
                        write_log(f"[agentic] Validasi output LLM gagal: {error}", level="warning")
                    last_error = "; ".join(validation_errors[:3])
                    write_log(f"[agentic] LLM JSON ditolak karena tidak lolos validasi (attempt {attempt})")
                    continue
                write_log(f"[agentic] LLM JSON berhasil diparse dan lolos validasi: {list(normalized.keys())}")
                return normalized, prompt, latest_response_text
            else:
                write_log(f"[agentic] LLM response bukan JSON valid (attempt {attempt})")
                last_error = "Response bukan JSON valid"

        except Exception as e:
            last_error = str(e)
            write_log(f"[agentic] LLM gagal (attempt {attempt}): {e}")

        if attempt < max_retries:
            time.sleep(2.0 * attempt)

    write_log(f"[agentic] Gagal generate variasi setelah {max_retries} attempts: {last_error}", level="error")
    return None, prompt, latest_response_text


def expected_output_files(scene_type: str, agentic_config: dict) -> list[str]:
    """Return the allowed output filenames for a scene type/config."""
    return _get_scene_type_outputs(scene_type, agentic_config)
