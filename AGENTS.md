# AGENTS.md — Developer Guide for video_ai_creator

## Overview

Python pipeline that generates video content scene-by-scene. Each scene lives in `api_production/<project>/scene_<n>/` as a collection of JSON config files. The pipeline reads scene configs, builds ComfyUI workflows from JSON templates in `api_template/`, posts them to a remote ComfyUI server, polls for output, downloads results, and composes final video+audio.

A PySide6 GUI (`scene_manager_ui.py`) provides visual editing of scenes.

## Quick Start

```powershell
# Setup
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Run CLI
python main.py --project demo_project --scene scene_1

# Run UI
.\run_ui.bat   # Windows
./run_ui.sh    # POSIX
```

## CLI

```
python main.py --server HOST:PORT --project PROJECT --scene SCENE [--scene SCENE2 ...] [--loop N]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--server` / `-s` | from `server_config.json` | ComfyUI host:port |
| `--project` / `-p` | required | Project name under `api_production/` |
| `--scene` / `-S` | all scenes | Scene name(s) to process; repeatable |
| `--loop` / `-L` | 1 | Number of iterations over selected scenes |

Scene order is numeric (`scene_1`, `scene_2`, ...). The pipeline stops on first failure.

## Scene Structure

Each scene directory contains JSON files. All prompt files are created upfront for every scene so the `scene_type` can be changed without creating new files.

### Core files (per scene)

| File | Purpose |
|------|---------|
| `scene_meta.json` | Scene title, description, type, duration, voice text, voice character |
| `project_settings.json` | Project-level: video size, prompt generation config, voice provider, caption settings |

### Prompt files (scene-type-dependent; always created)

| File | Used by |
|------|---------|
| `z_image_prompt.json` | Initial image generation |
| `wan22_i2v_prompt.json` | WAN image-to-video |
| `wan22_t2v_prompt.json` | WAN text-to-video |
| `wan22_s2v_prompt.json` | WAN speech-to-video |
| `wan22_t2v_batch_extra_prompts.json` | WAN T2V batch variants |
| `minimax_h3_t2v_prompt.json` | MiniMax H3 text-to-video |
| `minimax_h3_i2v_prompt.json` | MiniMax H3 image-to-video |
| `minimax_h3_i2v_panjang_prompt.json` | MiniMax H3 long I2V |
| `minimax_h3_s2v_prompt.json` | MiniMax H3 speech-to-video |
| `minimax_h3_r2v_prompt.json` | MiniMax H3 reference-to-video |
| `image_edit_prompt.json` | Image editing |
| `qwen_image_edit_prompt.json` | Qwen image editing |
| `z_image_extra_prompts.json` | Extra image generations |
| `web_scroll_prompt.json` | Web scroll video |
| `image_pan_prompt.json` | Image pan video |
| `image_zoom_prompt.json` | Image zoom video |
| `web_search_prompt.json` | Web search video |

### Scene types

| `scene_type` | Description |
|---|---|
| `wan22_i2v` | Generate image → WAN image-to-video |
| `wan22_t2v_i2v` | WAN text-to-video → last frame → WAN image-to-video (two-stage) |
| `wan22_t2v` | WAN text-to-video only |
| `wan22_s2v` | Generate image → WAN speech-to-video (lip-sync from audio) |
| `wan22_t2v_batch` | WAN text-to-video with extra prompt variants |
| `minimax-h3_t2v_i2v` | MiniMax H3 text-to-video → image-to-video |
| `minimax-h3_i2v` | MiniMax H3 image-to-video |
| `minimax-h3_i2v-panjang` | MiniMax H3 long image-to-video (multi-segment) |
| `minimax-h3_s2v` | MiniMax H3 speech-to-video |
| `minimax-h3_r2v` | MiniMax H3 reference-to-video |
| `i2v` | Hold images as a simple video |
| `web_scroll` | Scroll web page into video |
| `image_pan` | Pan across an image |
| `image_zoom` | Zoom into an image |

## Architecture

