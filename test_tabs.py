import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QImage
from gui import MainWindow


class TabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        for name in ('YuGothR.ttc', 'cambria.ttc', 'segoeui.ttf'):
            QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + name)

    def setUp(self):
        self.window = MainWindow()
        self.assertIs(self.window.tabs.currentWidget(), self.window.pair_page)
        self.window.show()
        self.window.tabs.setCurrentWidget(self.window.pair_page)
        self.app.processEvents()
        self.page = self.window.pair_page

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_state_theme_animation_and_invalid_recovery(self):
        page = self.page
        self.assertEqual(self.window.tabs.count(), 2)
        self.assertTrue(page.valid)
        page.teeth2.spin.setValue(37)
        page.toggle_animation()
        for _ in range(365):
            page._animation_step()
        angle = page.canvas._gear2_group.rotation()
        page.checks['base_circle'].setChecked(True)
        self.assertAlmostEqual(page.canvas._gear2_group.rotation(), angle)
        page.canvas.update_animation(page.animation_angle, False)
        self.assertAlmostEqual(page.canvas._gear2_group.rotation(), angle)
        self.window.tabs.setCurrentWidget(self.window.planetary_page)
        self.assertFalse(page.timer.isActive())
        self.window.planetary_page.sun_teeth.spin.setValue(18)
        self.window.toggle_theme()
        self.assertTrue(page.dark)
        self.window.tabs.setCurrentWidget(self.window.pair_page)
        self.assertEqual(page.teeth2.value(), 37)
        self.assertEqual(self.window.planetary_page.sun_teeth.value(), 18)
        page.teeth1.spin.setValue(3)
        page.shift1.spin.setValue(-1.)
        self.assertFalse(page.valid)
        self.assertFalse(page.timer.isActive())
        self.assertFalse(page.save_button.isEnabled())
        self.assertIsNone(page.canvas._gear1_group)
        page.shift1.spin.setValue(0.)
        page.teeth1.spin.setValue(20)
        self.assertTrue(page.valid)
        page.root_shape.setCurrentIndex(1)
        self.assertTrue(page.valid, page.warning.text())
        self.window.toggle_theme()
        self.app.processEvents()
        Path('artifacts').mkdir(exist_ok=True)
        self.window.grab().save('artifacts/pair-light.png')
        self.window.toggle_theme()
        self.app.processEvents()
        self.window.grab().save('artifacts/pair-dark.png')
        page.toggle_animation()
        self.window.close()
        self.assertFalse(page.timer.isActive())

    def test_export_and_display_do_not_reset_rotation(self):
        page = self.page
        page.toggle_animation()
        page._animation_step()
        rotation = page.canvas._gear1_group.rotation()
        models = page.make_gears()
        with patch.object(models[0], 'profile', side_effect=AssertionError('不要な再計算')):
            page.highlight.setCurrentIndex(1)
            self.window.toggle_theme()
        self.assertAlmostEqual(rotation, page.canvas._gear1_group.rotation())
        with tempfile.TemporaryDirectory() as folder:
            for suffix in ('png', 'svg'):
                filename = str(Path(folder) / ('pair.' + suffix))
                with patch('simple_gear.page.QFileDialog.getSaveFileName', return_value=(filename, suffix)):
                    page.save_image()
                self.assertGreater(Path(filename).stat().st_size, 100)
                self.assertAlmostEqual(rotation, page.canvas._gear1_group.rotation())
                if suffix == 'png':
                    self.assertFalse(QImage(filename).isNull())
                else:
                    size = page.canvas.viewport().size()
                    self.assertIn(f'viewBox="0 0 {size.width()} {size.height()}"', Path(filename).read_text())


if __name__ == '__main__':
    unittest.main()
