import copy
import json
import os
import ast
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests
from scripts.timeout_config import LLM_CALL_TIMEOUT_SECONDS
from scripts.runtime_service_controller import ensure_llama

from gemini.gemini_image import find_gemini_key
from scripts.server_config import load_server_config
from minimax_h3_i2v.minimax_h3_i2v import is_valid_minimax_h3_i2v_prompt
from minimax_h3_prompt import (
    REF2VA_SECTION_KEYS,
    serialize_ref2va_prompt,
    validate_ref2va_prompt,
    normalize_minimax_prompt_payload,
    parse_structured_response,
    serialize_structured_prompt,
    validate_structured_prompt,
    protect_ref2va_tokens,
    restore_ref2va_tokens,
)

LOGGER = logging.getLogger(__name__)

_MINIMAX_DIALOGUE_BLOCK_PATTERN = re.compile(r"<d>.*?</d>", re.IGNORECASE | re.DOTALL)


def _protect_minimax_dialogue_blocks(text: str) -> tuple[str, dict[str, str]]:
    """Protect complete MiniMax dialogue blocks during id_new -> en translation."""
    replacements: dict[str, str] = {}

    def replace(match):
        placeholder = f"__MINIMAX_DIALOGUE_{len(replacements) + 1:03d}__"
        replacements[placeholder] = match.group(0)
        return placeholder

    return _MINIMAX_DIALOGUE_BLOCK_PATTERN.sub(replace, str(text or "")), replacements


def _restore_minimax_dialogue_blocks(text: str, replacements: dict[str, str]) -> str:
    result = str(text or "")
    missing = [placeholder for placeholder in replacements if placeholder not in result]
    if missing:
        raise ValueError(
            "Translasi MiniMax mengubah atau menghilangkan dialog dalam <d>...</d>: "
            + ", ".join(missing)
        )
    for placeholder, original in replacements.items():
        result = result.replace(placeholder, original)
    return result

DEFAULT_TRANSLATE_MODEL = "gemini-3.1-flash-lite"
DEFAULT_PROMPT_GENERATION_MODEL = "gemini-3.1-flash-lite"
LOCAL_PROMPT_PROVIDER = "llama.cpp"
LEGACY_LOCAL_PROMPT_PROVIDER = "ollama"
DEFAULT_LOCAL_PROMPT_HOST = "nextgenserver"
DEFAULT_LOCAL_PROMPT_PORT = 8080
LOCAL_LLM_TIMEOUT_SECONDS = LLM_CALL_TIMEOUT_SECONDS


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
    "minimax_h3_t2v_prompt.json": ["positive_prompt"],
    "minimax_h3_i2v_prompt.json": ["positive_prompt"],
    "minimax_h3_s2v_prompt.json": ["positive_prompt"],
    "minimax_h3_r2v_prompt.json": ["positive_prompt"],
    "wan22_s2v_prompt.json": ["positive_prompt", "negative_prompt"],
    "project_settings_cover.json": ["positive_prompt", "negative_prompt"],
}

GROUP_PROMPT_FIELDS = {
    "z_image_extra_prompts.json": ["positive_prompt", "negative_prompt"],
    "image_edit_prompt.json": ["prompt"],
    "wan22_t2v_batch_extra_prompts.json": ["positive_prompt", "negative_prompt"],
}

LORA_TRIGGER_WORDS_FIELD = "lora_trigger_words"

TRIGGER_WORD_PROMPT_FIELDS = {
    "z_image_prompt.json": ["positive_prompt"],
    "z_image_extra_prompts.json": ["positive_prompt"],
    "wan22_i2v_prompt.json": ["positive_prompt_one", "positive_prompt_two"],
    "wan22_t2v_prompt.json": ["positive_prompt"],
    "wan22_t2v_batch_extra_prompts.json": ["positive_prompt"],
}

MINIMAX_H3_I2V_RUNTIME_CONTEXT = (
    "MiniMax H3 audiovisual video prompt. Active MiniMax H3 mode: I2VA. "
    "The English prompt must begin exactly with: "
    "For the target video, at 0.00 seconds into the target video, <Picture 1> "
    "(from [Shot 1]) is fully referenced. Then write, in order, "
    "integrated_multimodal_description:, overall_soundscape:, and non_diegetic_music:."
)


