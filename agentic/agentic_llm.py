"""Gemini text-only API and prompt builder for agentic variations."""
import json
import re
import time
from pathlib import Path

import requests

from logging_config import write_log
from gemini.gemini_image import find_gemini_key


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


def call_ollama_text(
    prompt: str,
    model_name: str,
    host: str = "nextgenserver",
    port: int = 11434,
    timeout: int = 120,
    response_format: str | dict | None = None,
) -> str:
    """Call Ollama generate API with text-only response."""
    host = str(host or "").strip() or "nextgenserver"
    base_url = host if host.startswith(("http://", "https://")) else f"http://{host}"
    url = f"{base_url.rstrip('/')}:{int(port)}/api/generate"
    payload = {
        "model": str(model_name or "").strip(),
        "prompt": prompt,
        "stream": False,
        "think": True,
        "options": {
            "temperature": 1,
            "top_k": 20,
            "top_p": 0.95,
            "presence_penalty": 1.5,
            "repeat_penalty": 1,
            "draft_num_predict": 4,
        },
    }
    if response_format:
        payload["format"] = response_format

    start_time = time.perf_counter()
    resp = requests.post(url, json=payload, timeout=timeout)
    elapsed = time.perf_counter() - start_time

    if resp.status_code >= 400:
        write_log(
            f"[ollama] text generation gagal | model={model_name} | host={host} | port={port} | "
            f"elapsed={elapsed:.3f}s | status={resp.status_code} | error={resp.text[:600]}",
            level="error",
        )
        raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text[:600]}")

    result = resp.json()
    text = _extract_best_ollama_text(result, prefer_json=bool(response_format))
    if not text:
        write_log(
            f"[ollama] text generation gagal — response tanpa teks | model={model_name} | "
            f"host={host} | port={port} | elapsed={elapsed:.3f}s",
            level="error",
        )
        raise RuntimeError(f"Ollama response has no text data: {json.dumps(result)[:500]}")

    write_log(
        f"[ollama] text generation sukses | model={model_name} | host={host} | port={port} | elapsed={elapsed:.3f}s"
    )
    return _clean_text(text)


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
    return normalized


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
    root_payloads: dict[str, dict] = {}
    for filename in output_files:
        payload = _normalize_schema_template(filename, _read_json_file(scene_dir / filename))
        if isinstance(payload, dict):
            root_payloads[filename] = payload
    if root_payloads:
        collected.append(("root_scene", root_payloads))

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
            return {key: "" for key in value.keys()}
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
        properties[filename] = _json_schema_from_template(template_payload)
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
    "wan22_t2v_batch": ["wan22_t2v_prompt.json", "wan22_t2v_batch_extra_prompts.json"],
    "wan22_s2v": ["wan22_s2v_prompt.json", "z_image_prompt.json"],
    "i2v": ["z_image_prompt.json"],
    "image_pan": ["z_image_prompt.json"],
    "image_zoom": ["z_image_prompt.json"],
}

PROMPT_VALUE_KEYS = {"id_old", "id_new", "en"}


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
            "Berikut adalah isi JSON dari root scene dan variasi yang sudah dibuat sebelumnya. "
            "Gunakan semuanya sebagai pembanding agar variasi baru TIDAK SAMA dengan root scene maupun variasi yang sudah ada."
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
    lines.append("Struktur setiap file output HARUS sama persis dengan file input aslinya.")
    lines.append("Gunakan schema contoh berikut sebagai acuan langsung:")
    for of in output_files:
        template_path = scene_dir / of
        template_payload = _normalize_schema_template(of, _read_json_file(template_path))
        if template_payload is not None:
            lines.append(f"\n--- SCHEMA WAJIB {of} ---")
            lines.append(json.dumps(_blank_prompt_fields(template_payload), ensure_ascii=False, indent=2))
    lines.append("")

    lines.append(
        "Setiap file JSON harus memiliki struktur yang sama dengan file aslinya, "
        "hanya saja field prompt (id_new, id_old, en) diisi dengan prompt baru yang sudah divariasikan.\n"
    )

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
        if input_keys != output_keys:
            errors.append(
                f"{path_text}: key output harus sama persis dengan input "
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
        if input_keys != output_keys:
            errors.append(
                f"{path_text}: key output harus sama persis dengan input "
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
            en = _clean_text(output_dict.get("en", ""))

            if not id_new:
                id_new = id_old or en
            if not id_old:
                id_old = id_new or en
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

        _validate_output_structure_and_changes(
            input_payload,
            output_payload,
            (filename,),
            errors,
        )

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

        structure_errors: list[str] = []
        _validate_output_structure(input_payload, output_payload, (filename,), structure_errors)
        if structure_errors:
            errors.extend(structure_errors)
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
    if provider not in {"gemini", "ollama"}:
        provider = "gemini"

    # Determine model
    if not model_name:
        model_name = str(pg.get("model", "gemini-3.1-flash-lite")).strip()
    if not model_name:
        model_name = "gemini-3.1-flash-lite"
    ollama_host = str(pg.get("host", "nextgenserver")).strip() or "nextgenserver"
    try:
        ollama_port = int(pg.get("port", 11434))
    except (TypeError, ValueError):
        ollama_port = 11434
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
            if provider == "ollama":
                response_text = call_ollama_text(
                    prompt,
                    model_name=model_name,
                    host=ollama_host,
                    port=ollama_port,
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
