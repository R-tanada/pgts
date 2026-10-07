"""拡張ラグランジュの符号と、実問題の制約・改善・履歴を検証。"""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

import optimize_profile_shift as shared
import optimize_profile_shift_quasi_newton as quasi
from profile_shift_model import Gearbox, Model, reference_center_distances


class QuasiNewtonTests(unittest.TestCase):
    def test_augmented_objective_penalizes_violation(self):
        np, _, _ = shared.load_scientific_libraries()
        # 初期乗数0では、可行点は元の目的値、違反-0.2にはrho*g²/2。
        zero = np.zeros(1)
        self.assertEqual(quasi.augmented_objective(-0.9, np.array([0.2]), zero, 10, np), -0.9)
        self.assertAlmostEqual(quasi.augmented_objective(-0.9, np.array([-0.2]), zero, 10, np), -0.7)

    def test_multistart_result_is_feasible_and_improves_paper_geometry(self):
        config, settings = quasi.load_settings(Path(__file__).resolve().parent.parent / "code" / "quasi_newton_config.json")
        gearbox = Gearbox()
        best, trials, _ = quasi.optimize(gearbox, config, settings)
        self.assertIsNotNone(best)
        final, margins, index = best
        center = reference_center_distances(gearbox)["a"]
        reference = Model(gearbox, config["friction_coefficient"])
        reference.calculate([2, 1.21, center])
        self.assertGreaterEqual(final.forward_efficiency, reference.forward_efficiency)
        self.assertGreaterEqual(min(margins.values()), -config["feasibility_tolerance"])
        trial = trials[index]
        self.assertTrue(trial["solver_success"])
        self.assertTrue(trial["feasible"])
        self.assertEqual(trial["history"][-1]["variables"], trial["final_variables"])
        self.assertLessEqual(trial["outer_stages"][-1]["multiplier_residual"], config["feasibility_tolerance"])
        successful = [t["forward_efficiency"] for t in trials if t["solver_success"] and t["feasible"]]
        self.assertGreaterEqual(len(successful), 2)
        self.assertLess(max(successful) - min(successful), 1e-6)


if __name__ == "__main__":
    unittest.main()
