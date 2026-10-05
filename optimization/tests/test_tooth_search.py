"""数式の境界、等配位相、列挙の網羅性、保存結果を検証する。"""
import csv
import itertools
import tempfile
import unittest
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

import tooth_search as search


class ToothSearchTests(unittest.TestCase):
    def setUp(self):
        self.settings, _ = search.load_settings(Path(__file__).resolve().parent.parent / "code" / "search_config.json")

    def test_speed_ratio_and_zero_output(self):
        teeth = search.ToothCounts(20, 30, 80, 29, 79)
        self.assertEqual(search.speed_ratio(teeth), Fraction(1, 237))
        stationary = search.ToothCounts(20, 30, 80, 30, 80)
        self.assertFalse(search.satisfies_reduction_ratio(stationary, self.settings))

    def test_ratio_bounds_and_direction(self):
        teeth = search.ToothCounts(20, 30, 80, 29, 79)
        settings = replace(self.settings, reduction_min=Fraction(237),
                           reduction_max=Fraction(237), direction="same")
        self.assertTrue(search.satisfies_reduction_ratio(teeth, settings))
        self.assertFalse(search.satisfies_reduction_ratio(teeth, replace(settings, direction="opposite")))
        self.assertFalse(search.satisfies_reduction_ratio(teeth, replace(settings, reduction_min=Fraction(238))))

    def test_center_distance_with_different_modules(self):
        settings = replace(self.settings, module2=Fraction("0.5"))
        teeth = search.ToothCounts(20, 30, 80, 30, 130)
        self.assertTrue(search.satisfies_center_distance(teeth, settings))
        self.assertFalse(search.satisfies_center_distance(replace(teeth, zr2=131), settings))

    def test_compound_phase_is_more_than_first_layer(self):
        teeth = search.ToothCounts(22, 20, 62, 24, 66)
        settings = replace(self.settings, planet_count=4)
        self.assertEqual((teeth.zs + teeth.zr1) % 4, 0)
        self.assertFalse(search.satisfies_equal_spacing(teeth, settings))

    def test_equal_spacing_against_direct_phase_search(self):
        # 次の等配位置で、P1の歯ピッチ単位の回転kによりP2も歯合わせできるか。
        for p1, p2, r1, r2, count in itertools.product(
                range(4, 9), range(4, 9), (30, 31), (32, 33), (2, 3, 4)):
            teeth = search.ToothCounts(12, p1, r1, p2, r2)
            settings = replace(self.settings, planet_count=count)
            phase = Fraction(r2 * p1 - r1 * p2, count * p1)
            second_layer_ok = any((phase + Fraction(k * p2, p1)).denominator == 1
                                  for k in range(p1))
            expected = (12 + r1) % count == 0 and second_layer_ok
            self.assertEqual(search.satisfies_equal_spacing(teeth, settings), expected)

    def test_internal_involute_catalog_boundary(self):
        # KHK internal-tech.pdf: 内歯車60歯の下限21歯。
        ring = search.StandardGear(60, 1, internal=True)
        self.assertFalse(search.satisfies_internal_involute(search.StandardGear(20, 1), ring))
        self.assertTrue(search.satisfies_internal_involute(search.StandardGear(21, 1), ring))
        # 基礎円内の歯先は、この解析式の適用範囲外。
        small_ring = search.StandardGear(30, 1, internal=True)
        self.assertFalse(search.satisfies_internal_involute(search.StandardGear(20, 1), small_ring))

    def test_trimming_catalog_boundaries(self):
        # KHK internal-tech.pdf: R60ではP<=43、R80ではP<=64。
        for ring_teeth, maximum_planet in ((60, 43), (80, 64), (100, 84)):
            ring = search.StandardGear(ring_teeth, 1, internal=True)
            self.assertTrue(search.satisfies_trimming(search.StandardGear(maximum_planet, 1), ring))
            self.assertFalse(search.satisfies_trimming(search.StandardGear(maximum_planet + 1, 1), ring))

    def test_trochoid_sufficient_condition(self):
        planet = search.StandardGear(40, 1)
        self.assertFalse(search.satisfies_trochoid(planet, search.StandardGear(49, 1, True)))
        self.assertTrue(search.satisfies_trochoid(planet, search.StandardGear(50, 1, True)))

    def test_external_involute_and_planet_clearance(self):
        self.assertTrue(search.satisfies_external_involute(
            search.StandardGear(20, 1), search.StandardGear(30, 1)))
        self.assertFalse(search.satisfies_external_involute(
            search.StandardGear(5, 1), search.StandardGear(100, 1)))
        teeth = search.ToothCounts(20, 30, 80, 29, 79)
        self.assertTrue(search.satisfies_outside_diameter(teeth, self.settings))
        self.assertFalse(search.satisfies_outside_diameter(
            teeth, replace(self.settings, planet_clearance_mm=100)))

    def test_enumeration_matches_five_nested_loops(self):
        settings = replace(self.settings, sun=search.ToothRange(20, 22),
                           planet1=search.ToothRange(20, 23), ring1=search.ToothRange(60, 68),
                           planet2=search.ToothRange(20, 24), ring2=search.ToothRange(60, 68))
        enumerated = set(search.enumerate_center_matched_teeth(settings))
        exhaustive = set()
        ranges = [settings.sun, settings.planet1, settings.ring1, settings.planet2, settings.ring2]
        for values in itertools.product(*(bounds.values() for bounds in ranges)):
            teeth = search.ToothCounts(*values)
            if search.satisfies_center_distance(teeth, settings):
                exhaustive.add(teeth)
        self.assertEqual(enumerated, exhaustive)
        self.assertGreater(len(enumerated), 0)

    def test_csv_roundtrip_and_all_saved_rows_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.csv"
            counts = search.save_candidates(self.settings, path)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), counts["accepted"])
            self.assertGreater(len(rows), 0)
            for row in rows:
                teeth = search.ToothCounts(*(int(row[name]) for name in ("zs", "zp1", "zr1", "zp2", "zr2")))
                self.assertIsNone(search.first_failed_constraint(teeth, self.settings))
                self.assertEqual(Fraction(row["G_exact"]), search.speed_ratio(teeth))


if __name__ == "__main__":
    unittest.main()
