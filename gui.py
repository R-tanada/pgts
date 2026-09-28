from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QColor, QPalette, QPainterPath, QRegion
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QTabWidget,
)
from ui_widgets import (theme_icon, gear_icon, disclosure_icon, make_resize_handles,
                        position_resize_handles)
from ui_common import DARK, LIGHT
from planetary_page import PlanetaryPage
from simple_gear.page import GearPairPage

class TitleBar(QFrame):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self.window().windowHandle()
            if handle:
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.window().toggle_maximized()
        else:
            super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dark = False
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setWindowTitle('歯車設計ツール')
        self.resize(1600, 980)
        self.setMinimumSize(1200, 680)
        root = QFrame()
        root.setObjectName('WindowFrame')
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(2, 2, 2, 2)
        main.setSpacing(0)
        title = TitleBar()
        title.setObjectName('TitleBar')
        title.setFixedHeight(50)
        bar = QHBoxLayout(title)
        bar.setContentsMargins(16, 0, 8, 0)
        self.logo_icon = QLabel()
        self.logo_icon.setAttribute(Qt.WA_TransparentForMouseEvents)
        bar.addWidget(self.logo_icon)
        logo = QLabel('歯車設計ツール')
        logo.setStyleSheet('font-size: 17px; font-weight: bold;')
        logo.setAttribute(Qt.WA_TransparentForMouseEvents)
        bar.addWidget(logo)
        bar.addStretch()
        self.theme_button = QPushButton('☾')
        self.theme_button.clicked.connect(self.toggle_theme)
        minimize = QPushButton('−')
        minimize.setToolTip('最小化')
        minimize.clicked.connect(self.showMinimized)
        self.maximize_button = QPushButton('□')
        self.maximize_button.setToolTip('最大化／元に戻す')
        self.maximize_button.clicked.connect(self.toggle_maximized)
        close = QPushButton('×')
        close.setToolTip('閉じる')
        close.clicked.connect(self.close)
        for button in (self.theme_button, minimize, self.maximize_button, close):
            button.setObjectName('TitleButton')
            button.setFixedSize(38, 32)
            bar.addWidget(button)
        main.addWidget(title)
        self.tabs = QTabWidget()
        self.planetary_page = PlanetaryPage()
        self.pair_page = GearPairPage()
        self.tabs.addTab(self.pair_page, '単純歯車対')
        self.tabs.addTab(self.planetary_page, '遊星歯車')
        self.tabs.setCurrentWidget(self.pair_page)
        main.addWidget(self.tabs, 1)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.apply_theme()
        self.resize_handles = make_resize_handles(self)
        position_resize_handles(self, self.resize_handles)

    def _tab_changed(self, index):
        if self.tabs.widget(index) is not self.pair_page:
            self.pair_page.pause_animation()

    def closeEvent(self, event):
        self.pair_page.pause_animation()
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_window_mask()
        if hasattr(self, 'resize_handles'):
            position_resize_handles(self, self.resize_handles)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self.update_window_mask()
        if event.type() == QEvent.WindowStateChange and hasattr(self, 'resize_handles'):
            position_resize_handles(self, self.resize_handles)

    def update_window_mask(self):
        # Clip the actual top-level window, not only the styled central frame.
        if self.isMaximized():
            self.clearMask()
        else:
            path = QPainterPath()
            path.addRoundedRect(0, 0, self.width(), self.height(), 8, 8)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def toggle_maximized(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def toggle_theme(self):
        self.dark = not self.dark
        self.apply_theme()

    def apply_theme(self):
        c = DARK if self.dark else LIGHT
        # Fusion arrows use palette roles even when the surrounding spinbox
        # is styled. Set these explicitly so OS dark mode cannot leak in.
        palette = self.palette()
        for role, key in ((QPalette.Window, 'bg'), (QPalette.Base, 'panel'),
                          (QPalette.Button, 'panel2'), (QPalette.Text, 'text'),
                          (QPalette.WindowText, 'text'), (QPalette.ButtonText, 'text')):
            palette.setColor(role, QColor(c[key]))
        self.setPalette(palette)
        self.setStyleSheet(f'''
            QWidget {{ background: {c['bg']}; color: {c['text']}; font-family: "Yu Gothic UI"; font-size: 14px; }}
            QFrame#WindowFrame {{ border: 2px solid {c['frame']}; border-radius: 8px; }}
            QLabel {{ background: transparent; }}
            QCheckBox {{ background: {c['panel']}; }}
            QFrame#TitleBar {{ background: {c['panel']}; border-bottom: 1px solid {c['border']}; }}
            QLabel#PageTitle {{ font-size: 25px; font-weight: bold; }}
            QLabel#PanelTitle {{ font-size: 24px; font-weight: bold; }}
            QLabel#InputLabel {{ font-size: 15px; }}
            QLabel#RatioValue {{ font-size: 32px; font-weight: bold; color: {c['accent']}; }}
            QLabel#Muted {{ color: {c['muted']}; font-size: 13px; }}
            QPushButton#ConstraintName {{ text-align: left; font-size: 21px; font-weight: bold; background: transparent; border: none; padding: 6px 30px 6px 0; }}
            QFrame#ConstraintRow {{ background: {c['panel'] if self.dark else '#F7FAFD'}; border: 1px solid {c['border']}; border-radius: 8px; }}
            QPushButton#Disclosure {{ text-align: left; padding: 10px 30px 10px 12px; font-size: 16px; }}
            QPushButton#Primary {{ background: {c['accent']}; color: {'#152438' if self.dark else '#FFFFFF'}; font-size: 20px; font-weight: bold; padding: 12px; }}
            QPushButton#Primary:disabled {{ background: {c['border']}; color: {c['muted']}; }}
            QPushButton#Playback {{ background: {c['accent']}; color: {'#152438' if self.dark else '#FFFFFF'}; font-weight: bold; padding: 10px; }}
            QWidget[designPage="true"] QFrame#ParameterBox {{ background: transparent; border: none; }}
            QWidget[designPage="true"] QLabel#InputLabel {{ font-size: 18px; }}
            QWidget[designPage="true"] QSpinBox, QWidget[designPage="true"] QDoubleSpinBox {{ font-size: 19px; min-height: 28px; }}
            QWidget[designPage="true"] QCheckBox {{ font-size: 16px; spacing: 8px; }}
            QWidget[designPage="true"] QCheckBox::indicator {{ width: 20px; height: 20px; }}
            QFrame#Card, QFrame#ParameterBox {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 10px; }}
            QFrame#ParameterBox {{ background: {c['panel2']}; }}
            QFrame#InputGroup {{ background: transparent; border: none; }}
            QFrame#RatioCard {{ background: {c['panel2']}; border: 1px solid {c['border']}; border-radius: 7px; }}
            QPushButton {{ background: {c['panel2']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 6px; }}
            QPushButton:hover {{ border-color: {c['accent']}; }}
            QPushButton#TitleButton {{ background: transparent; border: none; font-size: 18px; padding: 0; }}
            QPushButton#TitleButton:hover {{ background: {c['panel2']}; }}
            QSpinBox, QDoubleSpinBox {{ background: {c['panel']}; color: {c['text']}; font-size: 16px; border: 1px solid {c['border']}; border-radius: 6px; padding: 6px 22px 6px 6px; min-height: 22px; }}
            QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {c['accent']}; }}
            QSpinBox::up-button, QDoubleSpinBox::up-button {{ width: 20px; }}
            QSpinBox::down-button, QDoubleSpinBox::down-button {{ width: 20px; }}
            QScrollArea {{ border: none; }}
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{ background: {c['panel']}; font-size: 17px; padding: 12px 30px; border-bottom: 3px solid transparent; }}
            QTabBar::tab:selected {{ background: {c['panel2']}; color: {c['accent']}; border-bottom-color: {c['accent']}; }}
            QComboBox {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 4px; padding: 6px; }}
        ''')
        self.theme_button.setText('')
        self.logo_icon.setPixmap(gear_icon(c['accent']).pixmap(QSize(26, 26)))
        self.theme_button.setIcon(theme_icon(self.dark, c['text']))
        self.theme_button.setIconSize(QSize(24, 24))
        self.theme_button.setToolTip('ライトモードに切替' if self.dark else 'ダークモードに切替')
        self.theme_button.setAccessibleName(self.theme_button.toolTip())
        self.planetary_page.set_theme(self.dark)
        self.pair_page.set_theme(self.dark)
        for button in self.findChildren(QPushButton, 'Disclosure'):
            button.setIcon(disclosure_icon(button.isChecked(), c['text']))
