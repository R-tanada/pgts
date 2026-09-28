"""転位平歯車の概略形状と遊星機構の基本条件。
歯面はインボリュート。基礎円より内側は径方向の簡略接続。
工具による歯元創成は含まない。干渉の解析式検査はinterference.py。
"""
from __future__ import annotations
from dataclasses import dataclass
from math import atan, cos, isfinite, pi, sin, sqrt, tan
from typing import List, Tuple

Point = Tuple[float, float]

@dataclass
class GearSpec:
    module: float
    teeth: int
    pressure_angle_deg: float = 20.0
    profile_shift: float = 0.0

@dataclass
class PlanetarySpec:
    module: float = 2.0
    sun_teeth: int = 20
    planet_teeth: int = 20
    planet_count: int = 3
    pressure_angle_deg: float = 20.0
    ring_teeth: int = 60
    ring_rim_thickness: float = 3.5
    shift_enabled: bool = False
    sun_shift: float = 0.0
    planet_shift: float = 0.0
    ring_shift: float = 0.0

    def shift(self, member):
        return getattr(self, member + '_shift') if self.shift_enabled else 0.0

    @property
    def sun_tip_radius(self):
        return self.sun_pitch_radius + self.module * (1 + self.shift('sun'))

    @property
    def planet_tip_radius(self):
        return self.planet_pitch_radius + self.module * (1 + self.shift('planet'))

    @property
    def sun_planet_working_angle(self):
        return working_angle(self.pressure_angle_deg, self.sun_teeth + self.planet_teeth,
                             self.shift('sun') + self.shift('planet'))

    @property
    def planet_ring_working_angle(self):
        return working_angle(self.pressure_angle_deg, self.ring_teeth - self.planet_teeth,
                             self.shift('ring') - self.shift('planet'))

    @property
    def reduction_ratio(self):
        """リング固定・太陽入力・キャリア出力の理論速度比 n_s/n_c。"""
        return 1 + self.ring_teeth / self.sun_teeth

    @property
    def ring_outer_radius(self):
        return self.ring_pitch_radius + (1.25 + self.shift('ring')) * self.module + self.ring_rim_thickness

    @property
    def sun_planet_center_distance(self):
        return self.module * (self.sun_teeth + self.planet_teeth) / 2 * cos(self.pressure_angle_deg*pi/180) / cos(self.sun_planet_working_angle)

    @property
    def planet_ring_center_distance(self):
        return self.module * (self.ring_teeth - self.planet_teeth) / 2 * cos(self.pressure_angle_deg*pi/180) / cos(self.planet_ring_working_angle)

    @property
    def ring_sun_center_distance(self):
        """転位なしは歯数からの参考距離。転位ありは一致した中心距離のみ。"""
        if self.shift_enabled:
            asp, apr = self.sun_planet_center_distance, self.planet_ring_center_distance
            if abs(asp - apr) > center_tolerance(self):
                raise ValueError('太陽–遊星と遊星–リングの中心距離が一致しません')
            return asp
        return self.module * (self.ring_teeth + self.sun_teeth) / 4

    @property
    def planet_pitch_radius(self):
        return self.module * self.planet_teeth / 2

    @property
    def sun_pitch_radius(self):
        return self.module * self.sun_teeth / 2

    @property
    def ring_pitch_radius(self):
        return self.module * self.ring_teeth / 2


def inv(angle):
    return tan(angle) - angle


def working_angle(pressure_angle_deg, tooth_sum_or_difference, shift_sum_or_difference):
    """KHK tables 4.3/4.6; zero-backlash involute working pressure angle.

    A negative involute target has no physical solution and must not be clamped.
    Bisection is monotone on [0, pi/2); no optional solver dependency.
    """
    alpha = pressure_angle_deg * pi / 180
    if not (0 < alpha < pi/4 and tooth_sum_or_difference > 0
            and isfinite(shift_sum_or_difference)):
        raise ValueError('かみ合い圧力角の入力が適用範囲外です')
    if shift_sum_or_difference == 0:
        return alpha
    target = inv(alpha) + 2 * shift_sum_or_difference * tan(alpha) / tooth_sum_or_difference
    if target < 0 or not isfinite(target):
        raise ValueError('inv αw が負のため、かみ合い圧力角を定義できません')
    lo, hi = 0., pi/2 - 1e-10
    for _ in range(70):
        mid = (lo + hi)/2
        if inv(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi)/2


def center_tolerance(spec):
    """Numerical equality tolerance, not a manufacturing tolerance [mm]."""
    return 5e-6 * spec.module


def involute_point(rb: float, theta: float) -> Point:
    return rb * (cos(theta) + theta * sin(theta)), rb * (sin(theta) - theta * cos(theta))


def rotate(p: Point, angle: float) -> Point:
    c, s = cos(angle), sin(angle)
    return p[0] * c - p[1] * s, p[0] * s + p[1] * c


def translate(points: List[Point], dx: float, dy: float) -> List[Point]:
    return [(x + dx, y + dy) for x, y in points]


def _polar(r, angle):
    return r * cos(angle), r * sin(angle)


def _involute_angle(radius, base):
    t = sqrt(max(0.0, (radius / base) ** 2 - 1))
    return t - atan(t)


