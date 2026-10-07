"""決定変数の変換と、指定した転位係数の直接評価を検証。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))
from profile_shift_model import Gearbox, Model, center_for_external_shift_sum


class DirectEfficiencyTests(unittest.TestCase):
    def test_split_path_matches_optimization_path(self):
        gearbox = Gearbox()
        model = Model(gearbox)
        direct = Model(gearbox)
        for variables in ([1, 0.5, 21], [2, 1.21, 21.26791100127434], [0, 0, 22]):
            model.calculate(variables)
            xs, xp1, xr1, xp2, xr2 = direct.calculate_shifts(variables)
            direct.calculate_efficiency(xs, xp1, xr1, xp2, xr2, variables[2])
            self.assertEqual(model.to_dict(), direct.to_dict())

    def test_shift_conversion_has_no_side_effect(self):
        model = Model(Gearbox())
        model.calculate([1, 0.5, 21])
        before = model.to_dict()
        shifts = model.calculate_shifts([2, 1.21, 21.26791100127434])
        self.assertAlmostEqual(shifts[0], 0.476, places=10)
        self.assertAlmostEqual(shifts[1], 0.762, places=10)
        self.assertEqual(before, model.to_dict())

    def test_direct_input_is_preserved_and_equations_match(self):
        gearbox = Gearbox()
        center = center_for_external_shift_sum(gearbox, 0.476 + 0.762)
        model = Model(gearbox)
        model.calculate_efficiency(0.476, 0.762, 2, 0.536, 1.21, center)
        self.assertEqual(model.shifts.to_dict(),
                         {"xs": 0.476, "xp1": 0.762, "xr1": 2, "xp2": 0.536, "xr2": 1.21})
        # 入力xp2が歯先半径に直接反映される（変換ルートでは約0.537037になる）。
        tip_p2 = gearbox.module_c * (gearbox.zp2 / 2 + 1 + 0.536)
        self.assertAlmostEqual(model.meshes[2].tip_radius1, tip_p2, places=12)
        # 基礎効率を使って式(64)を独立に再計算。
        a, b, c = model.meshes
        expected = ((1 + a.basic_efficiency * b.basic_efficiency * gearbox.i1) * (1 - gearbox.i2)
                    / ((1 + gearbox.i1) * (1 - b.basic_efficiency * c.basic_efficiency * gearbox.i2)))
        self.assertAlmostEqual(model.forward_efficiency, expected, places=14)


if __name__ == "__main__":
    unittest.main()
