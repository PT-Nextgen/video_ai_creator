import copy
import json
import os
import ast
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from gemini.gemini_image import find_gemini_key
from scripts.project_settings import load_project_settings
from scripts.server_config import load_server_config

LOGGER = logging.getLogger(__name__)

DEFAULT_TRANSLATE_MODEL = "gemini-3.1-flash-lite"
DEFAULT_PROMPT_GENERATION_MODEL = "gemini-3.1-flash-lite"


def format_llm_runtime_log(
    provider: str,
    phase: str,
    model: str,
    elapsed_seconds: float | None,
    tok_per_sec: float | None,
    status: str = "sukses",
    extra_parts: list[str] | None = None,
) -> str:
    provider = str(provider or "").strip().lower() or "unknown"
    phase = str(phase or "").strip() or "call"
    model = str(model or "").strip() or "n/a"
    status = str(status or "").strip() or "sukses"
    parts = [
        f"[{provider}] {phase} {status}",
        f"model={model}",
        f"elapsed={elapsed_seconds:.3f}s" if isinstance(elapsed_seconds, (int, float)) else "elapsed=n/a",
        f"tok/s={tok_per_sec:.2f}" if isinstance(tok_per_sec, (int, float)) else "tok/s=n/a",
    ]
    if extra_parts:
        parts.extend(str(part) for part in extra_parts if str(part).strip())
    return " | ".join(parts)


PROMPT_TOP_LEVEL_FIELDS = {
    "scene_meta.json": ["sound_prompt"],
    "z_image_prompt.json": ["positive_prompt", "negative_prompt"],
    "wan22_i2v_prompt.json": [
        "positive_prompt_one",
        "negative_prompt_one",
        "positive_prompt_two",
        "negative_prompt_two",
    ],
    "wan22_t2v_prompt.json": ["positive_prompt", "negative_prompt"],
    "wan22_s2v_prompt.json": ["positive_prompt", "negative_prompt"],
    "project_settings_cover.json": ["positive_prompt", "negative_prompt"],
}

GROUP_PROMPT_FIELDS = {
    "z_image_extra_prompts.json": ["positive_prompt", "negative_prompt"],
    "image_edit_prompt.json": ["prompt"],
    "wan22_t2v_batch_extra_prompts.json": ["positive_prompt", "negative_prompt"],
}


@dataclass
class I18NPrompt:
    id_old: str
    id_new: str
    en: str


