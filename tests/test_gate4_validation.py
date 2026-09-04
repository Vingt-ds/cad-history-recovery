import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cadquery as cq


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = PROJECT_ROOT / "external"
if str(EXTERNAL) not in sys.path:
    sys.path.insert(0, str(EXTERNAL))

try:
    import gate4_validation
except ImportError:
    gate4_validation = None


class VolumeIouTests(unittest.TestCase):
    def _export(self, shape, path):
        cq.exporters.export(shape, str(path))
        return path

    def test_module_and_public_api_exist(self):
        self.assertIsNotNone(gate4_validation)
        self.assertTrue(hasattr(gate4_validation, "calculate_volume_iou"))

    def test_iou_is_symmetric_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._export(cq.Workplane("XY").box(10, 10, 10), root / "a.step")
            second = self._export(
                cq.Workplane("XY").transformed(offset=(5, 0, 0)).box(10, 10, 10),
                root / "b.step",
            )
            forward = gate4_validation.calculate_volume_iou(first, second)
            reverse = gate4_validation.calculate_volume_iou(second, first)

        self.assertAlmostEqual(forward["volume_iou"], reverse["volume_iou"], places=12)
        self.assertGreaterEqual(forward["volume_iou"], 0.0)
        self.assertLessEqual(forward["volume_iou"], 1.0)
        self.assertAlmostEqual(forward["volume_iou"], 1.0 / 3.0, places=9)
        self.assertAlmostEqual(
            forward["symmetric_difference_ratio"],
            1.0 - forward["volume_iou"],
            places=12,
        )

    def test_identical_and_disjoint_solids_return_one_and_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._export(cq.Workplane("XY").box(10, 10, 10), root / "a.step")
            same = self._export(cq.Workplane("XY").box(10, 10, 10), root / "same.step")
            far = self._export(
                cq.Workplane("XY").transformed(offset=(30, 0, 0)).box(10, 10, 10),
                root / "far.step",
            )
            identical = gate4_validation.calculate_volume_iou(first, same)
            disjoint = gate4_validation.calculate_volume_iou(first, far)

        self.assertAlmostEqual(identical["volume_iou"], 1.0, places=12)
        self.assertEqual(disjoint["volume_iou"], 0.0)

    def test_boolean_failure_is_null_and_surface_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._export(cq.Workplane("XY").box(10, 10, 10), root / "a.step")
            second = self._export(cq.Workplane("XY").box(10, 10, 10), root / "b.step")
            with mock.patch.object(
                gate4_validation,
                "_boolean_volumes",
                side_effect=RuntimeError("kernel boolean failed"),
            ):
                result = gate4_validation.calculate_volume_iou(first, second)

        self.assertIsNone(result["volume_iou"])
        self.assertIsNone(result["symmetric_difference_ratio"])
        self.assertTrue(result["boolean_validation_failed"])
        self.assertEqual(result["validation_mode"], "surface_only")
        self.assertNotIn("geometry_pass", result)


if __name__ == "__main__":
    unittest.main()
