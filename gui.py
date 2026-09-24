from __future__ import annotations

import math
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSize, QEvent
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QPalette, QPainterPath, QImage
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QDoubleSpinBox, QSpinBox, QScrollArea,
    QAbstractSpinBox, QLayout, QCheckBox,
)
from gear import (
    GearSpec, PlanetarySpec, gear_outline, ring_gear_outline,
    planetary_positions, planetary_constraints, ring_rotation, rotate,
)
from ui_widgets import (FractionEquation, theme_icon, make_resize_handles,
                        position_resize_handles)
from interference import interference_checks

DARK = dict(bg='#0E1117', panel='#151A22', panel2='#1B212C', border='#465166',
            text='#F4F6FA', muted='#A9B3C5', accent='#A399FF', good='#42D79A', bad='#FF8799')
LIGHT = dict(bg='#F3F5F9', panel='#FFFFFF', panel2='#EEF1F6', border='#CBD3DF',
             text='#171B24', muted='#566175', accent='#5849C6', good='#12754F', bad='#B52D45')


class Preview(QWidget):
    def __init__(self):
        super().__init__()
        self.spec = PlanetarySpec()
        self.dark = False
        self.points = None
        self.ring_polygon = None
        self.sun_polygon = None
        self.planet_polygons = []
        self.positions = []
        self.issues = []
        self.reference_diameter = 150.0
        self.show_reference = True
        self._shape_layer = None
        self.setMinimumSize(360, 360)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    @staticmethod
    def _polygon(points):
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
        path.closeSubpath()
        return path

    def set_reference(self, diameter, visible=True):
        self.reference_diameter = diameter
        self.show_reference = visible
        self.update()

    def set_spec(self, spec, checks):
        self._shape_layer = None
        self.spec = spec
        self.issues = []
        for check in checks:
            name, ok, detail = check
            if getattr(check, 'blocks_assembly', True) and ok is not True:
                self.issues.append(name + '：' + detail)
        self.points = None
        self.ring_polygon = None
        self.sun_polygon = None
        self.planet_polygons = []
        self.positions = []
        # Ring geometry remains available even when assembly checks fail.
        try:
            self.ring_polygon = self._polygon([rotate(p, ring_rotation(spec))
                for p in ring_gear_outline(GearSpec(spec.module, spec.ring_teeth,
                                                    spec.pressure_angle_deg), 20)])
        except ValueError as exc:
            self.issues.append('リング歯形：' + str(exc))
        try:
            self.sun_polygon = self._polygon(gear_outline(GearSpec(spec.module, spec.sun_teeth,
                                                                  spec.pressure_angle_deg), 20))
        except ValueError as exc:
            self.issues.append('太陽歯形：' + str(exc))
        if not self.issues:
            try:
                planet = gear_outline(GearSpec(spec.module, spec.planet_teeth,
                                              spec.pressure_angle_deg), 20)
                self.positions = planetary_positions(spec)
                self.planet_polygons = [self._polygon([
                    (x + rx, y + ry) for rx, ry in (rotate(v, angle) for v in planet)])
                    for x, y, angle in self.positions]
                self.points = self.sun_polygon, self.planet_polygons, self.ring_polygon
            except ValueError as exc:
                self.issues.append('遊星歯形：' + str(exc))
        self.update()

    def set_theme(self, dark):
        if self.dark != dark:
            self._shape_layer = None
        self.dark = dark
        self.update()

    def _render_shapes(self):
        # Rasterize the detailed contours only after a design/theme change.
        # Window resizing scales this high-resolution layer; circles and text
        # are still drawn at the current screen resolution.
        self._layer_extent = max(self.spec.ring_outer_radius,
                                 self.spec.sun_pitch_radius + self.spec.module) * 1.02
        self._shape_layer = QImage(1536, 1536, QImage.Format_ARGB32_Premultiplied)
        self._shape_layer.fill(Qt.transparent)
        p = QPainter(self._shape_layer)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(768, 768)
        p.scale(768 / self._layer_extent, 768 / self._layer_extent)
        c = DARK if self.dark else LIGHT
        pen = QPen(QColor(c['accent']), max(2.5, 1.2 * 768 / (self._layer_extent * self.view_scale())))
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(QColor(c['panel2']) if self.ring_polygon is not None else Qt.NoBrush)
        p.drawEllipse(QPointF(0, 0), self.spec.ring_outer_radius, self.spec.ring_outer_radius)
        for path, color in [(self.ring_polygon, c['bg']), (self.sun_polygon, c['panel2'])]:
            if path is not None:
                p.setBrush(QColor(color))
                p.drawPath(path)
        p.setBrush(QColor(c['panel']))
        for path in self.planet_polygons:
            p.drawPath(path)
        p.end()

    def view_scale(self):
        radius = max(self.spec.ring_outer_radius,
                     self.spec.sun_pitch_radius + self.spec.module)
        if self.show_reference:
            radius = max(radius, self.reference_diameter / 2)
        return max(1, min(self.width() - 50, self.height() - 60)) / (2 * radius)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = DARK if self.dark else LIGHT
        p.fillRect(self.rect(), QColor(c['bg']))
        s = self.spec
        scale = self.view_scale()
        cx, cy = self.width() / 2, (self.height() - 25) / 2
        p.save()
        p.translate(cx, cy)
        p.scale(scale, -scale)

        def pen(color, width=1.2, style=Qt.SolidLine):
            result = QPen(QColor(color), width, style)
            result.setCosmetic(True)
            return result

        if self._shape_layer is None:
            self._render_shapes()
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        extent = self._layer_extent
        p.drawImage(QRectF(-extent, -extent, 2*extent, 2*extent), self._shape_layer)
        p.setBrush(Qt.NoBrush)
        p.setPen(pen(c['muted'], 1, Qt.DotLine))
        p.drawEllipse(QPointF(0, 0), s.ring_pitch_radius, s.ring_pitch_radius)
        if self.sun_polygon is not None:
            p.drawEllipse(QPointF(0, 0), s.sun_pitch_radius, s.sun_pitch_radius)
        if self.points is not None:
            for x, y, _ in self.positions:
                p.drawEllipse(QPointF(x, y), s.planet_pitch_radius, s.planet_pitch_radius)
        if self.show_reference:
            p.setPen(pen('#D5953A' if self.dark else '#9B5F13', 1.8, Qt.DashLine))
            radius = self.reference_diameter / 2
            p.drawEllipse(QPointF(0, 0), radius, radius)
        p.restore()
        p.setPen(QColor(c['text']))
        if self.sun_polygon is not None:
            p.drawText(QRectF(cx-50, cy-22, 100, 44), Qt.AlignCenter, f'太陽\nz = {s.sun_teeth}')
        if self.points is not None:
            for i, (x, y, _) in enumerate(self.positions, 1):
                p.drawText(QRectF(cx+x*scale-50, cy-y*scale-22, 100, 44),
                           Qt.AlignCenter, f'遊星 {i}\nz = {s.planet_teeth}')
        elif self.sun_polygon is None:
            message = ('リングのみ表示中' if self.ring_polygon is not None
                       else 'リング歯形を定義できません\n外周・ピッチ円のみ表示中')
            p.drawText(QRectF(cx-170, cy-40, 340, 80), Qt.AlignCenter, message)
        p.drawText(QRectF(0, self.height()-28, self.width(), 25), Qt.AlignCenter,
                   '茶の破線：設計基準円　｜　点線：ピッチ円'
                   if self.show_reference else '点線：ピッチ円')
        p.end()


