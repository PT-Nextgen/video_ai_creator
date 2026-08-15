"""Structured prompt schema and serializer for MiniMax H3 T2VA/I2VA."""

from __future__ import annotations

import json
import copy
import ast
from numbers import Real


I2VA_FIRST_FRAME_PREFIX = (
    "For the target video, at 0.00 seconds into the target video, "
    "<Picture 1> (from [Shot 1]) is fully referenced."
)
REQUIRED_SHOT_KEYS = (
    "shot_id",
    "start",
    "end",
    "visual",
    "action",
    "camera",
    "dialogue",
    "diegetic_sound",
)
REQUIRED_AUDIO_KEYS = ("overall_soundscape", "non_diegetic_music")


def empty_structured_prompt(mode: str) -> dict:
    mode = "I2VA" if str(mode).upper() == "I2VA" else "T2VA"
    value = {
        "mode": mode,
        "shots": [],
        "overall_soundscape": "",
        "non_diegetic_music": "",
    }
    if mode == "I2VA":
        value["reference"] = {
            "picture": "Picture 1",
            "source": "[Shot 1]",
            "time": 0.0,
            "instruction": "fully referenced",
        }
    return value


def structured_prompt_entry(mode: str, id_new=None, en: dict | None = None) -> dict:
    mode = "I2VA" if str(mode).upper() == "I2VA" else "T2VA"
    if not isinstance(id_new, dict):
        id_new = empty_structured_prompt(mode)
    return {
        "id_old": copy.deepcopy(id_new),
        "id_new": copy.deepcopy(id_new),
        "en": en if isinstance(en, dict) else empty_structured_prompt(mode),
    }


def _recover_nested_legacy_prompt(value):
    """Unwrap the accidental one-shot string representation from old saves."""
    current = value
    for _ in range(4):
        if not isinstance(current, dict):
            break
        shots = current.get("shots")
        if not isinstance(shots, list) or len(shots) != 1 or not isinstance(shots[0], dict):
            break
        visual = shots[0].get("visual")
        if not isinstance(visual, str):
            break
        candidate = visual.strip()
        if not (candidate.startswith("{") and candidate.endswith("}")):
            break
        try:
            parsed = json.loads(candidate)
        except Exception:
            try:
                parsed = ast.literal_eval(candidate)
            except Exception:
                break
        if not isinstance(parsed, dict) or not isinstance(parsed.get("shots"), list):
            break
        current = parsed
    return current


