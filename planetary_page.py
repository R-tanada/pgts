from __future__ import annotations

import math
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSize, QEvent
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QPalette, QPainterPath, QImage
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QDoubleSpinBox, QSpinBox, QScrollArea,
    QAbstractSpinBox, QLayout, QCheckBox, QStyle,
)
from gear import (
    GearSpec, PlanetarySpec, gear_outline, ring_gear_outline,
    planetary_positions, planetary_constraints, ring_rotation, rotate,
)
from ui_widgets import (FractionEquation, theme_icon, disclosure_icon, make_resize_handles,
                        position_resize_handles)
from interference import interference_checks

from ui_common import DARK, LIGHT, ParameterBox, add_disclosure, DisclosureButton

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
                                                    spec.pressure_angle_deg, spec.shift('ring')), 20)])
        except ValueError as exc:
            self.issues.append('リング歯形：' + str(exc))
        try:
            self.sun_polygon = self._polygon(gear_outline(GearSpec(spec.module, spec.sun_teeth,
                                                                  spec.pressure_angle_deg, spec.shift('sun')), 20))
        except ValueError as exc:
            self.issues.append('太陽歯形：' + str(exc))
        if not self.issues:
            try:
                planet = gear_outline(GearSpec(spec.module, spec.planet_teeth,
                                              spec.pressure_angle_deg, spec.shift('planet')), 20)
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
                                 self.spec.sun_tip_radius) * 1.02
        self._shape_layer = QImage(1536, 1536, QImage.Format_ARGB32_Premultiplied)
        self._shape_layer.fill(Qt.transparent)
        p = QPainter(self._shape_layer)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(768, 768)
        p.scale(768 / self._layer_extent, 768 / self._layer_extent)
        c = DARK if self.dark else LIGHT
        pen = QPen(QColor(c['ring_line']), max(2.5, 1.2 * 768 / (self._layer_extent * self.view_scale())))
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(QColor(c['ring']) if self.ring_polygon is not None else Qt.NoBrush)
        p.drawEllipse(QPointF(0, 0), self.spec.ring_outer_radius, self.spec.ring_outer_radius)
        for path, color, outline in [(self.ring_polygon, c['bg'], c['ring_line']),
                                     (self.sun_polygon, c['sun'], c['sun_line'])]:
            if path is not None:
                pen.setColor(QColor(outline))
                p.setPen(pen)
                p.setBrush(QColor(color))
                p.drawPath(path)
        pen.setColor(QColor(c['planet_line']))
        p.setPen(pen)
        p.setBrush(QColor(c['planet']))
        for path in self.planet_polygons:
            p.drawPath(path)
        p.end()

    def view_scale(self):
        radius = max(self.spec.ring_outer_radius,
                     self.spec.sun_tip_radius)
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


class ConstraintPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName('Card')
        self.rows = QVBoxLayout(self)
        self.rows.setAlignment(Qt.AlignTop)
        self.rows.setSizeConstraint(QLayout.SetMinimumSize)
        self.rows.setContentsMargins(16, 16, 16, 16)
        self.rows.setSpacing(6)
        self.show_details = False
        self.expanded = {}
        self.row_buttons = {}
        self.row_bodies = {}

    def toggle_details(self, enabled):
        self.show_details = enabled
        self.expanded = {name: enabled for name, _, _ in self.last_args[0]}
        self.update_constraints(*self.last_args)

    def update_constraints(self, checks, spec, dark):
        self.last_args = checks, spec, dark
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.row_buttons = {}
        self.row_bodies = {}
        title = QLabel('制約条件')
        title.setObjectName('PanelTitle')
        header = QWidget()
        header.setStyleSheet('background: transparent;')
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 8)
        header_layout.addWidget(title)
        mode = QLabel('転位あり' if spec.shift_enabled else '転位なし')
        mode.setObjectName('Muted')
        header_layout.addWidget(mode)
        header_layout.addStretch()
        c = DARK if dark else LIGHT
        legend = QLabel(f'<span style="color:{c["good"]}">✓</span> 適合　'
                        f'<span style="color:{c["bad"]}">×</span> 不適合　'
                        f'<span style="color:{c["warning"]}">△</span> 注意　? 判定不可')
        legend.setWordWrap(True)
        legend.setMinimumWidth(270)
        legend.setObjectName('Muted')
        header_layout.addWidget(legend)
        self.rows.addWidget(header)
        formulas = {
            '中心距離条件': ('<i>a</i><sub>sp</sub> = <i>a</i><sub>pr</sub><br>'
                '<i>a</i><sub>sp</sub> = m(z<sub>s</sub>+z<sub>p</sub>) cos α / (2 cos α<sub>w,sp</sub>)<br>'
                '<i>a</i><sub>pr</sub> = m(z<sub>r</sub>−z<sub>p</sub>) cos α / (2 cos α<sub>w,pr</sub>)<br>'
                'inv α<sub>w,sp</sub> = inv α + 2(x<sub>s</sub>+x<sub>p</sub>) tan α / (z<sub>s</sub>+z<sub>p</sub>)<br>'
                'inv α<sub>w,pr</sub> = inv α + 2(x<sub>r</sub>−x<sub>p</sub>) tan α / (z<sub>r</sub>−z<sub>p</sub>)'
                if spec.shift_enabled else '<i>z</i><sub>r</sub> = <i>z</i><sub>s</sub> + 2<i>z</i><sub>p</sub><br>'
                'm(z<sub>s</sub>+z<sub>p</sub>)/2 = m(z<sub>r</sub>−z<sub>p</sub>)/2'),
            '拘束かみ合い条件': '(<i>z</i><sub>s</sub> + <i>z</i><sub>r</sub>) / <i>N</i> ∈ ℤ',
            '外径干渉条件': ('2<i>a</i> sin(π/<i>N</i>) &gt; <i>m</i>(<i>z</i><sub>p</sub> + 2 + 2<i>x</i><sub>p</sub>)'
                if spec.shift_enabled else '2<i>a</i> sin(π/<i>N</i>) &gt; <i>m</i>(<i>z</i><sub>p</sub> + 2)')
                if spec.planet_count > 1 else '<i>N</i> = 1：隣接歯車なし',
        }
        previous_group = None
        for check in checks:
            name, ok, detail = check
            group = ('遊星歯車の成立条件' if name in formulas else
                     '外歯車の制約' if getattr(check, 'key', '').startswith('undercut') else '内歯車の制約（遊星–リング）')
            if group != previous_group:
                subtitle = QLabel(group)
                subtitle.setObjectName('ConstraintGroup')
                subtitle.setStyleSheet(f'font-size: 16px; font-weight: bold; padding: 7px 0 3px; border-bottom: 1px solid {c["border"]};')
                self.rows.addWidget(subtitle)
                previous_group = group
            if name == '拘束かみ合い条件':
                detail += '\n等間隔配置・同一遊星の条件です。転位ON/OFFで式は変わりません。'
            blocking = getattr(check, 'blocks_assembly', True)
            symbol, status, color = (('✓', '適合', c['good']) if ok is True else
                ('?', '判定不可', c['muted']) if ok is None else
                ('×', '不適合', c['bad']) if blocking else ('△', '注意', c['warning']))
            row = QFrame()
            row.setObjectName('ConstraintRow')
            layout = QVBoxLayout(row)
            layout.setContentsMargins(12, 6, 10, 6)
            heading = QHBoxLayout()
            badge = QLabel(symbol)
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedSize(34, 34)
            badge.setStyleSheet(f'background: {color}; color: white; border-radius: 17px; font-size: 25px; font-weight: bold;')
            badge.setAccessibleName(status)
            badge.setToolTip(status)
            heading.addWidget(badge)
            short_name = name.split('（')[0].replace('切下げ', '切り下げ')
            if '切下げ' in name:
                short_name += '（太陽）' if '太陽' in name else '（遊星）'
            button = DisclosureButton()
            button.setObjectName('ConstraintName')
            button.setCheckable(True)
            button.setToolTip(name + '：' + status + '\n' + detail)
            button.setAccessibleName(name + '：' + status + '。数式と説明を開閉')
            heading.addWidget(button, 1)
            layout.addLayout(heading)
            body = QWidget()
            body.setStyleSheet('background: transparent;')
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(44, 0, 2, 6)
            formula = getattr(check, 'formula', formulas.get(name, ''))
            equation = QLabel(formula)
            equation.setWordWrap(True)
            equation.setTextFormat(Qt.RichText)
            equation.setStyleSheet(f'font-family: "Cambria Math"; font-size: 18px; background: {c["panel2"]}; padding: 10px; border-radius: 5px;')
            body_layout.addWidget(equation)
            value = QLabel(detail)
            value.setWordWrap(True)
            value.setObjectName('Muted')
            value.setTextFormat(Qt.PlainText)
            body_layout.addWidget(value)
            layout.addWidget(body)
            def toggle(opened, key=name, target=body, control=button, text=short_name):
                self.expanded[key] = opened
                target.setVisible(opened)
                control.setText(text)
                control.setIcon(disclosure_icon(opened, c['text']))
            button.toggled.connect(toggle)
            opened = self.expanded.get(name, False)
            button.blockSignals(True)
            button.setChecked(opened)
            button.blockSignals(False)
            body.setVisible(opened)
            button.setText(short_name)
            button.setIcon(disclosure_icon(opened, c['text']))
            self.row_buttons[name] = button
            self.row_bodies[name] = body
            self.rows.addWidget(row)