class ParameterBox(QFrame):
    changed = Signal()

    def __init__(self, title, value, minimum, maximum, decimals=0, suffix=''):
        super().__init__()
        self.setObjectName('ParameterBox')
        self.setMinimumHeight(54)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.addWidget(QLabel(title))
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


class ConstraintPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName('Card')
        self.rows = QVBoxLayout(self)
        self.rows.setAlignment(Qt.AlignTop)
        self.rows.setSizeConstraint(QLayout.SetMinimumSize)
        self.rows.setContentsMargins(16, 16, 16, 16)
        self.show_details = False

    def toggle_details(self, enabled):
        self.show_details = enabled
        self.update_constraints(*self.last_args)

    def update_constraints(self, checks, spec, dark):
        self.last_args = checks, spec, dark
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        title = QLabel('制約条件・干渉チェック')
        title.setObjectName('PanelTitle')
        self.rows.addWidget(title)
        details_toggle = QCheckBox('判定値・説明を表示')
        details_toggle.setChecked(self.show_details)
        details_toggle.toggled.connect(self.toggle_details)
        self.rows.addWidget(details_toggle)
        formulas = {
            '歯数関係': '<i>z</i><sub>r</sub> = <i>z</i><sub>s</sub> + 2<i>z</i><sub>p</sub>',
            '均等配置条件': None,
            '遊星歯車どうしのすきま': '2<i>a</i> sin(π/<i>N</i>) &gt; <i>m</i>(<i>z</i><sub>p</sub> + 2)'
            if spec.planet_count > 1 else '<i>N</i> = 1：隣接歯車なし',
        }
        c = DARK if dark else LIGHT
        for check in checks:
            name, ok, detail = check
            formula = getattr(check, 'formula', formulas.get(name))
            row = QWidget()
            row.setToolTip(detail)
            layout = QVBoxLayout(row)
            layout.setContentsMargins(0, 2, 0, 2)
            layout.setSpacing(3)
            blocking = getattr(check, 'blocks_assembly', True)
            status = '✓ 適合　' if ok is True else ('? 判定不可　' if ok is None else ('× 不適合　' if blocking else '△ 注意　'))
            label = QLabel(status + name)
            label.setWordWrap(True)
            label.setStyleSheet('color:' + (c['good'] if ok is True else c['bad']))
            layout.addWidget(label)
            if formula is None:
                equation = FractionEquation('<i>z</i><sub>s</sub> + <i>z</i><sub>r</sub>', '<i>N</i>', '∈ ℤ')
            else:
                equation = QLabel(formula)
                equation.setTextFormat(Qt.RichText)
                equation.setWordWrap(True)
                equation.setStyleSheet('font-family: "Cambria Math"; font-size: 16px;')
            layout.addWidget(equation)
            if name == '均等配置条件':
                value = (spec.sun_teeth + spec.ring_teeth) / spec.planet_count
                detail = f'計算値：{value:.6g}　（整数であること）'
            elif name == '歯数関係':
                detail = f'遊星の入力：{spec.planet_teeth} 歯　／　必要歯数：{(spec.ring_teeth - spec.sun_teeth) / 2:g} 歯'
            elif name == '遊星歯車どうしのすきま':
                detail = 'a = m(zᵣ + zₛ)/4（歯数関係成立時）'
            row.setToolTip(detail)
            if detail and self.show_details:
                value_label = QLabel(detail)
                value_label.setObjectName('Muted')
                value_label.setWordWrap(True)
                layout.addWidget(value_label)
            self.rows.addWidget(row)
        legend = QLabel('s：太陽　p：遊星　r：リング\nN：遊星個数　a：中心距離\n'
                        'αap・αar：遊星・リングの歯先圧力角\ninv α = tan α − α（角度はrad）\n'
                        '干渉：標準歯たけ・転位なしの解析式。\nθの定義と適用範囲は設計計算メモを参照。')
        legend.setObjectName('Muted')
        if self.show_details:
            self.rows.addWidget(legend)
        else:
            legend.deleteLater()


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
        self.setWindowTitle('遊星歯車設計ツール')
        self.resize(1500, 900)
        self.setMinimumSize(1200, 680)
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        title = TitleBar()
        title.setObjectName('TitleBar')
        title.setFixedHeight(46)
        bar = QHBoxLayout(title)
        bar.setContentsMargins(16, 0, 8, 0)
        logo = QLabel('◆　遊星歯車設計ツール')
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
        content = QHBoxLayout()
        content.setContentsMargins(18, 16, 18, 0)
        content.setSpacing(18)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(360)
        self.parameter_scroll = scroll
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        left_layout.setContentsMargins(0, 0, 10, 0)
        left_layout.setSpacing(12)
        header = QLabel('遊星歯車の設計')
        header.setObjectName('PageTitle')
        left_layout.addWidget(header)
        subtitle = QLabel('標準平歯車・転位係数 x = 0')
        subtitle.setObjectName('Muted')
        left_layout.addWidget(subtitle)
        card = QFrame()
        card.setObjectName('Card')
        fields = QVBoxLayout(card)
        fields.setContentsMargins(14, 14, 14, 14)
        label = QLabel('基本パラメータ')
        label.setObjectName('PanelTitle')
        fields.addWidget(label)
        self.module = ParameterBox('モジュール m', 2., .5, 10., 2, ' mm')
        self.sun_teeth = ParameterBox('太陽歯車の歯数', 20, 6, 100)
        self.planet_teeth = ParameterBox('遊星歯車の歯数', 20, 6, 100)
        self.ring_teeth = ParameterBox('リング歯車の歯数', 60, 6, 300)
        self.planet_count = ParameterBox('遊星歯車の個数', 3, 1, 8)
        self.angle = ParameterBox('圧力角 α', 20., 10., 35., 1, ' °')
        for field in (self.module, self.sun_teeth, self.planet_teeth,
                      self.ring_teeth, self.planet_count, self.angle):
            fields.addWidget(field)
            field.changed.connect(self.update_model)
        self.fit_planet_button = QPushButton('リングを基準に遊星歯数を合わせる')
        self.fit_planet_button.setToolTip('リングと太陽の歯数を保持し、遊星歯数 = (リング − 太陽) / 2 にします')
        self.fit_planet_button.clicked.connect(self.fit_planet)
        fields.addWidget(self.fit_planet_button)
        self.fit_feedback = QLabel()
        self.fit_feedback.setWordWrap(True)
        self.fit_feedback.setObjectName('Muted')
        fields.addWidget(self.fit_feedback)
        input_help = QLabel('入力欄の上下限はこのアプリの対応範囲です。\n歯車の成立・干渉の回避条件ではありません。')
        input_help.setWordWrap(True)
        input_help.setObjectName('Muted')
        fields.addWidget(input_help)
        left_layout.addWidget(card)
        reference_card = QFrame()
        reference_card.setObjectName('Card')
        reference_layout = QVBoxLayout(reference_card)
        reference_title = QLabel('リング外形・設計基準円')
        reference_title.setObjectName('PanelTitle')
        reference_layout.addWidget(reference_title)
        self.rim_thickness = ParameterBox('リング外周の厚さ', 3.5, .1, 1000., 2, ' mm')
        self.rim_thickness.setToolTip('リング歯元円から外周までの半径方向の厚さ')
        self.rim_thickness.changed.connect(self.update_model)
        reference_layout.addWidget(self.rim_thickness)
        self.reference_diameter = ParameterBox('設計基準円の直径', 150., 1., 10000., 1, ' mm')
        self.reference_diameter.spin.setSingleStep(1.)
        self.reference_diameter.changed.connect(self.update_reference)
        reference_layout.addWidget(self.reference_diameter)
        self.reference_visible = QCheckBox('設計基準円を表示する')
        self.reference_visible.setChecked(True)
        self.reference_visible.toggled.connect(self.update_reference)
        reference_layout.addWidget(self.reference_visible)
        reference_note = QLabel('基準円の直径は歯数・モジュールを変えても固定です。\n外周の厚さは歯元円から測ります。')
        reference_note.setWordWrap(True)
        reference_note.setObjectName('Muted')
        reference_layout.addWidget(reference_note)
        left_layout.addWidget(reference_card)
        self.constraints = ConstraintPanel()
        note = QLabel('歯形は概略表示です。切下げ後の歯元形状・工具による創成・強度は未評価です。干渉は解析式で判定します。')
        note.setWordWrap(True)
        note.setObjectName('Muted')
        left_layout.addWidget(note)
        left_layout.addStretch()
        scroll.setWidget(left)
        content.addWidget(scroll)
        self.constraint_scroll = QScrollArea()
        self.constraint_scroll.setWidgetResizable(True)
        self.constraint_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.constraint_scroll.setFixedWidth(370)
        self.constraint_scroll.setWidget(self.constraints)
        content.addWidget(self.constraint_scroll)
        preview_card = QFrame()
        preview_card.setObjectName('Card')
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        top = QHBoxLayout()
        preview_title = QLabel('組立プレビュー')
        preview_title.setObjectName('PanelTitle')
        top.addWidget(preview_title)
        top.addStretch()
        self.status = QLabel()
        top.addWidget(self.status)
        preview_layout.addLayout(top)
        ratio_card = QFrame()
        ratio_card.setObjectName('ParameterBox')
        ratio_layout = QVBoxLayout(ratio_card)
        ratio_layout.setContentsMargins(12, 8, 12, 8)
        self.ratio_value = QLabel()
        self.ratio_value.setWordWrap(True)
        self.ratio_value.setObjectName('RatioValue')
        ratio_layout.addWidget(self.ratio_value)
        ratio_caption = QLabel('リング固定｜太陽入力 → キャリア出力<br>'
                              '<i>i</i> = <i>n</i><sub>s</sub>/<i>n</i><sub>c</sub> = 1 + <i>z</i><sub>r</sub>/<i>z</i><sub>s</sub>')
        ratio_caption.setTextFormat(Qt.RichText)
        ratio_caption.setWordWrap(True)
        ratio_layout.addWidget(ratio_caption)
        preview_layout.addWidget(ratio_card)
        self.warning_banner = QLabel()
        self.warning_banner.setWordWrap(True)
        self.warning_banner.setTextFormat(Qt.PlainText)
        self.warning_banner.setContentsMargins(12, 8, 12, 8)
        preview_layout.addWidget(self.warning_banner)
        self.envelope_status = QLabel()
        self.envelope_status.setWordWrap(True)
        preview_layout.addWidget(self.envelope_status)
        self.preview = Preview()
        preview_layout.addWidget(self.preview, 1)
        self.geometry_note = QLabel()
        self.geometry_note.setWordWrap(True)
        self.geometry_note.setObjectName('Muted')
        preview_layout.addWidget(self.geometry_note)
        content.addWidget(preview_card, 1)
        main.addLayout(content, 1)
        main.addSpacing(8)
        self.apply_theme()
        self.update_model()
        self.resize_handles = make_resize_handles(self)
        position_resize_handles(self, self.resize_handles)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'resize_handles'):
            position_resize_handles(self, self.resize_handles)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, 'resize_handles'):
            position_resize_handles(self, self.resize_handles)

    def fit_planet(self):
        required = (self.ring_teeth.value() - self.sun_teeth.value()) / 2
        if not required.is_integer():
            self.fit_feedback.setText(f'必要歯数は {required:g} 歯です。整数にならないため変更していません。太陽歯数の奇数・偶数をリングに合わせてください。')
            return
        spin = self.planet_teeth.spin
        if not spin.minimum() <= required <= spin.maximum():
            self.fit_feedback.setText(f'必要歯数 {required:g} は入力範囲（{spin.minimum()}〜{spin.maximum()} 歯）外です。変更していません。')
            return
        spin.setValue(int(required))
        self.fit_feedback.setText(f'遊星を {required:g} 歯に設定しました。リング・太陽は維持しています。均等配置は別途判定します。')

    def toggle_maximized(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def update_model(self):
        self.fit_feedback.clear()
        self.spec = PlanetarySpec(module=float(self.module.value()),
            sun_teeth=int(self.sun_teeth.value()), planet_teeth=int(self.planet_teeth.value()),
            ring_teeth=int(self.ring_teeth.value()), planet_count=int(self.planet_count.value()),
            pressure_angle_deg=float(self.angle.value()),
            ring_rim_thickness=float(self.rim_thickness.value()))
        checks = planetary_constraints(self.spec) + interference_checks(self.spec)
        self.preview.set_spec(self.spec, checks)
        self.constraints.update_constraints(checks, self.spec, self.dark)
        c = DARK if self.dark else LIGHT
        ok = not self.preview.issues
        self.ratio_value.setText(f'減速比　{self.spec.reduction_ratio:.4f} : 1'
                                + ('　（参考値）' if not ok else ''))
        self.ratio_value.setToolTip('太陽の回転数 ÷ キャリアの回転数。条件不適合時は歯数から求めた理論参考値です。')
        notices = [check for check in checks if not getattr(check, 'blocks_assembly', True) and tuple(check)[1] is not True]
        self.status.setText('● 要確認' if not ok else ('● 加工・組立に注意' if notices else '● 検査項目に適合'))
        self.status.setStyleSheet('color:' + (c['good'] if ok and not notices else c['bad']))
        messages = []
        if not ok:
            messages.append('遊星は非表示です。リング・太陽は参考形状を表示しています。')
            messages.append('確認項目：' + '／'.join(issue.split('：', 1)[0] for issue in self.preview.issues))
        if notices:
            messages.append('加工・組立上の注意：' + '／'.join(check.name for check in notices))
        self.warning_banner.setText('\n'.join(messages))
        self.warning_banner.setToolTip('\n'.join(self.preview.issues + [c.detail for c in notices]))
        self.warning_banner.setStyleSheet(f"color: {c['bad']}; background: {c['panel2']}; border-radius: 6px;")
        self.warning_banner.setVisible(not ok or bool(notices))
        s = self.spec
        self.geometry_note.setText(f'必要中心距離 m(zᵣ+zₛ)/4：{s.ring_sun_center_distance:.2f} mm\n'
            f'現在の歯数による距離　太陽–遊星：{s.sun_planet_center_distance:.2f} mm'
            f'　／　遊星–リング：{s.planet_ring_center_distance:.2f} mm\n'
            '転位なし・バックラッシなし。工具の創成歯形と強度は未評価です。')
        self.update_reference()

    def update_reference(self):
        diameter = float(self.reference_diameter.value())
        self.preview.set_reference(diameter, self.reference_visible.isChecked())
        outer = 2 * self.spec.ring_outer_radius
        difference = diameter - outer
        comparison = (f'直径差 {difference:.2f} mm' if difference >= 0
                      else f'基準円を {-difference:.2f} mm 超過')
        self.envelope_status.setText(f'リング外径：{outer:.2f} mm　／　基準円直径：{diameter:g} mm　｜　{comparison}')
        c = DARK if self.dark else LIGHT
        self.envelope_status.setStyleSheet('color:' + (c['muted'] if difference >= 0 else c['bad']))

    def toggle_theme(self):
        self.dark = not self.dark
        self.apply_theme()
        self.update_model()

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
            QWidget {{ background: {c['bg']}; color: {c['text']}; font-family: "Yu Gothic UI"; font-size: 13px; }}
            QLabel {{ background: transparent; }}
            QFrame#TitleBar {{ background: {c['panel']}; border-bottom: 1px solid {c['border']}; }}
            QLabel#PageTitle {{ font-size: 25px; font-weight: bold; }}
            QLabel#PanelTitle {{ font-size: 16px; font-weight: bold; }}
            QLabel#RatioValue {{ font-size: 22px; font-weight: bold; color: {c['accent']}; }}
            QLabel#Muted {{ color: {c['muted']}; font-size: 12px; }}
            QFrame#Card, QFrame#ParameterBox {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 10px; }}
            QFrame#ParameterBox {{ background: {c['panel2']}; }}
            QPushButton {{ background: {c['panel2']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 6px; }}
            QPushButton:hover {{ border-color: {c['accent']}; }}
            QPushButton#TitleButton {{ background: transparent; border: none; font-size: 18px; padding: 0; }}
            QPushButton#TitleButton:hover {{ background: {c['panel2']}; }}
            QSpinBox, QDoubleSpinBox {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 4px; padding: 6px 22px 6px 6px; min-height: 22px; }}
            QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {c['accent']}; }}
            QSpinBox::up-button, QDoubleSpinBox::up-button {{ width: 20px; }}
            QSpinBox::down-button, QDoubleSpinBox::down-button {{ width: 20px; }}
            QScrollArea {{ border: none; }}
        ''')
        self.theme_button.setText('')
        self.theme_button.setIcon(theme_icon(self.dark, c['text']))
        self.theme_button.setIconSize(QSize(24, 24))
        self.theme_button.setToolTip('ライトモードに切替' if self.dark else 'ダークモードに切替')
        self.theme_button.setAccessibleName(self.theme_button.toolTip())
        self.preview.set_theme(self.dark)
