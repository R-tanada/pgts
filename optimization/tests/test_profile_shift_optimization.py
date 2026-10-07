"""論文式の数値確認、幾何制約、複数初期値の最適化を検証。"""
import math
import unittest
from fractions import Fraction
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

import optimize_profile_shift as optimizer
import profile_shift_model as model


class ProfileModelTests(unittest.TestCase):
    def setUp(self):
        self.gearbox = model.Gearbox()
        self.center = model.reference_center_distances(self.gearbox)["a"]
        self.variables = [2.0, 1.210, self.center]
        self.reference = model.Model(self.gearbox, 0.1)
        self.reference.calculate(self.variables)

    def test_calculate_updates_same_model_without_returning_result(self):
        snapshot = self.reference.to_dict()
        candidate = [1.0, 0.5, 21.0]
        self.assertIsNone(self.reference.calculate(candidate))
        fresh = model.Model(self.gearbox, 0.1)
        fresh.calculate(candidate)
        self.assertEqual(self.reference.to_dict(), fresh.to_dict())
        self.assertEqual(snapshot["center_mm"], self.center)
        self.assertNotEqual(snapshot["shifts"], self.reference.shifts.to_dict())
        self.reference.calculate(self.variables)
        self.assertEqual(self.reference.to_dict(), snapshot)

    def test_fixed_tooth_ratio(self):
        self.assertEqual(self.gearbox.speed_ratio, Fraction(62, 5967))
        self.assertAlmostEqual(float(1 / self.gearbox.speed_ratio), 96.24193548387096)
        self.assertTrue(all(optimizer.fixed_assembly_checks(self.gearbox).values()))

    def test_dependent_shifts_preserve_common_center(self):
        shifts = self.reference.shifts
        for mesh, relation in zip(self.reference.meshes,
                                  (shifts.xs + shifts.xp1, shifts.xp1 - shifts.xr1,
                                   shifts.xp2 - shifts.xr2)):
            involute_working = (model.involute(self.gearbox.alpha)
                                + 2*math.tan(self.gearbox.alpha)*relation / (mesh.z1 + mesh.sign*mesh.z2))
            angle = model.angle_from_involute(involute_working)
            reconstructed = mesh.module * abs(mesh.z1 + mesh.sign*mesh.z2) * math.cos(self.gearbox.alpha) / (2*math.cos(angle))
            self.assertAlmostEqual(reconstructed, self.center, places=10)

    def test_paper_rounding_and_contact_discrepancy_are_visible(self):
        centers = model.reference_center_distances(self.gearbox)
        self.assertLess(abs(centers["a"] - centers["c"]), 0.001)
        self.assertAlmostEqual(self.reference.shifts.xs, 0.476, places=10)
        self.assertAlmostEqual(self.reference.shifts.xp1, 0.762, places=10)
        self.assertAlmostEqual(self.reference.meshes[0].contact_ratio, 1.232, delta=0.001)
        self.assertAlmostEqual(self.reference.meshes[2].contact_ratio, 1.565, delta=0.001)
        # 表に合わせて式(83)を変更していないことを確認する。
        self.assertAlmostEqual(self.reference.meshes[1].contact_ratio, 1.3162720214, places=8)
        self.assertGreater(abs(self.reference.meshes[1].contact_ratio - 1.420), 0.1)

    def test_contact_ratios_match_independent_line_of_action(self):
        base_pitch = math.pi * math.cos(self.gearbox.alpha)
        for mesh in self.reference.meshes:
            tangent1 = math.sqrt(mesh.tip_radius1**2 - mesh.base_radius1**2)
            tangent2 = math.sqrt(mesh.tip_radius2**2 - mesh.base_radius2**2)
            if mesh.sign == 1:
                length = tangent1 + tangent2 - mesh.center * math.sin(mesh.working_angle)
            else:
                length = tangent1 - tangent2 + mesh.center * math.sin(mesh.working_angle)
            geometric_contact = length / (mesh.module * base_pitch)
            self.assertAlmostEqual(mesh.contact_ratio, geometric_contact, places=12)

    def test_lossless_efficiencies(self):
        forward, backward = model.total_efficiencies(self.gearbox, 1.0, 1.0, 1.0)
        self.assertAlmostEqual(forward, 1.0)
        self.assertAlmostEqual(backward, 1.0)

    def test_objective_formula_independent_calculation(self):
        eta_a, eta_b, eta_c = (mesh.basic_efficiency for mesh in self.reference.meshes)
        g = float(self.gearbox.speed_ratio)
        torque_multiplier = (1 + eta_a*eta_b*self.gearbox.i1) / (1 - eta_b*eta_c*self.gearbox.i2)
        self.assertAlmostEqual(self.reference.forward_efficiency, g*torque_multiplier, places=12)

    def test_reverse_efficiency_from_independent_eq74_force_balance(self):
        # 式(74)のtau_p=tau_ca=0を2x2線形方程式で直接解く。
        # 逆効率の閉形式と別の計算経路にして、eta_aの因子を検証。
        gearbox, reference = self.gearbox, self.reference
        center = reference.center_mm
        eta_a, eta_b, eta_c = [mesh.basic_efficiency for mesh in reference.meshes]
        rs = center * gearbox.zs / (gearbox.zs + gearbox.zp1)
        rp11 = center * gearbox.zp1 / (gearbox.zs + gearbox.zp1)
        rp12 = center * gearbox.zp1 / (gearbox.zr1 - gearbox.zp1)
        rr1 = center * gearbox.zr1 / (gearbox.zr1 - gearbox.zp1)
        rp2 = center * gearbox.zp2 / (gearbox.zr2 - gearbox.zp2)
        rr2 = center * gearbox.zr2 / (gearbox.zr2 - gearbox.zp2)
        a00, a01 = rp11, -rp12*eta_b
        a10, a11 = -rs*eta_a-rp11, -rr1+rp12*eta_b
        # f_r2p2=1として残りの2力を解く。
        b0, b1 = rp2, rr2*eta_c-rp2
        determinant = a00*a11-a01*a10
        force_sp1 = (b0*a11-a01*b1)/determinant
        torque_out = -rs*eta_a*force_sp1
        torque_in = rr2*eta_c
        efficiency = torque_out/torque_in/float(gearbox.speed_ratio)
        self.assertAlmostEqual(efficiency, reference.backward_efficiency, places=12)
        self.assertAlmostEqual(reference.backward_efficiency_force_balance,
                               reference.backward_efficiency, places=12)

    def test_efficiency_comparison_is_measured_table_iv(self):
        rows = optimizer.efficiency_comparison_rows(self.reference)
        self.assertEqual(rows[0]["paper_measured_percent"], 89.0)
        self.assertEqual(rows[1]["paper_measured_percent"], 85.3)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["quantity"], "backward_eq75")
        self.assertAlmostEqual(rows[0]["difference_pp"],
                               100*self.reference.forward_efficiency-89.0)

    def test_shifted_constraints_pass_at_reference(self):
        margins = model.constraint_margins(self.reference, self.gearbox, -2, 2, 1, 2, 0, True)
        self.assertGreaterEqual(min(margins.values()), -1e-10)
        # 転位上限を超えた点を可行と誤認しない。
        bad = model.Model(self.gearbox, 0.1)
        bad.calculate([2.1, 1.21, self.center])
        bad_margins = model.constraint_margins(bad, self.gearbox, -2, 2, 1, 2, 0, True)
        self.assertLess(bad_margins["xr1_upper"], 0)

    def test_trochoid_and_trimming_catalog_boundaries(self):
        # 無転位の場合はKHKのカタログと一致する。
        for planet, ring, trochoid_ok, trimming_ok in (
            (51, 60, True, False), (52, 60, False, False),
            (43, 60, True, True), (44, 60, True, False),
            (72, 80, True, False), (73, 80, False, False),
            (64, 80, True, True), (65, 80, True, False),
        ):
            mesh = model.Mesh("test", planet, ring, -1, 1,
                                         (ring - planet)/2, (planet+2)/2,
                                         (ring-2)/2, math.radians(20), 0.1)
            self.assertEqual(model.internal_trochoid_margin(mesh) >= 0, trochoid_ok)
            self.assertEqual(model.internal_trimming_margin(mesh) >= 0, trimming_ok)