```
main.py (orchestrator)
├── process_scene() — dispatches by scene_type
│   ├── z_image/ — initial image generation
│   │   ├── z_image.py — Z-Image Turbo / Flux.2 workflows
│   │   ├── gemini_image.py — Gemini direct API image generation
│   │   └── flux2/ — Flux.2 workflow builder
│   ├── wan22_i2v/ — WAN image-to-video
│   ├── wan22_t2v/ — WAN text-to-video
│   ├── wan22_s2v/ — WAN speech-to-video
│   ├── minimax_h3_t2v/ — MiniMax H3 T2V
│   ├── minimax_h3_i2v/ — MiniMax H3 I2V
│   ├── minimax_h3_r2v/ — MiniMax H3 Reference-to-Video
│   ├── minimax_h3_i2v_panjang.py — MiniMax H3 long I2V segments
│   ├── gemini/ — Gemini TTS
│   ├── scripts/comfyui_api.py — ComfyUI HTTP client (upload, post, poll, download)
│   ├── scripts/generate_compose.py — Audio/video composition via ffmpeg
│   └── scripts/generate_web_scroll_video.py / generate_image_pan_video.py / generate_image_zoom_video.py
├── scene_manager_ui.py — PySide6 GUI
├── prompt_localization.py — bilingual prompt handling (id_old / id_new / en)
└── logging_config.py — unified logging to content_creation.log
```

### Workflow execution pattern (repeatable)

1. Read scene JSONs via `_read_scene_json()` → calls `prompt_localization.read_json_for_runtime()` for bilingual resolution
2. Build workflow from `api_template/` JSON template: load template → `copy.deepcopy()` → traverse-and-replace string placeholders → set numeric params (width, height, seed, strength) via hardcoded node IDs
3. Upload assets (image, audio, video) to ComfyUI via `comfyui_api.upload_file()` — retries multiple upload endpoints
4. Post workflow via `comfyui_api.post_workflow_api()` — tries `/api/workflow`, falls back to `/prompt`
5. Wait for output via `comfyui_api.wait_for_output()` — polls `/history/{prompt_id}`
6. Download via `comfyui_api.get_file_url(server, filename)` → `download_file_url()`
7. Post-process: compose audio (`scripts/generate_compose.compose_scene()`), trim video, remove audio, extract last frame

### Config loading

- `server_config.json` is the authoritative config file. `scripts/server_config.py` loads it and merges with `DEFAULT_SERVER_CONFIG` defaults.
- Each scene has its own `project_settings.json` with per-project settings (prompt generation provider, voice settings, caption config).
- Runtime service switching (llama ↔ ComfyUI) is handled by `RuntimeServiceController` in `scripts/runtime_service_controller.py`.
- `project_uses_llama(project_dir)` checks if the project needs a local LLM.

## Prompt Localization

All prompts use a bilingual format with three fields: `id_old`, `id_new`, `en`.

- `id_new` — Indonesian text displayed and edited in the UI
- `id_old` — Snapshot of `id_new` at last sync; if `id_old != id_new`, translation is triggered
- `en` — English version sent to APIs/ComfyUI

**MiniMax structured prompts**: Each field value is a nested JSON object (not a string). The UI shows `id_new` as formatted JSON. Runtime ensures `en` exists by translating only when `id_old != id_new` or `en` is empty.

**Lora trigger words**: Stored as plain text in `lora_trigger_words` field, prepended to English positive prompt at runtime (not written to file).

### Key functions

- `prompt_localization.read_json_for_runtime()` — reads scene JSON, translates if needed
- `prompt_localization.resolve_prompt_payload_for_runtime()` — resolves id_new→en translation
- `prompt_localization.prepend_lora_trigger_words()` — adds LoRA words to English prompt
- `prompt_localization.prepare_prompt_payload_for_save()` — formats data for writing JSON

## Key Gotchas

### Workflow template manipulation

Workflows use **hardcoded node IDs** (e.g., `"97"`, `"3"`, `"86"`) for parameter injection. Adding new parameters requires finding the correct node ID in the template. Node IDs are strings in the workflow dict, not integers.

### Upload endpoint fallback chain

`upload_file()` tries these endpoints in order:
- Images: `/upload/image`, `/api/upload/image` (both as `image` and `file` field)
- Audio/other: `/upload/{type}`, `/api/upload/{type}`, plus image endpoints as fallback

Always check the full attempt log if uploads fail.

### ComfyUI output detection

`wait_for_output()` accepts `output_node_ids` to restrict matching to specific nodes. Some workflows expose input media in history — use `require_output_type=True` to reject `type=input` items.

### Scene duration constraints

