"""CSV候補が事前判定だけでも、最適化で全条件を確認することを検証。"""
import csv
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from optimization import optimize_candidates as opt
from optimization import profile_shift_model as model


class CandidateOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.config = opt.load_config(Path(__file__).resolve().parents[2]/"optimization/optimization_config.json")
        self.row = dict(zs="12", zp1="39", zr1="90", zp2="32", zr2="81",
                        ma="0.8", mc="0.8467", a_min="999", a_max="1000", status="passed")
        self.g = opt.gearbox_from_row(self.row, self.config)

    def test_common_center_and_shared_p1(self):
        m = model.Model(self.g)
        m.calculate([2, 1.21, 21.267911])
        s = m.shifts
        for mesh, shift in zip(m.meshes, (s.xs+s.xp1, s.xp1-s.xr1, s.xp2-s.xr2)):
            expected = ((mesh.z1+mesh.sign*mesh.z2)
                        * (model.involute(mesh.working_angle)-model.involute(self.g.alpha))
                        / (2*math.tan(self.g.alpha)))
            self.assertAlmostEqual(shift, expected, places=11)
            self.assertEqual(mesh.center, m.center_mm)
        self.assertEqual(m.meshes[0].tip_radius2, m.meshes[1].tip_radius1)
        # 任意の転位を直接代入する入口でも、共有P1の転位は一つ。
        m.calculate_efficiency(s.xs, s.xp1, s.xr1, s.xp2, s.xr2, m.center_mm)

    def test_internal_involute_and_trimming_switch(self):
        m = model.Model(self.g)
        m.calculate([2, 1.21, 21.267911])
        on = opt.margins_for(m, self.config)
        off = opt.margins_for(m, dict(self.config, include_trimming_constraint=False))
        self.assertEqual(set(on)-set(off), {"b_trimming", "c_trimming"})
        self.assertIn("b_involute", off)
        self.assertIn("c_involute", off)
        self.assertNotIn("a_involute", off)
        self.assertEqual(len(on), 44)
        # 内歯の歯先圧力角が0なら、作動圧力角>0で干渉する。
        m.meshes[1].tip_angle2 = 0
        self.assertLess(model.internal_involute_margin(m.meshes[1]), 0)

    def test_shared_shift_and_neighbor_failures_are_not_hidden(self):
        m = model.Model(self.g)
        m.calculate([2, 1.21, 21.267911])
        m.shifts.xp1 = self.config["shift_upper"] + .2
        self.assertLess(opt.margins_for(m, self.config)["xp1_upper"], 0)
        for mesh in m.meshes[1:]:
            mesh.tip_radius1 = m.center_mm
        margins = opt.margins_for(m, self.config)
        self.assertLess(margins["b_planet_clearance"], 0)
        self.assertLess(margins["c_planet_clearance"], 0)

    def test_csv_order_and_bom(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            source = Path(directory)/"candidates.csv"
            fields = list(reversed(list(self.row)))
            with source.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow(self.row)
            index, row = next(opt.read_candidates(source))
            g = opt.gearbox_from_row(row, self.config)
            self.assertEqual(index, 1)
            self.assertEqual(g.to_dict(), self.g.to_dict())
            # CSVの過去の中心距離範囲は探索区間として使わない。
            self.assertLess(opt.variable_bounds(g, self.config)[2][1], 999)

    def test_bad_candidate_does_not_stop_next_row(self):
        bad = dict(self.row, zs="12.5")
        self.assertEqual(opt.optimize_candidate(1, bad, self.config)["status"], "candidate_rejected")
        incompatible = dict(self.row, ma=".1", mc="10")
        self.assertEqual(opt.optimize_candidate(2, incompatible, self.config)["status"], "candidate_rejected")

    def test_candidate_numbers_survive_filtering_and_reordering(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            source = Path(directory)/"input.csv"
            with source.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["番号", *self.row])
                writer.writeheader()
                writer.writerows([dict(self.row, 番号=27), dict(self.row, 番号=5)])
            self.assertEqual([i for i, row in opt.read_candidates(source)], [27, 5])

    def test_trochoid_domain_and_invalid_evaluation_are_rejected(self):
        m = model.Model(self.g)
        m.calculate([2, 1.21, 21.267911])
        m.meshes[1].tip_radius2 = 1000
        self.assertLess(model.internal_trochoid_margin(m.meshes[1]), 0)
        np, scipy, _ = opt.load_scientific_libraries()

        def solver(fun, start, **kwargs):
            from types import SimpleNamespace
            self.assertTrue(math.isfinite(fun(start)))
            self.assertEqual(len(kwargs["constraints"]["fun"](start)), 44)
            return SimpleNamespace(x=start, success=True, message="test", nit=1)

        with patch.object(opt, "load_scientific_libraries", return_value=(np, scipy, solver)), \
             patch.object(model.Model, "calculate", side_effect=ZeroDivisionError("singular")):
            best, trials, _ = opt.optimize(self.g, dict(self.config, start_count=1))
        self.assertIsNone(best)
        self.assertFalse(trials[0]["accepted"])
        json.dumps(trials, allow_nan=False)

    def test_empty_csv_produces_current_empty_results(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            source = Path(directory)/"empty.csv"
            source.write_text("ma,mc,zs,zp1,zr1,zp2,zr2\n", encoding="utf-8")
            output = Path(directory)/"output"
            summary = opt.run_batch(source, output, self.config)
            self.assertEqual(summary["processed_count"], 0)
            with (output/"results.csv").open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                self.assertIn("最適化判定", reader.fieldnames)
                self.assertEqual(list(reader), [])

    def test_success_flag_does_not_override_constraint_violation(self):
        np, _, _ = opt.load_scientific_libraries()

        def solver(fun, start, **kwargs):
            from types import SimpleNamespace
            return SimpleNamespace(x=np.array([0., 0., 0.]), success=True, message="test", nit=1)

        with patch.object(opt, "load_scientific_libraries", return_value=(np, type("SciPy", (), {"__version__": "test"}), solver)):
            best, trials, _ = opt.optimize(self.g, dict(self.config, start_count=1))
        self.assertIsNone(best)
        self.assertTrue(trials[0]["solver_success"])
        self.assertFalse(trials[0]["accepted"])
        self.assertTrue(trials[0]["violated_constraints"])

    def test_real_solver_and_saved_batch(self):
        # 既知の成立する候補と不正行を同時に処理し、保存まで検証。
        config = dict(self.config, start_count=2, max_iterations=200, workers=1)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            source = Path(directory)/"input.csv"
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(self.row))
                writer.writeheader()
                writer.writerows([dict(self.row, zs="bad"), self.row])
            summary = opt.run_batch(source, Path(directory)/"output", config)
            self.assertEqual(summary["processed_count"], 2)
            self.assertEqual(summary["successful_candidate_count"], 1)
            output = Path(directory)/"output"
            self.assertEqual(sorted(p.name for p in output.iterdir()), ["results.csv", "summary.json"])
            with (output/"results.csv").open(encoding="utf-8-sig", newline="") as stream:
                saved = list(csv.DictReader(stream))
            self.assertEqual(len(saved), 2)
            self.assertEqual(list(saved[0]), ["番号", "最適化判定", "zs", "zp1", "zr1", "zp2", "zr2",
                "減速比", "順効率（％）", "逆効率（％）", "かみ合い率_S-P1", "かみ合い率_P1-R1", "かみ合い率_P2-R2",
                "xs", "xp1", "xr1", "xp2", "xr2"])
            self.assertEqual(saved[0]["順効率（％）"], "")
            self.assertEqual(saved[0]["最適化判定"], "未収束")
            success = saved[1]
            self.assertEqual(success["最適化判定"], "収束")
            self.assertEqual(float(success["xr1"]), summary["best"]["shifts"]["xr1"])
            self.assertAlmostEqual(float(success["減速比"]), float(abs(1/self.g.speed_ratio)))
            self.assertAlmostEqual(float(success["逆効率（％）"]), 100*summary["best"]["backward_efficiency"])
            for mesh, label in zip(summary["best"]["meshes"], ("S-P1", "P1-R1", "P2-R2")):
                self.assertAlmostEqual(float(success[f"かみ合い率_{label}"]),
                                       mesh["approach_ratio"] + mesh["recess_ratio"])
            # 並列でも候補の固定値・初期値・最適解は変わらない。
            parallel = opt.run_batch(source, Path(directory)/"parallel", config, workers=2)
            self.assertEqual(parallel["best_candidate_index"], summary["best_candidate_index"])
            self.assertAlmostEqual(parallel["best"]["forward_efficiency"], summary["best"]["forward_efficiency"], places=10)
            with (Path(directory)/"parallel/results.csv").open(encoding="utf-8-sig", newline="") as stream:
                parallel_rows = list(csv.DictReader(stream))
            self.assertEqual(len(parallel_rows), len(saved))
            for left, right in zip(saved, parallel_rows):
                for key in left:
                    if key in {"番号", "最適化判定", "zs", "zp1", "zr1", "zp2", "zr2"} or not left[key]:
                        self.assertEqual(left[key], right[key])
                    else:
                        self.assertAlmostEqual(float(left[key]), float(right[key]), places=10)

    def test_repeated_execution_recalculates_and_overwrites(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            source, output = Path(directory)/"input.csv", Path(directory)/"output"
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(self.row))
                writer.writeheader()
                writer.writerow(dict(self.row, zs="bad"))
            config = dict(self.config, workers=1)
            opt.run_batch(source, output, config)
            with patch.object(opt, "batch_candidate", wraps=opt.batch_candidate) as batch:
                summary = opt.run_batch(source, output, dict(config, friction_coefficient=.12))
            self.assertEqual(batch.call_count, 1)
            self.assertEqual(summary["processed_count"], 1)
            self.assertNotIn("run_identity", summary)
            self.assertEqual(sorted(p.name for p in output.iterdir()), ["results.csv", "summary.json"])
            with (output/"results.csv").open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 1)

    def test_workers_from_config_without_command_line_option(self):
        import sys
        summary = {"successful_candidate_count": 0, "processed_count": 0,
                   "converged_feasible_trial_count": 0, "trial_count": 0}
        with patch.object(sys, "argv", ["optimize_candidates.py"]), \
             patch.object(opt, "load_scientific_libraries"), \
             patch.object(opt, "run_batch", return_value=summary) as batch:
            opt.main()
        self.assertEqual(batch.call_args.args[2]["workers"], self.config["workers"])
        with patch.object(sys, "argv", ["optimize_candidates.py", "--workers", "2"]), \
             patch.object(opt, "load_scientific_libraries"), \
             patch.object(opt, "run_batch", return_value=summary) as batch:
            opt.main()
        self.assertEqual(batch.call_args.args[2]["workers"], 2)

    def test_crashing_geometry_is_rejected_before_slsqp(self):
        row = dict(self.row, zs="18", zp1="36", zr1="81", zp2="38", zr2="81")
        with patch.object(opt, "optimize", side_effect=AssertionError("must not call solver")):
            report = opt.optimize_candidate(1796, row, self.config)
        self.assertEqual(report["status"], "geometry_rejected")
        self.assertLess(report["necessary_recess_margins"]["b_recess_upper"], -self.config["feasibility_tolerance"])
        self.assertIsNone(report["best"])
        self.assertEqual(report["trials"], [])

    def test_recess_precheck_bounds_all_sampled_designs(self):
        import random
        rng = random.Random(13)
        for g in (self.g, model.Gearbox(zs=18, zp1=36, zr1=81, zp2=38, zr2=81)):
            bounds = opt.variable_bounds(g, self.config)
            upper = opt.necessary_recess_margins(g, self.config, bounds)
            for _ in range(150):
                m = model.Model(g, self.config["friction_coefficient"])
                m.calculate([rng.uniform(lo, hi) for lo, hi in bounds])
                for mesh in m.meshes[1:]:
                    self.assertLessEqual(mesh.recess_ratio, upper[f"{mesh.name}_recess_upper"]+1e-10)



if __name__ == "__main__":
    unittest.main()