def _runtime_translation_fn(
    filename: str,
    translate_fn: Callable[[str], str] | None,
    translate_provider: str | None,
    project_dir: str | Path | None,
):
    """Use the MiniMax I2VA prompt writer when an I2V prompt was edited."""
    if filename != "minimax_h3_i2v_prompt.json":
        return translate_fn

    translator = get_prompt_translator(translate_provider, project_dir=project_dir)

    def translate_minimax_i2v(text: str) -> str:
        result = translator.generate_prompt_multilang(
            text,
            context=MINIMAX_H3_I2V_RUNTIME_CONTEXT,
        )
        english_value = result.get("en", "") if isinstance(result, dict) else ""
        english = serialize_structured_prompt(english_value) if isinstance(english_value, dict) else _clean_text(english_value)
        if not is_valid_minimax_h3_i2v_prompt(english):
            raise ValueError(
                "Hasil regenerasi prompt MiniMax H3 I2VA tidak mengikuti format skill."
            )
        return english

    return translate_minimax_i2v


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
        timeout: int = LLM_CALL_TIMEOUT_SECONDS,
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

    def translate_to_english(self, text: str, context: str = "") -> str:
        text = _clean_text(text)
        if not text:
            return ""
        if not context and text in self._cache:
            return self._cache[text]
        instruction = (
            "Translate the following prompt to natural English for AI generation.\n"
            "Preserve intent, style, and detail.\n"
            "Return only the translated text without extra explanation."
        )
        payload_text = _compose_prompt_request_text(text, context) if context else text
        translated = self._call_text_model(
            self.translate_model_name,
            instruction,
            payload_text,
            timeout=LLM_CALL_TIMEOUT_SECONDS,
            phase="translate_to_english",
        )
        if not translated:
            translated = text
        if not context:
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
            timeout=LLM_CALL_TIMEOUT_SECONDS,
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
            timeout=LLM_CALL_TIMEOUT_SECONDS,
            phase="translate_to_indonesian",
        )
        return translated or text


