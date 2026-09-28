"""両タブで共用する配色と数値入力カード。"""
from PySide6.QtCore import Signal
from PySide6.QtGui import QPalette, QPainter
from ui_widgets import disclosure_icon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QDoubleSpinBox, QSpinBox, QAbstractSpinBox, QPushButton, QStyle

DARK = dict(bg='#0E1117', panel='#151A22', panel2='#1B212C', border='#465166',
            text='#F4F6FA', muted='#A9B3C5', accent='#80B8F0', good='#42D79A', bad='#FF8799',
            warning='#E9B960', frame='#8193AC', sun='#294C70', sun_line='#91C4F5',
            planet='#254D49', planet_line='#88CFC4', ring='#354152', ring_line='#A7B6CA')
LIGHT = dict(bg='#EFF3F6', panel='#FFFFFF', panel2='#EDF4FA', border='#D0DEEB',
             text='#172D49', muted='#566B82', accent='#2D83D5', good='#218F68', bad='#BD354A',
             warning='#946000', frame='#8296AE', sun='#BCD5EF', sun_line='#376C9D',
             planet='#BBDDD7', planet_line='#367E78', ring='#D0D7E0', ring_line='#69788C')


class DisclosureButton(QPushButton):
    """Keep the disclosure arrow at the right edge, independent of text length."""
    def setIcon(self, icon):
        self._arrow = icon
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if hasattr(self, '_arrow'):
            painter = QPainter(self)
            self._arrow.paint(painter, self.width() - 28, (self.height() - 18) // 2, 18, 18)
            painter.end()


def add_disclosure(layout, title, widget):
    button = DisclosureButton(title)
    button.setIcon(disclosure_icon(False, LIGHT['text']))
    button.setObjectName('Disclosure')
    button.setCheckable(True)
    widget.hide()
    def toggle(opened):
        widget.setVisible(opened)
        button.setIcon(disclosure_icon(opened, button.palette().color(QPalette.ButtonText)))
    button.toggled.connect(toggle)
    layout.addWidget(button)
    layout.addWidget(widget)
    return button


class ParameterBox(QFrame):
    changed = Signal()

    def __init__(self, title, value, minimum, maximum, decimals=0, suffix=''):
        super().__init__()
        self.setObjectName('ParameterBox')
        self.setMinimumHeight(54)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        label = QLabel(title)
        label.setObjectName('InputLabel')
        label.setWordWrap(True)
        layout.addWidget(label, 1)
        layout.addStretch()
        self.spin = QDoubleSpinBox() if decimals else QSpinBox()
        self.spin.setRange(minimum, maximum)
        if decimals:
            self.spin.setDecimals(decimals)
            self.spin.setSingleStep(.1 if decimals == 2 else .5)
        self.spin.setValue(value)
        self.spin.setSuffix(suffix)
        self.spin.setAccessibleName(title)
        self.spin.setToolTip(f'このアプリの入力対応範囲：{minimum}〜{maximum}{suffix}。干渉・強度の保証値ではありません。')
        self.spin.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.spin.setKeyboardTracking(False)
        self.spin.setMinimumWidth(130)
        self.spin.valueChanged.connect(lambda _value: self.changed.emit())
        layout.addWidget(self.spin)

    def value(self):
        return self.spin.value()


