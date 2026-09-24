"""数式・テーマアイコン・ネイティブリサイズ用の小さなUI部品。"""
import math

from PySide6.QtCore import Qt, QPointF, QSize
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QIcon, QPainter,
                          QPainterPath, QPalette, QPen, QPixmap, QTextDocument)
from PySide6.QtWidgets import QWidget


def theme_icon(dark, color):
    # Vector painting avoids missing moon/sun glyphs and scales at high DPI.
    pixmap = QPixmap(48, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color), 1.6, Qt.SolidLine, Qt.RoundCap))
    if dark:
        p.drawEllipse(QPointF(12, 12), 4, 4)
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(12 + 7 * math.cos(a), 12 + 7 * math.sin(a)),
                       QPointF(12 + 9 * math.cos(a), 12 + 9 * math.sin(a)))
    else:
        moon, cutout = QPainterPath(), QPainterPath()
        moon.addEllipse(QPointF(12, 12), 8, 8)
        cutout.addEllipse(QPointF(16, 8), 7, 7)
        p.drawPath(moon.subtracted(cutout))
    p.end()
    return QIcon(pixmap)


class FractionEquation(QWidget):
    """Align the relation's math axis with the fraction bar, not numerator."""
    def __init__(self, numerator, denominator, tail):
        super().__init__()
        self.math_font = QFont('Cambria Math')
        self.math_font.setPixelSize(17)
        self.tail = tail
        self.docs = []
        for text in (numerator, denominator):
            doc = QTextDocument(self)
            doc.setDocumentMargin(0)
            doc.setDefaultFont(self.math_font)
            doc.setHtml(text)
            doc.adjustSize()
            self.docs.append(doc)
        self.fraction_width = max(doc.size().width() for doc in self.docs) + 8
        self.axis_y = self.docs[0].size().height() + 4
        self.setMinimumHeight(self.sizeHint().height())
        self.setAccessibleName('太陽歯数とリング歯数の和を遊星個数で割った値が整数')

    def sizeHint(self):
        fm = QFontMetricsF(self.math_font)
        return QSize(math.ceil(self.fraction_width + fm.horizontalAdvance(self.tail) + 10),
                     math.ceil(sum(doc.size().height() for doc in self.docs) + 8))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = self.palette().color(QPalette.WindowText)
        p.setPen(QPen(color, 1))
        p.drawLine(QPointF(0, self.axis_y), QPointF(self.fraction_width, self.axis_y))
        for doc, top in zip(self.docs, (0, self.axis_y + 4)):
            p.save()
            p.translate((self.fraction_width - doc.size().width()) / 2, top)
            context = doc.documentLayout().PaintContext()
            context.palette.setColor(QPalette.Text, color)
            doc.documentLayout().draw(p, context)
            p.restore()
        p.setFont(self.math_font)
        fm = QFontMetricsF(self.math_font)
        p.drawText(QPointF(self.fraction_width + 7, self.axis_y + fm.xHeight() / 2), self.tail)
        p.end()


class ResizeHandle(QWidget):
    def __init__(self, parent, edges, cursor):
        super().__init__(parent)
        self.edges = edges
        self.setCursor(cursor)
        self.setStyleSheet('background: transparent;')

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.window().isMaximized():
            handle = self.window().windowHandle()
            if handle and handle.startSystemResize(self.edges):
                event.accept()
                return
        super().mousePressEvent(event)


def make_resize_handles(window):
    return [ResizeHandle(window, edges, cursor) for edges, cursor in (
        (Qt.LeftEdge, Qt.SizeHorCursor), (Qt.RightEdge, Qt.SizeHorCursor),
        (Qt.TopEdge, Qt.SizeVerCursor), (Qt.BottomEdge, Qt.SizeVerCursor),
        (Qt.TopEdge | Qt.LeftEdge, Qt.SizeFDiagCursor),
        (Qt.TopEdge | Qt.RightEdge, Qt.SizeBDiagCursor),
        (Qt.BottomEdge | Qt.LeftEdge, Qt.SizeBDiagCursor),
        (Qt.BottomEdge | Qt.RightEdge, Qt.SizeFDiagCursor),
    )]


def position_resize_handles(window, handles):
    w, h, b = window.width(), window.height(), 6
    rectangles = ((0, b, b, h-2*b), (w-b, b, b, h-2*b),
                  (b, 0, w-2*b, b), (b, h-b, w-2*b, b),
                  (0, 0, b, b), (w-b, 0, b, b),
                  (0, h-b, b, b), (w-b, h-b, b, b))
    for handle, rect in zip(handles, rectangles):
        handle.setGeometry(*rect)
        handle.setVisible(not window.isMaximized() and not window.isFullScreen())
        handle.raise_()
