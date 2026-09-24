
import numpy as np
from dataclasses import dataclass


# ============================================================
# 歯車パラメータ
# ============================================================

@dataclass
class Gear:
    # 基本諸元
    module: float = 2.0
    teeth: int = 20
    pressure_angle_deg: float = 20.0

    # 転位係数
    profile_shift: float = 0.0

    # 歯車対の円周方向バックラッシ [mm]
    # 歯車対全体のピッチ円上の隙間として扱う。
    backlash: float = 0.0

    # 標準歯車
    addendum_coefficient: float = 1.0
    dedendum_coefficient: float = 1.25

    # ラック工具のクリアランス係数
    clearance_coefficient: float = 0.25

    # 描画点数
    points: int = 400


# ============================================================
# インボリュート歯車クラス
# ============================================================

class InvoluteGear:

    def __init__(self, gear: Gear):

        self.g = gear

        self.m = gear.module
        self.z = gear.teeth

        self.alpha = np.deg2rad(
            gear.pressure_angle_deg
        )

        self.x = gear.profile_shift
        self.backlash = max(0.0, gear.backlash)

        self.ha = gear.addendum_coefficient
        self.hf = gear.dedendum_coefficient

        self.c = gear.clearance_coefficient

        self._calculate_dimensions()


    # ========================================================
    # 基本寸法
    # ========================================================

    def _calculate_dimensions(self):

        # ----------------------------------------------------
        # ピッチ円
        # ----------------------------------------------------

        self.pitch_radius = (
            self.m * self.z / 2
        )

        self.pitch_diameter = (
            2 * self.pitch_radius
        )

        # ----------------------------------------------------
        # 基礎円
        # ----------------------------------------------------

        self.base_radius = (
            self.pitch_radius
            * np.cos(self.alpha)
        )

        self.base_diameter = (
            2 * self.base_radius
        )

        # ----------------------------------------------------
        # 歯先円
        # ----------------------------------------------------

        self.addendum_radius = (
            self.pitch_radius
            + self.m
            * (
                self.ha
                + self.x
            )
        )

        self.addendum_diameter = (
            2 * self.addendum_radius
        )

        # ----------------------------------------------------
        # 歯底円
        # ----------------------------------------------------

        self.root_radius = (
            self.pitch_radius
            - self.m
            * (
                self.hf
                - self.x
            )
        )

        # 円弧表示用の歯底半径。
        # 標準歯車では基準円から 1.25m 内側。
        # 転位の有無にかかわらず、表示上の「円弧」はこの基準で描く。
        self.arc_root_radius = (
            self.pitch_radius - 1.25 * self.m
        )

        self.root_diameter = (
            2 * self.root_radius
        )

        # ----------------------------------------------------
        # 1歯のピッチ角
        # ----------------------------------------------------

        self.pitch_angle = (
            2 * np.pi / self.z
        )

        # ----------------------------------------------------
        # ラック工具先端R
        # ----------------------------------------------------

        self.cutter_tip_radius = (
            self.c * self.m
            / (
                1
                - np.sin(self.alpha)
            )
        )


    # ========================================================
    # インボリュート関数
    # ========================================================

    @staticmethod
    def involute_function(t):

        return (
            t
            - np.arctan(t)
        )


    # ========================================================
    # インボリュート座標
    # ========================================================

    def involute_xy(self, t):

        rb = self.base_radius

        x = rb * (
            np.cos(t)
            + t * np.sin(t)
        )

        y = rb * (
            np.sin(t)
            - t * np.cos(t)
        )

        return x, y


    # ========================================================
    # ラック工具による歯元トロコイド
    # ========================================================

    def trochoid_xy(self, psi):

        r = self.pitch_radius
        m = self.m
        alpha = self.alpha
        x_shift = self.x

        # ----------------------------------------------------
        # ラック工具先端R
        # ----------------------------------------------------

        rr = self.cutter_tip_radius

        # ----------------------------------------------------
        # ラック工具の基本寸法
        # ----------------------------------------------------

        a0 = (
            self.ha * m
            + self.c * m
            - rr
        )

        b = (
            np.pi * m / 4
            + self.ha * m * np.tan(alpha)
            + rr * np.cos(alpha)
        )

        # ----------------------------------------------------
        # 転位による工具位置変化
        # ----------------------------------------------------

        a1 = (
            a0
            - x_shift * m
        )

        # ----------------------------------------------------
        # ラック工具の回転角
        # ----------------------------------------------------

        u = (
            a1 / np.tan(psi)
            + b
        ) / r

        # ----------------------------------------------------
        # トロコイド
        # ----------------------------------------------------

        x = (
            r * np.sin(u)
            - (
                a1 / np.sin(psi)
                + rr
            )
            * np.cos(psi - u)
        )

        y = (
            r * np.cos(u)
            - (
                a1 / np.sin(psi)
                + rr
            )
            * np.sin(psi - u)
        )

        return x, y


    # ========================================================
    # ピッチ円上の歯厚
    # ========================================================

    def half_tooth_angle(self):

        return (
            np.pi / (2 * self.z)
            + (
                2
                * self.x
                * np.tan(self.alpha)
                / self.z
            )
        )


    # ========================================================
    # インボリュートの配置角
    # ========================================================

    def backlash_flank_angle(self):
        """バックラッシをフランクの角度移動量へ変換する。

        ``backlash`` は歯車対全体のピッチ円上の円周方向隙間 [mm]。
        その隙間を2つの歯車で等分するため、各歯車の各フランクは
        ピッチ円上で backlash/2 だけ内側へ移動させる。
        """
        return self.backlash / (2.0 * self.pitch_radius)

    def involute_rotation(self):

        r = self.pitch_radius
        rb = self.base_radius

        half_tooth = (
            self.half_tooth_angle()
        )

        # ピッチ円上のインボリュートパラメータ

        t_pitch = np.sqrt(
            (
                r / rb
            ) ** 2
            - 1
        )

        inv_pitch = (
            self.involute_function(
                t_pitch
            )
        )

        # 歯の中心線をY軸方向に置く

        rotation = (
            np.pi / 2
            - half_tooth
            - inv_pitch
        )

        return rotation


    # ========================================================
    # インボリュートとトロコイドの交点
    # ========================================================

    def find_transition(self):

        alpha = self.alpha

        # ----------------------------------------------------
        # トロコイドを生成
        # ----------------------------------------------------

        psi = np.linspace(
            alpha,
            np.pi / 2,
            self.g.points * 10
        )

        xt, yt = self.trochoid_xy(
            psi
        )

        radius = np.hypot(
            xt,
            yt
        )

        angle_root = np.unwrap(
            np.arctan2(
                yt,
                xt
            )
        )

        # ----------------------------------------------------
        # インボリュート側
        # ----------------------------------------------------

        rotation = (
            self.involute_rotation()
        )

        rb = self.base_radius

        valid = radius >= rb

        diff = np.full_like(
            radius,
            np.nan
        )

        t = np.zeros_like(
            radius
        )

        t[valid] = np.sqrt(
            (
                radius[valid] / rb
            ) ** 2
            - 1
        )

        involute_angle = (
            rotation
            + self.involute_function(t)
        )

        diff[valid] = (
            angle_root[valid]
            - involute_angle[valid]
        )

        # ----------------------------------------------------
        # 交点
        # ----------------------------------------------------

        crossings = []

        for i in range(
            1,
            len(psi)
        ):

            if not (
                np.isfinite(diff[i - 1])
                and np.isfinite(diff[i])
            ):
                continue

            if (
                diff[i - 1]
                * diff[i]
                < 0
            ):

                crossings.append(i)

        # ----------------------------------------------------
        # 交点なし
        # ----------------------------------------------------

        if len(crossings) == 0:

            return alpha, False

        # ----------------------------------------------------
        # 最初の有効な交点
        # ----------------------------------------------------

        for idx in crossings:

            if (
                psi[idx]
                - alpha
                > np.deg2rad(0.05)
            ):

                return (
                    psi[idx],
                    True
                )

        return alpha, False


    # ========================================================
    # 1歯の右歯面
    # ========================================================

    def right_flank(self):

        psi_transition, undercut = (
            self.find_transition()
        )

        # ----------------------------------------------------
        # トロコイド
        # ----------------------------------------------------

        psi_root = np.linspace(
            np.pi / 2,
            psi_transition,
            self.g.points
        )

        xt, yt = self.trochoid_xy(
            psi_root
        )

        # ----------------------------------------------------
        # 接続点半径
        # ----------------------------------------------------

        r_transition = np.hypot(
            xt[-1],
            yt[-1]
        )

        # ----------------------------------------------------
        # インボリュート
        # ----------------------------------------------------

        rb = self.base_radius

        t_start = np.sqrt(
            (
                r_transition / rb
            ) ** 2
            - 1
        )

        t_end = np.sqrt(
            (
                self.addendum_radius / rb
            ) ** 2
            - 1
        )

        t_inv = np.linspace(
            t_start,
            t_end,
            self.g.points
        )

        xi, yi = self.involute_xy(
            t_inv
        )

        rotation = (
            self.involute_rotation()
        )

        xi_rot = (
            xi * np.cos(rotation)
            - yi * np.sin(rotation)
        )

        yi_rot = (
            xi * np.sin(rotation)
            + yi * np.cos(rotation)
        )

        # ----------------------------------------------------
        # トロコイド + インボリュート
        # ----------------------------------------------------

        x = np.concatenate([
            xt,
            xi_rot
        ])

        y = np.concatenate([
            yt,
            yi_rot
        ])

        # バックラッシは、元の歯形を壊さずフランク全体を
        # 歯の中心側へ周方向に移動して表現する。
        # 0 mm なら v15 の歯形と完全に同一になる。
        delta = self.backlash_flank_angle()
        if delta != 0.0:
            x, y = self.rotate(x, y, delta)

        return x, y, undercut


    # ========================================================
    # 円弧モデル用の簡略歯面
    # ========================================================

    def right_flank_arc(self):
        """加工を無視した簡略モデルの右歯面。

        トロコイド計算は一切行わず、歯底円から基礎円までは
        半径方向の直線、基礎円から歯先円まではインボリュートとする。
        """
        rb = self.base_radius
        r_root = self.arc_root_radius

        t_end = np.sqrt(
            max(0.0, (self.addendum_radius / rb) ** 2 - 1.0)
        )
        t_inv = np.linspace(0.0, t_end, self.g.points)
        xi, yi = self.involute_xy(t_inv)
        rotation = self.involute_rotation()
        xi_rot, yi_rot = self.rotate(xi, yi, rotation)

        # 基礎円上の始点と同じ角度で歯底円まで半径方向に延長。
        theta0 = np.arctan2(yi_rot[0], xi_rot[0])
        x_root = r_root * np.cos(theta0)
        y_root = r_root * np.sin(theta0)

        x = np.concatenate([[x_root], xi_rot])
        y = np.concatenate([[y_root], yi_rot])
        delta = self.backlash_flank_angle()
        if delta != 0.0:
            x, y = self.rotate(x, y, delta)

        return x, y, False

    def left_flank_arc(self):
        # 右歯面を反転するだけで、右側の +delta が
        # 左側では自動的に -delta になる。
        x, y, undercut = self.right_flank_arc()
        return -x, y, undercut


    # ========================================================
    # 左歯面
    # ========================================================

    def left_flank(self):

        # 右歯面を反転するだけで、右側の +delta が
        # 左側では自動的に -delta になる。
        # これによりバックラッシ0では v15 と完全一致し、
        # バックラッシありでも左右対称に歯厚が減少する。
        x, y, undercut = self.right_flank()
        return -x, y, undercut


    # ========================================================
    # 回転
    # ========================================================

    @staticmethod
    def rotate(x, y, angle):

        c = np.cos(angle)
        s = np.sin(angle)

        xr = (
            c * x
            - s * y
        )

        yr = (
            s * x
            + c * y
        )

        return xr, yr


    # ========================================================
    # 1周分の輪郭を生成
    # ========================================================

    def profile(self, root_shape="arc"):

        if root_shape == "arc":
            xr, yr, undercut = self.right_flank_arc()
            xl, yl, _ = self.left_flank_arc()
        else:
            # トロコイドは最初のプログラムと同じ生成経路を使用。
            xr, yr, undercut = self.right_flank()
            xl, yl, _ = self.left_flank()

        profile = []

        for i in range(self.z):

            angle = (
                i * self.pitch_angle
            )

            # ------------------------------------------------
            # 右歯面
            # ------------------------------------------------

            x1, y1 = self.rotate(
                xr,
                yr,
                angle
            )

            # ------------------------------------------------
            # 歯先円弧
            # ------------------------------------------------

            theta_r = np.arctan2(
                yr[-1],
                xr[-1]
            )

            theta_l = np.arctan2(
                yl[-1],
                xl[-1]
            )

            theta_tip = np.linspace(
                theta_r,
                theta_l,
                30
            )

            xt = (
                self.addendum_radius
                * np.cos(theta_tip)
            )

            yt = (
                self.addendum_radius
                * np.sin(theta_tip)
            )

            xt, yt = self.rotate(
                xt,
                yt,
                angle
            )

            # ------------------------------------------------
            # 左歯面
            # ------------------------------------------------

            x2, y2 = self.rotate(
                xl[::-1],
                yl[::-1],
                angle
            )

            # ------------------------------------------------
            # 歯元の接続形状
            # ------------------------------------------------
            # 円弧：加工を無視した単純モデル。
            #       arc_root_radius の同心円弧だけを使用する。
            #
            # トロコイド：元のプログラムと同じ歯底円弧を使用。
            #             トロコイドそのものは左右歯面側に含まれる。

            theta_root_start = (
                np.arctan2(yl[0], xl[0]) + angle
            )
            theta_root_end = (
                np.arctan2(yr[0], xr[0])
                + (i + 1) * self.pitch_angle
            )

            while theta_root_end <= theta_root_start:
                theta_root_end += 2 * np.pi

            theta_root = np.linspace(
                theta_root_start, theta_root_end, 50
            )

            root_radius = (
                self.arc_root_radius
                if root_shape == "arc"
                else self.root_radius
            )
            xroot = root_radius * np.cos(theta_root)
            yroot = root_radius * np.sin(theta_root)

            # ------------------------------------------------
            # 輪郭を保存
            # ------------------------------------------------

            profile.append({
                "right_flank": (x1, y1),
                "tip": (xt, yt),
                "left_flank": (x2, y2),
                "root": (xroot, yroot)
            })

        return profile, undercut


    # ========================================================
    # PowerPoint用画像保存
    # ========================================================

    def save_gear(
        self,
        filename="gear.svg",
        linewidth=1.5,
        dpi=300
    ):
        """
        PowerPoint用の歯車画像を保存する。

        filename:
            .svg → ベクター画像
            .png → 透明背景PNG

        linewidth:
            歯車輪郭線の太さ

        dpi:
            PNG保存時の解像度

        Matplotlibには依存せず、SVGは直接生成し、PNGはPillowで
        ラスタライズする。
        """

        profiles, undercut = self.profile()
        margin = self.m * 1.0
        limit = self.addendum_radius + margin

        filename_lower = filename.lower()

        if filename_lower.endswith(".svg"):
            paths = []
            for tooth in profiles:
                for key in ("right_flank", "tip", "left_flank", "root"):
                    x, y = tooth[key]
                    if len(x) == 0:
                        continue
                    commands = [f"M {float(x[0]):.8f} {-float(y[0]):.8f}"]
                    commands.extend(
                        f"L {float(xi):.8f} {-float(yi):.8f}"
                        for xi, yi in zip(x[1:], y[1:])
                    )
                    paths.append(
                        f'<path d="{" ".join(commands)}" fill="none" '
                        f'stroke="black" stroke-width="{float(linewidth):g}" '
                        f'stroke-linecap="round" stroke-linejoin="round"/>'
                    )

            svg = (
                '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
                '<svg xmlns="http://www.w3.org/2000/svg" '
                f'viewBox="{-limit:g} {-limit:g} {2*limit:g} {2*limit:g}" '
                f'width="{2*limit:g}" height="{2*limit:g}">\n'
                + "\n".join(paths)
                + "\n</svg>\n"
            )
            with open(filename, "w", encoding="utf-8") as f:
                f.write(svg)

        elif filename_lower.endswith(".png"):
            from PIL import Image, ImageDraw

            pixels_per_mm = dpi / 25.4
            size = max(1, int(np.ceil(2 * limit * pixels_per_mm)))
            image = Image.new("RGBA", (size, size), (255, 255, 255, 0))
            draw = ImageDraw.Draw(image)
            scale = (size - 1) / (2 * limit)

            def to_px(x, y):
                return (
                    (x + limit) * scale,
                    (limit - y) * scale,
                )

            width_px = max(1, int(round(linewidth * pixels_per_mm)))
            for tooth in profiles:
                for key in ("right_flank", "tip", "left_flank", "root"):
                    x, y = tooth[key]
                    points = [to_px(float(xi), float(yi)) for xi, yi in zip(x, y)]
                    if len(points) >= 2:
                        draw.line(points, fill=(0, 0, 0, 255), width=width_px, joint="curve")

            image.save(
                filename,
                "PNG",
                dpi=(dpi, dpi),
            )
        else:
            raise ValueError("filenameは .svg または .png を指定してください")

        print(f"Saved: {filename}")

        if undercut:
            print("WARNING: Undercut detected.")
