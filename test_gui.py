import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import patch, Mock
from time import perf_counter
from PySide6.QtCore import Qt, QPoint
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
        window.tabs.setCurrentWidget(window.planetary_page)
        window.show()
        self.app.processEvents()
        self.assertFalse(window.dark)
        self.assertTrue(window.windowFlags() & Qt.FramelessWindowHint)
        self.assertFalse(window.findChildren(QSlider))
        self.assertIsNone(window.planetary_page.preview.points)
        self.assertTrue(window.planetary_page.preview.issues)
        self.assertIn('4.0000 : 1', window.planetary_page.ratio_value.text())
        self.assertIn('参考値', window.planetary_page.ratio_value.text())
        self.assertIsNotNone(window.planetary_page.preview.ring_polygon)
        self.assertIsNotNone(window.planetary_page.preview.sun_polygon)
        self.assertEqual(window.planetary_page.preview.planet_polygons, [])
        self.assertEqual(window.theme_button.text(), '')
        self.assertFalse(window.theme_button.icon().isNull())
        window.planetary_page.sun_teeth.spin.setValue(24)
        window.planetary_page.planet_teeth.spin.setValue(18)
        # Formerly accepted: pitch circles fit but internal involute interference exists.
        self.assertIsNone(window.planetary_page.preview.points)
        self.assertTrue(any('インボリュート干渉' in issue for issue in window.planetary_page.preview.issues))
        window.planetary_page.sun_teeth.spin.setValue(18)
        window.planetary_page.planet_teeth.spin.setValue(21)
        self.assertIsNotNone(window.planetary_page.preview.points)
        self.assertFalse(window.planetary_page.preview.issues)
        self.assertIn('4.3333 : 1', window.planetary_page.ratio_value.text())
        self.assertNotIn('参考値', window.planetary_page.ratio_value.text())
        window.planetary_page.ring_teeth.spin.stepUp()
        self.assertEqual(window.planetary_page.spec.ring_teeth, 61)
        self.assertIsNone(window.planetary_page.preview.points)
        window.planetary_page.ring_teeth.spin.stepDown()
        self.assertIsNotNone(window.planetary_page.preview.points)
        self.app.processEvents()
        os.makedirs('artifacts', exist_ok=True)
        window.grab().save('artifacts/preview-light.png')
        scroll = window.planetary_page.constraint_scroll
        self.assertGreater(scroll.x(), window.planetary_page.parameter_scroll.x())
        self.assertEqual(scroll.verticalScrollBar().maximum(), 0)
        window.planetary_page.constraints.toggle_details(True)
        self.app.processEvents()
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        self.app.processEvents()
        window.grab().save('artifacts/constraints.png')
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum() // 2)
        self.app.processEvents()
        window.grab().save('artifacts/interference-constraints.png')
        scroll.verticalScrollBar().setValue(0)
        window.toggle_theme()
        self.assertTrue(window.planetary_page.preview.dark)
        self.app.processEvents()
        window.grab().save('artifacts/preview-dark.png')
        window.planetary_page.ring_teeth.spin.stepUp()
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
        window.tabs.setCurrentWidget(window.planetary_page)
        window.planetary_page.sun_teeth.spin.setValue(24)
        window.planetary_page.fit_planet_button.click()
        self.assertEqual(window.planetary_page.planet_teeth.value(), 18)
        self.assertEqual(window.planetary_page.ring_teeth.value(), 60)
        self.assertEqual(window.planetary_page.sun_teeth.value(), 24)
        window.planetary_page.ring_teeth.spin.setValue(61)
        window.planetary_page.fit_planet_button.click()
        self.assertEqual(window.planetary_page.planet_teeth.value(), 18)
        self.assertIn('整数', window.planetary_page.fit_feedback.text())
        window.planetary_page.ring_teeth.spin.setValue(300)
        window.planetary_page.fit_planet_button.click()
        self.assertEqual(window.planetary_page.planet_teeth.value(), 18)
        self.assertIn('入力範囲', window.planetary_page.fit_feedback.text())
        window.planetary_page.reference_diameter.spin.setValue(180)
        window.planetary_page.module.spin.setValue(3)
        self.assertEqual(window.planetary_page.preview.reference_diameter, 180)
        self.assertIn('超過', window.planetary_page.envelope_status.text())
        self.assertAlmostEqual(2 * window.planetary_page.spec.ring_outer_radius, 914.5)
        with patch('planetary_page.ring_gear_outline', side_effect=AssertionError('不要な再計算')):
            window.planetary_page.reference_diameter.spin.setValue(1000)
            window.planetary_page.reference_visible.setChecked(False)
        self.assertFalse(window.planetary_page.preview.show_reference)
        self.assertNotIn('超過', window.planetary_page.envelope_status.text())
        window.planetary_page.ring_teeth.spin.setValue(6)
        self.assertIsNone(window.planetary_page.preview.ring_polygon)
        self.assertIsNotNone(window.planetary_page.preview.sun_polygon)
        self.assertTrue(any('リング歯形' in reason for reason in window.planetary_page.preview.issues))
        window.close()

    def test_constraint_disclosure_survives_edits_and_theme(self):
        window = MainWindow()
        window.tabs.setCurrentWidget(window.planetary_page)
        self.assertEqual([window.tabs.tabText(i) for i in range(2)], ['単純歯車対', '遊星歯車'])
        page = window.planetary_page
        window.show()
        panel = page.constraints
        name = '中心距離条件'
        panel.row_buttons[name].click()
        opened = panel.row_buttons[name].isChecked()
        page.module.spin.setValue(3)
        window.toggle_theme()
        self.app.processEvents()
        self.assertEqual(panel.row_buttons[name].isChecked(), opened)
        self.assertEqual(panel.row_bodies[name].isHidden(), not opened)
        self.assertIn('適合', panel.row_buttons[name].accessibleName())
        page.ring_teeth.spin.setValue(61)
        self.assertIn('不適合', panel.row_buttons[name].accessibleName())
        panel.row_buttons[name].setChecked(True)
        self.assertFalse(panel.row_bodies[name].isHidden())
        window.resize(1200, 680)
        self.app.processEvents()
        self.assertGreaterEqual(page.preview_scroll.widget().height(),
                                page.preview_scroll.widget().minimumSizeHint().height())
        window.close()

    def test_resize_reuses_geometry_and_native_handles(self):
        window = MainWindow()
        window.tabs.setCurrentWidget(window.planetary_page)
        window.planetary_page.sun_teeth.spin.setValue(100)
        window.planetary_page.planet_teeth.spin.setValue(100)
        window.planetary_page.ring_teeth.spin.setValue(300)
        window.planetary_page.planet_count.spin.setValue(4)
        window.show()
        self.app.processEvents()
        self.assertIsNotNone(window.planetary_page.preview.points)
        layer = window.planetary_page.preview._shape_layer
        self.assertIsNotNone(layer)
        with patch('planetary_page.rotate', side_effect=AssertionError('再描画中の頂点再計算')):
            with patch('planetary_page.gear_outline', side_effect=AssertionError('再描画中の歯形再計算')):
                start = perf_counter()
                for i in range(24):
                    window.resize(1050 + i * 10, 700 + i * 5)
                    self.app.processEvents()
                    window.planetary_page.preview.repaint()
                print(f'\nResize + repaint, 300-tooth ring: {(perf_counter()-start)*1000/24:.2f} ms/frame')
        self.assertIs(window.planetary_page.preview._shape_layer, layer)
        self.assertFalse(window.mask().contains(QPoint(0, 0)))
        self.assertTrue(window.mask().contains(window.rect().center()))
        native = Mock()
        native.startSystemResize.return_value = True
        with patch.object(window, 'windowHandle', return_value=native):
            for handle in window.resize_handles:
                QTest.mouseClick(handle, Qt.LeftButton)
                native.startSystemResize.assert_called_with(handle.edges)
        window.toggle_maximized()
        self.app.processEvents()
        self.assertTrue(all(not handle.isVisible() for handle in window.resize_handles))
        self.assertTrue(window.mask().isEmpty())
        window.toggle_maximized()
        self.app.processEvents()
        self.assertTrue(all(handle.isVisible() for handle in window.resize_handles))
        self.assertFalse(window.mask().contains(QPoint(0, 0)))
        window.planetary_page.ring_teeth.spin.setValue(299)
        window.resize(1020, 680)
        self.app.processEvents()
        window.grab().save('artifacts/preview-small.png')
        window.close()


if __name__ == '__main__':
    unittest.main()
