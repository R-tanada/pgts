"""simple gear の外歯車計算を移植したモデル。

backlash は各歯車の歯厚減少量。円弧モデルの歯底円は転位によらず
r - 1.25m とする元の簡略モデルを継承する。中心距離補正は含まない。
画像保存は view.py に分離し、NumPy 以外の描画依存を持たない。
"""
import numpy as np
from dataclasses import dataclass

@dataclass
class Gear:
    module: float = 2.0
    teeth: int = 20
    pressure_angle_deg: float = 20.0
    profile_shift: float = 0.0
    backlash: float = 0.0
    addendum_coefficient: float = 1.0
    dedendum_coefficient: float = 1.25
    clearance_coefficient: float = 0.25
    points: int = 400

class InvoluteGear:

    def __init__(self, gear: Gear):
        self.g = gear
        self.m = gear.module
        self.z = gear.teeth
        self.alpha = np.deg2rad(gear.pressure_angle_deg)
        self.x = gear.profile_shift
        self.backlash = max(0.0, gear.backlash)
        self.ha = gear.addendum_coefficient
        self.hf = gear.dedendum_coefficient
        self.c = gear.clearance_coefficient
        self._calculate_dimensions()

    def _calculate_dimensions(self):
        self.pitch_radius = self.m * self.z / 2
        self.pitch_diameter = 2 * self.pitch_radius
        self.base_radius = self.pitch_radius * np.cos(self.alpha)
        self.base_diameter = 2 * self.base_radius
        self.addendum_radius = self.pitch_radius + self.m * (self.ha + self.x)
        self.addendum_diameter = 2 * self.addendum_radius
        self.root_radius = self.pitch_radius - self.m * (self.hf - self.x)
        self.arc_root_radius = self.pitch_radius - 1.25 * self.m
        self.root_diameter = 2 * self.root_radius
        self.pitch_angle = 2 * np.pi / self.z
        self.cutter_tip_radius = self.c * self.m / (1 - np.sin(self.alpha))

    @staticmethod
    def involute_function(t):
        return t - np.arctan(t)

    def involute_xy(self, t):
        rb = self.base_radius
        x = rb * (np.cos(t) + t * np.sin(t))
        y = rb * (np.sin(t) - t * np.cos(t))
        return (x, y)

    def trochoid_xy(self, psi):
        r = self.pitch_radius
        m = self.m
        alpha = self.alpha
        x_shift = self.x
        rr = self.cutter_tip_radius
        a0 = self.ha * m + self.c * m - rr
        b = np.pi * m / 4 + self.ha * m * np.tan(alpha) + rr * np.cos(alpha)
        a1 = a0 - x_shift * m
        u = (a1 / np.tan(psi) + b) / r
        x = r * np.sin(u) - (a1 / np.sin(psi) + rr) * np.cos(psi - u)
        y = r * np.cos(u) - (a1 / np.sin(psi) + rr) * np.sin(psi - u)
        return (x, y)

    def half_tooth_angle(self):
        return np.pi / (2 * self.z) + 2 * self.x * np.tan(self.alpha) / self.z

    def backlash_flank_angle(self):
        """バックラッシをフランクの角度移動量へ変換する。

        ``backlash`` はこの歯車のピッチ円上の歯厚減少量 [mm]。
        各フランクを backlash/2 ずつ内側へ移動させる。
        """
        return self.backlash / (2.0 * self.pitch_radius)

    def involute_rotation(self):
        r = self.pitch_radius
        rb = self.base_radius
        half_tooth = self.half_tooth_angle()
        t_pitch = np.sqrt((r / rb) ** 2 - 1)
        inv_pitch = self.involute_function(t_pitch)
        rotation = np.pi / 2 - half_tooth - inv_pitch
        return rotation

    def find_transition(self):
        alpha = self.alpha
        psi = np.linspace(alpha, np.pi / 2, self.g.points * 10)
        xt, yt = self.trochoid_xy(psi)
        radius = np.hypot(xt, yt)
        angle_root = np.unwrap(np.arctan2(yt, xt))
        rotation = self.involute_rotation()
        rb = self.base_radius
        valid = radius >= rb
        diff = np.full_like(radius, np.nan)
        t = np.zeros_like(radius)
        t[valid] = np.sqrt((radius[valid] / rb) ** 2 - 1)
        involute_angle = rotation + self.involute_function(t)
        diff[valid] = angle_root[valid] - involute_angle[valid]
        crossings = []
        for i in range(1, len(psi)):
            if not (np.isfinite(diff[i - 1]) and np.isfinite(diff[i])):
                continue
            if diff[i - 1] * diff[i] < 0:
                crossings.append(i)
        if len(crossings) == 0:
            return (alpha, False)
        for idx in crossings:
            if psi[idx] - alpha > np.deg2rad(0.05):
                return (psi[idx], True)
        return (alpha, False)

    def right_flank(self):
        psi_transition, undercut = self.find_transition()
        psi_root = np.linspace(np.pi / 2, psi_transition, self.g.points)
        xt, yt = self.trochoid_xy(psi_root)
        r_transition = np.hypot(xt[-1], yt[-1])
        rb = self.base_radius
        t_start = np.sqrt((r_transition / rb) ** 2 - 1)
        t_end = np.sqrt((self.addendum_radius / rb) ** 2 - 1)
        t_inv = np.linspace(t_start, t_end, self.g.points)
        xi, yi = self.involute_xy(t_inv)
        rotation = self.involute_rotation()
        xi_rot = xi * np.cos(rotation) - yi * np.sin(rotation)
        yi_rot = xi * np.sin(rotation) + yi * np.cos(rotation)
        x = np.concatenate([xt, xi_rot])
        y = np.concatenate([yt, yi_rot])
        delta = self.backlash_flank_angle()
        if delta != 0.0:
            x, y = self.rotate(x, y, delta)
        return (x, y, undercut)

    def right_flank_arc(self):
        """加工を無視した簡略モデルの右歯面。

        トロコイド計算は一切行わず、歯底円から基礎円までは
        半径方向の直線、基礎円から歯先円まではインボリュートとする。
        """
        rb = self.base_radius
        r_root = self.arc_root_radius
        t_end = np.sqrt(max(0.0, (self.addendum_radius / rb) ** 2 - 1.0))
        t_inv = np.linspace(0.0, t_end, self.g.points)
        xi, yi = self.involute_xy(t_inv)
        rotation = self.involute_rotation()
        xi_rot, yi_rot = self.rotate(xi, yi, rotation)
        theta0 = np.arctan2(yi_rot[0], xi_rot[0])
        x_root = r_root * np.cos(theta0)
        y_root = r_root * np.sin(theta0)
        x = np.concatenate([[x_root], xi_rot])
        y = np.concatenate([[y_root], yi_rot])
        delta = self.backlash_flank_angle()
        if delta != 0.0:
            x, y = self.rotate(x, y, delta)
        return (x, y, False)

    def left_flank_arc(self):
        x, y, undercut = self.right_flank_arc()
        return (-x, y, undercut)

    def left_flank(self):
        x, y, undercut = self.right_flank()
        return (-x, y, undercut)

    @staticmethod
    def rotate(x, y, angle):
        c = np.cos(angle)
        s = np.sin(angle)
        xr = c * x - s * y
        yr = s * x + c * y
        return (xr, yr)

    def profile(self, root_shape='arc'):
        if root_shape == 'arc':
            xr, yr, undercut = self.right_flank_arc()
            xl, yl, _ = self.left_flank_arc()
        else:
            xr, yr, undercut = self.right_flank()
            xl, yl, _ = self.left_flank()
        profile = []
        for i in range(self.z):
            angle = i * self.pitch_angle
            x1, y1 = self.rotate(xr, yr, angle)
            theta_r = np.arctan2(yr[-1], xr[-1])
            theta_l = np.arctan2(yl[-1], xl[-1])
            theta_tip = np.linspace(theta_r, theta_l, 30)
            xt = self.addendum_radius * np.cos(theta_tip)
            yt = self.addendum_radius * np.sin(theta_tip)
            xt, yt = self.rotate(xt, yt, angle)
            x2, y2 = self.rotate(xl[::-1], yl[::-1], angle)
            theta_root_start = np.arctan2(yl[0], xl[0]) + angle
            theta_root_end = np.arctan2(yr[0], xr[0]) + (i + 1) * self.pitch_angle
            while theta_root_end <= theta_root_start:
                theta_root_end += 2 * np.pi
            theta_root = np.linspace(theta_root_start, theta_root_end, 50)
            root_radius = self.arc_root_radius if root_shape == 'arc' else self.root_radius
            xroot = root_radius * np.cos(theta_root)
            yroot = root_radius * np.sin(theta_root)
            profile.append({'right_flank': (x1, y1), 'tip': (xt, yt), 'left_flank': (x2, y2), 'root': (xroot, yroot)})
        return (profile, undercut)
