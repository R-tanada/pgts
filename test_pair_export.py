import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QFontDatabase
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QGraphicsPathItem, QGraphicsEllipseItem
from PySide6.QtTest import QTest
from gui import MainWindow


def rgba(image):
    image = image.convertToFormat(QImage.Format_RGBA8888)
    return np.frombuffer(image.bits(), dtype=np.uint8).reshape(image.height(), image.width(), 4).copy()


class PairExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        for font in ('YuGothR.ttc', 'cambria.ttc', 'segoeui.ttf'):
            QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)

    def setUp(self):
        self.window = MainWindow()
        self.page = self.window.pair_page
        self.window.tabs.setCurrentWidget(self.page)
        self.window.resize(1300, 800)
        self.window.show()
        QTest.qWait(20)

    def tearDown(self):
        self.window.close()

    def test_module_keeps_position_scale_and_angle_but_teeth_refit(self):
        page, view = self.page, self.page.canvas
        page.toggle_animation()
        page._animation_step()
        page.pause_animation()
        rotation = view._gear1_group.rotation()
        transform = view.viewportTransform()
        old_width = view._gear1_group.childItems()[0].path().boundingRect().width()
        page.module.spin.setValue(3.)
        QTest.qWait(20)
        self.assertEqual(view.viewportTransform(), transform)
        self.assertAlmostEqual(view._gear1_group.rotation(), rotation)
        self.assertAlmostEqual(view._gear1_group.childItems()[0].path().boundingRect().width()/old_width, 1.5, places=6)
        self.assertFalse(view._auto_fit)
        # Large reductions must not clamp a previously panned scene position.
        view.centerOn(20000, 30000)
        transform = view.viewportTransform()
        page.module.spin.setValue(.1)
        QTest.qWait(20)
        self.assertEqual(view.viewportTransform(), transform)
        page.teeth2.spin.setValue(37)
        QTest.qWait(20)
        self.assertTrue(view._auto_fit)
        self.assertNotEqual(view.viewportTransform(), transform)

    def test_png_svg_match_current_cropped_view_in_black(self):
        page, view = self.page, self.page.canvas
        page.checks['base_circle'].setChecked(True)
        page.checks['pitch_point'].setChecked(True)
        page.checks['action_line'].setChecked(True)
        page.highlight.setCurrentText('基準円')
        page.toggle_animation()
        page._animation_step()
        page.pause_animation()
        view._stop_auto_fit()
        view.scale(1.8, 1.8)
        view.centerOn(14, 5)
        with tempfile.TemporaryDirectory() as folder:
            for dark in (False, True):
                if self.window.dark != dark:
                    self.window.toggle_theme()
                QTest.qWait(20)
                transform = view.viewportTransform()
                rotations = view._gear1_group.rotation(), view._gear2_group.rotation()
                items = [item for item in view.scene.items() if isinstance(item, (QGraphicsPathItem, QGraphicsEllipseItem))]
                pens = [item.pen() for item in items]
                for suffix in ('png', 'svg'):
                    filename = str(Path(folder)/('preview.'+suffix))
                    with patch('simple_gear.page.QFileDialog.getSaveFileName', return_value=(filename, suffix)):
                        page.save_image()
                png = QImage(str(Path(folder)/'preview.png'))
                self.assertEqual(png.size(), view.viewport().size())
                pixels = rgba(png)
                self.assertTrue(np.all(pixels[pixels[:,:,3]>0, :3] == 0))
                self.assertGreater(np.count_nonzero(pixels[:,:,3]), 100)
                svg_path = Path(folder)/'preview.svg'
                svg_text = svg_path.read_text(encoding='utf-8')
                self.assertNotIn('<image', svg_text)
                renderer = QSvgRenderer(str(svg_path))
                self.assertTrue(renderer.isValid())
                self.assertEqual(renderer.defaultSize(), png.size(), svg_text[:800])
                svg_image = QImage(png.size(), QImage.Format_ARGB32)
                svg_image.fill(Qt.transparent)
                painter = QPainter(svg_image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                renderer.render(painter)
                painter.end()
                svg_pixels = rgba(svg_image)
                self.assertTrue(np.all(svg_pixels[svg_pixels[:,:,3]>0, :3] == 0))
                Path('artifacts').mkdir(exist_ok=True)
                png.save('artifacts/export-viewport-black.png')
                svg_image.save('artifacts/export-svg-rendered.png')
                for label, source in (('png', png), ('svg', svg_image)):
                    sample = QImage(source.size(), QImage.Format_RGB32)
                    sample.fill(Qt.white)
                    sample_painter = QPainter(sample)
                    sample_painter.drawImage(0, 0, source)
                    sample_painter.end()
                    sample.save(f'artifacts/export-{label}-white-preview.png')
                a, b = pixels[:,:,3]>30, svg_pixels[:,:,3]>30
                similarity = np.count_nonzero(a & b) / np.count_nonzero(a | b)
                # SVG decimal rounding and rasterization can shift edge coverage
                # by one pixel; require matching geometry within that tolerance.
                self.assertGreater(similarity, .94, f'PNG/SVG coverage mismatch: {similarity}')
                def expanded(mask):
                    padded = np.pad(mask, 1)
                    return np.logical_or.reduce([padded[y:y+mask.shape[0], x:x+mask.shape[1]]
                                                 for y in range(3) for x in range(3)])
                self.assertFalse(np.any(a & ~expanded(b)))
                self.assertFalse(np.any(b & ~expanded(a)))
                self.assertLess(abs(float(pixels[:,:,3].sum()) / float(svg_pixels[:,:,3].sum()) - 1), .02)
                self.assertEqual(transform, view.viewportTransform())
                self.assertEqual(rotations, (view._gear1_group.rotation(), view._gear2_group.rotation()))
                self.assertEqual(pens, [item.pen() for item in items])


if __name__ == '__main__':
    unittest.main()