def validate_structured_prompt(value, expected_mode: str | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["positive_prompt harus berupa object."]
    for key in ("id_old", "id_new", "en"):
        if key not in value:
            errors.append(f"positive_prompt.{key} wajib ada.")
    en = value.get("en")
    if not isinstance(en, dict):
        errors.append("positive_prompt.en harus berupa object JSON nested.")
        return errors
    mode = str(en.get("mode", "")).upper()
    if mode not in {"T2VA", "I2VA"}:
        errors.append("positive_prompt.en.mode harus T2VA atau I2VA.")
    if expected_mode and mode != str(expected_mode).upper():
        errors.append(f"mode harus {expected_mode}.")

    for key in ("id_old", "id_new"):
        localized = value.get(key)
        if not isinstance(localized, dict):
            errors.append(f"positive_prompt.{key} harus berupa object JSON nested.")
            continue
        localized_mode = str(localized.get("mode", "")).upper()
        if localized_mode != mode:
            errors.append(f"positive_prompt.{key}.mode harus {mode}.")
        if localized.get("shots") is not None and not isinstance(localized.get("shots"), list):
            errors.append(f"positive_prompt.{key}.shots harus berupa array.")
    if isinstance(value.get("id_old"), dict) and isinstance(value.get("id_new"), dict):
        if value["id_old"] != value["id_new"]:
            errors.append("positive_prompt.id_old harus sama persis dengan positive_prompt.id_new.")

    shots = en.get("shots")
    if not isinstance(shots, list) or not shots:
        errors.append("positive_prompt.en.shots wajib berupa array berisi minimal satu shot.")
    else:
        previous_end = 0.0
        for index, shot in enumerate(shots):
            prefix = f"positive_prompt.en.shots[{index}]"
            if not isinstance(shot, dict):
                errors.append(f"{prefix} harus berupa object.")
                continue
            for key in REQUIRED_SHOT_KEYS:
                if key not in shot:
                    errors.append(f"{prefix}.{key} wajib ada.")
            start, end = shot.get("start"), shot.get("end")
            if not isinstance(start, Real) or isinstance(start, bool) or not isinstance(end, Real) or isinstance(end, bool):
                errors.append(f"{prefix}.start dan end harus berupa angka.")
            elif float(start) < 0 or float(end) <= float(start) or float(start) < previous_end:
                errors.append(f"{prefix} memiliki timeline tidak valid atau tidak berurutan.")
            else:
                previous_end = float(end)
            for key in REQUIRED_SHOT_KEYS:
                if key not in {"start", "end"} and not isinstance(shot.get(key), str):
                    errors.append(f"{prefix}.{key} harus berupa string.")

    for key in REQUIRED_AUDIO_KEYS:
        if not isinstance(en.get(key), str) or not str(en.get(key)).strip():
            errors.append(f"positive_prompt.en.{key} wajib berupa string tidak kosong.")
    if mode == "I2VA":
        reference = en.get("reference")
        if not isinstance(reference, dict):
            errors.append("I2VA wajib memiliki positive_prompt.en.reference.")
        else:
            if reference.get("picture") != "Picture 1":
                errors.append("I2VA reference.picture harus Picture 1.")
            if reference.get("source") != "[Shot 1]":
                errors.append("I2VA reference.source harus [Shot 1].")
            if reference.get("time") != 0.0:
                errors.append("I2VA reference.time harus 0.0.")
            if reference.get("instruction") != "fully referenced":
                errors.append("I2VA reference.instruction tidak valid.")
    elif "reference" in en:
        errors.append("T2VA tidak boleh memiliki field reference.")
    return errors


def serialize_structured_prompt(value) -> str:
    """Convert the nested JSON prompt to the exact MiniMax workflow text."""
    if not isinstance(value, dict):
        return str(value or "").strip()
    mode = str(value.get("mode", "T2VA")).upper()
    lines: list[str] = []
    if mode == "I2VA":
        lines.extend([I2VA_FIRST_FRAME_PREFIX, ""])
    lines.append("integrated_multimodal_description:")
    for shot in value.get("shots", []) if isinstance(value.get("shots"), list) else []:
        if not isinstance(shot, dict):
            continue
        lines.append(
            f"[{shot.get('shot_id', 'Shot 1')}] "
            f"From {float(shot.get('start', 0)):.2f} to {float(shot.get('end', 0)):.2f} seconds, "
            f"visual: {shot.get('visual', '')}; action: {shot.get('action', '')}; "
            f"camera: {shot.get('camera', '')}; dialogue: {shot.get('dialogue', '')}; "
            f"diegetic sound: {shot.get('diegetic_sound', '')}."
        )
    lines.extend([
        "",
        f"overall_soundscape: {value.get('overall_soundscape', '')}",
        "",
        f"non_diegetic_music: {value.get('non_diegetic_music', '')}",
    ])
    return "\n".join(lines).strip()


def prompt_entry_to_display(value) -> str:
    if isinstance(value, dict) and isinstance(value.get("en"), dict):
        return serialize_structured_prompt(value["en"])
    if isinstance(value, dict):
        return str(value.get("id_new", "") or value.get("en", "")).strip()
    return str(value or "").strip()


def parse_structured_response(payload, expected_mode: str) -> tuple[dict | None, list[str]]:
    """Accept the strict nested response shape used by the MiniMax button."""
    if not isinstance(payload, dict) or set(payload.keys()) != {"positive_prompt"}:
        return None, ["Response MiniMax harus object dengan satu key positive_prompt."]
    entry = copy.deepcopy(payload.get("positive_prompt"))
    # Some models emit shot_id as 1, 2, ... although the workflow schema uses
    # the textual identifiers Shot 1, Shot 2, ... . Normalize that harmless
    # representation before strict validation.
    if isinstance(entry, dict):
        for localized_key in ("en", "id_new", "id_old"):
            localized = entry.get(localized_key)
            if isinstance(localized, dict) and isinstance(localized.get("shots"), list):
                for index, shot in enumerate(localized["shots"], start=1):
                    if isinstance(shot, dict):
                        shot_id = shot.get("shot_id")
                        if isinstance(shot_id, (int, float)) and not isinstance(shot_id, bool):
                            shot["shot_id"] = f"Shot {int(shot_id)}"
                        elif not isinstance(shot_id, str) or not shot_id.strip():
                            shot["shot_id"] = f"Shot {index}"
    errors = validate_structured_prompt(entry, expected_mode=expected_mode)
    if errors:
        return None, errors
    normalized = dict(entry)
    normalized["id_old"] = copy.deepcopy(normalized.get("id_new", {}))
    return normalized, []


def normalize_minimax_prompt_payload(data: dict, mode: str) -> dict:
    """Return a MiniMax payload with the nested prompt schema."""
    result = dict(data or {})
    entry = result.get("positive_prompt")
    if isinstance(entry, dict) and isinstance(entry.get("en"), dict):
        # MiniMax uses one Indonesian source identity.  Repair legacy or
        # manually edited payloads so the two ids can never diverge.
        normalized_entry = dict(entry)
        synced_id = normalized_entry.get("id_new")
        if not isinstance(synced_id, dict):
            synced_id = normalized_entry.get("id_old")
        if not isinstance(synced_id, dict):
            legacy_text = str(synced_id or "").strip()
            synced_id = empty_structured_prompt(mode)
            if legacy_text:
                synced_id["shots"] = [{
                    "shot_id": "Shot 1", "start": 0.0, "end": 1.0,
                    "visual": legacy_text, "action": "", "camera": "",
                    "dialogue": "", "diegetic_sound": "",
                }]
                synced_id["overall_soundscape"] = "N/A"
                synced_id["non_diegetic_music"] = "N/A"
        synced_id = _recover_nested_legacy_prompt(synced_id)
        normalized_entry["id_old"] = copy.deepcopy(synced_id)
        normalized_entry["id_new"] = copy.deepcopy(synced_id)
        normalized_entry["en"] = _recover_nested_legacy_prompt(normalized_entry["en"])
        result["positive_prompt"] = normalized_entry
        return result
    if isinstance(entry, dict):
        id_new = entry.get("id_new") or entry.get("id_old") or ""
        old_en = entry.get("en", "")
    else:
        id_new = str(entry or "")
        old_en = ""
    nested = empty_structured_prompt(mode)
    if isinstance(id_new, str) and id_new.strip():
        nested["shots"] = [{
            "shot_id": "Shot 1", "start": 0.0, "end": 1.0,
            "visual": id_new.strip(), "action": "", "camera": "",
            "dialogue": "", "diegetic_sound": "",
        }]
        nested["overall_soundscape"] = "N/A"
        nested["non_diegetic_music"] = "N/A"
        id_new = nested
    if isinstance(old_en, str) and old_en.strip():
        nested["shots"] = [{
            "shot_id": "Shot 1", "start": 0.0, "end": 1.0,
            "visual": old_en.strip(), "action": "", "camera": "",
            "dialogue": "", "diegetic_sound": "",
        }]
        nested["overall_soundscape"] = "N/A"
        nested["non_diegetic_music"] = "N/A"
    result["positive_prompt"] = structured_prompt_entry(mode, id_new=id_new, en=nested)
    return result
