"""転位なし平歯車の概略形状と遊星機構の基本条件。
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

    @property
    def reduction_ratio(self):
        """リング固定・太陽入力・キャリア出力の理論速度比 n_s/n_c。"""
        return 1 + self.ring_teeth / self.sun_teeth

    @property
    def ring_outer_radius(self):
        return self.ring_pitch_radius + 1.25 * self.module + self.ring_rim_thickness

    @property
    def sun_planet_center_distance(self):
        return self.module * (self.sun_teeth + self.planet_teeth) / 2

    @property
    def planet_ring_center_distance(self):
        return self.module * (self.ring_teeth - self.planet_teeth) / 2

    @property
    def ring_sun_center_distance(self):
        """同心条件成立時の中心距離。未成立時は必要中心距離の参考値。"""
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
    if spec.profile_shift != 0:
        raise ValueError("現在の歯形は転位係数 x = 0 のみ対応しています")
    n = max(4, samples)
    m, z = spec.module, spec.teeth
    alpha = spec.pressure_angle_deg * pi / 180
    rp = m * z / 2
    rb = rp * cos(alpha)
    tip = rp - m if internal else rp + m
    root = rp + 1.25 * m if internal else rp - 1.25 * m
    half = pi / (2 * z)
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
    checks = [
        ("歯数関係", s.ring_teeth == s.sun_teeth + 2 * s.planet_teeth,
         f"zᵣ = zₛ + 2zₚ　（{s.ring_teeth} / {s.sun_teeth + 2 * s.planet_teeth}）"),
        ("均等配置条件", *assembly_condition(s)),
    ]
    adjacent = (s.planet_count == 1 or
                2 * s.sun_planet_center_distance * sin(pi / max(1, s.planet_count))
                > s.module * (s.planet_teeth + 2))
    checks.append(("遊星歯車どうしのすきま", adjacent,
                   "2aₛₚ sin(π/N) > m(zₚ + 2)" if s.planet_count > 1 else "N = 1：隣接歯車なし"))
    return checks