class GeminiPromptTranslator:
    def __init__(
        self,
        translate_model_name: str = DEFAULT_TRANSLATE_MODEL,
        prompt_generation_model_name: str = DEFAULT_PROMPT_GENERATION_MODEL,
    ):
        self.translate_model_name = str(translate_model_name or "").strip() or DEFAULT_TRANSLATE_MODEL
        self.prompt_generation_model_name = (
            str(prompt_generation_model_name or "").strip() or DEFAULT_PROMPT_GENERATION_MODEL
        )
        self.api_key = find_gemini_key()
        self._cache: dict[str, str] = {}
        self.last_call_metrics: dict | None = None

    def _call_text_model(
        self,
        model_name: str,
        instruction: str,
        text: str,
        timeout: int = 60,
        phase: str = "call",
    ) -> str:
        if not self.api_key:
            raise RuntimeError(
                "Gemini API key tidak ditemukan. Tambahkan GEMINIKEY / GEMINI_API_KEY / GOOGLE_API_KEY di keys.cfg."
            )

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            f"?key={self.api_key}"
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
            "generationConfig": {},
        }

        start_time = time.perf_counter()
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            elapsed_seconds = time.perf_counter() - start_time
            if response.status_code >= 400:
                self.last_call_metrics = {
                    "provider": "gemini",
                    "model": model_name,
                    "elapsed_seconds": elapsed_seconds,
                    "tok_per_sec": None,
                    "prompt_token_count": None,
                    "candidates_token_count": None,
                    "total_token_count": None,
                    "status_code": response.status_code,
                    "ok": False,
                }
                LOGGER.error(
                    format_llm_runtime_log(
                        "gemini",
                        phase,
                        model_name,
                        elapsed_seconds,
                        None,
                        status="gagal",
                        extra_parts=[f"status_code={response.status_code}", f"error={response.text[:600]}"],
                    )
                )
                raise RuntimeError(f"Gemini error {response.status_code}: {response.text[:600]}")

            response_payload = response.json()
            translated_text = _clean_text(_extract_text_from_gemini_response(response_payload))
            usage = response_payload.get("usageMetadata") or response_payload.get("usage_metadata") or {}
            if not isinstance(usage, dict):
                usage = {}

            prompt_token_count = usage.get("promptTokenCount", usage.get("prompt_token_count"))
            candidates_token_count = usage.get("candidatesTokenCount", usage.get("candidates_token_count"))
            total_token_count = usage.get("totalTokenCount", usage.get("total_token_count"))

            tok_per_sec = None
            if isinstance(candidates_token_count, (int, float)) and elapsed_seconds > 0:
                tok_per_sec = float(candidates_token_count) / elapsed_seconds

            self.last_call_metrics = {
                "provider": "gemini",
                "model": model_name,
                "elapsed_seconds": elapsed_seconds,
                "tok_per_sec": tok_per_sec,
                "prompt_token_count": prompt_token_count,
                "candidates_token_count": candidates_token_count,
                "total_token_count": total_token_count,
                "status_code": response.status_code,
                "ok": True,
            }
            LOGGER.info(
                format_llm_runtime_log(
                    "gemini",
                    phase,
                    model_name,
                    elapsed_seconds,
                    tok_per_sec,
                    extra_parts=[
                        f"prompt_tokens={prompt_token_count}" if prompt_token_count is not None else None,
                        f"output_tokens={candidates_token_count}" if candidates_token_count is not None else None,
                        f"total_tokens={total_token_count}" if total_token_count is not None else None,
                    ],
                )
            )
            return translated_text
        except requests.RequestException as exc:
            elapsed_seconds = time.perf_counter() - start_time
            self.last_call_metrics = {
                "provider": "gemini",
                "model": model_name,
                "elapsed_seconds": elapsed_seconds,
                "tok_per_sec": None,
                "prompt_token_count": None,
                "candidates_token_count": None,
                "total_token_count": None,
                "status_code": None,
                "ok": False,
                "error": str(exc),
            }
            LOGGER.error(
                format_llm_runtime_log(
                    "gemini",
                    phase,
                    model_name,
                    elapsed_seconds,
                    None,
                    status="gagal",
                    extra_parts=[f"error={exc}"],
                )
            )
            raise

    def translate_to_english(self, text: str) -> str:
        text = _clean_text(text)
        if not text:
            return ""
        if text in self._cache:
            return self._cache[text]
        instruction = (
            "Translate the following prompt to natural English for AI generation.\n"
            "Preserve intent, style, and detail.\n"
            "Return only the translated text without extra explanation."
        )
        translated = self._call_text_model(
            self.translate_model_name,
            instruction,
            text,
            timeout=60,
            phase="translate_to_english",
        )
        if not translated:
            translated = text
        self._cache[text] = translated
        return translated

    def generate_prompt_to_english(self, text: str, context: str = "") -> str:
        text = _clean_text(text)
        if not text:
            return ""
        instruction = (
            "You are a senior AI prompt engineer.\n"
            "Rewrite the prompt into a polished English prompt for image generation.\n"
            "Preserve the subject, composition, style, lighting, atmosphere, and important details.\n"
            "Use the provided context to improve the prompt.\n"
            "Return only the English prompt without bullet points, quotes, or explanation."
        )
        payload_text = _compose_prompt_request_text(text, context)
        generated = self._call_text_model(
            self.prompt_generation_model_name,
            instruction,
            payload_text,
            timeout=90,
            phase="generate_prompt_to_english",
        )
        return generated or text

    def translate_to_indonesian(self, text: str, context: str = "") -> str:
        text = _clean_text(text)
        if not text:
            return ""
        instruction = (
            "Translate the following prompt into natural Indonesian.\n"
            "Preserve meaning, tone, and detail.\n"
            "Return only the Indonesian prompt without explanation."
        )
        payload_text = _compose_prompt_request_text(text, context)
        translated = self._call_text_model(
            self.translate_model_name,
            instruction,
            payload_text,
            timeout=90,
            phase="translate_to_indonesian",
        )
        return translated or text