def _outline(spec: GearSpec, samples: int, internal: bool) -> List[Point]:
    if (not isfinite(spec.module) or spec.module <= 0 or spec.teeth < 6
            or int(spec.teeth) != spec.teeth
            or not 0 < spec.pressure_angle_deg < 45):
        raise ValueError("モジュール・歯数・圧力角が描画可能範囲外です")
    if not isfinite(spec.profile_shift):
        raise ValueError('転位係数が有限値ではありません')
    n = max(4, samples)
    m, z = spec.module, spec.teeth
    alpha = spec.pressure_angle_deg * pi / 180
    rp = m * z / 2
    rb = rp * cos(alpha)
    x = spec.profile_shift
    tip = rp + m * (x - 1) if internal else rp + m * (1 + x)
    root = rp + m * (1.25 + x) if internal else rp - m * (1.25 - x)
    half = pi / (2 * z) + (-1 if internal else 1) * 2*x*tan(alpha)/z
    if min(tip, root) <= 0 or (not internal and tip < rb):
        raise ValueError('歯先円・歯元円がインボリュート歯形の定義域外です')
    inv_alpha = tan(alpha) - alpha

    def width(radius):
        inv = _involute_angle(radius, rb)
        return half + inv - inv_alpha if internal else half + inv_alpha - inv

    if min(width(root), width(tip)) <= 0 or max(width(root), width(tip)) >= pi / z:
        raise ValueError("歯先または歯元の幅が描画可能範囲外です")

    # Counterclockwise: negative flank root→tip, tip arc,
    # positive flank tip→root, root arc to the next tooth.
    # Include base and pitch radii to preserve exact pitch tooth thickness.
    radii = [root + (tip - root) * j / (n - 1) for j in range(n)]
    radii += [r for r in (rb, rp) if min(root, tip) < r < max(root, tip)]
    radii = sorted(set(radii), reverse=internal)
    pts = []
    pitch = 2 * pi / z
    for i in range(z):
        center = i * pitch
        pts.extend(_polar(r, center - width(r)) for r in radii)
        w = width(tip)
        pts.extend(_polar(tip, center - w + 2 * w * j / n) for j in range(1, n + 1))
        pts.extend(_polar(r, center + width(r)) for r in reversed(radii[:-1]))
        w = width(root)
        pts.extend(_polar(root, center + w + (pitch - 2 * w) * j / n)
                   for j in range(1, n + 1))
    return pts


def gear_outline(spec: GearSpec, samples_per_curve: int = 12) -> List[Point]:
    return _outline(spec, samples_per_curve, False)


def ring_gear_outline(spec: GearSpec, samples_per_curve: int = 12) -> List[Point]:
    return _outline(spec, samples_per_curve, True)


def ring_rotation(spec: PlanetarySpec) -> float:
    # Odd planet tooth count puts a tooth at the outward contact; ring gap
    # must face it. Even count puts a gap there, facing a ring tooth.
    return (spec.planet_teeth % 2) * pi / spec.ring_teeth


def planetary_positions(spec: PlanetarySpec) -> List[Tuple[float, float, float]]:
    radius = spec.sun_planet_center_distance
    result = []
    for i in range(spec.planet_count):
        angle = 2 * pi * i / spec.planet_count
        rotation = (1 + spec.sun_teeth / spec.planet_teeth) * angle + pi - pi / spec.planet_teeth
        result.append((radius * cos(angle), radius * sin(angle), rotation))
    return result


def assembly_condition(spec: PlanetarySpec) -> Tuple[bool, str]:
    numerator = spec.sun_teeth + spec.ring_teeth
    if spec.planet_count < 1:
        return False, "遊星歯車の個数は1以上にしてください"
    value = numerator / spec.planet_count
    ok = numerator % spec.planet_count == 0
    return ok, f"(zₛ + zᵣ) / N = {value:.4g}（{'整数' if ok else '整数ではありません'}）"


def planetary_constraints(spec: PlanetarySpec) -> List[Tuple[str, bool, str]]:
    s = spec
    try:
        asp, apr = s.sun_planet_center_distance, s.planet_ring_center_distance
        center_ok = abs(asp - apr) <= center_tolerance(s)
        detail = f'太陽–遊星：{asp:.8f} mm ／ 遊星–リング：{apr:.8f} mm\n差：{abs(asp-apr):.8g} mm'
        detail += (f'\n数値一致の許容差：{center_tolerance(s):.3g} mm（加工公差ではありません）'
                   if s.shift_enabled else '\n転位なしでは zᵣ = zₛ + 2zₚ と等価です。')
    except ValueError as exc:
        center_ok, detail = None, str(exc)
    checks = [('中心距離条件', center_ok, detail),
              ('拘束かみ合い条件', *assembly_condition(s))]
    if s.planet_count == 1:
        adjacent, detail = True, 'N = 1：隣接歯車なし'
    elif center_ok is not True:
        adjacent, detail = None, '中心距離条件が成立していないため、共通の遊星軸位置を確定できません。'
    else:
        spacing = 2 * asp * sin(pi / s.planet_count)
        diameter = 2 * s.planet_tip_radius
        adjacent = spacing > diameter and diameter > 0
        detail = f'隣接軸間距離：{spacing:.6f} mm ／ 遊星歯先径：{diameter:.6f} mm'
    checks.append(('外径干渉条件', adjacent, detail))
    return checks