- `wan22_t2v_i2v`: duration must be exactly 5, 10, or 15 seconds
- `wan22_s2v`: audio duration must be < 19.2 seconds (selects template B1-B4)
- `minimax-h3`: duration 1.0–30.0 seconds, up to 1 decimal place
- `minimax-h3_r2v`: audio duration < 15.0 seconds, video max 15 seconds

### Audio composition markers

After a scene video is produced, `write_audio_composed_marker()` records the composition state. Subsequent scene edits detect the marker and skip recomposing if audio is unchanged. Invalidate with `clear_audio_composed_marker()` after downloading a new video.

### Prompt generation provider

`prompt_generation.provider` in `project_settings.json` defaults to `gemini` but can be `llama.cpp`. The provider affects prompt generation, translation, and agentic flows. `scripts/runtime_service_controller.py` handles switching between llama and ComfyUI services.

### Speech file naming

Speech files must match `speech_*` pattern (e.g., `speech_01.mp3`) for wan22_s2v scenes.

### Image extensions

Recognized: `.png`, `.jpg`, `.jpeg`, `.webp`. Video: `.mp4`, `.mov`, `.webm`, `.avi`, `.mkv`. Audio: `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, `.ogg`.

## Runtime Controller

`RuntimeServiceController` manages switching between local LLM services (llama.cpp) and ComfyUI:
- Health checks at configured intervals
- Switch timeout (300s default) for long-running operations
- API key from environment variable (`VIDEO_RUNTIME_API_KEY`)

## Testing / Running

```powershell
# Run a single scene
python main.py --project demo_project --scene scene_1

# Run all scenes in a project
python main.py --project demo_project

# Loop over scenes (e.g., 3 iterations)
python main.py --project demo_project --loop 3

# Run with specific server
python main.py --server nextgenserver:8188 --project demo_project
```

Log output goes to `content_creation.log`. Each run gets a unique `RUN_ID` appended to log lines.

## UI

`scene_manager_ui.py` launches a full PySide6 GUI for:
- Creating/editing projects and scenes
- Editing bilingual prompts (id_new / en)
- Generating images, videos, voice, captions
- Managing project settings

Launch with `run_ui.bat` (Windows) or `run_ui.sh` (POSIX).

## File Paths Reference

| Constant | Location |
|----------|----------|
| `API_PRODUCTION_ROOT` | `api_production/` — projects and scenes |
| `API_TEMPLATE` | `api_template/` — ComfyUI workflow JSON templates |
| `ROOT` | Project root |
| `LOG_FILE` | `content_creation.log` (root) |
| `KEYS_CFG` | `keys.cfg` (root) — Gemini API key storage |
| `VENV_PYTHON` | `.venv/Scripts/python.exe` |

## Adding a New Scene Type

1. Create the module directory `new_module/` with `__init__.py`, `new_module.py`
2. Define `DEFAULT_PROMPT`, `SIZE_OPTIONS`, and template name constants
3. Implement `build_workflow(prompt, ...) → dict` — load from `api_template/`, apply parameter replacements
4. Implement `send_workflow(workflow, ...) → dict` — post to ComfyUI
5. Add branch in `process_scene()` in `main.py`
6. Add scene type to `RUNTIME_PROMPTS_BY_SCENE_TYPE` in `prompt_localization.py`
7. Ensure scene creation in `scene_manager_ui.py` generates required prompt files

## MiniMax H3 Prompt Schema

### I2VA (`minimax_h3_i2v_prompt.json`)

```json
{
  "positive_prompt": {
    "id_new": {
      "mode": "I2VA",
      "shots": [
        {
          "shot_id": "Shot 1",
          "start": 0.0,
          "end": 5.0,
          "visual": "...",
          "action": "...",
          "camera": "...",
          "dialogue": "...",
          "diegetic_sound": "..."
        }
      ],
      "overall_soundscape": "...",
      "non_diegetic_music": "..."
    }
  }
}
```

### S2V/Ref2VA (`minimax_h3_r2v_prompt.json`)

Exactly six fields in `positive_prompt.en`: `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music`.

### Protected tokens

`<Picture 1>`, `<Audio 1>`, `<Subject 1>`, `<Video 1>`, etc. are preserved verbatim during translation. `<d>...</d>` dialogue blocks are protected with placeholders.
