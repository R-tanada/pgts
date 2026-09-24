import os
import time

import numpy as np

from PySide6.QtCore import QPoint, QRectF, QSize, QTimer, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsItemGroup,
    QGraphicsScene,
    QGraphicsView,
)

from gear import Gear, InvoluteGear


# ============================================================
# QGraphicsView based gear canvas
# ============================================================

class GearView(QGraphicsView):
    """歯車プレビュー用QGraphicsView。

    シーン座標は x=右、y=上の数学座標になるよう、描画時に
    y座標だけ反転している。左ドラッグでパン、ホイールでズーム。
    """

    def __init__(self, parent=None):
        self.scene = QGraphicsScene()
        super().__init__(self.scene, parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setBackgroundBrush(Qt.transparent)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setInteractive(False)
        self.setMouseTracking(True)

        self._pan_start = None
        self._view_initialized = False
        self._preview_render_ms = 40.0

        # アニメーション用。歯車形状は毎フレーム再計算せず、
        # GraphicsItem の回転だけを更新する。
        self._gear1_group = None
        self._gear2_group = None
        self._animation_gear1 = None
        self._animation_gear2 = None
        self._animation_gear2_center = None
        self._animation_contact_items = []
        self._animation_base_rot1 = 0.0
        self._animation_base_rot2 = 0.0
        self._animation_highlight_aux = "なし"

    @staticmethod
    def _aux_color(name, highlight_aux):
        return QColor("red") if highlight_aux == name else QColor("black")

    # ----------------------------
    # マウス操作
    # ----------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pan_start = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_start is not None:
            pos = event.position().toPoint()

            # QGraphicsView のスクロールバーを画面ピクセル量で動かす。
            # これならズーム倍率に関係なく、マウスを動かした方向・量と
            # コンテンツの移動方向・量が一致する。
            dx = pos.x() - self._pan_start.x()
            dy = pos.y() - self._pan_start.y()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - dx
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - dy
            )
            self._pan_start = pos

            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pan_start = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        pos = event.position().toPoint()
        before = self.mapToScene(pos)
        scale = 1.15 if event.angleDelta().y() > 0 else (1.0 / 1.15)
        self.scale(scale, scale)
        after = self.mapToScene(pos)
        delta = after - before
        self.translate(delta.x(), delta.y())
        event.accept()

    # ----------------------------
    # 描画ヘルパ
    # ----------------------------
    @staticmethod
    def _path_from_xy(x, y):
        path = QPainterPath()
        if len(x) == 0:
            return path
        path.moveTo(float(x[0]), float(-y[0]))
        for xi, yi in zip(x[1:], y[1:]):
            path.lineTo(float(xi), float(-yi))
        return path

    def _add_path(self, x, y, width=1.5, dashed=False, color=None):
        item = QGraphicsPathItem(self._path_from_xy(x, y))
        pen = QPen(color or QColor("black"))
        # 線幅はシーン座標ではなく画面上のpxで一定にする。
        pen.setWidthF(width)
        pen.setCosmetic(True)
        if dashed:
            pen.setStyle(Qt.DashLine)
        item.setPen(pen)
        item.setBrush(Qt.NoBrush)
        self.scene.addItem(item)
        return item

    def _add_point(self, x, y, diameter=7.0, color=None):
        # 点は「中心位置」をscene座標で持ち、ズームしても
        # 画面上の大きさだけ一定にする。
        # ItemIgnoresTransformations を使う場合、scene座標そのものに
        # 楕円を置くのではなく、原点中心のローカル楕円を setPos()
        # する必要がある。
        r = diameter / 2.0
        pen = QPen(color or QColor("black"))
        pen.setWidthF(0.8)
        pen.setCosmetic(True)

        item = QGraphicsEllipseItem(-r, -r, 2.0 * r, 2.0 * r)
        item.setPen(pen)
        item.setBrush(QBrush(color or QColor("black")))
        item.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        item.setPos(float(x), float(-y))
        self.scene.addItem(item)
        return item

    def _draw_single_gear(self, gear_model, center=(0.0, 0.0), root_shape="arc", rotation=0.0):
        profiles, _ = gear_model.profile(root_shape=root_shape)
        cx, cy = center

        # 歯車形状はローカル座標で一度だけ生成し、
        # 回転はグループ全体に与える。これによりアニメーション時の
        # トロコイド再計算・全Path再生成を避ける。
        group = QGraphicsItemGroup()
        self.scene.addItem(group)

        # 子要素を先にグループへ追加してから、グループの位置・回転を設定する。
        # QGraphicsItemGroupは、位置を先に設定してからaddToGroup()すると
        # 子要素のシーン座標を保持するために内部変換が入るため、
        # 歯車2の中心が歯車1側へ戻る原因になる。
        for tooth in profiles:
            for key in ("right_flank", "tip", "left_flank", "root"):
                x, y = tooth[key]
                item = QGraphicsPathItem(self._path_from_xy(x, y))
                pen = QPen(QColor("black"))
                pen.setWidthF(1.5)
                pen.setCosmetic(True)
                item.setPen(pen)
                item.setBrush(Qt.NoBrush)
                group.addToGroup(item)

        # グループ完成後に中心位置と回転を与える。
        group.setPos(float(cx), float(-cy))
        group.setRotation(-np.degrees(rotation))

        return group

    def _draw_aux_line(self, x, y, color=None):
        self._add_path(x, y, width=0.7, dashed=True, color=color)

    def _draw_circle(self, radius, center=(0.0, 0.0), color=None):
        theta = np.linspace(0.0, 2.0 * np.pi, 720)
        cx, cy = center
        self._add_path(
            cx + radius * np.cos(theta),
            cy + radius * np.sin(theta),
            width=0.7,
            dashed=True,
            color=color,
        )

    @staticmethod
    def _contact_positions(gear1, gear2, phi1):
        rb1 = gear1.base_radius
        rb2 = gear2.base_radius
        ra1 = gear1.addendum_radius
        ra2 = gear2.addendum_radius
        alpha = gear1.alpha

        beta = np.pi / 2 - alpha
        direction = np.array([np.cos(beta), np.sin(beta)])

        approach = (
            np.sqrt(max(0.0, ra2**2 - rb2**2))
            - gear2.pitch_radius * np.sin(alpha)
        )
        recess = (
            np.sqrt(max(0.0, ra1**2 - rb1**2))
            - gear1.pitch_radius * np.sin(alpha)
        )

        phase = (
            (phi1 + gear1.pitch_angle / 2.0) % gear1.pitch_angle
        ) - gear1.pitch_angle / 2.0

        offset = rb1 * phase
        base_pitch = np.pi * gear1.m * np.cos(alpha)

        k_min = int(np.floor((-approach - offset) / base_pitch)) - 1
        k_max = int(np.ceil((recess - offset) / base_pitch)) + 1

        points = []
        for k in range(k_min, k_max + 1):
            travel = offset + k * base_pitch
            if -approach - 1e-9 <= travel <= recess + 1e-9:
                point = np.array([gear1.pitch_radius, 0.0]) + travel * direction
                points.append((point[0], point[1]))

        points.sort(key=lambda p: p[0] * direction[0] + p[1] * direction[1])
        return points

    # ----------------------------
    # メイン描画
    # ----------------------------
    def draw_gear(
        self,
        gear1,
        gear2=None,
        show_reference_circle=False,
        show_pitch_point=False,
        show_base_circle=False,
        show_root_circle=False,
        show_addendum_circle=False,
        show_action_line=False,
        show_mating_gear=False,
        show_center_line=False,
        show_midline=False,
        highlight_aux="なし",
        root_shape="arc",
        animation_angle=0.0,
        show_contact_point=False,
        render=True,
    ):
        old_center = self.mapToScene(self.viewport().rect().center())
        had_view = self._view_initialized
        old_transform = self.transform() if had_view else None

        self.scene.clear()
        self.scene.setSceneRect(QRectF())
        self._gear1_group = None
        self._gear2_group = None
        self._animation_gear1 = gear1
        self._animation_gear2 = gear2 if show_mating_gear else None
        self._animation_gear2_center = None
        self._animation_contact_items = []
        self._animation_highlight_aux = highlight_aux

        contact_rotation1 = (
            -(np.pi / 2 + gear1.half_tooth_angle()) + animation_angle
        )

        self._animation_base_rot1 = contact_rotation1
        self._gear1_group = self._draw_single_gear(
            gear1, (0.0, 0.0), root_shape=root_shape, rotation=contact_rotation1
        )
        self._add_point(0.0, 0.0, diameter=7.0)

        if show_reference_circle:
            self._draw_circle(gear1.pitch_radius, color=self._aux_color("基準円", highlight_aux))
        if show_base_circle:
            self._draw_circle(gear1.base_radius, color=self._aux_color("基礎円", highlight_aux))
        if show_root_circle:
            root_radius = gear1.arc_root_radius if root_shape == "arc" else gear1.root_radius
            self._draw_circle(root_radius, color=self._aux_color("歯底円", highlight_aux))
        if show_addendum_circle:
            self._draw_circle(gear1.addendum_radius, color=self._aux_color("歯先円", highlight_aux))

        gear2_center = None
        if show_mating_gear and gear2 is not None:
            center_distance = gear1.pitch_radius + gear2.pitch_radius
            gear2_center = (center_distance, 0.0)
            self._animation_gear2_center = gear2_center
            backlash_phase2 = gear2.backlash / gear2.pitch_radius
            contact_rotation2 = (
                np.pi / 2
                - gear2.half_tooth_angle()
                + backlash_phase2
                - animation_angle * gear1.z / gear2.z
            )

            self._animation_base_rot2 = contact_rotation2
            self._gear2_group = self._draw_single_gear(
                gear2,
                gear2_center,
                root_shape=root_shape,
                rotation=contact_rotation2,
            )
            self._add_point(gear2_center[0], gear2_center[1], diameter=7.0)

            if show_center_line:
                self._draw_aux_line(
                    [0.0, gear2_center[0]], [0.0, 0.0],
                    color=self._aux_color("中心を結ぶ線", highlight_aux),
                )

            if show_midline:
                xp = gear1.pitch_radius
                span = max(gear1.addendum_radius, gear2.addendum_radius) + gear1.m
                self._draw_aux_line(
                    [xp, xp], [-span, span],
                    color=self._aux_color("中央の線", highlight_aux),
                )

            if show_reference_circle:
                self._draw_circle(gear2.pitch_radius, gear2_center, color=self._aux_color("基準円", highlight_aux))
            if show_base_circle:
                self._draw_circle(gear2.base_radius, gear2_center, color=self._aux_color("基礎円", highlight_aux))
            if show_root_circle:
                root_radius = gear2.arc_root_radius if root_shape == "arc" else gear2.root_radius
                self._draw_circle(root_radius, gear2_center, color=self._aux_color("歯底円", highlight_aux))
            if show_addendum_circle:
                self._draw_circle(gear2.addendum_radius, gear2_center, color=self._aux_color("歯先円", highlight_aux))

            if show_pitch_point:
                self._add_point(
                    gear1.pitch_radius, 0.0, diameter=8.0,
                    color=self._aux_color("ピッチ点", highlight_aux),
                )

            if show_action_line:
                alpha = gear1.alpha
                line_angle = np.pi / 2 - alpha
                dx = np.cos(line_angle)
                dy = np.sin(line_angle)
                x0 = gear1.pitch_radius
                length = gear1.addendum_radius + gear2.addendum_radius
                self._add_path(
                    [x0 - length * dx, x0 + length * dx],
                    [-(length * dy), length * dy],
                    width=0.7,
                    dashed=True,
                    color=self._aux_color("力の作用線", highlight_aux),
                )

            if show_contact_point:
                # アニメーション中にプレビューを再構築した場合も、
                # ここで生成した接触点を動的Itemとして管理する。
                # これを管理リストに入れないと、次のanimation stepで
                # 古い接触点が残り、新しい点と重なって表示される。
                for cx, cy in self._contact_positions(gear1, gear2, animation_angle):
                    self._animation_contact_items.append(
                        self._add_point(cx, cy, diameter=8.0, color=self._aux_color("ピッチ点", highlight_aux))
                    )

        else:
            if show_midline:
                xp = gear1.pitch_radius
                span = gear1.addendum_radius + gear1.m
                self._draw_aux_line(
                    [xp, xp], [-span, span],
                    color=self._aux_color("中央の線", highlight_aux),
                )

            if show_pitch_point:
                self._add_point(
                    gear1.pitch_radius, 0.0, diameter=8.0,
                    color=self._aux_color("ピッチ点", highlight_aux),
                )

            if show_action_line:
                alpha = gear1.alpha
                line_angle = np.pi / 2 - alpha
                dx = np.cos(line_angle)
                dy = np.sin(line_angle)
                x0 = gear1.pitch_radius
                length = gear1.addendum_radius * 2.0
                self._add_path(
                    [x0 - length * dx, x0 + length * dx],
                    [-length * dy, length * dy],
                    width=0.7,
                    dashed=True,
                    color=self._aux_color("力の作用線", highlight_aux),
                )

        # シーン矩形は十分大きく確保する。
        # 内容ぴったりの矩形だと、未ズーム時にスクロールバーの可動域が
        # ほぼゼロになり、パンできなくなるため。
        content_rect = self.scene.itemsBoundingRect().adjusted(-1.0, -1.0, 1.0, 1.0)
        if content_rect.isValid():
            margin = max(content_rect.width(), content_rect.height(), 100.0) * 10.0
            self.scene.setSceneRect(
                content_rect.adjusted(-margin, -margin, margin, margin)
            )

        if not had_view:
            self._fit_initial_view(gear1, gear2, show_mating_gear)
            self._view_initialized = True
        else:
            self.setTransform(old_transform)
            new_center = self.mapFromScene(old_center)
            viewport_center = self.viewport().rect().center()
            delta = viewport_center - new_center
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())

        if render:
            self.viewport().update()

    def update_animation(self, animation_angle, show_contact_point=True):
        """アニメーション中は歯車の回転だけを更新する。"""
        gear1 = self._animation_gear1
        gear2 = self._animation_gear2
        if gear1 is None or self._gear1_group is None:
            return

        # 描画時に決めた初期位相をそのまま基準にする。
        # これによりアニメーション開始時に歯車2だけ位相がずれることを防ぐ。
        rot1 = self._animation_base_rot1 + animation_angle
        self._gear1_group.setRotation(-np.degrees(rot1))

        if gear2 is not None and self._gear2_group is not None:
            rot2 = self._animation_base_rot2 - animation_angle * gear1.z / gear2.z
            self._gear2_group.setRotation(-np.degrees(rot2))

        # 接触点だけは最大2点なので、ここだけ更新する。
        for item in self._animation_contact_items:
            self.scene.removeItem(item)
            del item
        self._animation_contact_items = []

        if show_contact_point and gear2 is not None:
            for cx, cy in self._contact_positions(gear1, gear2, animation_angle):
                self._animation_contact_items.append(
                    self._add_point(cx, cy, diameter=8.0, color=self._aux_color("ピッチ点", self._animation_highlight_aux))
                )

        self.viewport().update()

    def _fit_initial_view(self, gear1, gear2, show_mating):
        if show_mating and gear2 is not None:
            center_distance = gear1.pitch_radius + gear2.pitch_radius
            limit = center_distance + gear2.addendum_radius + gear2.m
            rect = QRectF(
                -gear1.addendum_radius - gear1.m,
                -limit * 0.55,
                limit + gear1.addendum_radius + gear1.m,
                limit * 1.10,
            )
        else:
            limit = gear1.addendum_radius + gear1.m
            rect = QRectF(-limit, -limit, 2 * limit, 2 * limit)
        self.fitInView(rect, Qt.KeepAspectRatio)

    # ----------------------------
    # 出力
    # ----------------------------
    def visible_scene_rect(self):
        return self.mapToScene(self.viewport().rect()).boundingRect()

    def render_to_image(self, rect=None, width=None, height=None):
        if rect is None:
            rect = self.visible_scene_rect()
        if width is None or height is None:
            size = self.viewport().size()
            width = max(1, size.width())
            height = max(1, size.height())

        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self.scene.render(painter, QRectF(0, 0, width, height), rect)
        painter.end()
        return image

    def render_svg(self, filename, rect=None, width=1400, height=1400):
        from PySide6.QtSvg import QSvgGenerator

        if rect is None:
            rect = self.scene.itemsBoundingRect().adjusted(-1, -1, 1, 1)
        generator = QSvgGenerator()
        generator.setFileName(filename)
        generator.setSize(QSize(width, height))
        generator.setViewBox(rect)
        generator.setTitle("Involute Gear")

        painter = QPainter(generator)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self.scene.render(painter, QRectF(0, 0, width, height), rect)
        painter.end()


class GearWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Involute Gear Image Generator")
        self.resize(1250, 800)

        self.canvas = GearView()

        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._animation_step)
        self.animation_angle = 0.0

        common_group = QGroupBox("共通設定")
        common_form = QFormLayout()

        self.module_spin = QDoubleSpinBox()
        self.module_spin.setRange(0.1, 100.0)
        self.module_spin.setSingleStep(0.1)
        self.module_spin.setDecimals(2)
        self.module_spin.setValue(2.0)
        self.module_spin.setSuffix(" mm")

        self.pressure_spin = QDoubleSpinBox()
        self.pressure_spin.setRange(1.0, 45.0)
        self.pressure_spin.setSingleStep(1.0)
        self.pressure_spin.setDecimals(1)
        self.pressure_spin.setValue(20.0)
        self.pressure_spin.setSuffix(" °")

        self.backlash_spin = QDoubleSpinBox()
        self.backlash_spin.setRange(0.0, 2.0)
        self.backlash_spin.setSingleStep(0.05)
        self.backlash_spin.setDecimals(2)
        self.backlash_spin.setValue(0.0)
        self.backlash_spin.setSuffix(" mm")

        common_form.addRow("モジュール", self.module_spin)
        common_form.addRow("圧力角", self.pressure_spin)
        common_form.addRow("バックラッシ", self.backlash_spin)
        common_group.setLayout(common_form)

        gear1_group = QGroupBox("歯車1")
        form1 = QFormLayout()
        self.teeth1_spin = QSpinBox()
        self.teeth1_spin.setRange(3, 500)
        self.teeth1_spin.setValue(20)
        self.shift1_spin = QDoubleSpinBox()
        self.shift1_spin.setRange(-1.0, 1.0)
        self.shift1_spin.setSingleStep(0.05)
        self.shift1_spin.setDecimals(2)
        self.shift1_spin.setValue(0.0)
        form1.addRow("歯数", self.teeth1_spin)
        form1.addRow("転位係数", self.shift1_spin)
        gear1_group.setLayout(form1)

        gear2_group = QGroupBox("歯車2")
        form2 = QFormLayout()
        self.teeth2_spin = QSpinBox()
        self.teeth2_spin.setRange(3, 500)
        self.teeth2_spin.setValue(20)
        self.shift2_spin = QDoubleSpinBox()
        self.shift2_spin.setRange(-1.0, 1.0)
        self.shift2_spin.setSingleStep(0.05)
        self.shift2_spin.setDecimals(2)
        self.shift2_spin.setValue(0.0)
        form2.addRow("歯数", self.teeth2_spin)
        form2.addRow("転位係数", self.shift2_spin)
        gear2_group.setLayout(form2)

        display_group = QGroupBox("表示")
        display_layout = QVBoxLayout()

        self.reference_check = QCheckBox("基準円")
        self.pitch_point_check = QCheckBox("ピッチ点")
        self.mating_check = QCheckBox("ついになる歯車")
        self.base_check = QCheckBox("基礎円")
        self.root_check = QCheckBox("歯底円")
        self.addendum_check = QCheckBox("歯先円")
        self.root_shape_combo = QComboBox()
        self.root_shape_combo.addItems(["円弧", "トロコイド"])
        self.action_line_check = QCheckBox("力の作用線")
        self.center_line_check = QCheckBox("中心を結ぶ線")
        self.midline_check = QCheckBox("中央の線（ピッチ点を通る垂直線）")
        self.highlight_combo = QComboBox()
        self.highlight_combo.addItems([
            "なし",
            "基準円",
            "ピッチ点",
            "基礎円",
            "歯底円",
            "歯先円",
            "力の作用線",
            "中心を結ぶ線",
            "中央の線",
        ])

        for w in (
            self.reference_check,
            self.pitch_point_check,
            self.mating_check,
            self.base_check,
        ):
            display_layout.addWidget(w)

        root_shape_layout = QHBoxLayout()
        root_shape_layout.addWidget(self.root_check)
        root_shape_layout.addWidget(self.root_shape_combo)
        root_shape_layout.addStretch()
        display_layout.addLayout(root_shape_layout)

        for w in (
            self.addendum_check,
            self.action_line_check,
            self.center_line_check,
            self.midline_check,
        ):
            display_layout.addWidget(w)

        highlight_layout = QHBoxLayout()
        highlight_layout.addWidget(QLabel("強調する補助線"))
        highlight_layout.addWidget(self.highlight_combo)
        display_layout.addLayout(highlight_layout)
        display_group.setLayout(display_layout)

        animation_group = QGroupBox("かみ合いシミュレーション")
        animation_layout = QHBoxLayout()
        self.play_button = QPushButton("▶ 再生")
        self.stop_button = QPushButton("■ 停止")
        self.play_button.clicked.connect(self.start_animation)
        self.stop_button.clicked.connect(self.stop_animation)
        animation_layout.addWidget(self.play_button)
        animation_layout.addWidget(self.stop_button)
        animation_group.setLayout(animation_layout)

        self.save_button = QPushButton("画像を保存")
        self.save_button.clicked.connect(self.save_image)
        left_layout = QVBoxLayout()
        left_layout.addWidget(common_group)
        left_layout.addWidget(gear1_group)
        left_layout.addWidget(gear2_group)
        left_layout.addWidget(display_group)
        left_layout.addWidget(animation_group)
        left_layout.addWidget(self.save_button)
        left_layout.addStretch()

        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        left_widget.setFixedWidth(300)

        main_layout = QHBoxLayout()
        main_layout.addWidget(left_widget)
        main_layout.addWidget(self.canvas, 1)

        central = QWidget()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        for widget in (
            self.module_spin,
            self.pressure_spin,
            self.backlash_spin,
            self.teeth1_spin,
            self.shift1_spin,
            self.teeth2_spin,
            self.shift2_spin,
        ):
            widget.valueChanged.connect(self.update_preview)

        for widget in (
            self.reference_check,
            self.pitch_point_check,
            self.mating_check,
            self.base_check,
            self.root_check,
            self.addendum_check,
            self.action_line_check,
            self.center_line_check,
            self.midline_check,
        ):
            widget.toggled.connect(self.update_preview)

        self.root_shape_combo.currentIndexChanged.connect(self.update_preview)
        self.highlight_combo.currentIndexChanged.connect(self.update_preview)
        self.update_preview()

    def make_gears(self):
        common = dict(
            module=self.module_spin.value(),
            pressure_angle_deg=self.pressure_spin.value(),
            backlash=self.backlash_spin.value(),
        )
        gear1 = InvoluteGear(
            Gear(**common, teeth=self.teeth1_spin.value(), profile_shift=self.shift1_spin.value())
        )
        gear2 = InvoluteGear(
            Gear(**common, teeth=self.teeth2_spin.value(), profile_shift=self.shift2_spin.value())
        )
        return gear1, gear2

    def _root_shape(self):
        return "trochoid" if self.root_shape_combo.currentIndex() == 1 else "arc"

    def update_preview(self):
        t0 = time.perf_counter()
        try:
            gear1, gear2 = self.make_gears()
            self.canvas.draw_gear(
                gear1,
                gear2,
                show_reference_circle=self.reference_check.isChecked(),
                show_pitch_point=self.pitch_point_check.isChecked(),
                show_base_circle=self.base_check.isChecked(),
                show_root_circle=self.root_check.isChecked(),
                show_addendum_circle=self.addendum_check.isChecked(),
                show_action_line=self.action_line_check.isChecked(),
                show_mating_gear=self.mating_check.isChecked(),
                show_center_line=self.center_line_check.isChecked(),
                show_midline=self.midline_check.isChecked(),
                highlight_aux=self.highlight_combo.currentText(),
                root_shape=self._root_shape(),
                animation_angle=self.animation_angle,
                show_contact_point=self.timer.isActive(),
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self.canvas._preview_render_ms = (
                0.8 * self.canvas._preview_render_ms + 0.2 * elapsed_ms
            )
        except Exception as e:
            self.canvas.scene.clear()
            text = self.canvas.scene.addText(f"計算エラー\n{e}")
            text.setDefaultTextColor(Qt.black)
            text.setPos(0, 0)
            self.canvas.viewport().update()

    def start_animation(self):
        if not self.mating_check.isChecked():
            self.mating_check.setChecked(True)
        self.timer.start()

    def stop_animation(self):
        self.timer.stop()
        self.animation_angle = 0.0
        self.update_preview()

    def _animation_step(self):
        self.animation_angle += np.deg2rad(1.0)
        if self.animation_angle >= 2 * np.pi:
            self.animation_angle -= 2 * np.pi
        self.canvas.update_animation(self.animation_angle, show_contact_point=True)

    def save_image(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "画像を保存",
            "gear.png",
            "PNG (*.png)",
        )
        if not filename:
            return

        gear1, gear2 = self.make_gears()
        self.canvas.draw_gear(
            gear1,
            gear2,
            show_reference_circle=self.reference_check.isChecked(),
            show_pitch_point=self.pitch_point_check.isChecked(),
            show_base_circle=self.base_check.isChecked(),
            show_root_circle=self.root_check.isChecked(),
            show_addendum_circle=self.addendum_check.isChecked(),
            show_action_line=self.action_line_check.isChecked(),
            show_mating_gear=self.mating_check.isChecked(),
            show_center_line=self.center_line_check.isChecked(),
            show_midline=self.midline_check.isChecked(),
            highlight_aux=self.highlight_combo.currentText(),
            root_shape=self._root_shape(),
            animation_angle=0.0,
            show_contact_point=False,
        )

        try:
            rect = self.canvas.scene.itemsBoundingRect().adjusted(-1, -1, 1, 1)
            # 旧版の600 dpi出力を意識した高解像度PNG。
            size = 1400
            image = self.canvas.render_to_image(rect=rect, width=size, height=size)
            image.setDotsPerMeterX(int(600 / 0.0254))
            image.setDotsPerMeterY(int(600 / 0.0254))
            if not image.save(filename, "PNG"):
                raise RuntimeError("PNGの保存に失敗しました")
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", f"画像の保存に失敗しました。\n\n{e}")

def create_window():
    return GearWindow()
