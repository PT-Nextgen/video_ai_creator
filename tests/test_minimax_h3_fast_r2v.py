"""Offline regressions for FastH3 R2V/S2V templates and editor integration."""

import copy
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import scene_manager_ui as ui
from minimax_h3_r2v import minimax_h3_r2v as r2v


class WorkflowTests(unittest.TestCase):
    def assert_valid_graph(self, workflow):
        visited = set()
        visiting = set()

        def visit(node_id):
            self.assertIn(node_id, workflow)
            self.assertNotIn(node_id, visiting, "Workflow contains a cycle")
            if node_id in visited:
                return
            visiting.add(node_id)
            for value in workflow[node_id]["inputs"].values():
                if isinstance(value, list) and len(value) == 2:
                    visit(value[0])
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in workflow:
            visit(node_id)

    def test_all_selected_references_reach_the_workflow(self):
        for fast in (False, True):
            for image_count in range(6):
                with self.subTest(fast=fast, image_count=image_count):
                    images = [f"picture_{i}.png" for i in range(image_count)]
                    audios = [f"audio_{i}.wav" for i in range(3)]
                    workflow = r2v.build_workflow(
                        {"fast_mode": fast}, image_names=images,
                        audio_names=audios, video_name="reference.mp4",
                    )
                    inputs = workflow[r2v.MAIN_NODE]["inputs"]
                    actual_images = [
                        workflow[inputs[f"ref_images.ref_image_{i}"][0]]["inputs"]["image"]
                        for i in range(image_count)
                    ]
                    self.assertEqual(actual_images, images)
                    self.assertEqual(
                        sum(key.startswith("ref_images.") for key in inputs), image_count
                    )
                    for i, audio in enumerate(audios):
                        node_id = inputs[f"ref_audios.ref_audio_{i}"][0]
                        self.assertEqual(workflow[node_id]["inputs"]["audio"], audio)
                    self.assertEqual(inputs["ref_video_audios.ref_video_audio_0"], ["152", 2])
                    self.assert_valid_graph(workflow)

    def test_fast_s2v_uses_required_model_and_only_its_two_assets(self):
        prompt = copy.deepcopy(r2v.DEFAULT_PROMPT)
        prompt.update(fast_mode=True, h3_cache={"steps": "invalid"})
        workflow = r2v.build_workflow(
            prompt, image_name="portrait.png", audio_name="speech.wav",
            duration_override=7.5, fps_override=60,
            remove_picture_2_reference=True, remove_picture_3_reference=True,
            remove_video_1_reference=True,
            remove_audio_2_reference=True, remove_audio_3_reference=True,
        )
        inputs = workflow[r2v.MAIN_NODE]["inputs"]
        refs = {key for key in inputs if key.startswith("ref_") and key != "ref_image_size"}
        self.assertEqual(refs, {"ref_images.ref_image_0", "ref_audios.ref_audio_0"})
        self.assertEqual(workflow["127"]["inputs"]["unet_name"], r2v.FAST_UNET_MODEL)
        self.assertEqual(workflow["124"]["inputs"]["steps"], 8)
        self.assertEqual(workflow["167"]["inputs"]["shift_video"], 12)
        self.assertEqual(workflow["167"]["inputs"]["shift_audio"], 3)
        self.assertEqual(workflow["165"]["inputs"]["start_percent"], 0.0)
        self.assertEqual(workflow["130"]["inputs"]["fps"], 24)
        self.assertEqual(workflow["132"]["inputs"]["value"], 7.5)
        self.assertFalse(any(n["class_type"] == "UC_MiniMaxH3Cache" for n in workflow.values()))
        self.assert_valid_graph(workflow)

    def test_normal_cache_and_special_mode_still_build(self):
        for cached in (False, True):
            for special in (False, True):
                with self.subTest(cached=cached, special=special):
                    prompt = {"h3_cache_enabled": cached, "special_mode": special}
                    workflow = r2v.build_workflow(prompt, audio_names=["speech.wav"])
                    self.assertEqual("162" in workflow, cached)
                    self.assertEqual(workflow["124"]["inputs"]["steps"], 20)
                    if special:
                        self.assertEqual(workflow["127"]["inputs"]["unet_name"], r2v.SPECIAL_UNET_MODEL)
                    self.assert_valid_graph(workflow)
        with self.assertRaisesRegex(ValueError, "Mode Cepat dan Mode Khusus"):
            r2v.build_workflow({"fast_mode": True, "special_mode": True})


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix="fast_r2v_test_", dir=Path(__file__).resolve().parent
        )
        self.addCleanup(self.temp.cleanup)
        self.window = ui.SceneEditorWindow()
        self.window.loading_scene = True
        self.window.current_scene_dir = Path(self.temp.name)
        self.window.duration_decimal_input.setText("5.0")
        self.addCleanup(self.dispose_window)

    def dispose_window(self):
        logging.getLogger().removeHandler(self.window._ui_log_handler)
        self.window.current_scene_dir = None
        self.window.deleteLater()

    def test_fast_mode_ignores_invalid_hidden_cache_but_preserves_valid_edits(self):
        for suffix, scene_type in (("r2v", ui.MINIMAX_H3_R2V_SCENE_TYPE), ("s2v", ui.MINIMAX_H3_S2V_SCENE_TYPE)):
            with self.subTest(scene_type=scene_type):
                self.window.scene_type_combo.setCurrentText(scene_type)
                fast = getattr(self.window, f"minimax_h3_{suffix}_fast_mode_input")
                fields = getattr(self.window, f"minimax_h3_{suffix}_h3_cache_inputs")
                fast.setChecked(True)
                fields["steps"].setText("")
                fields["reuse_threshold"].setText("0.12")
                gather = self.window.gather_minimax_h3_r2v_prompt if suffix == "r2v" else lambda: self.window.gather_scene_data()[4]
                prompt = gather()
                self.assertTrue(prompt["fast_mode"])
                self.assertEqual(prompt["h3_cache"]["steps"], r2v.DEFAULT_H3_CACHE["steps"])
                self.assertEqual(prompt["h3_cache"]["reuse_threshold"], 0.12)
                fast.setChecked(False)
                with self.assertRaisesRegex(ValueError, "Steps wajib diisi"):
                    gather()
                fields["steps"].setText("20")

    def test_mode_toggles_update_cache_visibility_and_saved_flags(self):
        for suffix, scene_type in (("r2v", ui.MINIMAX_H3_R2V_SCENE_TYPE), ("s2v", ui.MINIMAX_H3_S2V_SCENE_TYPE)):
            with self.subTest(scene_type=scene_type):
                self.window.scene_type_combo.setCurrentText(scene_type)
                fast = getattr(self.window, f"minimax_h3_{suffix}_fast_mode_input")
                special = getattr(self.window, f"minimax_h3_{suffix}_special_mode_input")
                cache = getattr(self.window, f"minimax_h3_{suffix}_h3_cache_group")
                special.setChecked(True)
                fast.setChecked(True)
                self.assertFalse(special.isChecked())
                self.assertTrue(cache.isHidden())
                special.setChecked(True)
                self.assertFalse(fast.isChecked())
                self.assertFalse(cache.isHidden())

    def test_live_status_validates_the_unsaved_r2v_prompt(self):
        self.window.scene_type_combo.setCurrentText(ui.MINIMAX_H3_R2V_SCENE_TYPE)
        prompt = {"fast_mode": True, "references": {"images": ["new.png"]}}
        with patch.object(self.window, "gather_scene_data", return_value=({},) * 7), \
                patch.object(self.window, "gather_minimax_h3_prompts", return_value=({}, {})), \
                patch.object(self.window, "gather_minimax_h3_r2v_prompt", return_value=prompt), \
                patch.object(ui, "validate_scene_data", return_value=[]) as validate:
            self.window.refresh_scene_status()
        self.assertIs(validate.call_args.kwargs["minimax_h3_r2v_prompt"], prompt)


if __name__ == "__main__":
    unittest.main()