class PromptTranslator:
    def __init__(
        self,
        prompt_generation_provider: str = "gemini",
        prompt_generation_model_name: str = DEFAULT_PROMPT_GENERATION_MODEL,
        prompt_generation_host: str = DEFAULT_LOCAL_PROMPT_HOST,
        prompt_generation_port: int = DEFAULT_LOCAL_PROMPT_PORT,
        translate_provider: str = "gemini",
        translate_model_name: str = DEFAULT_TRANSLATE_MODEL,
    ):
        self._gemini = GeminiPromptTranslator(
            translate_model_name=translate_model_name,
            prompt_generation_model_name=prompt_generation_model_name,
        )
        self.prompt_generation_provider = (
            str(prompt_generation_provider or "").strip().lower() or "gemini"
        )
        if self.prompt_generation_provider == LEGACY_LOCAL_PROMPT_PROVIDER:
            self.prompt_generation_provider = LOCAL_PROMPT_PROVIDER
        if self.prompt_generation_provider not in {"gemini", LOCAL_PROMPT_PROVIDER}:
            self.prompt_generation_provider = "gemini"
        self.prompt_generation_model_name = (
            str(prompt_generation_model_name or "").strip() or DEFAULT_PROMPT_GENERATION_MODEL
        )
        self.prompt_generation_host = str(prompt_generation_host or "").strip() or DEFAULT_LOCAL_PROMPT_HOST
        try:
            self.prompt_generation_port = int(prompt_generation_port)
        except (TypeError, ValueError):
            self.prompt_generation_port = DEFAULT_LOCAL_PROMPT_PORT
        if self.prompt_generation_port <= 0:
            self.prompt_generation_port = DEFAULT_LOCAL_PROMPT_PORT
        self.translate_provider = str(translate_provider or "gemini").strip().lower() or "gemini"
        if self.translate_provider == LEGACY_LOCAL_PROMPT_PROVIDER:
            self.translate_provider = LOCAL_PROMPT_PROVIDER
        if self.translate_provider not in {"gemini", LOCAL_PROMPT_PROVIDER}:
            self.translate_provider = "gemini"
        self.translate_model_name = str(translate_model_name or DEFAULT_TRANSLATE_MODEL).strip() or DEFAULT_TRANSLATE_MODEL
        self.last_call_metrics: dict | None = None

    def _call_local_text_model(
        self,
        model_name: str,
        prompt_text: str,
        timeout: int = LOCAL_LLM_TIMEOUT_SECONDS,
        phase: str = "generate_prompt_to_english",
    ) -> str:
        ensure_llama(reason=f"prompt localization phase={phase}")
        host = self.prompt_generation_host
        port = self.prompt_generation_port
        base_url = host if host.startswith(("http://", "https://")) else f"http://{host}"
        server_base_url = f"{base_url.rstrip('/')}:{port}"
        chat_payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt_text}],
            "stream": False,
        }
        if phase in {"generate_prompt_multilang", "translate_minimax_structured_id_new"}:
            chat_payload["response_format"] = {"type": "json_object"}
        attempts = [
            (
                f"{server_base_url}/v1/chat/completions",
                chat_payload,
                _extract_best_openai_compatible_text,
            ),
            (
                f"{server_base_url}/completion",
                {
                    "prompt": prompt_text,
                },
                _extract_best_llama_cpp_completion_text,
            ),
            (
                f"{server_base_url}/api/generate",
                {
                    "model": model_name,
                    "prompt": prompt_text,
                    "stream": False,
                },
                _extract_best_ollama_text,
            ),
        ]
        start_time = time.perf_counter()
        errors: list[str] = []
        try:
            prefer_json = phase in {"generate_prompt_multilang", "translate_minimax_structured_id_new"}
            for url, payload, extractor in attempts:
                try:
                    response = requests.post(url, json=payload, timeout=timeout)
                except requests.RequestException as exc:
                    errors.append(f"{url} -> {exc}")
                    continue
                if response.status_code >= 400:
                    errors.append(f"{url} -> HTTP {response.status_code}: {response.text[:240]}")
                    continue
                response_payload = response.json()
                generated_text = extractor(response_payload, prefer_json=prefer_json)
                if not generated_text:
                    errors.append(f"{url} -> response tanpa teks")
                    continue
                elapsed_seconds = time.perf_counter() - start_time
                tok_per_sec = _extract_tok_per_sec_from_payload(response_payload)
                self.last_call_metrics = {
                    "provider": LOCAL_PROMPT_PROVIDER,
                    "model": model_name,
                    "elapsed_seconds": elapsed_seconds,
                    "tok_per_sec": tok_per_sec,
                    "ok": True,
                    "status_code": response.status_code,
                }
                LOGGER.info(
                    format_llm_runtime_log(
                        LOCAL_PROMPT_PROVIDER,
                        phase,
                        model_name,
                        elapsed_seconds,
                        tok_per_sec,
                        extra_parts=[f"host={host}", f"port={port}", f"endpoint={url}"],
                    )
                )
                return generated_text
        except requests.RequestException as exc:
            errors.append(str(exc))
        elapsed_seconds = time.perf_counter() - start_time
        self.last_call_metrics = {
            "provider": LOCAL_PROMPT_PROVIDER,
            "model": model_name,
            "elapsed_seconds": elapsed_seconds,
            "tok_per_sec": None,
            "ok": False,
            "status_code": None,
            "error": "; ".join(errors),
        }
        LOGGER.error(
            format_llm_runtime_log(
                LOCAL_PROMPT_PROVIDER,
                phase,
                model_name,
                elapsed_seconds,
                None,
                status="gagal",
                extra_parts=[f"host={host}", f"port={port}", f"errors={' || '.join(errors[:3])}"],
            )
        )
        raise RuntimeError(f"llama.cpp error: {' || '.join(errors[:3])}")

    def translate_to_english(self, text: str, context: str = "") -> str:
        text = _clean_text(text)
        if not text:
            return ""
        if self.translate_provider == "gemini":
            result = self._gemini.translate_to_english(text, context=context)
            self.last_call_metrics = self._gemini.last_call_metrics
            return result
        instruction = (
            "Translate the following prompt to natural English for AI generation.\n"
            "Preserve intent, style, and detail.\n"
            "Return only the translated text without extra explanation.\n"
        )
        payload_text = _compose_prompt_request_text(text, context) if context else text
        result = self._call_local_text_model(
            self.translate_model_name,
            instruction + "\n" + payload_text,
            timeout=LOCAL_LLM_TIMEOUT_SECONDS,
            phase="translate_to_english",
        )
        return result or text

    def translate_to_indonesian(self, text: str, context: str = "") -> str:
        text = _clean_text(text)
        if not text:
            return ""
        if self.translate_provider == "gemini":
            result = self._gemini.translate_to_indonesian(text, context=context)
            self.last_call_metrics = self._gemini.last_call_metrics
            return result
        instruction = (
            "Translate the following prompt into natural Indonesian.\n"
            "Preserve meaning, tone, and detail.\n"
            "Return only the Indonesian prompt without explanation.\n\n"
        )
        payload_text = instruction + _compose_prompt_request_text(text, context)
        result = ""
        for attempt in range(3):
            request_text = payload_text
            if attempt:
                request_text += (
                    "\n\nIMPORTANT: The previous output was identical to the source. "
                    "Translate it into Indonesian now; do not copy the source unchanged."
                )
            result = self._call_local_text_model(
                self.translate_model_name,
                request_text,
                timeout=LOCAL_LLM_TIMEOUT_SECONDS,
                phase="translate_to_indonesian",
            )
            if result.strip().casefold() != text.strip().casefold():
                break
            LOGGER.warning(
                "[%s] translasi Indonesia mengembalikan teks sumber pada percobaan %d/%d; mencoba ulang",
                LOCAL_PROMPT_PROVIDER,
                attempt + 1,
                3,
            )
        return result or text

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
        generated = self._call_local_text_model(
            self.prompt_generation_model_name,
            payload_text,
            timeout=LOCAL_LLM_TIMEOUT_SECONDS,
            phase="generate_prompt_to_english",
        )
        return generated or text

    def generate_prompt_multilang(self, text: str, context: str = "") -> dict:
        text = _clean_text(text)
        if not text:
            return {"en": "", "id_new": ""}
        if "Active MiniMax H3 mode: Ref2VA" in str(context or ""):
            instruction = (
                "You are a senior MiniMax H3 Ref2VA video prompt engineer.\n"
                "Generate only the English workflow prompt as JSON. Do not return id_new or id_old.\n"
                "The JSON must contain exactly one top-level key en. en must be an object with exactly these six string fields: "
                + ", ".join(REF2VA_SECTION_KEYS) + ".\n"
                "Use only the active reference tokens listed in the context; do not invent, rename, or renumber any Picture, Video, or Audio label. If a reference category is marked none, do not mention it. Non-reference semantic tokens such as <Subject N>, <Shot N>, <d>, </d>, and speaker IDs remain allowed. Preserve every technical token in angle brackets character-for-character.\n"
                'Return JSON only in this shape: {"en":{"subject_definitions":"...","summary":"...","retention_analysis":"...","detailed_description":"...","overall_soundscape":"...","non_diegetic_music":"..."}}'
            )
        elif "MiniMax H3" in str(context or ""):
            active_mode = str(context or "")
            expected_mode = "I2VA" if "Active MiniMax H3 mode: I2VA" in active_mode else "T2VA"
            mode_instruction = (
                "The target is a MiniMax H3 audiovisual video prompt. Follow the MiniMax H3 base prompt guide.\n"
                "This is the creative generation phase. Return only the English workflow object; do not generate id_new or id_old in this phase.\n"
                "Every shot.shot_id must be a string exactly like Shot 1, Shot 2, and never a number.\n"
                "Every shot.start and shot.end must be JSON numbers. All other shot fields and both audio fields must be JSON strings.\n"
                "en must be a JSON object with mode, shots, overall_soundscape, and non_diegetic_music.\n"
                "Each shot must contain shot_id, start, end, visual, action, camera, dialogue, and diegetic_sound.\n"
                "Use at least two shots when the scene has multiple actions. Do not return a text prompt in en.\n"
            )
            if "Active MiniMax H3 mode: I2VA" in active_mode:
                output_shape = (
                    '{"en":{"mode":"I2VA","reference":{"picture":"Picture 1",'
                    '"source":"[Shot 1]","time":0.0,"instruction":"fully referenced"},'
                    '"shots":[{"shot_id":"Shot 1","start":0.0,"end":1.0,'
                    '"visual":"...","action":"...","camera":"...",'
                    '"dialogue":"...","diegetic_sound":"..."}],'
                    '"overall_soundscape":"...","non_diegetic_music":"..."}}'
                )
                mode_instruction += (
                    "This is I2VA. en must additionally contain reference with picture Picture 1, source [Shot 1], time 0.0, and instruction fully referenced.\n"
                )
            elif "Active MiniMax H3 mode: T2VA" in active_mode:
                output_shape = (
                    '{"en":{"mode":"T2VA","shots":[{"shot_id":"Shot 1",'
                    '"start":0.0,"end":1.0,"visual":"...","action":"...",'
                    '"camera":"...","dialogue":"...","diegetic_sound":"..."}],'
                    '"overall_soundscape":"...","non_diegetic_music":"..."}}'
                )
                mode_instruction += "This is T2VA. Do not add an image-alignment instruction.\n"
            else:
                raise ValueError("MiniMax H3 prompt context must declare the active T2VA or I2VA mode.")
            instruction = (
                "You are a senior AI video prompt engineer and bilingual writer.\n"
                + mode_instruction
                + "Return JSON only with exactly this shape: "
                + output_shape
            )
        else:
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
                timeout=LLM_CALL_TIMEOUT_SECONDS,
                phase="generate_prompt_multilang",
            )
            self.last_call_metrics = self._gemini.last_call_metrics
        else:
            response_text = self._call_local_text_model(
                self.prompt_generation_model_name,
                instruction + "\n\n" + payload_text,
                timeout=LOCAL_LLM_TIMEOUT_SECONDS,
                phase="generate_prompt_multilang",
            )
        if "Active MiniMax H3 mode: Ref2VA" in str(context or ""):
            raw_payload = _parse_json_object_response(response_text)
            raw_en = raw_payload.get("en") if isinstance(raw_payload, dict) else None
            if isinstance(raw_en, dict) and isinstance(raw_en.get("en"), dict):
                raw_en = raw_en["en"]
            errors = validate_ref2va_prompt(raw_en)
            if errors:
                raise RuntimeError("Response MiniMax H3 Ref2VA fase en tidak valid: " + "; ".join(errors[:3]))
            raw_id_new = self._translate_ref2va_fields_to_indonesian(raw_en)
            return {"id_old": copy.deepcopy(raw_id_new), "id_new": copy.deepcopy(raw_id_new), "en": raw_en}
        if "MiniMax H3" in str(context or ""):
            raw_payload = _parse_json_object_response(response_text)
            raw_en = raw_payload.get("en") if isinstance(raw_payload, dict) else None
            if not isinstance(raw_en, dict) and isinstance(raw_payload, dict):
                raw_en = raw_payload.get("positive_prompt", {}).get("en") if isinstance(raw_payload.get("positive_prompt"), dict) else None
            if not isinstance(raw_en, dict):
                raise RuntimeError("Response MiniMax H3 fase en tidak valid: field en harus berupa object JSON.")
            expected_mode = "I2VA" if "Active MiniMax H3 mode: I2VA" in str(context or "") else "T2VA"
            if expected_mode == "I2VA":
                # The reference object is a structural control field, not
                # creative text. Some LLM responses omit it despite the
                # schema instruction, so restore the exact skill contract
                # deterministically before validation and translation.
                raw_en = copy.deepcopy(raw_en)
                raw_en["mode"] = "I2VA"
                raw_en["reference"] = {
                    "picture": "Picture 1",
                    "source": "[Shot 1]",
                    "time": 0.0,
                    "instruction": "fully referenced",
                }
            en_probe = {"positive_prompt": {"id_old": raw_en, "id_new": raw_en, "en": raw_en}}
            _, errors = parse_structured_response(en_probe, expected_mode=expected_mode)
            if errors:
                raise RuntimeError("Response MiniMax H3 fase en tidak valid: " + "; ".join(errors[:3]))

            raw_id_new = self._translate_minimax_prompt_fields_to_indonesian(raw_en, expected_mode)
            return {
                "id_old": copy.deepcopy(raw_id_new),
                "id_new": copy.deepcopy(raw_id_new),
                "en": raw_en,
            }
        parsed = _parse_multilang_prompt_response(response_text)
        if not parsed["en"] and not parsed["id_new"]:
            raise RuntimeError("LLM tidak mengembalikan JSON multibahasa yang valid.")
        if not parsed["id_new"]:
            parsed["id_new"] = parsed["en"]
        if not parsed["en"]:
            parsed["en"] = parsed["id_new"]
        return parsed

    def _translate_minimax_prompt_fields_to_indonesian(self, value: dict, mode: str) -> dict:
        """Translate only natural-language leaf fields; preserve JSON structure locally."""
        translatable_keys = {
            "visual",
            "action",
            "camera",
            "dialogue",
            "diegetic_sound",
            "overall_soundscape",
            "non_diegetic_music",
        }
        fixed_keys = {"shot_id", "picture", "source", "instruction", "mode"}

        def translate_node(node, key: str = ""):
            if isinstance(node, dict):
                return {child_key: translate_node(child_value, child_key) for child_key, child_value in node.items()}
            if isinstance(node, list):
                return [translate_node(item, key) for item in node]
            if not isinstance(node, str) or key in fixed_keys or key not in translatable_keys:
                return copy.deepcopy(node)
            if not node.strip() or node.strip().upper() == "N/A":
                return node
            context = (
                f"MiniMax H3 {mode} field translation. Translate this single field value into natural Indonesian. "
                "Return only the translated text; do not add JSON, labels, or explanation. "
                "Preserve names, dialogue, visible text, and technical identifiers as appropriate. "
                "NEVER translate, rewrite, remove, reformat, or renumber any substring enclosed in angle "
                "brackets <...>. Preserve it character-for-character, including reference labels such as "
                "<Subject N>, <Subject 1>, <Picture N>, <Picture 1>, <Video N>, <Video 1>, <Audio N>, "
                "and <Audio 1>, plus control tokens <d>, </d>, <scenetrans>, and <cutoff>. "
                "Also preserve shot identifiers such as [Shot N], [Shot 1], speaker identifiers such as "
                "(S1), (S2), and (S1,S2), and mode identifiers T2VA, I2VA, FL2VA, L2VA, and Ref2VA exactly."
            )
            return self.translate_to_indonesian(node, context=context) or node

        translated = translate_node(value)
        if not isinstance(translated, dict):
            raise RuntimeError("Hasil translasi field MiniMax tidak berupa object JSON.")
        return translated

    def _translate_ref2va_fields_to_indonesian(self, value: dict) -> dict:
        errors = validate_ref2va_prompt(value)
        if errors:
            raise ValueError("Prompt Ref2VA tidak valid: " + "; ".join(errors[:3]))
        translated = {}
        for key in REF2VA_SECTION_KEYS:
            text = value[key]
            if not text.strip() or text.strip().upper() == "N/A":
                translated[key] = text
                continue
            protected, replacements = protect_ref2va_tokens(text)
            translated_text = self.translate_to_indonesian(
                protected,
                context=("MiniMax H3 Ref2VA field translation. Translate only this field to Indonesian. "
                         "Do not change, translate, or remove technical placeholders such as "
                         "__REF2VA_TOKEN_001__. Return only the translated field text.")
            ) or protected
            translated[key] = restore_ref2va_tokens(translated_text, replacements)
        return translated

    def translate_ref2va_prompt_to_indonesian(self, en: dict) -> dict:
        return self._translate_ref2va_fields_to_indonesian(en)

    def translate_ref2va_prompt_to_english(self, id_new: dict) -> dict:
        errors = validate_ref2va_prompt(id_new)
        if errors:
            raise ValueError("Prompt Ref2VA tidak valid: " + "; ".join(errors[:3]))
        result = {}
        for key in REF2VA_SECTION_KEYS:
            text = id_new[key]
            if not text.strip() or text.strip().upper() == "N/A":
                result[key] = text
                continue
            dialogue_protected, dialogue_replacements = _protect_minimax_dialogue_blocks(text)
            protected, replacements = protect_ref2va_tokens(dialogue_protected)
            translated_text = self.translate_to_english(
                protected,
                context=(
                    "MiniMax H3 English field translation. Translate the surrounding prompt text only. "
                    "Do not translate, rewrite, remove, or alter any __MINIMAX_DIALOGUE_NNN__ placeholder; "
                    "each placeholder contains an original <d>...</d> dialogue block and must remain unchanged."
                ),
            ) or protected
            translated_text = restore_ref2va_tokens(translated_text, replacements)
            result[key] = _restore_minimax_dialogue_blocks(translated_text, dialogue_replacements)
        return result

    def translate_structured_prompt_to_indonesian(self, en: dict, mode: str = "T2VA") -> dict:
        """Translate MiniMax English leaf fields while preserving its JSON structure."""
        if not isinstance(en, dict):
            raise ValueError("Prompt en MiniMax harus berupa object JSON.")
        probe = {"positive_prompt": {"id_old": en, "id_new": en, "en": en}}
        _, errors = parse_structured_response(probe, expected_mode=mode)
        if errors:
            raise ValueError("Prompt en MiniMax tidak valid: " + "; ".join(errors[:3]))
        return self._translate_minimax_prompt_fields_to_indonesian(en, mode)

    def translate_structured_prompt_to_english(self, id_new: dict, mode: str = "T2VA") -> dict:
        """Translate edited Indonesian MiniMax leaf fields back to English."""
        if not isinstance(id_new, dict):
            raise ValueError("id_new MiniMax harus berupa object JSON.")
        translatable_keys = {
            "visual", "action", "camera", "dialogue", "diegetic_sound",
            "overall_soundscape", "non_diegetic_music",
        }
        fixed_keys = {"shot_id", "picture", "source", "instruction", "mode"}

        def translate_node(node, key: str = ""):
            if isinstance(node, dict):
                return {child_key: translate_node(child_value, child_key) for child_key, child_value in node.items()}
            if isinstance(node, list):
                return [translate_node(item, key) for item in node]
            if not isinstance(node, str) or key in fixed_keys or key not in translatable_keys:
                return copy.deepcopy(node)
            if not node.strip() or node.strip().upper() == "N/A":
                return node
            context = (
                f"MiniMax H3 {mode} field translation. Translate this single field value into natural English. "
                "Return only the translated text; do not add JSON, labels, or explanation. "
                "Do not translate, rewrite, remove, or alter any __MINIMAX_DIALOGUE_NNN__ placeholder; "
                "each placeholder contains an original <d>...</d> dialogue block and must remain unchanged."
            )
            dialogue_protected, dialogue_replacements = _protect_minimax_dialogue_blocks(node)
            translated = self.translate_to_english(dialogue_protected, context=context) or dialogue_protected
            return _restore_minimax_dialogue_blocks(translated, dialogue_replacements)

        en = translate_node(id_new)
        probe = {"positive_prompt": {"id_old": en, "id_new": en, "en": en}}
        _, errors = parse_structured_response(probe, expected_mode=mode)
        if errors:
            raise RuntimeError("Hasil translasi MiniMax tidak valid: " + "; ".join(errors[:3]))
        return en


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


