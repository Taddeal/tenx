"""
Unit tests for pipeline contracts, hashing, camera mapping, end-card rendering, and subtitles.
Run with: python -m unittest discover -s tests
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from jsonschema import validate
from pipeline.utils import stable_hash


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPipelineContracts(unittest.TestCase):
    def test_storyboard_validates_against_schema(self):
        with open(os.path.join(PROJECT_ROOT, "schema", "storyboard.schema.json"), encoding="utf-8") as f:
            schema = json.load(f)
        with open(os.path.join(PROJECT_ROOT, "storyboard.json"), encoding="utf-8") as f:
            sb = json.load(f)
        validate(instance=sb, schema=schema)
        self.assertGreaterEqual(len(sb["shots"]), 8)
        self.assertLessEqual(len(sb["shots"]), 12)

    def test_stable_hash_changes_on_single_edit(self):
        h1 = stable_hash("line one", "Schedar")
        h2 = stable_hash("line one", "Schedar")
        h3 = stable_hash("line two", "Schedar")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)

    def test_subtitle_wrapping_and_formatting(self):
        asm = load_module(os.path.join(PROJECT_ROOT, "pipeline", "05_assemble.py"), "assemble")
        self.assertEqual(asm.fmt_srt_time(65.25), "00:01:05,250")
        wrapped = asm.wrap_subtitle("This is a fairly long subtitle line that should split into two balanced lines.", max_chars=40)
        self.assertEqual(len(wrapped.splitlines()), 2)

    def test_camera_direction_mapping(self):
        shots_mod = load_module(os.path.join(PROJECT_ROOT, "pipeline", "03_shots.py"), "shots")
        self.assertEqual(shots_mod.camera_to_direction("slow push-in"), "push_in")
        self.assertEqual(shots_mod.camera_to_direction("dolly back"), "pull_out")
        self.assertEqual(shots_mod.camera_to_direction("pan right"), "pan_right")
        self.assertEqual(shots_mod.camera_to_direction("pan up"), "pan_up")

    def test_end_card_renders_png(self):
        asm = load_module(os.path.join(PROJECT_ROOT, "pipeline", "05_assemble.py"), "assemble")
        with open(os.path.join(PROJECT_ROOT, "storyboard.json"), encoding="utf-8") as f:
            sb = json.load(f)
        with tempfile.TemporaryDirectory() as tmp:
            out_png = os.path.join(tmp, "ec.png")
            asm.create_end_card_image(sb, out_png, 1280, 720)
            self.assertTrue(os.path.exists(out_png))
            self.assertGreater(os.path.getsize(out_png), 1000)

    def test_multilanguage_glyph_coverage(self):
        asm = load_module(os.path.join(PROJECT_ROOT, "pipeline", "05_assemble.py"), "assemble")
        bench = load_module(os.path.join(PROJECT_ROOT, "pipeline", "benchmark_languages.py"), "benchmark_languages")
        font = asm.find_ethiopic_font(36)
        for code in ("am", "om", "ti"):
            pack = bench.LANGUAGE_PACKS[code]
            combined = " ".join(pack["beats"].values()) + " " + pack["end_card_proverb"]
            self.assertEqual(bench.check_font_glyphs(font, combined), [], f"Missing glyphs for {code}")


if __name__ == "__main__":
    unittest.main()
