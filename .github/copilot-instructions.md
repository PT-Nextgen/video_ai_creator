# Copilot instructions for video_ai_creator

This file gives concise, repository-specific guidance so an AI coding agent can be immediately productive.

- **Entry point**: `main.py` orchestrates scene processing per project folder under `api_production/<project>/scene_*`.
  - Typical command: `python main.py --server 127.0.0.1:8188 --project demo_project --scene scene_1`

- **Server/config**: `server_config.json` is authoritative; helpers in `scripts/server_config.py` (`get_server_address`) build defaults `comfyui:127.0.0.1:8188` and `audio:127.0.0.1:7777`.

- **ComfyUI integration**: see `scripts/comfyui_api.py`.
  - Uploads try multiple endpoints (`/upload/image`, `/api/upload/image`, etc.).
  - Workflows posted to `/api/workflow` with fallback to `/prompt`.
  - Use `get_file_url()` which returns `/view?filename=...` for downloads.
  - Output polling is done via `get_history_for_prompt()` and `wait_for_output()`.

- **Major components & responsibilities**:
  - `main.py`: high-level orchestration for scene types (`default`, `wan22_i2v`, `wan22_s2v`, `i2v`, `web_scroll`, `image_pan`).
  - `scene_manager_ui.py`: GUI for editing projects and scenes (useful to see JSON conventions and validations).
  - `prompt_localization.py`: handles bilingual prompt storage and runtime translation (`id_old` / `id_new` / `en`).
  - `scripts/workflow_builders.py`: utilities to load/validate JSON prompts used by workflows.
  - Image/flow modules:
    - `z_image/z_image.py` — build/send initial image workflows for ComfyUI.
    - `wan22_i2v/wan22_i2v.py` — build/send WAN (image->video) workflows.
    - `wan22_s2v/wan22_s2v.py` — speech-to-video pipeline, trimming and duration checks.
    - `gemini/*` — Gemini image and TTS special-case handling.

- **Data flow summary**:
  1. Read scene JSONs from `api_production/<project>/<scene>/` (`scene_meta.json`, `z_image_prompt.json`, `wan22_*_prompt.json`, etc.).
  2. Generate or pick source image(s) (Gemini direct API or ComfyUI workflow).
  3. Upload assets to ComfyUI via `comfyui_api.upload_file()`.
  4. Post workflow (`post_workflow_api`) and poll history for outputs.
  5. Download produced files (`download_file_url`) and run post-processing (mix audio, trim, burn captions).

- **Prompts & conventions**:
  - Prompts are bilingual objects with `id_old`, `id_new`, `en` — UI writes `id_new`; runtime ensures `en` exists via Gemini when needed.
  - `id_new` is displayed in UI; `en` is sent to APIs/ComfyUI.
  - Speech files must be named `speech_*` (e.g., `speech_01.mp3`) for `wan22_s2v` scenes; audio max duration enforced by `WAN22_S2V_MAX_AUDIO_DURATION`.

- **File expectations**:
  - Scene folder must contain required files per `scene_type` (see `README.md` for exact lists).
  - Image file extensions recognized: `.png`, `.jpg`, `.jpeg`, `.webp`.
  - Video ext checks follow `_matches_type_by_ext` in `scripts/comfyui_api.py`.

- **Developer workflows**:
  - Virtualenv: `.venv` is used. Example setup shown in `README.md` (Windows PowerShell / cmd and POSIX variants).
  - Run `main.py` to process scenes; use `--scene` to limit scope and `--loop` to repeat.
  - UI: `run_ui.bat` / `run_ui.sh` available to launch the scene manager.

- **Patterns to follow when editing code**:
  - Prefer using existing helpers: `scripts/comfyui_api.py`, `scripts/server_config.py`, `scripts/workflow_builders.py`, and `prompt_localization.py` rather than reimplementing network/config logic.
  - Use `write_log()` (from `logging_config`) for operational messages so `content_creation.log` and RUN_ID are consistent.
  - For image/video workflows, mirror existing retry/polling patterns (see `generate_web_scroll_video` / `generate_image_pan_video` usage in `main.py`).

- **Quick code pointers / examples**:
  - Build and post a workflow: check `z_image.build_z_image_workflow()` then `comfyui_api.post_workflow_api()`; wait via `comfyui_api.wait_for_output()`.
  - Upload a file: `comfyui_api.upload_file(server, path, file_type='audio')`.
  - Read server address: `scripts.server_config.get_server_address('comfyui')`.

If anything here is unclear or you'd like more detail on a particular module/workflow, tell me which area (e.g., `wan22_s2v` trimming, prompt localization, ComfyUI API behavior) and I will expand or adjust the instructions.
