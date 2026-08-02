import unittest
import json
import tempfile
from pathlib import Path

from handfont_compiler.cli import dispatch
from handfont_compiler.pipeline import _apply_glyph_transform, _automatic_contextual_alternates, _expanded_kerning_pairs, _normalize_x_height, _outline_height, _trace_cache_key
from handfont_compiler.template import generate_template


class CompilerProtocolTests(unittest.TestCase):
    def test_health_check(self) -> None:
        result = dispatch({"command": "health-check"})
        self.assertTrue(result["success"])
        self.assertIn("compile-font", result["capabilities"])

    def test_unknown_command(self) -> None:
        result = dispatch({"command": "not-real"})
        self.assertFalse(result["success"])

    def test_contextual_alternates_are_generated_for_imported_variants(self) -> None:
        features = _automatic_contextual_alternates([
            {"glyphName": "A", "variantIndex": 0},
            {"glyphName": "A.alt01", "variantIndex": 1, "variantGroup": "A"},
            {"glyphName": "A.alt02", "variantIndex": 2, "variantGroup": "A"},
            {"glyphName": "B", "variantIndex": 0},
        ])
        self.assertIn("feature calt", features)
        self.assertIn("A' by A.alt01", features)
        self.assertIn("A' by A.alt02", features)
        self.assertIn("feature ss01", features)
        self.assertIn("sub A by A.alt01", features)
        self.assertIn("sub A A' by A.alt01", features)
        self.assertIn("sub A.alt01 A' by A.alt02", features)

    def test_contextual_alternates_require_a_compiled_base(self) -> None:
        features = _automatic_contextual_alternates([
            {"glyphName": "A.alt01", "variantIndex": 1, "variantGroup": "A"},
        ])
        self.assertEqual(features, "")

    def test_kerning_pair_expands_across_imported_variants(self) -> None:
        style = {
            "glyphs": [
                {"glyphName": "A", "status": "imported", "sourceImagePath": "A.png"},
                {"glyphName": "A.alt01", "variantGroup": "A", "status": "imported", "sourceImagePath": "A1.png"},
                {"glyphName": "V", "status": "imported", "sourceImagePath": "V.png"},
                {"glyphName": "V.alt01", "variantGroup": "V", "status": "imported", "sourceImagePath": "V1.png"},
            ],
            "kerningPairs": [{"leftGlyph": "A", "rightGlyph": "V", "value": -80}],
        }
        pairs = _expanded_kerning_pairs(style)
        self.assertEqual(len(pairs), 4)
        self.assertEqual(pairs[("A.alt01", "V.alt01")], -80)

    def test_exact_form_kerning_overrides_all_forms(self) -> None:
        style = {
            "glyphs": [
                {"glyphName": "A", "status": "imported", "sourceImagePath": "A.png"},
                {"glyphName": "A.alt01", "variantGroup": "A", "status": "imported", "sourceImagePath": "A1.png"},
                {"glyphName": "V", "status": "imported", "sourceImagePath": "V.png"},
                {"glyphName": "V.alt01", "variantGroup": "V", "status": "imported", "sourceImagePath": "V1.png"},
            ],
            "kerningPairs": [
                {"leftGlyph": "A", "rightGlyph": "V", "value": -80, "scope": "all-forms"},
                {"leftGlyph": "A.alt01", "rightGlyph": "V.alt01", "value": -25, "scope": "exact-forms"},
            ],
        }
        pairs = _expanded_kerning_pairs(style)
        self.assertEqual(pairs[("A", "V")], -80)
        self.assertEqual(pairs[("A.alt01", "V.alt01")], -25)

    def test_x_height_normalization_preserves_width_and_scales_from_baseline(self) -> None:
        paths = [[(0, 0), (50, 0), (50, 100), (0, 100)]]
        normalized = _normalize_x_height(paths, 200)
        self.assertEqual(_outline_height(normalized), 200)
        self.assertEqual(normalized[0][1], (50, 0))
        self.assertEqual(normalized[0][2], (50, 200))

    def test_replacement_template_preserves_exact_glyph_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project.json").write_text(json.dumps({"id": "test", "familyName": "Test"}), encoding="utf-8")
            result = generate_template(str(root), "regular", "", requested_glyphs=[
                {"character": "a", "glyphName": "a.alt02", "variantIndex": 2},
                {"character": "1", "glyphName": "uni0031.alt01", "variantIndex": 1},
            ], purpose="replacement")
            cells = result["templates"][0]["cells"]
            self.assertEqual([cell["glyphName"] for cell in cells], ["a.alt02", "uni0031.alt01"])
            self.assertEqual(result["templates"][0]["purpose"], "replacement")

    def test_glyph_transform_scales_around_baseline_and_horizontal_center(self) -> None:
        paths = [[(0, 0), (100, 0), (100, 100), (0, 100)]]
        transformed = _apply_glyph_transform(paths, {"scaleX": 1.5, "scaleY": 1.5})
        self.assertEqual(transformed[0], [(-25, 0), (125, 0), (125, 150), (-25, 150)])

    def test_trace_cache_key_changes_with_trace_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "glyph.png"
            image.write_bytes(b"source")
            first = _trace_cache_key(image, {"threshold": 160}, None, 700)
            second = _trace_cache_key(image, {"threshold": 180}, None, 700)
            self.assertNotEqual(first, second)
            self.assertEqual(first, _trace_cache_key(image, {"threshold": 160}, None, 700))


if __name__ == "__main__":
    unittest.main()