class OptimizationTests(unittest.TestCase):
    def test_multistart_slsqp_is_feasible_and_improves_reference(self):
        config = optimizer.load_config(Path(__file__).resolve().parent.parent / "code" / "optimization_config.json")
        gearbox = model.Gearbox()
        best_record, trials, _ = optimizer.optimize(gearbox, config)
        self.assertIsNotNone(best_record)
        best, margins, index = best_record
        self.assertTrue(trials[index]["solver_success"])
        self.assertEqual(trials[index]["history"][0]["iteration"], 0)
        self.assertEqual(trials[index]["history"][-1]["variables"], trials[index]["final_variables"])
        self.assertTrue(trials[index]["history"][-1]["feasible"])
        self.assertGreaterEqual(min(margins.values()), -config["feasibility_tolerance"])
        center = model.reference_center_distances(gearbox)["a"]
        reference = model.Model(gearbox, config["friction_coefficient"])
        reference.calculate([2, 1.21, center])
        self.assertGreaterEqual(best.forward_efficiency, reference.forward_efficiency - 1e-9)
        successful = [trial["forward_efficiency"] for trial in trials if trial["solver_success"] and trial["feasible"]]
        self.assertGreaterEqual(len(successful), 2)
        self.assertLess(max(successful) - min(successful), 1e-7)
        self.assertAlmostEqual(best.shifts.xr1, 2.0, places=5)
        # 論文値の完全再現ではなく、独立して計算した結果であることを確認。
        self.assertGreater(abs(best.shifts.xs - model.PAPER_SHIFTS.xs), 0.01)
        self.assertEqual(set(best.shifts.to_dict()), set(model.PAPER_SHIFTS.to_dict()))


if __name__ == "__main__":
    unittest.main()
