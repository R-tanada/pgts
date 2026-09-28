"""歯車対のシーン描画・回転・パン／ズーム・PNG／SVG出力。"""
import numpy as np
from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsPathItem,
    QGraphicsItemGroup, QGraphicsScene, QGraphicsView,
)
from ui_common import DARK, LIGHT


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

        self.ink = LIGHT["accent"]
        self.highlight = LIGHT["bad"]
        self._pan_start = None
        self._view_initialized = False
        self._auto_fit = True
        self._fit_rect = None
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self._apply_fit)
        for scrollbar in (self.horizontalScrollBar(), self.verticalScrollBar()):
            scrollbar.sliderPressed.connect(self._stop_auto_fit)
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

    def _aux_color(self, name, highlight_aux):
        return QColor(self.highlight if highlight_aux == name else self.ink)

    def set_theme(self, dark):
        colors = DARK if dark else LIGHT
        self.ink, self.highlight = colors['accent'], colors['bad']
        self.setBackgroundBrush(QColor(colors['bg']))

    def clear_geometry(self):
        # Clear Python references together with their scene-owned C++ items.
        self._gear1_group = self._gear2_group = None
        self._animation_gear1 = self._animation_gear2 = None
        self._animation_contact_items = []
        self.scene.clear()

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
            self._stop_auto_fit()
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
        self._stop_auto_fit()
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
        pen = QPen(color or QColor(self.ink))
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
        pen = QPen(color or QColor(self.ink))
        pen.setWidthF(0.8)
        pen.setCosmetic(True)

        item = QGraphicsEllipseItem(-r, -r, 2.0 * r, 2.0 * r)
        item.setPen(pen)
        item.setBrush(QBrush(color or QColor(self.ink)))
        item.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        item.setPos(float(x), float(-y))
        self.scene.addItem(item)
        return item

    def _draw_single_gear(self, gear_model, center=(0.0, 0.0), root_shape="arc", rotation=0.0):
        cache = getattr(gear_model, '_preview_profiles', None)
        if cache is None:
            cache = gear_model._preview_profiles = {}
        if root_shape not in cache:
            with np.errstate(invalid='raise', divide='raise', over='raise'):
                profiles, undercut = gear_model.profile(root_shape=root_shape)
            for tooth in profiles:
                for x, y in tooth.values():
                    if not (np.all(np.isfinite(x)) and np.all(np.isfinite(y))):
                        raise ValueError('このパラメータでは有限な歯形を計算できません。')
            cache[root_shape] = profiles
        profiles = cache[root_shape]
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
                pen = QPen(QColor(self.ink))
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

        self._animation_base_rot1 = contact_rotation1 - animation_angle
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

            self._animation_base_rot2 = contact_rotation2 + animation_angle * gear1.z / gear2.z
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

        if not had_view or self._auto_fit:
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
        margin = gear1.m
        if show_mating and gear2 is not None:
            center_distance = gear1.pitch_radius + gear2.pitch_radius
            left = -gear1.addendum_radius - margin
            right = center_distance + gear2.addendum_radius + margin
            height = max(gear1.addendum_radius, gear2.addendum_radius) + margin
            rect = QRectF(left, -height, right-left, 2*height)
        else:
            limit = gear1.addendum_radius + gear1.m
            rect = QRectF(-limit, -limit, 2 * limit, 2 * limit)
        self._fit_rect = rect
        self._auto_fit = True
        self._apply_fit()

    def _stop_auto_fit(self):
        self._auto_fit = False
        self._fit_timer.stop()

    def _apply_fit(self):
        if self._auto_fit and self._fit_rect is not None:
            self.fitInView(self._fit_rect, Qt.KeepAspectRatio)
            self.centerOn(self._fit_rect.center())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Fit after the enclosing layout and scrollbars settle, not while
        # constructing the hidden widget with its temporary viewport size.
        if getattr(self, '_auto_fit', False) and hasattr(self, '_fit_timer'):
            self._fit_timer.start(0)

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
        generator.setViewBox(QRectF(0, 0, width, height))
        generator.setTitle("Involute Gear")

        painter = QPainter(generator)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self.scene.render(painter, QRectF(0, 0, width, height), rect)
        painter.end()


