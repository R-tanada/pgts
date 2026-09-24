import math
import unittest

from gear import (GearSpec, PlanetarySpec, gear_outline, ring_gear_outline,
                  planetary_constraints, planetary_positions, ring_rotation)


class GeometryTests(unittest.TestCase):
    def test_ring_fixed_ratio(self):
        for sun, ring, expected in ((20, 60, 4), (40, 80, 3), (16, 80, 6)):
            self.assertEqual(PlanetarySpec(sun_teeth=sun, ring_teeth=ring).reduction_ratio, expected)

    def test_outline_order_and_pitch_thickness(self):
        # A positive radius and monotone polar angle exclude crossings.
        for internal, generator in ((False, gear_outline), (True, ring_gear_outline)):
            for z in (18, 20, 21, 40, 60, 100, 300):
                for angle in (10, 20, 35):
                    with self.subTest(internal=internal, z=z, angle=angle):
                        try:
                            points = generator(GearSpec(2, z, angle))
                        except ValueError:
                            continue  # unsupported pointed/overlapping tooth envelope
                        radii = [math.hypot(*p) for p in points]
                        self.assertAlmostEqual(min(radii), z - (2 if internal else 2.5))
                        self.assertAlmostEqual(max(radii), z + (2.5 if internal else 2))
                        travel = 0
                        for a, b in zip(points, points[1:] + points[:1]):
                            delta = math.atan2(a[0]*b[1] - a[1]*b[0], a[0]*b[0] + a[1]*b[1])
                            self.assertGreaterEqual(delta, -1e-12)
                            travel += delta
                        self.assertAlmostEqual(travel, 2 * math.pi)
                        pitch_points = [p for p in points if abs(math.hypot(*p)-z) < 1e-9]
                        self.assertEqual(len(pitch_points), 2*z)
                        for p in pitch_points:
                            phase = (math.atan2(p[1], p[0]) * z + math.pi) % (2*math.pi)-math.pi
                            self.assertAlmostEqual(abs(phase), math.pi/2)

    def test_assembly_and_independent_ring(self):
        self.assertFalse(all(ok for _, ok, _ in planetary_constraints(PlanetarySpec())))
        valid = PlanetarySpec(sun_teeth=24, planet_teeth=18, ring_teeth=60)
        self.assertTrue(all(ok for _, ok, _ in planetary_constraints(valid)))
        valid.ring_teeth = 61
        self.assertFalse(planetary_constraints(valid)[0][1])
        crowded = PlanetarySpec(sun_teeth=20, planet_teeth=20, ring_teeth=60, planet_count=8)
        self.assertFalse(planetary_constraints(crowded)[-1][1])

    def test_mesh_phase_even_and_odd_planets(self):
        for zp, zr in ((18, 60), (21, 66)):
            s = PlanetarySpec(sun_teeth=24, planet_teeth=zp, ring_teeth=zr)
            for x, y, rot in planetary_positions(s):
                a = math.atan2(y, x)
                sun_phase = s.sun_teeth * a
                planet_in = zp * (a + math.pi - rot)
                planet_out = zp * (a - rot)
                ring_phase = zr * (a - ring_rotation(s))
                self.assertAlmostEqual(math.cos(sun_phase + planet_in), -1)
                self.assertAlmostEqual(math.cos(ring_phase - planet_out), -1)

    def test_invalid_shape_rejected(self):
        for s in (GearSpec(0, 20), GearSpec(2, 0), GearSpec(2, 20, 0), GearSpec(2, 20, 20, 1)):
            with self.assertRaises(ValueError):
                gear_outline(s)


if __name__ == '__main__':
    unittest.main()
