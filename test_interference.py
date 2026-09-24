import math
import unittest

from gear import PlanetarySpec, planetary_positions, planetary_constraints
from interference import interference_checks, undercut_checks


class InterferenceTests(unittest.TestCase):
    def test_khk_catalog_boundary_values(self):
        # KHK internal-tech.pdf p208: allowable mating pinion tooth counts.
        # Check both sides of each published boundary; no values are fitted.
        for ring, lower, trochoid_upper, trimming_upper in (
                (60, 21, 51, 43), (80, 20, 72, 64), (100, 19, 92, 84),
                (120, 19, 112, 104), (160, 19, 152, 144), (200, 18, 192, 184)):
            for key, pairs in (
                ('involute', ((lower-1, False), (lower, True))),
                ('trochoid', ((trochoid_upper, True), (trochoid_upper+1, False))),
                ('trimming', ((trimming_upper, True), (trimming_upper+1, False)))):
                for planet, expected in pairs:
                    with self.subTest(ring=ring, planet=planet, check=key):
                        checks = {c.key: c for c in interference_checks(
                            PlanetarySpec(ring_teeth=ring, planet_teeth=planet))}
                        self.assertIs(checks[key].ok, expected)

    def test_scale_invariance_and_pressure_angle(self):
        for angle in (10, 20, 35):
            results = []
            for module in (.5, 2, 10):
                results.append([(c.key, c.ok) for c in interference_checks(
                    PlanetarySpec(module=module, pressure_angle_deg=angle))])
            self.assertEqual(results[0], results[1])
            self.assertEqual(results[1], results[2])
        self.assertFalse(interference_checks(PlanetarySpec())[0].ok)
        self.assertTrue(interference_checks(PlanetarySpec(pressure_angle_deg=35))[0].ok)

    def test_undercut_strict_rack_limit(self):
        for angle in (10, 20, 35):
            limit = math.ceil(2 / math.sin(math.radians(angle))**2)
            s = PlanetarySpec(sun_teeth=limit-1, planet_teeth=limit, pressure_angle_deg=angle)
            checks = undercut_checks(s)
            self.assertFalse(checks[0].ok)
            self.assertTrue(checks[1].ok)
            self.assertFalse(checks[0].blocks_assembly)

    def test_out_of_domain_is_not_a_pass(self):
        for s in (PlanetarySpec(ring_teeth=30), PlanetarySpec(ring_teeth=20),
                  PlanetarySpec(pressure_angle_deg=0), PlanetarySpec(module=0)):
            self.assertTrue(all(c.ok is None for c in interference_checks(s)[:3]))
        trim = interference_checks(PlanetarySpec(planet_teeth=44))[2]
        self.assertFalse(trim.ok)
        self.assertFalse(trim.blocks_assembly)
        self.assertIn('軸方向', trim.detail)

    def test_center_distance_sum_and_difference_are_equivalent(self):
        for zs, zp in ((20, 20), (18, 21), (24, 18), (40, 20)):
            s = PlanetarySpec(sun_teeth=zs, planet_teeth=zp, ring_teeth=zs+2*zp)
            self.assertAlmostEqual(s.ring_sun_center_distance, s.sun_planet_center_distance)
            self.assertAlmostEqual(s.ring_sun_center_distance, s.planet_ring_center_distance)
            for x, y, _ in planetary_positions(s):
                actual = math.hypot(x, y)
                self.assertAlmostEqual(actual, s.sun_pitch_radius+s.planet_pitch_radius)
                self.assertAlmostEqual(actual+s.planet_pitch_radius, s.ring_pitch_radius)
            names = [name for name, _, _ in planetary_constraints(s)]
            self.assertNotIn('同心条件', names)
            self.assertNotIn('入力範囲', names)


if __name__ == '__main__':
    unittest.main()
