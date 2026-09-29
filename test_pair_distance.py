import test_pair_export
from PySide6.QtTest import QTest
from PySide6.QtCore import QPointF
import unittest


class PairDistanceTests(unittest.TestCase):
    setUpClass = classmethod(test_pair_export.PairExportTests.setUpClass.__func__)
    setUp = test_pair_export.PairExportTests.setUp
    tearDown = test_pair_export.PairExportTests.tearDown
    def test_parameter_edits_keep_view_and_animation_phase(self):
        page, view = self.page, self.page.canvas
        page._animation_step()
        phase = page.animation_angle
        view.scale(1.4, 1.4)
        view.centerOn(12, 5)
        transform = view.viewportTransform()
        for field, value in ((page.angle, 25.), (page.shift1, .2),
                             (page.shift2, .1), (page.backlash, .15),
                             (page.center_distance, 43.)):
            field.spin.setValue(value)
            QTest.qWait(20)
            self.assertTrue(page.valid)
            self.assertEqual(view.viewportTransform(), transform)
            self.assertEqual(page.animation_angle, phase)
            self.assertTrue(page.warning.isHidden())
        self.assertEqual(view._gear2_group.pos(), QPointF(43, 0))
        self.assertFalse(page.contact_supported())
        page.fit_view()
        self.assertAlmostEqual(view._fit_rect.right(), 43 + page.make_gears()[1].addendum_radius + page.module.value())

    def test_distance_auto_manual_and_reset(self):
        page = self.page
        page.module.spin.setValue(3.)
        self.assertEqual(page.center_distance.value(), 60.)
        page.center_distance.spin.setValue(63.)
        page.teeth2.spin.setValue(30)
        self.assertEqual(page.center_distance.value(), 63.)
        self.assertEqual(page.canvas._gear2_group.pos().x(), 63.)
        transform = page.canvas.viewportTransform()
        page.reset_center_distance()
        QTest.qWait(20)
        self.assertEqual(page.center_distance.value(), 75.)
        self.assertEqual(page.canvas.viewportTransform(), transform)
        self.assertTrue(page.contact_supported())
        page.teeth2.spin.setValue(20)
        self.assertEqual(page.center_distance.value(), 60.)


if __name__ == '__main__':
    unittest.main()
