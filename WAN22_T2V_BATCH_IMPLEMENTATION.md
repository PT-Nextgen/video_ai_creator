# WAN22_T2V_BATCH Scene Type - Implementation Summary

## Overview
Scene type `wan22_t2v_batch` has been implemented to support text-to-video generation with multiple prompts per scene. Each prompt is processed sequentially, and all resulting videos are concatenated into one final video.

## Files Modified

### 1. `scripts/project_cli.py`
- Added `WAN22_T2V_BATCH_SCENE_TYPE = "wan22_t2v_batch"` constant
- Added `DEFAULT_WAN22_T2V_EXTRA_PROMPTS` template with 3 empty groups
- Added `"wan22_t2v_batch"` to `SCENE_TYPE_CHOICES`
- Updated `duration_options_for_scene_type()` to return `[5, 10]` for `wan22_t2v_batch`
- Updated `build_scene_templates()` to return extra prompts as 10th value
- Updated `create_scene_files()` to accept and write `wan22_t2v_extra_prompts`
- Updated `sync_scene_prompt_files()` to accept and write `wan22_t2v_extra_prompts.json`
- Updated `sync_project_size_to_scene_files()` to include `wan22_t2v_extra_prompts.json`
- Updated `create_scene_in_project()` to validate duration and pass extra prompts

### 2. `scene_manager_ui.py`
- Added `WAN22_T2V_BATCH_SCENE_TYPE` constant
- Added `DEFAULT_WAN22_T2V_EXTRA_PROMPTS` template
- Updated `duration_options_for_scene_type()` for `wan22_t2v_batch`
- Updated `build_scene_templates()` to return extra prompts
- Updated `create_scene_files()` to handle extra prompts
- Updated `sync_scene_prompt_files()` to write extra prompts JSON
- Updated `sync_project_size_to_scene_files()` to include extra prompts in project size calculation
- Updated `create_scene_in_project()` to validate duration
- Added `self.t2v_extra_tab = None` to `__init__`
- Added `wan22_t2v_batch` to both type dropdowns (`type_combo` and `scene_type_combo`)
- Updated `update_scene_type_tabs()` visibility:
  - `wan_t2v_tab`: visible for both `wan22_t2v_i2v` and `wan22_t2v_batch`
  - `wan_tab` (WAN22_I2V): NOT visible for `wan22_t2v_batch`
  - `z_tab`, `image_edit_tab`: NOT visible for `wan22_t2v_batch`
  - `t2v_extra_tab`: visible ONLY for `wan22_t2v_batch`
- Updated `agentic_create_initial_image_policy()` to return `(False, False)` for `wan22_t2v_batch`
- Created `t2v_extra_tab` widget with 3 groups of positive/negative prompts and "Buat Prompt" buttons
- Added widget instances: `t2v_extra_positive_inputs`, `t2v_extra_negative_inputs`, `t2v_extra_generate_prompt_buttons`
- Added methods:
  - `gather_wan22_t2v_extra_prompts()`
  - `load_wan22_t2v_extra_prompts()`
  - `load_wan22_t2v_extra_prompts_into_ui()`
  - `generate_wan_t2v_extra_prompt_from_ui(slot_index)`
- Updated prompt generation methods:
  - `_build_prompt_generation_context()` to handle `wan_t2v_batch_extra`
  - `_set_prompt_widget_text()` to handle `wan_t2v_batch_extra`
  - `_prompt_file_and_key()` to return `wan22_t2v_extra_prompts.json`
  - `_prompt_group_index()` to include `wan_t2v_batch_extra`
  - `prompt_label` dict in `_start_prompt_generation()` to include `wan_t2v_batch_extra`
- Added validation for `wan22_t2v_batch` in `validate_scene_data()`:
  - Duration must be 5 or 10 seconds
  - Main positive prompt must be filled
- Updated `save_current_scene()` to gather and save extra prompts

### 3. `wan22_t2v/wan22_t2v.py`
- Added `_set_length_inputs(workflow: dict, length: int)` function to set node "74" length field
- Updated `build_workflow()` to accept optional `length: int | None = None` parameter
- When `length` is provided, calls `_set_length_inputs()` to dynamically set the video length

### 4. `main.py`
- Added `wan22_t2v_batch` processing branch with full logic:
  1. Validates duration (5 or 10 seconds)
  2. Reads main prompt from `wan22_t2v_prompt.json`
  3. Reads extra prompts from `wan22_t2v_extra_prompts.json`
  4. Counts filled positive prompts
  5. Calculates `frames_per_prompt = ceil(duration * 16 / total_prompts)`
  6. Loops through all prompts (main + filled extras):
     - Builds workflow with appropriate prompt
     - Sets `length = frames_per_prompt`
     - Sends to ComfyUI, waits, downloads video
  7. Concatenates all videos using `_concat_video_segments()`
  8. Finalizes: mix audio → caption → VRAM cleanup

## Key Design Decisions

1. **Frame Calculation**: `frames_per_prompt = ceil(duration * 16 / total_filled_prompts)`
   - Total duration is divided across all prompts
   - FPS = 16 (I2V_FPS)

2. **Duration Options**: Only 5 and 10 seconds (simpler than wan22_t2v_i2v which has 5, 10, 15)

3. **Extra Prompts Storage**: New file `wan22_t2v_extra_prompts.json` (not reusing z_image_extra_prompts)

4. **Lora Configuration**: Shared from the main WAN22_T2V tab, not per-prompt

5. **Video Concatenation**: All videos from prompts are concatenated per scene, then compose handles all scenes

6. **Buat Prompt Button**: Only on positive prompts (not negative)

7. **Agentic Support**: Variations run all prompts per variation (create_initial_image=False for both main and extra)

## Testing Checklist

- [ ] Create a new project with `wan22_t2v_batch` scene type
- [ ] Verify UI tabs show correctly (WAN22_T2V + Prompt Tambahan)
- [ ] Enter main prompt and at least one extra prompt
- [ ] Click "Buat Prompt" buttons to test LLM generation
- [ ] Save scene and verify `wan22_t2v_extra_prompts.json` is created
- [ ] Run the scene and verify:
  - Each prompt is processed sequentially
  - Frame count is correct per video
  - All videos are concatenated
  - Final video has correct total duration
- [ ] Test with 1, 2, and 3 extra prompts
- [ ] Test with both 5 and 10 second durations
- [ ] Test agentic mode with variations

## Usage Example

1. Select scene type: `wan22_t2v_batch`
2. Set duration: 5 or 10 seconds
3. Fill in the WAN22_T2V tab:
   - Positive prompt (main scene description)
   - Optional: Lora settings, size
4. Fill in the Prompt Tambahan tab:
   - Group 1: Additional scene details (positive), optional negative
   - Group 2: More details (optional)
   - Group 3: More details (optional)
   - Click "Buat Prompt" to generate prompts via LLM
5. Save scene
6. Run project - videos will be generated and concatenated

## Example Output

For a 10-second scene with 2 extra prompts (3 total):
- Frames per prompt: `ceil(10 * 16 / 3) = ceil(160 / 3) = 54 frames`
- Each video: ~3.375 seconds at 16 FPS
- Final video: ~10.125 seconds (3 concatenated videos)
