"""確認用コードの数式・本番との分離を検証する。"""
import math
import unittest
from tests.experiments.common import load_settings, ROOT
from tests.experiments.check_efficiency import evaluate_design
from tests.experiments.single_quasi_newton import augmented_objective, optimize
from optimization import optimize_candidates as opt


class ExperimentTests(unittest.TestCase):
    def test_augmented_lagrangian_sign(self):
        np, _, _ = opt.load_scientific_libraries()
        self.assertAlmostEqual(augmented_objective(-.9, np.array([.2]), np.zeros(1), 10., np), -.9)
        self.assertAlmostEqual(augmented_objective(-.9, np.array([-.2]), np.zeros(1), 10., np), -.7)

    def test_direct_shifts_are_not_replaced(self):
        data, g, c, output = load_settings()
        self.assertTrue(output.is_relative_to(ROOT/"tests"))
        direct = dict(data["evaluation"])
        direct.pop("center_mm")
        report = evaluate_design(g, c, direct)
        self.assertEqual(report["evaluation"]["shifts"], direct)
        self.assertFalse(report["center_consistent"])
        self.assertGreater(report["maximum_center_error_mm"], 0)

    def test_quasi_newton_matches_feasible_slsqp(self):
        data, g, config, _ = load_settings()
        best, _, _ = opt.optimize(g, config)
        quasi, trials, _ = optimize(g, config, data["quasi_newton"])
        self.assertIsNotNone(best)
        self.assertIsNotNone(quasi)
        self.assertGreaterEqual(min(quasi[1].values()), -config["feasibility_tolerance"])
        self.assertAlmostEqual(best[0].forward_efficiency, quasi[0].forward_efficiency, places=7)
        self.assertTrue(trials[quasi[2]]["history"])


if __name__ == "__main__":
    unittest.main()
