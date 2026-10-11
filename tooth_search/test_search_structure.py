"""小範囲の総当たりとの照合。実行: python -m unittest discover -s tooth_search"""
import csv
import importlib.util
import math
import random
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("tooth_candidates", Path(__file__).with_name("test.py"))
search = importlib.util.module_from_spec(spec)
spec.loader.exec_module(search)


class SearchStructureTests(unittest.TestCase):
    def test_unshifted_angles_and_centers(self):
        for sign in (1, -1):
            self.assertAlmostEqual(search.working_angle(0, 0, sign, 12, 36, 20), math.radians(20))
        for teeth in (12, 24, 60):
            centers = search.center_range(0.8, teeth, 0, 0)
            self.assertAlmostEqual(centers[0], 0.8 * teeth / 2)
            self.assertAlmostEqual(centers[1], centers[0])

    def test_small_search_matches_exhaustive(self):
        modules = [1.0, 1.25]
        diameter = 21
        expected = set()
        # 中心距離を先に計算。総当たり側には歯数範囲の絞り込みを使わない。
        external = {}
        internal = {}
        for module in modules:
            maximum = math.floor(diameter / module)
            for teeth in range(1, 2*maximum + 1):
                external[module, teeth] = search.center_range(module, teeth, -4, 4)
                internal[module, teeth] = search.center_range(module, teeth, -4, 4)
        for ma in modules:
            maximum1 = math.floor(diameter / ma)
            for zs in range(6, maximum1 + 1):
                for p1 in range(6, maximum1):
                    for r1 in range(p1 + 1, maximum1 + 1):
                        if (zs + r1) % 3:
                            continue
                        ab = search.overlap(external[ma, zs+p1], internal[ma, r1-p1])
                        if ab is None or not search.internal_involute_possible(ma, p1, r1, ab):
                            continue
                        ya_min = ab[0] / ma - (zs+p1)/2
                        if not search.planet_can_fit(ma, p1, ab, min(ya_min-2, -2)):
                            continue
                        if not search.pair_trochoid_possible(ma, p1, r1, ab, zs):
                            continue
                        for mc in modules:
                            maximum2 = math.floor(diameter / mc)
                            for r2 in range(7, maximum2 + 1):
                                for p2 in range(6, r2):
                                    if (r2*p1-r1*p2) % (3*math.gcd(p1, p2)):
                                        continue
                                    # 総当たり側では式を直接計算する。
                                    speed_numerator = zs * (r2*p1 - r1*p2)
                                    if speed_numerator == 0:
                                        continue
                                    reduction = r2*p1*(zs+r1) / abs(speed_numerator)
                                    if not search.reduction_min <= reduction <= search.reduction_max:
                                        continue
                                    abc = search.overlap(ab, internal[mc, r2-p2])
                                    if abc is None:
                                        continue
                                    if not search.planet_can_fit(mc, p2, abc, -2):
                                        continue
                                    if not search.internal_involute_possible(mc, p2, r2, abc):
                                        continue
                                    if not search.pair_trochoid_possible(mc, p2, r2, abc):
                                        continue
                                    if not search.pair_trochoid_possible(ma, p1, r1, abc, zs):
                                        continue
                                    expected.add((ma, mc, zs, p1, r1, r2, p2))
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "candidates.csv"
            count = search.search(modules, diameter, diameter, output)
            actual = set()
            with open(output, encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    actual.add((float(row["ma"]), float(row["mc"]), int(row["zs"]),
                                int(row["zp1"]), int(row["zr1"]), int(row["zr2"]), int(row["zp2"])))
                    self.assertTrue(search.reduction_min <= float(row["reduction"]) <= search.reduction_max)
            self.assertGreater(len(expected), 0)
            self.assertEqual(actual, expected)
            self.assertEqual(count, len(actual))

    def test_reduction_ratio(self):
        self.assertIsNone(search.reduction_ratio(12, 24, 60, 24, 60))
        self.assertAlmostEqual(search.reduction_ratio(10, 44, 98, 37, 91), 114.4)
        # 同歯数比で出力方向が反転しても、倍率は絶対値で求める。
        self.assertAlmostEqual(search.reduction_ratio(12, 24, 60, 24, 72), 36)
        self.assertAlmostEqual(search.reduction_ratio(12, 24, 60, 36, 72), 24)

    def test_reduction_limits_in_search(self):
        previous_min = search.reduction_min
        previous_max = search.reduction_max
        try:
            with tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "candidates.csv"
                search.reduction_min = 1
                search.reduction_max = math.inf
                search.search([1.0], 21, 21, output)
                with open(output, encoding="utf-8-sig", newline="") as file:
                    original = list(csv.DictReader(file))
                # 実在する候補の倍率を上下限の両方に設定して、境界を含むことを確認。
                boundary = float(original[0]["reduction"])
                expected = []
                for row in original:
                    if float(row["reduction"]) == boundary:
                        expected.append(row)
                search.reduction_min = boundary
                search.reduction_max = boundary
                count = search.search([1.0], 21, 21, output)
                with open(output, encoding="utf-8-sig", newline="") as file:
                    actual = list(csv.DictReader(file))
                self.assertEqual(actual, expected)
                self.assertEqual(count, len(expected))
                search.reduction_min = 100
                search.reduction_max = 10
                with self.assertRaises(ValueError):
                    search.search([1.0], 21, 21, output)
        finally:
            search.reduction_min = previous_min
            search.reduction_max = previous_max

    def test_internal_interference_catalog_examples(self):
        # 標準20度、リング50歯。KHK表のインボリュート境界21/22。
        for planet, expected in ((21, False), (22, True)):
            result = search.internal_interference(1, planet, 50, (50-planet)/2, planet+2, 48)
            self.assertEqual(result["involute"], expected)
        # 同じリングのトロコイド境界41/42。
        for planet, expected in ((41, True), (42, False)):
            result = search.internal_interference(1, planet, 50, (50-planet)/2, planet+2, 48)
            self.assertEqual(result["trochoid"], expected)
        # 同じリングのトリミング境界33/34。
        for planet, expected in ((33, True), (34, False)):
            result = search.internal_interference(1, planet, 50, (50-planet)/2, planet+2, 48)
            self.assertEqual(result["trimming"], expected)

    def test_trochoid_range_catalog_boundary(self):
        # 幅0の範囲なら、具体値の判定と同じ41/42歯の境界になる。
        for planet, expected in ((41, True), (42, False)):
            center = (50-planet)/2
            possible = search.trochoid_possible(
                1, planet, 50, (center, center), (planet+2, planet+2), (48, 48))
            self.assertEqual(possible, expected)
        # 点だけでなく、干渉する境界付近の狭い範囲も除外できる。
        self.assertFalse(search.trochoid_possible(
            1, 42, 50, (3.99999, 4.00001), (43.99999, 44.00001), (47.99999, 48.00001)))

    def test_trochoid_range_keeps_noninterfering_witnesses(self):
        # 実際に非干渉の点を含む範囲が、粗い判定で落ちないことを確認。
        rng = random.Random(20261010)
        checked = 0
        for _ in range(2000):
            planet = rng.randint(6, 60)
            ring = planet + rng.randint(2, 50)
            xp = rng.uniform(-2, 2)
            xr = rng.uniform(-2, 2)
            try:
                aw = search.working_angle(xp, xr, -1, planet, ring, 20)
            except ValueError:
                continue
            center = (ring-planet)*math.cos(search.alpha)/(2*math.cos(aw))
            p_tip = planet+2+2*xp
            r_tip = ring-2+2*xr
            exact = search.internal_interference(1, planet, ring, center, p_tip, r_tip)
            if exact["trochoid"] is not True:
                continue
            width = rng.uniform(0, 2)
            centers = (max((ring-planet)*math.cos(search.alpha)/2, center-width), center+width)
            self.assertTrue(search.trochoid_possible(
                1, planet, ring, centers, (p_tip-width, p_tip+width), (r_tip-width, r_tip+width)))
            self.assertTrue(search.pair_trochoid_possible(1, planet, ring, centers))
            checked += 1
        self.assertGreater(checked, 100)

    def test_shortened_p1_keeps_noninterfering_witnesses(self):
        rng = random.Random(37)
        checked = 0
        for _ in range(5000):
            sun = rng.randint(6, 30)
            planet = rng.randint(10, 50)
            ring = sun + 2*planet + rng.randint(-4, 4)
            xs = rng.uniform(-2, 2)
            xp = rng.uniform(-2, 2)
            try:
                aw = search.working_angle(xs, xp, 1, sun, planet, 20)
            except ValueError:
                continue
            center = (sun+planet)*math.cos(search.alpha)/(2*math.cos(aw))
            base_center = (ring-planet)*math.cos(search.alpha)/2
            if center < base_center:
                continue
            aw_internal = math.acos(base_center/center)
            xr = xp + (ring-planet)*(search.involute(aw_internal)-search.involute(search.alpha))/(2*math.tan(search.alpha))
            if not -2 <= xr <= 2:
                continue
            ya = center - (sun+planet)/2
            p_tip = planet+2+2*min(ya-xs, xp)
            r_tip = ring-2+2*xr
            result = search.internal_interference(1, planet, ring, center, p_tip, r_tip)
            if result["trochoid"] is True:
                self.assertTrue(search.pair_trochoid_possible(
                    1, planet, ring, (center, center+0.1), sun))
                checked += 1
        self.assertGreater(checked, 100)


if __name__ == "__main__":
    unittest.main()