class PlanetaryPage(QWidget):
    def __init__(self):
        super().__init__()
        self.dark = False
        self.setObjectName('PlanetaryPage')
        self.setProperty('designPage', True)
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        content = QHBoxLayout()
        content.setContentsMargins(18, 16, 18, 0)
        content.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(320)
        self.parameter_scroll = scroll
        left = QFrame()
        left.setObjectName('Card')
        left_layout = QVBoxLayout(left)
        left_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        left_layout.setContentsMargins(18, 16, 18, 16)
        left_layout.setSpacing(12)
        card = QFrame()
        card.setObjectName('InputGroup')
        fields = QVBoxLayout(card)
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setSpacing(9)
        label = QLabel('基本パラメータ')
        label.setObjectName('PanelTitle')
        fields.addWidget(label)
        self.module = ParameterBox('モジュール m', 2., .5, 10., 2, ' mm')
        self.sun_teeth = ParameterBox('太陽の歯数', 20, 6, 100)
        self.planet_teeth = ParameterBox('遊星の歯数', 20, 6, 100)
        self.ring_teeth = ParameterBox('リングの歯数', 60, 6, 300)
        self.planet_count = ParameterBox('遊星の個数', 3, 1, 8)
        self.angle = ParameterBox('圧力角 α', 20., 10., 35., 1, ' °')
        for field in (self.module, self.sun_teeth, self.planet_teeth,
                      self.ring_teeth, self.planet_count, self.angle):
            fields.addWidget(field)
            field.changed.connect(self.update_model)
        self.fit_planet_button = QPushButton('遊星歯数を合わせる')
        self.fit_planet_button.setObjectName('Primary')
        self.fit_planet_button.setToolTip('リングと太陽の歯数を保持し、遊星歯数 = (リング − 太陽) / 2 にします')
        self.fit_planet_button.clicked.connect(self.fit_planet)
        fields.addWidget(self.fit_planet_button)
        self.fit_feedback = QLabel()
        self.fit_feedback.setWordWrap(True)
        self.fit_feedback.setObjectName('Muted')
        fields.addWidget(self.fit_feedback)
        self.fit_feedback.setVisible(False)
        helper = QLabel('リング・太陽の歯数を保持')
        helper.setAlignment(Qt.AlignCenter)
        helper.setObjectName('Muted')
        fields.addWidget(helper)
        self.shift_enabled = QCheckBox('転位を使用する')
        self.shift_enabled.setToolTip('ON：3つの転位係数を独立入力し、かみ合い中心距離で判定します。OFF：係数を保持して転位なしとして計算します。')
        fields.addWidget(self.shift_enabled)
        self.shift_fields = QFrame()
        self.shift_fields.setObjectName('InputGroup')
        shift_layout = QVBoxLayout(self.shift_fields)
        shift_layout.setContentsMargins(0, 0, 0, 0)
        shift_layout.setSpacing(9)
        self.sun_shift = ParameterBox('太陽の転位係数 xₛ', 0., -1., 1., 6)
        self.planet_shift = ParameterBox('遊星の転位係数 xₚ', 0., -1., 1., 6)
        self.ring_shift = ParameterBox('リングの転位係数 xᵣ', 0., -1., 1., 6)
        for field in (self.sun_shift, self.planet_shift, self.ring_shift):
            field.spin.setSingleStep(.01)
            field.changed.connect(self.update_model)
            shift_layout.addWidget(field)
        shift_help = QLabel('各係数を独立に入力（全遊星で共通）\nリングの正転位は歯先円・歯元円を大きくします。')
        shift_help.setObjectName('Muted')
        shift_help.setWordWrap(True)
        shift_layout.addWidget(shift_help)
        fields.addWidget(self.shift_fields)
        self.shift_fields.hide()
        self.shift_enabled.toggled.connect(self.update_model)
        input_help = QLabel('入力欄の上下限はこのアプリの対応範囲です。\n歯車の成立・干渉の回避条件ではありません。')
        input_help.setWordWrap(True)
        input_help.setObjectName('Muted')

        left_layout.addWidget(card)
        reference_card = QFrame()
        reference_card.setObjectName('InputGroup')
        reference_layout = QVBoxLayout(reference_card)
        reference_layout.setContentsMargins(0, 12, 0, 0)
        reference_layout.setSpacing(9)
        reference_title = QLabel('外形・基準円')
        reference_title.setObjectName('PanelTitle')
        reference_layout.addWidget(reference_title)
        self.rim_thickness = ParameterBox('リング外周の厚さ', 3.5, .1, 1000., 2, ' mm')
        self.rim_thickness.setToolTip('リング歯元円から外周までの半径方向の厚さ')
        self.rim_thickness.changed.connect(self.update_model)
        reference_layout.addWidget(self.rim_thickness)
        self.reference_diameter = ParameterBox('基準円の直径', 150., 1., 10000., 1, ' mm')
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
        reference_note.deleteLater()
        left_layout.addWidget(reference_card)
        self.constraints = ConstraintPanel()
        note = QLabel('歯形は概略表示です。切下げ後の歯元形状・工具による創成・強度は未評価です。干渉は解析式で判定します。')
        note.setWordWrap(True)
        note.setObjectName('Muted')
        input_help.setText(input_help.text() + '\n\n基準円の直径は入力変更後も保持します。外周の厚さは歯元円から測ります。\n\n' + note.text())
        note.deleteLater()
        add_disclosure(left_layout, '入力について', input_help)
        left_layout.addStretch()
        scroll.setWidget(left)
        content.addWidget(scroll, 25)
        self.constraint_scroll = QScrollArea()
        self.constraint_scroll.setWidgetResizable(True)
        self.constraint_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.constraint_scroll.setMinimumWidth(410)
        self.constraint_scroll.setWidget(self.constraints)
        content.addWidget(self.constraint_scroll, 36)
        preview_card = QFrame()
        preview_card.setObjectName('Card')
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        top = QHBoxLayout()
        preview_title = QLabel('プレビュー')
        preview_title.setObjectName('PanelTitle')
        top.addWidget(preview_title)
        top.addStretch()
        self.status = QLabel()
        top.addWidget(self.status)
        preview_layout.addLayout(top)
        ratio_card = QFrame()
        ratio_card.setObjectName('RatioCard')
        ratio_layout = QVBoxLayout(ratio_card)
        ratio_layout.setContentsMargins(14, 12, 14, 12)
        self.ratio_value = QLabel()
        self.ratio_value.setWordWrap(True)
        self.ratio_value.setObjectName('RatioValue')
        ratio_layout.addWidget(self.ratio_value)
        ratio_caption = QLabel('リング固定｜太陽入力 → キャリア出力')
        ratio_caption.setToolTip('i = nₛ / n꜀ = 1 + zᵣ / zₛ')
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
        preview_layout.addWidget(QLabel('強度・加工性は未評価'))
        add_disclosure(preview_layout, '計算・モデルの詳細', self.geometry_note)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setWidget(preview_card)
        content.addWidget(self.preview_scroll, 39)
        main.addLayout(content, 1)
        main.addSpacing(8)
        for field in self.findChildren(ParameterBox):
            field.layout().setContentsMargins(0, 5, 0, 5)
            field.spin.setFixedWidth(160)
        self.update_model()

    def fit_planet(self):
        if self.shift_enabled.isChecked():
            return
        self.fit_feedback.show()
        required = (self.ring_teeth.value() - self.sun_teeth.value()) / 2
        if not required.is_integer():
            self.fit_feedback.setText(f'必要歯数は {required:g} 歯です。整数にならないため変更していません。太陽歯数の奇数・偶数をリングに合わせてください。')
            return
        spin = self.planet_teeth.spin
        if not spin.minimum() <= required <= spin.maximum():
            self.fit_feedback.setText(f'必要歯数 {required:g} は入力範囲（{spin.minimum()}〜{spin.maximum()} 歯）外です。変更していません。')
            return
        spin.setValue(int(required))
        self.fit_feedback.show()
        self.fit_feedback.setText(f'遊星を {required:g} 歯に設定しました。リング・太陽は維持しています。拘束かみ合いは別途判定します。')

    def update_model(self):
        self.fit_feedback.clear()
        self.fit_feedback.hide()
        shifted = self.shift_enabled.isChecked()
        self.shift_fields.setVisible(shifted)
        self.fit_planet_button.setEnabled(not shifted)
        self.fit_planet_button.setToolTip('転位ありでは歯数だけで中心距離が決まらないため使用できません。'
            if shifted else 'リングと太陽を保持し、遊星歯数 = (リング − 太陽) / 2 にします')
        self.spec = PlanetarySpec(module=float(self.module.value()),
            sun_teeth=int(self.sun_teeth.value()), planet_teeth=int(self.planet_teeth.value()),
            ring_teeth=int(self.ring_teeth.value()), planet_count=int(self.planet_count.value()),
            pressure_angle_deg=float(self.angle.value()),
            ring_rim_thickness=float(self.rim_thickness.value()),
            shift_enabled=shifted, sun_shift=self.sun_shift.value(),
            planet_shift=self.planet_shift.value(), ring_shift=self.ring_shift.value())
        checks = planetary_constraints(self.spec) + interference_checks(self.spec)
        self.preview.set_spec(self.spec, checks)
        self.constraints.update_constraints(checks, self.spec, self.dark)
        c = DARK if self.dark else LIGHT
        ok = not self.preview.issues
        self.ratio_value.setText(f'減速比　{self.spec.reduction_ratio:.4f} : 1'
                                + ('　（参考値）' if not ok else ''))
        self.ratio_value.setToolTip('太陽の回転数 ÷ キャリアの回転数。条件不適合時は歯数から求めた理論参考値です。')
        notices = [check for check in checks if not getattr(check, 'blocks_assembly', True) and tuple(check)[1] is not True]
        self.status.setText('× 要確認' if not ok else ('△ 加工・組立に注意' if notices else '✓ 検査項目に適合'))
        self.status.setWordWrap(True)
        self.status.setStyleSheet('color:' + (c['bad'] if not ok else c['warning'] if notices else c['good']))
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
        distances = []
        for name, attr in (('太陽–遊星', 'sun_planet'), ('遊星–リング', 'planet_ring')):
            try:
                a = getattr(s, attr + '_center_distance')
                aw = math.degrees(getattr(s, attr + '_working_angle'))
                distances.append(f'{name}：a = {a:.8f} mm、αw = {aw:.6f}°')
            except ValueError as exc:
                distances.append(f'{name}：{exc}')
        self.geometry_note.setText(('転位あり' if shifted else '転位なし') + '・理論バックラッシ0\n' + '\n'.join(distances)
            + '\n歯先短縮なし・標準歯たけの概略歯形。工具創成・強度・かみあい率は未評価です。')
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

    def set_theme(self, dark):
        self.dark = dark
        self.preview.set_theme(dark)
        self.update_model()
