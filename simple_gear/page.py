"""共通の入力カードとテーマを使う、外歯車対の設計ページ。"""
from math import pi
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QScrollArea, QCheckBox, QComboBox, QFileDialog, QMessageBox, QSizePolicy,
)
from ui_common import ParameterBox, LIGHT, DARK
from .geometry import Gear, InvoluteGear
from .view import GearView


def card(title):
    frame = QFrame()
    frame.setObjectName('Card')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 14, 14, 14)
    label = QLabel(title)
    label.setObjectName('PanelTitle')
    layout.addWidget(label)
    return frame, layout


def scroll_column(layout, width):
    widget = QFrame()
    widget.setObjectName('Card')
    widget.setLayout(layout)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setMinimumWidth(width)
    scroll.setWidget(widget)
    return scroll


class GearPairPage(QWidget):
    def __init__(self):
        super().__init__()
        self.dark = False
        self.setProperty("designPage", True)
        self.animation_angle = 0.0
        self.valid = False
        self._model_key = None
        self._models = None
        self._first_show = True
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._animation_step)
        content = QHBoxLayout(self)
        content.setContentsMargins(18, 16, 18, 8)
        content.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(16)
        left.setContentsMargins(18, 16, 18, 16)
        common, fields = card('基本パラメータ')
        common.setObjectName('InputGroup')
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setSpacing(10)
        self.module = ParameterBox('モジュール m', 2., .1, 100., 2, ' mm')
        self.angle = ParameterBox('圧力角 α', 20., 1., 45., 1, ' °')
        self.backlash = ParameterBox('各歯車の歯厚減少量', 0., 0., 2., 2, ' mm')
        self.backlash.setToolTip('元コードのバックラッシ入力です。各歯車のピッチ円上の歯厚をこの値だけ減らします。転位なしでは歯車対全体の隙間は入力値の2倍です。')
        for field in (self.module, self.angle, self.backlash):
            fields.addWidget(field)
        left.addWidget(common)
        self.teeth1 = ParameterBox('歯数 z₁', 20, 3, 500)
        self.shift1 = ParameterBox('転位係数 x₁', 0., -1., 1., 2)
        self.teeth2 = ParameterBox('歯数 z₂', 20, 3, 500)
        self.shift2 = ParameterBox('転位係数 x₂', 0., -1., 1., 2)
        for title, teeth, shift in [('歯車1（入力）', self.teeth1, self.shift1),
                                     ('歯車2（出力）', self.teeth2, self.shift2)]:
            frame, fields = card(title)
            frame.setObjectName('InputGroup')
            fields.setContentsMargins(0, 0, 0, 0)
            fields.setSpacing(10)
            fields.addWidget(teeth)
            fields.addWidget(shift)
            shift.spin.setSingleStep(.05)
            left.addWidget(frame)
        left.addStretch()
        content.addWidget(scroll_column(left, 320), 25)

        middle = QVBoxLayout()
        middle.setContentsMargins(16, 16, 16, 16)
        middle.setSpacing(18)
        display, options = card('表示・歯元形状')
        display.setObjectName('InputGroup')
        options.setContentsMargins(0, 0, 0, 0)
        options.setSpacing(12)
        self.checks = {}
        for key, text, enabled in [
            ('mating_gear', '歯車2を表示', True),
            ('reference_circle', '基準円（ピッチ円）', True),
            ('base_circle', '基礎円', False), ('root_circle', '歯底円', False),
            ('addendum_circle', '歯先円', False), ('pitch_point', 'ピッチ点', False),
            ('action_line', '力の作用線', False), ('center_line', '中心を結ぶ線', False),
            ('midline', 'ピッチ点を通る垂直線', False),
        ]:
            check = QCheckBox(text)
            check.setChecked(enabled)
            options.addWidget(check)
            self.checks[key] = check
        options.addWidget(QLabel('歯元形状'))
        self.root_shape = QComboBox()
        self.root_shape.addItems(['円弧（簡略モデル）', 'トロコイド（創成モデル）'])
        options.addWidget(self.root_shape)
        options.addWidget(QLabel('強調する補助線'))
        self.highlight = QComboBox()
        self.highlight.addItems(['なし', '基準円', 'ピッチ点', '基礎円', '歯底円', '歯先円',
                                 '力の作用線', '中心を結ぶ線', '中央の線'])
        options.addWidget(self.highlight)
        middle.addWidget(display)
        info, info_layout = card('計算値・モデルの範囲')
        info.setObjectName('InputGroup')
        info_layout.setContentsMargins(0, 0, 0, 0)
        self.dimensions = QLabel()
        self.dimensions.setWordWrap(True)
        info_layout.addWidget(self.dimensions)
        note = QLabel('中心距離は基準円半径の和で固定です。転位に応じた中心距離の補正・干渉判定は未対応です。\n\n円弧モードの歯底半径は転位によらない簡略値です。加工用歯形としては扱わないでください。')
        note.setObjectName('Muted')
        note.setWordWrap(True)
        info_layout.addWidget(note)
        middle.addWidget(info)
        middle.addStretch()
        content.addWidget(scroll_column(middle, 320), 28)

        preview, layout = card('プレビュー')
        ratio_card = QFrame()
        ratio_card.setObjectName('RatioCard')
        ratio_layout = QVBoxLayout(ratio_card)
        ratio_layout.setContentsMargins(14, 12, 14, 12)
        self.ratio = QLabel()
        self.ratio.setObjectName('RatioValue')
        self.ratio.setWordWrap(True)
        ratio_layout.addWidget(self.ratio)
        caption = QLabel('歯車1入力 → 歯車2出力 ｜ i = z₂ / z₁（回転方向は逆）')
        caption.setWordWrap(True)
        ratio_layout.addWidget(caption)
        layout.addWidget(ratio_card)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setTextFormat(Qt.PlainText)
        layout.addWidget(self.warning)
        self.canvas = GearView()
        # The scene can be very large for panning; its size hint must not make
        # the enclosing preview taller than the visible column.
        self.canvas.setMinimumSize(350, 100)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        layout.addWidget(self.canvas, 1)
        # Only the preview body scrolls; playback remains at the column bottom.
        preview_column = QWidget()
        column_layout = QVBoxLayout(preview_column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(6)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setWidget(preview)
        column_layout.addWidget(self.preview_scroll, 1)
        self.controls = QFrame()
        self.controls.setObjectName('Card')
        controls_layout = QVBoxLayout(self.controls)
        controls_layout.setContentsMargins(14, 10, 14, 10)
        buttons = QHBoxLayout()
        self.play_button = QPushButton('▶ 再生')
        self.play_button.setObjectName('Playback')
        self.play_button.clicked.connect(self.toggle_animation)
        self.reset_button = QPushButton('初期角度に戻す')
        self.reset_button.clicked.connect(self.reset_animation)
        self.fit_button = QPushButton('全体を表示')
        self.fit_button.clicked.connect(self.fit_view)
        self.save_button = QPushButton('画像を保存')
        self.save_button.clicked.connect(self.save_image)
        for button in (self.play_button, self.reset_button, self.fit_button, self.save_button):
            buttons.addWidget(button)
        controls_layout.addLayout(buttons)
        help_text = QLabel('左ドラッグ：移動　／　ホイール：拡大・縮小')
        help_text.setObjectName('Muted')
        controls_layout.addWidget(help_text)
        content.addWidget(preview_column, 47)
        column_layout.addWidget(self.controls)
        for field in self.findChildren(ParameterBox):
            field.layout().setContentsMargins(0, 5, 0, 5)
            field.spin.setFixedWidth(160)
        for field in (self.module, self.angle, self.backlash, self.teeth1,
                      self.shift1, self.teeth2, self.shift2):
            field.changed.connect(self.parameters_changed)
        for check in self.checks.values():
            check.toggled.connect(self.update_preview)
        self.root_shape.currentIndexChanged.connect(self.update_preview)
        self.highlight.currentIndexChanged.connect(self.update_preview)
        self.update_preview()

    def make_gears(self):
        key = tuple(field.value() for field in (self.module, self.angle, self.backlash,
                    self.teeth1, self.shift1, self.teeth2, self.shift2))
        if key != self._model_key:
            m, alpha, backlash, z1, x1, z2, x2 = key
            models = tuple(InvoluteGear(Gear(module=m, pressure_angle_deg=alpha,
                           backlash=backlash, teeth=z, profile_shift=x))
                           for z, x in ((z1, x1), (z2, x2)))
            for i, gear in enumerate(models, 1):
                if gear.root_radius <= 0 or gear.arc_root_radius <= 0:
                    raise ValueError(f'歯車{i}：歯底半径が0以下です。歯数・転位を見直してください。')
                if gear.addendum_radius < gear.base_radius:
                    raise ValueError(f'歯車{i}：歯先円が基礎円より小さく、インボリュート歯面を定義できません。')
                if gear.half_tooth_angle() <= gear.backlash_flank_angle():
                    raise ValueError(f'歯車{i}：歯厚が0以下です。歯厚減少量・転位を見直してください。')
            self._models, self._model_key = models, key
        return self._models

    def parameters_changed(self):
        self.pause_animation()
        self.animation_angle = 0.0
        self.update_preview()
        self.fit_view()

    def update_preview(self):
        colors = DARK if self.dark else LIGHT
        self.warning.setStyleSheet(f"color: {colors['bad']}; background: {colors['panel2']}; padding: 8px; border-radius: 6px;")
        self.ratio.setText(f'減速比　{self.teeth2.value() / self.teeth1.value():.4f} : 1')
        try:
            gears = self.make_gears()
            shifted = bool(self.shift1.value() or self.shift2.value())
            self.canvas.draw_gear(*gears, **{'show_' + key: c.isChecked() for key, c in self.checks.items()},
                highlight_aux=self.highlight.currentText(),
                root_shape='trochoid' if self.root_shape.currentIndex() else 'arc',
                animation_angle=self.animation_angle,
                show_contact_point=self.timer.isActive() and not shifted)
            self.valid = True
            a = sum(g.pitch_radius for g in gears)
            self.dimensions.setText(f'中心距離：{a:g} mm\n歯車1 基準円径：{gears[0].pitch_diameter:g} mm\n歯車2 基準円径：{gears[1].pitch_diameter:g} mm')
            self.warning.setText('転位を含む参考表示です。中心距離を補正していないため、重なり・隙間が生じることがあります。接触点は非表示です。' if shifted else '')
        except (ValueError, FloatingPointError, OverflowError) as exc:
            self.valid = False
            self.pause_animation()
            self.canvas.clear_geometry()
            self.dimensions.setText('歯形を定義できません')
            self.warning.setText(str(exc))
        self.warning.setVisible(bool(self.warning.text()))
        self.play_button.setEnabled(self.valid)
        self.save_button.setEnabled(self.valid)

    def set_theme(self, dark):
        self.dark = dark
        self.canvas.set_theme(dark)
        self.update_preview()

    def toggle_animation(self):
        if self.timer.isActive():
            self.pause_animation()
        elif self.valid:
            self.checks['mating_gear'].setChecked(True)
            self.timer.start()
            self.play_button.setText('Ⅱ 一時停止')

    def pause_animation(self):
        self.timer.stop()
        self.play_button.setText('▶ 再生')

    def reset_animation(self):
        self.pause_animation()
        self.animation_angle = 0.0
        self.update_preview()

    def _animation_step(self):
        # Do not wrap at one input revolution: the output may not yet have
        # completed a revolution, so wrapping would introduce a phase jump.
        self.animation_angle += pi / 180
        self.canvas.update_animation(self.animation_angle,
            show_contact_point=not (self.shift1.value() or self.shift2.value()))

    def fit_view(self):
        if self.valid:
            self.canvas._fit_initial_view(*self.make_gears(), self.checks['mating_gear'].isChecked())

    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            QTimer.singleShot(0, self.fit_view)

    def hideEvent(self, event):
        self.pause_animation()
        super().hideEvent(event)

    def save_image(self):
        self.pause_animation()
        filename, selected = QFileDialog.getSaveFileName(self, '歯車対の画像を保存',
                              'gear-pair.png', 'PNG (*.png);;SVG (*.svg)')
        if not filename:
            return
        if not filename.lower().endswith(('.png', '.svg')):
            filename += '.svg' if selected.startswith('SVG') else '.png'
        try:
            rect = self.canvas.scene.itemsBoundingRect().adjusted(-2, -2, 2, 2)
            if filename.lower().endswith('.svg'):
                self.canvas.render_svg(filename, rect)
            elif not self.canvas.render_to_image(rect, 1400, 1400).save(filename, 'PNG'):
                raise OSError('PNGファイルを書き込めませんでした。')
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(self, '保存エラー', str(exc))
