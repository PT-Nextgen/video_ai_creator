"""Regression tests for Agentic scene/variation state handling."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentic import agentic_pipeline as pipeline


class AgenticPipelineTests(unittest.TestCase):
    def test_agentic_config_is_not_copied_between_scene_and_variation(self):
        with tempfile.TemporaryDirectory(
            prefix="agentic_copy_test_", dir=Path(__file__).resolve().parent
        ) as temp_dir:
            root = Path(temp_dir) / "scene_1"
            variation = root / "variasi1"
            root.mkdir(parents=True)
            variation.mkdir()
            (root / "agentic.json").write_text(
                json.dumps({"number_of_variations": 0}), encoding="utf-8"
            )
            (root / "scene_meta.json").write_text("{}", encoding="utf-8")

            self.assertTrue(pipeline._copy_scene_baseline_files(root, variation))
            self.assertFalse((variation / "agentic.json").exists())

            (variation / "agentic.json").write_text(
                json.dumps({"number_of_variations": 10}), encoding="utf-8"
            )
            destination = Path(temp_dir) / "destination"
            self.assertTrue(pipeline._copy_dir_contents(variation, destination))
            self.assertFalse((destination / "agentic.json").exists())

    def test_execute_skips_scene_when_root_count_is_zero(self):
        with tempfile.TemporaryDirectory(
            prefix="agentic_execute_test_", dir=Path(__file__).resolve().parent
        ) as temp_dir:
            scene_dir = Path(temp_dir) / "scene_2"
            variation_dir = scene_dir / "variasi1"
            variation_dir.mkdir(parents=True)
            (scene_dir / "scene_meta.json").write_text(
                json.dumps({"scene_type": "i2v"}), encoding="utf-8"
            )
            (scene_dir / "agentic.json").write_text(
                json.dumps({"number_of_variations": 0}), encoding="utf-8"
            )
            (variation_dir / "agentic.json").write_text(
                json.dumps({"number_of_variations": 10}), encoding="utf-8"
            )

            with patch.object(pipeline, "_process_scene_with_main") as process_scene:
                self.assertTrue(
                    pipeline.execute_variations_for_scene(
                        scene_dir, "subject", "localhost:8188"
                    )
                )

            process_scene.assert_not_called()
            root_config = json.loads((scene_dir / "agentic.json").read_text(encoding="utf-8"))
            self.assertEqual(root_config["number_of_variations"], 0)
            self.assertFalse((variation_dir / pipeline.STATUS_DONE_FILENAME).exists())


if __name__ == "__main__":
    unittest.main()