class PromptTranslator:
    def __init__(
        self,
        prompt_generation_provider: str = "gemini",
        prompt_generation_model_name: str = DEFAULT_PROMPT_GENERATION_MODEL,
        prompt_generation_host: str = "nextgenserver",
        prompt_generation_port: int = 11434,
    ):
        self._gemini = GeminiPromptTranslator(
            translate_model_name=prompt_generation_model_name,
            prompt_generation_model_name=prompt_generation_model_name,
        )
        self.prompt_generation_provider = (
            str(prompt_generation_provider or "").strip().lower() or "gemini"
        )
        if self.prompt_generation_provider not in {"gemini", "ollama"}:
            self.prompt_generation_provider = "gemini"
        self.prompt_generation_model_name = (
            str(prompt_generation_model_name or "").strip() or DEFAULT_PROMPT_GENERATION_MODEL
        )
        self.prompt_generation_host = str(prompt_generation_host or "").strip() or "nextgenserver"
        try:
            self.prompt_generation_port = int(prompt_generation_port)
        except (TypeError, ValueError):
            self.prompt_generation_port = 11434
        if self.prompt_generation_port <= 0:
            self.prompt_generation_port = 11434
        self.translate_model_name = self.prompt_generation_model_name
        self.last_call_metrics: dict | None = None

    def _call_ollama_text_model(
        self,
        model_name: str,
        prompt_text: str,
        timeout: int = 90,
        phase: str = "generate_prompt_to_english",
    ) -> str:
        host = self.prompt_generation_host
        port = self.prompt_generation_port
        base_url = host if host.startswith(("http://", "https://")) else f"http://{host}"
        url = f"{base_url.rstrip('/')}:{port}/api/generate"
        payload = {
            "model": model_name,
            "prompt": prompt_text,
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
        start_time = time.perf_counter()
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            elapsed_seconds = time.perf_counter() - start_time
            if response.status_code >= 400:
                self.last_call_metrics = {
                    "provider": "ollama",
                    "model": model_name,
                    "elapsed_seconds": elapsed_seconds,
                    "tok_per_sec": None,
                    "ok": False,
                    "status_code": response.status_code,
                }
                LOGGER.error(
                    format_llm_runtime_log(
                        "ollama",
                        phase,
                        model_name,
                        elapsed_seconds,
                        None,
                        status="gagal",
                        extra_parts=[f"status_code={response.status_code}", f"error={response.text[:600]}"],
                    )
                )
                raise RuntimeError(f"Ollama error {response.status_code}: {response.text[:600]}")
            response_payload = response.json()
            generated_text = _extract_best_ollama_text(response_payload, prefer_json=(phase == "generate_prompt_multilang"))
            eval_count = response_payload.get("eval_count")
            eval_duration = response_payload.get("eval_duration")
            tok_per_sec = None
            if isinstance(eval_count, (int, float)) and isinstance(eval_duration, (int, float)) and eval_duration > 0:
                tok_per_sec = float(eval_count) / (float(eval_duration) / 1_000_000_000.0)
            self.last_call_metrics = {
                "provider": "ollama",
                "model": model_name,
                "elapsed_seconds": elapsed_seconds,
                "tok_per_sec": tok_per_sec,
                "ok": True,
                "status_code": response.status_code,
            }
            LOGGER.info(
                format_llm_runtime_log(
                    "ollama",
                    phase,
                    model_name,
                    elapsed_seconds,
                    tok_per_sec,
                    extra_parts=[f"host={host}", f"port={port}"],
                )
            )
            return generated_text
        except requests.RequestException as exc:
            elapsed_seconds = time.perf_counter() - start_time
            self.last_call_metrics = {
                "provider": "ollama",
                "model": model_name,
                "elapsed_seconds": elapsed_seconds,
                "tok_per_sec": None,
                "ok": False,
                "status_code": None,
                "error": str(exc),
            }
            LOGGER.error(
                format_llm_runtime_log(
                    "ollama",
                    phase,
                    model_name,
                    elapsed_seconds,
                    None,
                    status="gagal",
                    extra_parts=[f"error={exc}", f"host={host}", f"port={port}"],
                )
            )
            raise

    def translate_to_english(self, text: str) -> str:
        text = _clean_text(text)
        if not text:
            return ""
        if self.prompt_generation_provider == "gemini":
            result = self._gemini.translate_to_english(text)
            self.last_call_metrics = self._gemini.last_call_metrics
            return result
        instruction = (
            "Translate the following prompt to natural English for AI generation.\n"
            "Preserve intent, style, and detail.\n"
            "Return only the translated text without extra explanation.\n\n"
        )
        result = self._call_ollama_text_model(
            self.prompt_generation_model_name,
            instruction + text,
            timeout=90,
            phase="translate_to_english",
        )
        return result or text

    def translate_to_indonesian(self, text: str, context: str = "") -> str:
        text = _clean_text(text)
        if not text:
            return ""
        if self.prompt_generation_provider == "gemini":
            result = self._gemini.translate_to_indonesian(text, context=context)
            self.last_call_metrics = self._gemini.last_call_metrics
            return result
        instruction = (
            "Translate the following prompt into natural Indonesian.\n"
            "Preserve meaning, tone, and detail.\n"
            "Return only the Indonesian prompt without explanation.\n\n"
        )
        payload_text = instruction + _compose_prompt_request_text(text, context)
        result = self._call_ollama_text_model(
            self.prompt_generation_model_name,
            payload_text,
            timeout=90,
            phase="translate_to_indonesian",
        )
        return result

    def generate_prompt_to_english(self, text: str, context: str = "") -> str:
        text = _clean_text(text)
        if not text:
            return ""
        if self.prompt_generation_provider == "gemini":
            result = self._gemini.generate_prompt_to_english(text, context=context)
            self.last_call_metrics = self._gemini.last_call_metrics
            return result
        instruction = (
            "You are a senior AI prompt engineer.\n"
            "Rewrite the prompt into a polished English prompt for image generation.\n"
            "Preserve the subject, composition, style, lighting, atmosphere, and important details.\n"
            "Use the provided context to improve the prompt.\n"
            "Return only the English prompt without bullet points, quotes, or explanation.\n\n"
        )
        payload_text = instruction + _compose_prompt_request_text(text, context)
        generated = self._call_ollama_text_model(
            self.prompt_generation_model_name,
            payload_text,
            timeout=120,
            phase="generate_prompt_to_english",
        )
        return generated or text

    def generate_prompt_multilang(self, text: str, context: str = "") -> dict:
        text = _clean_text(text)
        if not text:
            return {"en": "", "id_new": ""}
        instruction = (
            "You are a senior AI prompt engineer and bilingual writer.\n"
            "Rewrite the prompt into a polished English prompt for image generation.\n"
            "Then provide a natural Indonesian version with the same meaning and detail.\n"
            "Preserve subject, composition, style, lighting, atmosphere, and important details.\n"
            "Use the provided context to improve the prompt.\n"
            "Return JSON only with exactly these keys: "
            '{"en":"...", "id_new":"..."}'
        )
        payload_text = _compose_prompt_request_text(text, context)
        if self.prompt_generation_provider == "gemini":
            response_text = self._gemini._call_text_model(
                self.prompt_generation_model_name,
                instruction,
                payload_text,
                timeout=120,
                phase="generate_prompt_multilang",
            )
            self.last_call_metrics = self._gemini.last_call_metrics
        else:
            response_text = self._call_ollama_text_model(
                self.prompt_generation_model_name,
                instruction + "\n\n" + payload_text,
                timeout=120,
                phase="generate_prompt_multilang",
            )
        parsed = _parse_multilang_prompt_response(response_text)
        if not parsed["en"] and not parsed["id_new"]:
            raise RuntimeError("LLM tidak mengembalikan JSON multibahasa yang valid.")
        if not parsed["id_new"]:
            parsed["id_new"] = parsed["en"]
        if not parsed["en"]:
            parsed["en"] = parsed["id_new"]
        return parsed


def _clean_text(value) -> str:
    return str(value or "").strip()


def _strip_markdown_code_fences(text: str) -> str:
    text = str(text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _parse_multilang_prompt_response(text: str) -> dict:
    raw = _strip_markdown_code_fences(text)
    payload = None
    try:
        payload = json.loads(raw)
    except Exception:
        # Try to extract JSON from markdown code blocks
        import re
        json_match = re.search(r'\{[^{}]*"en"[^{}]*\}[^{}]*\{[^{}]*"id_new"[^{}]*\}', raw, re.IGNORECASE)
        if json_match:
            try:
                payload = json.loads(json_match.group(0))
            except Exception:
                pass
        # Fallback: try to find JSON object
        if payload is None:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                try:
                    payload = json.loads(raw[start:end + 1])
                except Exception:
                    payload = None
    if not isinstance(payload, dict):
        return {"en": "", "id_new": ""}
    en = _clean_text(payload.get("en", ""))
    id_new = _clean_text(payload.get("id_new", ""))
    # Additional fallback: try alternative keys
    if not en:
        en = _clean_text(payload.get("english", "") or payload.get("en_prompt", ""))
    if not id_new:
        id_new = _clean_text(payload.get("indonesian", "") or payload.get("id_new_prompt", "") or payload.get("id", ""))
    return {
        "en": en,
        "id_new": id_new,
    }


def _extract_json_text_candidate(text: str) -> str:
    raw = _strip_markdown_code_fences(text)
    if not raw:
        return ""
    try:
        json.loads(raw)
        return raw
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidate = raw[start:end + 1].strip()
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    return ""


def _extract_best_ollama_text(payload: dict, prefer_json: bool = False) -> str:
    candidates: list[str] = []

    def add_candidate(value):
        if not isinstance(value, str):
            return
        cleaned = _clean_text(value)
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    add_candidate(payload.get("response", ""))
    message = payload.get("message")
    if isinstance(message, dict):
        add_candidate(message.get("content", ""))
    add_candidate(payload.get("thinking", ""))

    response_text = _clean_text(payload.get("response", ""))
    thinking_text = _clean_text(payload.get("thinking", ""))
    if response_text and thinking_text:
        add_candidate(f"{response_text}\n{thinking_text}")
        add_candidate(f"{thinking_text}\n{response_text}")

    if prefer_json:
        for candidate in candidates:
            json_candidate = _extract_json_text_candidate(candidate)
            if json_candidate:
                return json_candidate
    return candidates[0] if candidates else ""


def _compose_prompt_request_text(prompt_text: str, context: str = "") -> str:
    prompt_text = _clean_text(prompt_text)
    context = _clean_text(context)
    if context:
        return f"Context:\n{context}\n\nPrompt:\n{prompt_text}"
    return prompt_text


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


def _guess_project_dir_from_path(path: str | None) -> Path | None:
    if not path:
        return None
    try:
        current = Path(path).resolve()
    except Exception:
        return None
    if current.is_file():
        current = current.parent
    parts = list(current.parts)
    for idx, name in enumerate(parts):
        if str(name).lower() == "api_production" and idx + 1 < len(parts):
            candidate = Path(*parts[: idx + 2])
            if candidate.exists() and candidate.is_dir():
                return candidate
    return None


def get_prompt_translator(provider: str | None = None, project_dir: str | Path | None = None):
    _ = provider
    prompt_generation_provider = "gemini"
    prompt_generation_model = DEFAULT_PROMPT_GENERATION_MODEL
    prompt_generation_host = "nextgenserver"
    prompt_generation_port = 11434

    project_cfg = {}
    if project_dir:
        try:
            project_cfg = load_project_settings(Path(project_dir))
        except Exception:
            project_cfg = {}

    if isinstance(project_cfg, dict) and project_cfg:
        prompt_generation_config = (
            project_cfg.get("prompt_generation")
            if isinstance(project_cfg.get("prompt_generation"), dict)
            else {}
        )
        if isinstance(prompt_generation_config, dict):
            prompt_generation_provider = (
                str(prompt_generation_config.get("provider", prompt_generation_provider)).strip().lower()
                or prompt_generation_provider
            )
            prompt_generation_model = (
                str(prompt_generation_config.get("model", prompt_generation_model)).strip()
                or prompt_generation_model
            )
            prompt_generation_host = (
                str(prompt_generation_config.get("host", prompt_generation_host)).strip()
                or prompt_generation_host
            )
            try:
                prompt_generation_port = int(prompt_generation_config.get("port", prompt_generation_port))
            except (TypeError, ValueError):
                prompt_generation_port = 11434
    else:
        config = load_server_config()
        prompt_generation_config = config.get("prompt_generation") if isinstance(config, dict) else {}
        if isinstance(prompt_generation_config, dict):
            prompt_generation_provider = (
                str(prompt_generation_config.get("provider", prompt_generation_provider)).strip().lower()
                or prompt_generation_provider
            )
            prompt_generation_model = (
                str(prompt_generation_config.get("model", prompt_generation_model)).strip()
                or prompt_generation_model
            )
            prompt_generation_host = (
                str(prompt_generation_config.get("host", prompt_generation_host)).strip()
                or prompt_generation_host
            )
            try:
                prompt_generation_port = int(prompt_generation_config.get("port", prompt_generation_port))
            except (TypeError, ValueError):
                prompt_generation_port = 11434
    return PromptTranslator(
        prompt_generation_provider=prompt_generation_provider,
        prompt_generation_model_name=prompt_generation_model,
        prompt_generation_host=prompt_generation_host,
        prompt_generation_port=prompt_generation_port,
    )


def update_generated_prompt_entry(
    filename: str,
    data: dict,
    key: str,
    id_new: str,
    en: str,
    group_index: int | None = None,
) -> dict:
    result = copy.deepcopy(data or {})
    key = str(key or "").strip()
    id_new = _clean_text(id_new)
    en = _clean_text(en)
    synced_id = id_new or en

    if group_index is None:
        result[key] = {"id_old": synced_id, "id_new": synced_id, "en": en}
        return result

    groups = result.get("groups")
    if not isinstance(groups, list):
        groups = []
    while len(groups) <= group_index:
        groups.append({})
    item = dict(groups[group_index]) if isinstance(groups[group_index], dict) else {}
    item[key] = {"id_old": synced_id, "id_new": synced_id, "en": en}
    groups[group_index] = item
    result["groups"] = groups
    return result


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
    translate_fn: Callable[[str], str] | None,
    log_fn: Callable[[str], None] | None = None,
) -> tuple[dict, str, bool]:
    existing = _normalize_prompt_entry(existing_value)
    changed = not isinstance(existing_value, dict)
    should_translate = bool(existing.id_new) and (existing.id_old != existing.id_new or not existing.en)
    if should_translate:
        try:
            if translate_fn is None:
                translate_fn = get_prompt_translator().translate_to_english
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
    translate_fn: Callable[[str], str] | None = None,
    translate_provider: str | None = None,
    project_dir: str | Path | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> tuple[dict, dict, bool]:
    source = copy.deepcopy(data or {})
    resolved = copy.deepcopy(source)
    stored = copy.deepcopy(source)
    changed = False

    if translate_fn is None:
        translate_fn = get_prompt_translator(translate_provider, project_dir=project_dir).translate_to_english

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
    translate_provider: str | None = None,
    project_dir: str | Path | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict:
    if not os.path.exists(path):
        if required:
            raise FileNotFoundError(path)
        return {}

    if project_dir is None:
        project_dir = _guess_project_dir_from_path(path)

    source = _read_json_file(path)
    filename = os.path.basename(path)
    resolved, stored, changed = resolve_prompt_payload_for_runtime(
        filename,
        source,
        translate_provider=translate_provider,
        project_dir=project_dir,
        log_fn=log_fn,
    )
    if changed and persist_updates:
        _write_json_file(path, stored)
        if log_fn:
            log_fn(f"Prompt localization diperbarui: {path}")
    return resolved
