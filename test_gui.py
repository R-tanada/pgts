import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import patch, Mock
from time import perf_counter
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import QApplication, QSlider, QScrollArea
from PySide6.QtTest import QTest
from gui import MainWindow


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        # Qt's offscreen Windows backend does not discover system fonts.
        for name in ('YuGothR.ttc', 'cambria.ttc', 'segoeui.ttf'):
            QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + name)
        cls.app.setFont(QFont('Yu Gothic'))

    def test_input_preview_and_theme(self):
        window = MainWindow()
        window.show()
        self.app.processEvents()
        self.assertFalse(window.dark)
        self.assertTrue(window.windowFlags() & Qt.FramelessWindowHint)
        self.assertFalse(window.findChildren(QSlider))
        self.assertIsNone(window.preview.points)
        self.assertTrue(window.preview.issues)
        self.assertIn('4.0000 : 1', window.ratio_value.text())
        self.assertIn('参考値', window.ratio_value.text())
        self.assertIsNotNone(window.preview.ring_polygon)
        self.assertIsNotNone(window.preview.sun_polygon)
        self.assertEqual(window.preview.planet_polygons, [])
        self.assertEqual(window.theme_button.text(), '')
        self.assertFalse(window.theme_button.icon().isNull())
        window.sun_teeth.spin.setValue(24)
        window.planet_teeth.spin.setValue(18)
        # Formerly accepted: pitch circles fit but internal involute interference exists.
        self.assertIsNone(window.preview.points)
        self.assertTrue(any('インボリュート干渉' in issue for issue in window.preview.issues))
        window.sun_teeth.spin.setValue(18)
        window.planet_teeth.spin.setValue(21)
        self.assertIsNotNone(window.preview.points)
        self.assertFalse(window.preview.issues)
        self.assertIn('4.3333 : 1', window.ratio_value.text())
        self.assertNotIn('参考値', window.ratio_value.text())
        window.ring_teeth.spin.stepUp()
        self.assertEqual(window.spec.ring_teeth, 61)
        self.assertIsNone(window.preview.points)
        window.ring_teeth.spin.stepDown()
        self.assertIsNotNone(window.preview.points)
        self.app.processEvents()
        os.makedirs('artifacts', exist_ok=True)
        window.grab().save('artifacts/preview-light.png')
        scroll = window.constraint_scroll
        self.assertGreater(scroll.x(), window.parameter_scroll.x())
        self.assertEqual(scroll.verticalScrollBar().maximum(), 0)
        window.constraints.toggle_details(True)
        self.app.processEvents()
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        self.app.processEvents()
        window.grab().save('artifacts/constraints.png')
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum() // 2)
        self.app.processEvents()
        window.grab().save('artifacts/interference-constraints.png')
        scroll.verticalScrollBar().setValue(0)
        window.toggle_theme()
        self.assertTrue(window.preview.dark)
        self.app.processEvents()
        window.grab().save('artifacts/preview-dark.png')
        window.ring_teeth.spin.stepUp()
        window.toggle_theme()
        self.app.processEvents()
        window.grab().save('artifacts/preview-invalid.png')
        window.toggle_maximized()
        self.assertTrue(window.isMaximized())
        window.toggle_maximized()
        self.assertFalse(window.isMaximized())
        window.close()

    def test_ring_based_fit_and_reference(self):
        window = MainWindow()
        window.sun_teeth.spin.setValue(24)
        window.fit_planet_button.click()
        self.assertEqual(window.planet_teeth.value(), 18)
        self.assertEqual(window.ring_teeth.value(), 60)
        self.assertEqual(window.sun_teeth.value(), 24)
        window.ring_teeth.spin.setValue(61)
        window.fit_planet_button.click()
        self.assertEqual(window.planet_teeth.value(), 18)
        self.assertIn('整数', window.fit_feedback.text())
        window.ring_teeth.spin.setValue(300)
        window.fit_planet_button.click()
        self.assertEqual(window.planet_teeth.value(), 18)
        self.assertIn('入力範囲', window.fit_feedback.text())
        window.reference_diameter.spin.setValue(180)
        window.module.spin.setValue(3)
        self.assertEqual(window.preview.reference_diameter, 180)
        self.assertIn('超過', window.envelope_status.text())
        self.assertAlmostEqual(2 * window.spec.ring_outer_radius, 914.5)
        with patch('gui.ring_gear_outline', side_effect=AssertionError('不要な再計算')):
            window.reference_diameter.spin.setValue(1000)
            window.reference_visible.setChecked(False)
        self.assertFalse(window.preview.show_reference)
        self.assertNotIn('超過', window.envelope_status.text())
        window.ring_teeth.spin.setValue(6)
        self.assertIsNone(window.preview.ring_polygon)
        self.assertIsNotNone(window.preview.sun_polygon)
        self.assertTrue(any('リング歯形' in reason for reason in window.preview.issues))
        window.close()

    def test_resize_reuses_geometry_and_native_handles(self):
        window = MainWindow()
        window.sun_teeth.spin.setValue(100)
        window.planet_teeth.spin.setValue(100)
        window.ring_teeth.spin.setValue(300)
        window.planet_count.spin.setValue(4)
        window.show()
        self.app.processEvents()
        self.assertIsNotNone(window.preview.points)
        layer = window.preview._shape_layer
        self.assertIsNotNone(layer)
        with patch('gui.rotate', side_effect=AssertionError('再描画中の頂点再計算')):
            with patch('gui.gear_outline', side_effect=AssertionError('再描画中の歯形再計算')):
                start = perf_counter()
                for i in range(24):
                    window.resize(1050 + i * 10, 700 + i * 5)
                    self.app.processEvents()
                    window.preview.repaint()
                print(f'\nResize + repaint, 300-tooth ring: {(perf_counter()-start)*1000/24:.2f} ms/frame')
        self.assertIs(window.preview._shape_layer, layer)
        native = Mock()
        native.startSystemResize.return_value = True
        with patch.object(window, 'windowHandle', return_value=native):
            for handle in window.resize_handles:
                QTest.mouseClick(handle, Qt.LeftButton)
                native.startSystemResize.assert_called_with(handle.edges)
        window.toggle_maximized()
        self.app.processEvents()
        self.assertTrue(all(not handle.isVisible() for handle in window.resize_handles))
        window.toggle_maximized()
        self.app.processEvents()
        self.assertTrue(all(handle.isVisible() for handle in window.resize_handles))
        window.ring_teeth.spin.setValue(299)
        window.resize(1020, 680)
        self.app.processEvents()
        window.grab().save('artifacts/preview-small.png')
        window.close()


if __name__ == '__main__':
    unittest.main()
