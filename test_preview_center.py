import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from pathlib import Path
from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from gui import MainWindow


class PreviewCenterTests(unittest.TestCase):
    def test_center_follows_viewport_until_manual_navigation(self):
        app = QApplication.instance() or QApplication([])
        app.setStyle('Fusion')
        for font in ('YuGothR.ttc', 'cambria.ttc', 'segoeui.ttf'):
            QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
        window = MainWindow()
        self.addCleanup(window.close)
        page = window.pair_page
        window.tabs.setCurrentWidget(page)
        window.show()
        for size in ((1600, 980), (1200, 680), (1450, 900)):
            window.resize(*size)
            for teeth in (20, 37):
                page.teeth2.spin.setValue(teeth)
                QTest.qWait(20)
                app.processEvents()
                g1, g2 = page.make_gears()
                # Center of the two physical tip-circle envelopes, independent
                # of the view's fit rectangle and auxiliary graphics.
                center = QPointF((-g1.addendum_radius + g1.pitch_radius + g2.pitch_radius + g2.addendum_radius)/2, 0)
                pixel = page.canvas.mapFromScene(center)
                target = page.canvas.viewport().rect().center()
                self.assertLessEqual(abs(pixel.x()-target.x()), 2)
                self.assertLessEqual(abs(pixel.y()-target.y()), 2)
                outer = page.preview_scroll.viewport()
                top = page.canvas.mapTo(outer, QPoint(0, 0))
                bottom = page.canvas.mapTo(outer, QPoint(0, page.canvas.height()-1))
                self.assertGreaterEqual(top.y(), 0)
                self.assertLess(bottom.y(), outer.height())
        page.canvas._stop_auto_fit()
        page.canvas.scale(1.5, 1.5)
        scale = page.canvas.transform().m11()
        window.resize(1300, 750)
        QTest.qWait(20)
        self.assertAlmostEqual(page.canvas.transform().m11(), scale)
        page.fit_button.click()
        QTest.qWait(20)
        self.assertTrue(page.canvas._auto_fit)
        Path('artifacts').mkdir(exist_ok=True)
        window.grab().save('artifacts/pair-centered.png')


if __name__ == '__main__':
    unittest.main()
