"""転位の独立入力とON/OFFで計算が確実に切り替わることを検証。"""
import math
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from dataclasses import replace
from pathlib import Path
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtGui import QFontDatabase
from gear import (PlanetarySpec, GearSpec, planetary_constraints, gear_outline,
                  ring_gear_outline, working_angle, inv, center_tolerance)
from interference import interference_checks
from gui import MainWindow


class ShiftCalculationTests(unittest.TestCase):
    def test_khk_published_working_angles(self):
        # KHK dimension tables 4.3 and 4.6, independent published examples.
        aw = working_angle(20, 12+24, .6+.36)
        self.assertAlmostEqual(math.degrees(aw), 26.0886, places=4)
        a = 3*(12+24)/2 * math.cos(math.radians(20))/math.cos(aw)
        self.assertAlmostEqual(a, 56.4999, places=4)
        # The published x=.516 is rounded; allow the resulting 0.00034° error.
        self.assertAlmostEqual(math.degrees(working_angle(20, 24-16, .516)), 31.321258, delta=.0005)

    def test_zero_shifts_and_off_ignore_stored_inputs(self):
        base = PlanetarySpec(sun_teeth=18, planet_teeth=21)
        enabled = replace(base, shift_enabled=True)
        stored = replace(base, sun_shift=.7, planet_shift=-.4, ring_shift=.8)
        for s in (enabled, stored):
            self.assertEqual([ok for _, ok, _ in planetary_constraints(s)],
                             [ok for _, ok, _ in planetary_constraints(base)])
            self.assertEqual([c.ok for c in interference_checks(s)],
                             [c.ok for c in interference_checks(base)])
            self.assertAlmostEqual(s.ring_outer_radius, base.ring_outer_radius)

    def test_nonstandard_tooth_relation_uses_actual_centers(self):
        # Inverse equations from a chosen common center; old z relation fails.
        alpha = math.radians(20)
        a, m, zs, zp, zr, xs = 40.8, 2., 20, 20, 61, .2
        asp = math.acos(m*(zs+zp)*math.cos(alpha)/(2*a))
        apr = math.acos(m*(zr-zp)*math.cos(alpha)/(2*a))
        xp = (zs+zp)*(inv(asp)-inv(alpha))/(2*math.tan(alpha))-xs
        xr = xp+(zr-zp)*(inv(apr)-inv(alpha))/(2*math.tan(alpha))
        s = PlanetarySpec(module=m, sun_teeth=zs, planet_teeth=zp, ring_teeth=zr,
                          shift_enabled=True, sun_shift=xs, planet_shift=round(xp, 6), ring_shift=round(xr, 6))
        self.assertNotEqual(zr, zs+2*zp)
        self.assertTrue(planetary_constraints(s)[0][1])
        self.assertTrue(planetary_constraints(s)[1][1])
        self.assertLessEqual(abs(s.sun_planet_center_distance-s.planet_ring_center_distance), center_tolerance(s))
        self.assertFalse(planetary_constraints(replace(s, shift_enabled=False))[0][1])
        self.assertFalse(planetary_constraints(replace(s, ring_shift=xr+.001))[0][1])

    def test_shifted_pitch_thickness_and_radii(self):
        for internal, outline in ((False, gear_outline), (True, ring_gear_outline)):
            z, m, x = 60, 2., .2
            points = outline(GearSpec(m, z, 20, x))
            radii = [math.hypot(*p) for p in points]
            expected = (z+2*(x-1), z+2*(1.25+x)) if internal else (z-2*(1.25-x), z+2*(1+x))
            self.assertAlmostEqual(min(radii), expected[0])
            self.assertAlmostEqual(max(radii), expected[1])
            half = math.pi/(2*z) + (-1 if internal else 1)*2*x*math.tan(math.radians(20))/z
            pitch = [p for p in points if abs(math.hypot(*p)-z) < 1e-9]
            self.assertEqual(len(pitch), 2*z)
            for px, py in pitch:
                phase = (math.atan2(py, px)*z+math.pi)%(2*math.pi)-math.pi
                self.assertAlmostEqual(abs(phase), half*z)

    def test_undercut_and_internal_checks_use_shift(self):
        s = PlanetarySpec(sun_teeth=10, planet_teeth=35, ring_teeth=80)
        self.assertFalse(interference_checks(s)[3].ok)
        shifted = replace(s, shift_enabled=True, sun_shift=.5)
        self.assertTrue(interference_checks(shifted)[3].ok)
        self.assertIn('x</i>', interference_checks(shifted)[3].formula)
        for i in range(3):
            before = interference_checks(replace(s, shift_enabled=True))[i]
            after = interference_checks(replace(s, shift_enabled=True, ring_shift=.3))[i]
            self.assertNotEqual(before.detail, after.detail)
            self.assertIn('w,pr', after.formula)

    def test_adjacent_planets_use_shifted_tip_diameter(self):
        # The common center is unchanged while positive planet shift enlarges
        # its tip circle enough to collide with the adjacent planet.
        s = PlanetarySpec(sun_teeth=20, planet_teeth=20, ring_teeth=60, planet_count=5)
        self.assertTrue(planetary_constraints(s)[2][1])
        shifted = replace(s, shift_enabled=True, sun_shift=-1., planet_shift=1., ring_shift=1.)
        self.assertTrue(planetary_constraints(shifted)[0][1])
        self.assertFalse(planetary_constraints(shifted)[2][1])

    def test_invalid_angle_and_undefined_assembly(self):
        with self.assertRaises(ValueError):
            working_angle(20, 40, -2)
        s = PlanetarySpec(shift_enabled=True, sun_shift=-1, planet_shift=-1)
        self.assertIsNone(planetary_constraints(s)[0][1])
        self.assertIsNone(planetary_constraints(s)[2][1])
        with self.assertRaises(ValueError):
            gear_outline(GearSpec(2, 6, 20, -2))


class ShiftUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        for font in ('YuGothR.ttc', 'cambria.ttc', 'segoeui.ttf'):
            QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)

    def test_mode_switch_retains_inputs_and_changes_formulas_and_preview(self):
        window = MainWindow()
        page = window.planetary_page
        window.tabs.setCurrentWidget(page)
        window.show()
        self.app.processEvents()
        page.sun_teeth.spin.setValue(18)
        page.planet_teeth.spin.setValue(24)
        page.ring_teeth.spin.setValue(66)
        self.assertIsNotNone(page.preview.points)
        self.assertFalse(page.shift_fields.isVisible())
        page.shift_enabled.setChecked(True)
        page.sun_shift.spin.setValue(.2)
        page.planet_shift.spin.setValue(-.1)
        page.ring_shift.spin.setValue(0.)
        self.assertTrue(page.shift_fields.isVisible())
        self.assertFalse(page.fit_planet_button.isEnabled())
        page.fit_planet()
        self.assertEqual(page.planet_teeth.value(), 24)
        self.assertIsNotNone(page.preview.points, page.preview.issues)
        self.assertEqual([n for n, _, _ in planetary_constraints(page.spec)],
                         ['中心距離条件', '拘束かみ合い条件', '外径干渉条件'])
        self.app.processEvents()
        groups = [w.text() for w in page.constraints.findChildren(QLabel, 'ConstraintGroup') if not w.isHidden()]
        self.assertEqual(groups, ['遊星歯車の成立条件', '内歯車の制約（遊星–リング）', '外歯車の制約'])
        body = page.constraints.row_bodies['中心距離条件']
        self.assertIn('α<sub>w,sp', body.findChildren(QLabel)[0].text())
        self.assertGreater(page.shift_enabled.y(), page.fit_planet_button.y())
        page.ring_shift.spin.setValue(.1)
        self.assertIsNone(page.preview.points)
        self.assertIsNotNone(page.preview.ring_polygon)
        self.assertIsNotNone(page.preview.sun_polygon)
        page.shift_enabled.setChecked(False)
        self.assertTrue(page.fit_planet_button.isEnabled())
        self.assertIsNotNone(page.preview.points)
        self.assertEqual(page.ring_shift.value(), .1)
        self.assertNotIn('α<sub>w,sp', page.constraints.row_bodies['中心距離条件'].findChildren(QLabel)[0].text())
        page.shift_enabled.setChecked(True)
        self.assertIsNone(page.preview.points)
        page.ring_shift.spin.setValue(0.)
        self.app.processEvents()
        Path('artifacts').mkdir(exist_ok=True)
        window.grab().save('artifacts/shift-light.png')
        window.toggle_theme()
        self.app.processEvents()
        window.grab().save('artifacts/shift-dark.png')
        page.sun_shift.spin.setValue(-1.)
        page.planet_shift.spin.setValue(-1.)
        self.assertIsNone(page.preview.points)
        self.assertIn('定義できません', page.geometry_note.text())
        window.close()


if __name__ == '__main__':
    unittest.main()