def _parse_json_object_response(text: str) -> dict:
    raw = _strip_markdown_code_fences(text)
    try:
        payload = json.loads(raw)
    except Exception:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            payload = json.loads(raw[start:end + 1])
        except Exception:
            return {}
    return payload if isinstance(payload, dict) else {}


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


def _extract_best_openai_compatible_text(payload: dict, prefer_json: bool = False) -> str:
    candidates: list[str] = []

    def add_candidate(value):
        if isinstance(value, str):
            cleaned = _clean_text(value)
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)
        elif isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            if parts:
                add_candidate("\n".join(parts))

    for choice in payload.get("choices") or []:
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


def _extract_best_llama_cpp_completion_text(payload: dict, prefer_json: bool = False) -> str:
    candidates: list[str] = []
    for key in ("content", "completion", "response"):
        value = payload.get(key)
        if isinstance(value, str):
            cleaned = _clean_text(value)
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)
    if prefer_json:
        for candidate in candidates:
            json_candidate = _extract_json_text_candidate(candidate)
            if json_candidate:
                return json_candidate
    return candidates[0] if candidates else ""


def _extract_tok_per_sec_from_payload(payload: dict) -> float | None:
    usage = payload.get("usage")
    if isinstance(usage, dict):
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        eval_count = completion_tokens if isinstance(completion_tokens, (int, float)) else total_tokens
        total_duration = payload.get("timings", {}).get("predicted_per_second") if isinstance(payload.get("timings"), dict) else None
        if isinstance(total_duration, (int, float)) and total_duration > 0:
            return float(total_duration)
        if isinstance(eval_count, (int, float)):
            return None

    eval_count = payload.get("eval_count")
    eval_duration = payload.get("eval_duration")
    if isinstance(eval_count, (int, float)) and isinstance(eval_duration, (int, float)) and eval_duration > 0:
        return float(eval_count) / (float(eval_duration) / 1_000_000_000.0)
    return None


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
    config = load_server_config()
    prompt_generation_config = config.get("prompt_generation") if isinstance(config, dict) else {}
    prompt_generation_config = prompt_generation_config if isinstance(prompt_generation_config, dict) else {}
    translate_config = config.get("translate") if isinstance(config, dict) else {}
    translate_config = translate_config if isinstance(translate_config, dict) else {}
    project_provider = str(prompt_generation_config.get("provider", "gemini")).strip().lower() or "gemini"
    project_model = ""
    project_host = ""
    project_port = DEFAULT_LOCAL_PROMPT_PORT
    if project_dir:
        try:
            from scripts.project_settings import load_project_settings
            project_config = load_project_settings(Path(project_dir))
            project_prompt = project_config.get("prompt_generation", {}) if isinstance(project_config, dict) else {}
            if isinstance(project_prompt, dict):
                project_provider = str(project_prompt.get("provider", "gemini")).strip().lower() or "gemini"
                project_model = str(project_prompt.get("model", "")).strip()
                project_host = str(project_prompt.get("host", "")).strip()
                try:
                    project_port = int(project_prompt.get("port", DEFAULT_LOCAL_PROMPT_PORT))
                except (TypeError, ValueError):
                    project_port = DEFAULT_LOCAL_PROMPT_PORT
        except Exception:
            pass
    if project_provider == LEGACY_LOCAL_PROMPT_PROVIDER:
        project_provider = LOCAL_PROMPT_PROVIDER
    prompt_generation_provider = project_provider if project_provider in {"gemini", LOCAL_PROMPT_PROVIDER} else "gemini"
    if prompt_generation_provider == LOCAL_PROMPT_PROVIDER:
        prompt_generation_model = str(prompt_generation_config.get("model", DEFAULT_PROMPT_GENERATION_MODEL)).strip() or DEFAULT_PROMPT_GENERATION_MODEL
    else:
        prompt_generation_model = str(translate_config.get("model", DEFAULT_TRANSLATE_MODEL)).strip() or DEFAULT_TRANSLATE_MODEL
    prompt_generation_host = str(prompt_generation_config.get("host", DEFAULT_LOCAL_PROMPT_HOST)).strip() or DEFAULT_LOCAL_PROMPT_HOST
    try:
        prompt_generation_port = int(prompt_generation_config.get("port", DEFAULT_LOCAL_PROMPT_PORT))
    except (TypeError, ValueError):
        prompt_generation_port = DEFAULT_LOCAL_PROMPT_PORT
    if project_model and prompt_generation_provider == LOCAL_PROMPT_PROVIDER:
        project_model = prompt_generation_model
    if project_host and prompt_generation_provider == LOCAL_PROMPT_PROVIDER:
        prompt_generation_host = project_host
    if project_port > 0 and prompt_generation_provider == LOCAL_PROMPT_PROVIDER:
        prompt_generation_port = project_port
    return PromptTranslator(
        prompt_generation_provider=prompt_generation_provider,
        prompt_generation_model_name=prompt_generation_model,
        prompt_generation_host=prompt_generation_host,
        prompt_generation_port=prompt_generation_port,
        translate_provider=prompt_generation_provider,
        translate_model_name=prompt_generation_model,
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


def normalize_lora_trigger_words(value) -> str:
    return str(value or "").strip()


def prepend_lora_trigger_words(prompt_text: str, trigger_words: str) -> str:
    prompt_text = str(prompt_text or "").strip()
    trigger_words = normalize_lora_trigger_words(trigger_words)
    if not trigger_words:
        return prompt_text
    if not prompt_text:
        return trigger_words
    if prompt_text.casefold().startswith(trigger_words.casefold()):
        return prompt_text
    return f"{trigger_words} {prompt_text}"


def apply_lora_trigger_words_to_prompt_payload(
    filename: str,
    data: dict,
    trigger_words: str | None = None,
) -> dict:
    result = copy.deepcopy(data or {})
    fields = TRIGGER_WORD_PROMPT_FIELDS.get(str(filename or ""), [])
    if not fields:
        return result

    effective_trigger_words = normalize_lora_trigger_words(
        result.get(LORA_TRIGGER_WORDS_FIELD, "") if trigger_words is None else trigger_words
    )
    if not effective_trigger_words:
        return result

    groups = result.get("groups")
    if isinstance(groups, list):
        updated_groups = []
        for item in groups:
            group_item = dict(item) if isinstance(item, dict) else {}
            for key in fields:
                if key in group_item:
                    group_item[key] = prepend_lora_trigger_words(group_item.get(key, ""), effective_trigger_words)
            updated_groups.append(group_item)
        result["groups"] = updated_groups
        return result

    for key in fields:
        if key in result:
            result[key] = prepend_lora_trigger_words(result.get(key, ""), effective_trigger_words)
    return result


def _get_group_item(groups_value, index: int):
    if isinstance(groups_value, list) and 0 <= index < len(groups_value) and isinstance(groups_value[index], dict):
        return groups_value[index]
    return {}


def convert_prompt_payload_for_ui(filename: str, data: dict) -> dict:
    result = copy.deepcopy(data or {})
    if filename == "minimax_h3_t2v_prompt.json":
        # MiniMax editors now display id_new as JSON. Keep the complete nested
        # payload intact; flattening id_new with str(dict) corrupts it on the
        # next save by turning the whole object into a shot.visual string.
        return normalize_minimax_prompt_payload(result, "T2VA")
    elif filename == "minimax_h3_i2v_prompt.json":
        return normalize_minimax_prompt_payload(result, "I2VA")
    elif filename in {"minimax_h3_s2v_prompt.json", "minimax_h3_r2v_prompt.json"}:
        return result
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

    if filename in {"minimax_h3_s2v_prompt.json", "minimax_h3_r2v_prompt.json"}:
        incoming = result.get("positive_prompt")
        if isinstance(incoming, dict):
            normalized = dict(incoming)
            current_id = normalized.get("id_new") or normalized.get("id_old") or {}
            normalized.setdefault("id_old", copy.deepcopy(current_id))
            normalized["id_new"] = copy.deepcopy(current_id)
            normalized.setdefault("en", {})
            result["positive_prompt"] = normalized
        return result

    if filename in {"minimax_h3_t2v_prompt.json", "minimax_h3_i2v_prompt.json"}:
        mode = "I2VA" if filename.endswith("i2v_prompt.json") else "T2VA"
        incoming = result.get("positive_prompt")
        old = existing.get("positive_prompt")
        if isinstance(incoming, str):
            preserved = normalize_minimax_prompt_payload(existing, mode).get("positive_prompt")
            if not isinstance(preserved, dict):
                result = normalize_minimax_prompt_payload(result, mode)
            else:
                incoming_entry = normalize_minimax_prompt_payload(
                    {"positive_prompt": incoming.strip()}, mode
                ).get("positive_prompt", {})
                incoming_structured = incoming_entry.get("id_new", {}) if isinstance(incoming_entry, dict) else {}
                preserved["id_old"] = copy.deepcopy(incoming_structured)
                preserved["id_new"] = copy.deepcopy(incoming_structured)
                result["positive_prompt"] = preserved
        elif isinstance(incoming, dict):
            normalized = dict(incoming)
            current_id = normalized.get("id_new") or normalized.get("id_old") or {}
            normalized.setdefault("id_old", copy.deepcopy(current_id))
            normalized["id_new"] = copy.deepcopy(current_id)
            normalized.setdefault("en", {})
            result["positive_prompt"] = normalized
        else:
            result = normalize_minimax_prompt_payload(result, mode)
        return result

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

    file_translate_fn = _runtime_translation_fn(
        filename,
        translate_fn,
        translate_provider,
        project_dir,
    )

    if filename in {"minimax_h3_s2v_prompt.json", "minimax_h3_r2v_prompt.json"}:
        structured = source.get("positive_prompt")
        if isinstance(structured, dict):
            id_new = structured.get("id_new")
            errors = validate_ref2va_prompt(id_new)
            if errors:
                raise ValueError("Prompt MiniMax H3 Ref2VA tidak valid: " + "; ".join(errors[:3]))
            if structured.get("id_old") != id_new or not isinstance(structured.get("en"), dict):
                translator = get_prompt_translator(translate_provider, project_dir=project_dir)
                translated_en = translator.translate_ref2va_prompt_to_english(id_new)
                stored_entry = copy.deepcopy(structured)
                stored_entry["id_old"] = copy.deepcopy(id_new)
                stored_entry["id_new"] = copy.deepcopy(id_new)
                stored_entry["en"] = translated_en
                stored["positive_prompt"] = stored_entry
                resolved["positive_prompt"] = serialize_ref2va_prompt(translated_en)
                return resolved, stored, True
            errors = validate_ref2va_prompt(structured["en"])
            if errors:
                raise ValueError("Prompt MiniMax H3 Ref2VA en tidak valid: " + "; ".join(errors[:3]))
            resolved["positive_prompt"] = serialize_ref2va_prompt(structured["en"])
            stored["positive_prompt"] = structured
            return resolved, stored, changed

    if filename in {"minimax_h3_t2v_prompt.json", "minimax_h3_i2v_prompt.json"}:
        mode = "I2VA" if filename.endswith("i2v_prompt.json") else "T2VA"
        structured = source.get("positive_prompt")
        if isinstance(structured, dict):
            id_new = structured.get("id_new")
            probe = {"id_old": id_new, "id_new": id_new, "en": id_new}
            errors = validate_structured_prompt(probe, expected_mode=mode)
            if errors:
                raise ValueError("Prompt MiniMax H3 structured tidak valid: " + "; ".join(errors[:3]))
            if structured.get("id_old") != id_new or not isinstance(structured.get("en"), dict):
                translator = get_prompt_translator(translate_provider, project_dir=project_dir)
                translated_en = translator.translate_structured_prompt_to_english(id_new, mode=mode)
                stored_entry = copy.deepcopy(structured)
                stored_entry["id_old"] = copy.deepcopy(id_new)
                stored_entry["id_new"] = copy.deepcopy(id_new)
                stored_entry["en"] = translated_en
                stored["positive_prompt"] = stored_entry
                resolved["positive_prompt"] = serialize_structured_prompt(translated_en)
                return resolved, stored, True
            errors = validate_structured_prompt(structured, expected_mode=mode)
            if errors:
                raise ValueError("Prompt MiniMax H3 structured en tidak valid: " + "; ".join(errors[:3]))
            resolved["positive_prompt"] = serialize_structured_prompt(structured["en"])
            stored["positive_prompt"] = structured
            return resolved, stored, changed

    for key in _top_level_fields_for(filename):
        entry_value = source.get(key)
        stored_entry, runtime_text, entry_changed = _prompt_entry_for_runtime(entry_value, file_translate_fn, log_fn=log_fn)
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

    resolved = apply_lora_trigger_words_to_prompt_payload(filename, resolved)

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
