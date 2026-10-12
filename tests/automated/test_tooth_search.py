"""固定モジュール版を小範囲の総当たりと照合する。"""
import csv
import importlib.util
import math
import random
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "fixed_search", Path(__file__).resolve().parents[2]/"tooth_search/tooth_search.py")
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


class FixedSearchTests(unittest.TestCase):
    def setUp(self):
        # 利用者が変更する本番設定に依存しない検証条件。
        fixture = {"m_a": .8, "m_c": .8467, "x_min": -2, "x_max": 2,
                   "z_s_min": 8, "z_p1_min": 8, "z_p2_min": 8,
                   "pressure_angle": 20, "alpha": math.radians(20),
                   "planet_count": 3, "planet_clearance": 0., "check_trimming": True}
        self.previous = {key: getattr(t, key) for key in fixture}
        for key, value in fixture.items():
            setattr(t, key, value)

    def tearDown(self):
        for key, value in self.previous.items():
            setattr(t, key, value)

    def test_independent_ring_limits_and_reduction_range(self):
        previous = (t.z_r1_max, t.z_r2_max, t.reduction_min, t.reduction_max)
        try:
            t.z_r1_max = 22
            t.z_r2_max = 24
            t.reduction_min = 20
            t.reduction_max = 200
            expected = set()
            table_a = {}
            table_b = {}
            table_c = {}
            for n in range(1, 45):
                table_a[n] = t.center_range(t.m_a, n, 2*t.x_min, 2*t.x_max)
                table_b[n] = t.center_range(t.m_a, n, t.x_min-t.x_max, t.x_max-t.x_min)
                table_c[n] = t.center_range(t.m_c, n, t.x_min-t.x_max, t.x_max-t.x_min)
            # 歯数範囲を絞らない5重ループを基準にする。
            for s in range(t.z_s_min, 23):
                for p1 in range(t.z_p1_min, 22):
                    for r1 in range(p1 + 1, 23):
                        if r1 < t.ring_minimum() or (s+r1) % t.planet_count:
                            continue
                        ab = t.overlap(table_a[s+p1], table_b[r1-p1])
                        if ab is None:
                            continue
                        ya = ab[0]/t.m_a - (s+p1)/2
                        if not t.planet_can_fit(t.m_a, p1, ab, min(ya-t.x_max, t.x_min)):
                            continue
                        if not t.internal_involute_possible(t.m_a, p1, r1, ab):
                            continue
                        if not t.pair_trochoid_possible(t.m_a, p1, r1, ab, s):
                            continue
                        if t.check_trimming and not t.pair_trimming_possible(t.m_a, p1, r1, ab, s):
                            continue
                        for r2 in range(t.z_p2_min + 1, 25):
                            for p2 in range(t.z_p2_min, r2):
                                if r2 < t.ring_minimum():
                                    continue
                                if (r2*p1-r1*p2) % (t.planet_count*math.gcd(p1, p2)):
                                    continue
                                numerator = s*(r2*p1-r1*p2)
                                if numerator == 0:
                                    continue
                                reduction = r2*p1*(s+r1)/abs(numerator)
                                if not 20 <= reduction <= 200:
                                    continue
                                abc = t.overlap(ab, table_c[r2-p2])
                                if abc is None:
                                    continue
                                if not t.planet_can_fit(t.m_c, p2, abc, t.x_min):
                                    continue
                                if not t.internal_involute_possible(t.m_c, p2, r2, abc):
                                    continue
                                if not t.pair_trochoid_possible(t.m_c, p2, r2, abc):
                                    continue
                                if not t.pair_trochoid_possible(t.m_a, p1, r1, abc, s):
                                    continue
                                if t.check_trimming:
                                    if not t.pair_trimming_possible(t.m_c, p2, r2, abc):
                                        continue
                                    if not t.pair_trimming_possible(t.m_a, p1, r1, abc, s):
                                        continue
                                expected.add((s, p1, r1, r2, p2))
            with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
                output = Path(folder) / "candidates.csv"
                count = t.search(output)
                actual = set()
                with open(output, encoding="utf-8-sig", newline="") as file:
                    reader = csv.DictReader(file)
                    self.assertEqual(reader.fieldnames, ["番号", "ma", "mc", "zs", "zp1", "zr1", "zp2", "zr2", "減速比"])
                    for index, row in enumerate(reader, 1):
                        self.assertEqual(int(row["番号"]), index)
                        actual.add(tuple(int(row[k]) for k in ("zs", "zp1", "zr1", "zr2", "zp2")))
                        self.assertEqual(float(row["ma"]), 0.8)
                        self.assertEqual(float(row["mc"]), 0.8467)
                        self.assertTrue(20 <= float(row["減速比"]) <= 200)
                self.assertGreater(len(expected), 0)
                self.assertEqual(actual, expected)
                self.assertEqual(count, len(expected))
        finally:
            t.z_r1_max, t.z_r2_max, t.reduction_min, t.reduction_max = previous

    def test_trimming_standard_boundary(self):
        # KHKの標準20度・リング50歯では33歯が可、34歯はトリミング干渉。
        for planet, expected in ((33, True), (34, False)):
            center = (50-planet)/2
            self.assertEqual(t.trimming_possible(
                1, planet, 50, (center, center), (planet+2, planet+2), (48, 48)), expected)
        # 小さな幅の範囲でも、明らかな干渉は除外できる。
        self.assertFalse(t.trimming_possible(
            1, 34, 50, (7.99999, 8.00001), (35.99999, 36.00001), (47.99999, 48.00001)))

    def test_trimming_does_not_drop_valid_points(self):
        rng = random.Random(20261013)
        checked = 0
        for _ in range(2000):
            planet = rng.randint(8, 50)
            ring = planet + rng.randint(4, 50)
            xp = rng.uniform(-2, 2)
            xr = rng.uniform(-2, 2)
            try:
                aw = t.working_angle(xp, xr, -1, planet, ring, 20)
            except ValueError:
                continue
            p = planet/2 + 1 + xp
            r = ring/2 - 1 + xr
            bp = planet*math.cos(t.alpha)/2
            br = ring*math.cos(t.alpha)/2
            if p <= bp or r <= br:
                continue
            ap = math.acos(bp/p)
            ar = math.acos(br/r)
            q = planet/ring
            sp = (1-(math.cos(ap)/math.cos(ar))**2)/(1-q*q)
            sr = ((math.cos(ar)/math.cos(ap))**2-1)/(1/(q*q)-1)
            if not (0 <= sp <= 1 and 0 <= sr <= 1):
                continue
            margin = math.asin(math.sqrt(sp)) + t.involute(ap) - t.involute(aw)
            margin -= (math.asin(math.sqrt(sr)) + t.involute(ar) - t.involute(aw))/q
            if margin < 0:
                continue
            center = (br-bp)/math.cos(aw)
            width = rng.uniform(0, 1)
            centers = (max(br-bp, center-width), center+width)
            self.assertTrue(t.trimming_possible(
                1, planet, ring, centers, (2*p-width, 2*p+width), (2*r-width, 2*r+width)))
            self.assertTrue(t.pair_trimming_possible(1, planet, ring, centers))
            checked += 1
        self.assertGreater(checked, 100)

    def test_trimming_off_keeps_previous_candidates(self):
        previous = t.check_trimming
        try:
            t.check_trimming = False
            self.test_independent_ring_limits_and_reduction_range()
        finally:
            t.check_trimming = previous

    def test_trimming_keeps_shortened_p1_examples(self):
        rng = random.Random(37)
        checked = 0
        for _ in range(3000):
            sun = rng.randint(8, 30)
            planet = rng.randint(10, 50)
            ring = sun + 2*planet + rng.randint(-4, 4)
            xs = rng.uniform(-2, 2)
            xp = rng.uniform(-2, 2)
            try:
                aw_a = t.working_angle(xs, xp, 1, sun, planet, 20)
            except ValueError:
                continue
            center = (sun+planet)*math.cos(t.alpha)/(2*math.cos(aw_a))
            bp = planet*math.cos(t.alpha)/2
            br = ring*math.cos(t.alpha)/2
            if center < br-bp:
                continue
            aw = math.acos((br-bp)/center)
            xr = xp + (ring-planet)*(t.involute(aw)-t.involute(t.alpha))/(2*math.tan(t.alpha))
            if not -2 <= xr <= 2:
                continue
            ya = center - (sun+planet)/2
            p = planet/2 + 1 + min(ya-xs, xp)
            r = ring/2 - 1 + xr
            if p <= bp or r <= br:
                continue
            ap = math.acos(bp/p)
            ar = math.acos(br/r)
            q = planet/ring
            sp = (1-(math.cos(ap)/math.cos(ar))**2)/(1-q*q)
            sr = ((math.cos(ar)/math.cos(ap))**2-1)/(1/(q*q)-1)
            if not (0 <= sp <= 1 and 0 <= sr <= 1):
                continue
            margin = math.asin(math.sqrt(sp)) + t.involute(ap) - t.involute(aw)
            margin -= (math.asin(math.sqrt(sr)) + t.involute(ar) - t.involute(aw))/q
            if margin >= 0:
                self.assertTrue(t.pair_trimming_possible(
                    1, planet, ring, (center, center+0.1), sun))
                checked += 1
        self.assertGreater(checked, 100)


if __name__ == "__main__":
    unittest.main()
