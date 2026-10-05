"""範囲変更、可行性、比較の単位と保存を検証する。"""
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from compare_shift_limits import run_comparison
from optimize_profile_shift import load_config


class ShiftLimitComparisonTests(unittest.TestCase):
    def test_independent_optimizations_and_saved_comparison(self):
        config = load_config(Path(__file__).resolve().parent.parent / "code" / "optimization_config.json")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            reports, rows = run_comparison(config, output, with_plots=False)
            for limit, report in zip((2.0, 0.9), reports):
                self.assertEqual(report["objective_equation"], "64")
                self.assertEqual(report["settings"]["shift_lower"], -limit)
                self.assertEqual(report["settings"]["shift_upper"], limit)
                self.assertGreaterEqual(min(report["constraint_margins"].values()), -config["feasibility_tolerance"])
                for shift in report["best"]["shifts"].values():
                    self.assertLessEqual(abs(shift), limit+config["feasibility_tolerance"])
            self.assertGreaterEqual(reports[0]["best"]["forward_efficiency"], reports[1]["best"]["forward_efficiency"])
            self.assertEqual(reports[0]["gearbox"], reports[1]["gearbox"])
            self.assertEqual(reports[0]["settings"]["friction_coefficient"], reports[1]["settings"]["friction_coefficient"])
            saved = json.loads((output/"limits_comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["comparison"], rows)
            forward = next(row for row in rows if row["quantity"] == "forward_percent_eq64")
            self.assertAlmostEqual(forward["difference_0.9_minus_2.0"],
                                   100*(reports[1]["best"]["forward_efficiency"]-reports[0]["best"]["forward_efficiency"]))


if __name__ == "__main__":
    unittest.main()
