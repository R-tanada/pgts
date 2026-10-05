"""Table IIIの固定歯数モデル。数式と幾何制約だけを扱う（SciPy不要）。

独立変数: [xr1, xr2, center_mm]。
歯先径は一般的な転位歯車式で置き換えず、論文式(82)-(86)を使う。
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from fractions import Fraction


@dataclass(frozen=True)
class Gearbox:
    zs: int = 12
    zp1: int = 39
    zr1: int = 90
    zp2: int = 32
    zr2: int = 81
    module_a: float = 0.8
    module_c: float = 0.8467
    pressure_angle_deg: float = 20.0
    planet_count: int = 3

    @property
    def alpha(self) -> float:
        return math.radians(self.pressure_angle_deg)

    @property
    def i1(self) -> float:
        return self.zr1 / self.zs

    @property
    def i2(self) -> float:
        return self.zr1 * self.zp2 / (self.zr2 * self.zp1)

    @property
    def speed_ratio(self) -> Fraction:
        return Fraction(self.zs * (self.zr2 * self.zp1 - self.zr1 * self.zp2),
                        self.zr2 * self.zp1 * (self.zs + self.zr1))


@dataclass(frozen=True)
class ProfileShifts:
    xs: float
    xp1: float
    xr1: float
    xp2: float
    xr2: float


@dataclass(frozen=True)
class Mesh:
    """式(77)-(81)の一つのかみあい。1は外歯、2は相手歯車。"""
    name: str
    z1: int
    z2: int
    sign: int                  # 外歯かみあい:+1、内歯かみあい:-1
    module: float
    center: float
    working_angle: float
    base_radius1: float
    base_radius2: float
    tip_radius1: float
    tip_radius2: float
    tip_angle1: float
    tip_angle2: float
    approach_ratio: float
    recess_ratio: float
    basic_efficiency: float

    @property
    def contact_ratio(self) -> float:
        return self.approach_ratio + self.recess_ratio


@dataclass(frozen=True)
class Evaluation:
    center_mm: float
    shifts: ProfileShifts
    meshes: tuple[Mesh, Mesh, Mesh]
    forward_efficiency: float
    backward_efficiency: float
    backward_efficiency_force_balance: float


PAPER_SHIFTS = ProfileShifts(xs=0.476, xp1=0.762, xr1=2.000, xp2=0.536, xr2=1.210)
PAPER_CONTACT_RATIOS = {"a": 1.232, "b": 1.420, "c": 1.565}
PAPER_MEASURED_EFFICIENCIES = {"forward": 0.890, "backward": 0.853}


def involute(angle: float) -> float:
    return math.tan(angle) - angle


def angle_from_involute(value: float) -> float:
    """単調なインボリュート関数を二分法で反転する。"""
    if value < 0:
        raise ValueError("インボリュート関数の値は非負である必要があります")
    lower, upper = 0.0, math.pi / 2 - 1e-8
    for _ in range(80):
        middle = (lower + upper) / 2
        if involute(middle) < value:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2


def center_for_external_shift_sum(gearbox: Gearbox, shift_sum: float) -> float:
    """式(88)、(81)。外歯かみあいの転位和から中心距離を求める。"""
    tooth_sum = gearbox.zs + gearbox.zp1
    value = involute(gearbox.alpha) + 2 * math.tan(gearbox.alpha) * shift_sum / tooth_sum
    angle = angle_from_involute(value)
    return gearbox.module_a * tooth_sum * math.cos(gearbox.alpha) / (2 * math.cos(angle))


def working_angle(z1: int, z2: int, sign: int, module: float,
                  center: float, alpha: float) -> float:
    base_center = module * abs(z1 + sign * z2) * math.cos(alpha) / 2
    if center < base_center:
        raise ValueError("中心距離が基礎円接線の限界より小さい")
    return math.acos(min(1.0, base_center / center))


def shifts_from_variables(variables, gearbox: Gearbox) -> ProfileShifts:
    """式(88)。共通中心距離から従属変数xs,xp1,xp2を計算。"""
    xr1, xr2, center = map(float, variables)
    alpha = gearbox.alpha
    def shift_relation(z1, z2, sign, module):
        angle = working_angle(z1, z2, sign, module, center, alpha)
        return (z1 + sign * z2) * (involute(angle) - involute(alpha)) / (2 * math.tan(alpha))
    ka = shift_relation(gearbox.zs, gearbox.zp1, 1, gearbox.module_a)
    kb = shift_relation(gearbox.zp1, gearbox.zr1, -1, gearbox.module_a)
    kc = shift_relation(gearbox.zp2, gearbox.zr2, -1, gearbox.module_c)
    xp1 = xr1 + kb
    return ProfileShifts(xs=ka - xp1, xp1=xp1, xr1=xr1, xp2=xr2 + kc, xr2=xr2)


def mesh_evaluation(name, z1, z2, sign, module, center, tip1, tip2,
                    alpha, friction) -> Mesh:
    angle_w = working_angle(z1, z2, sign, module, center, alpha)
    base1, base2 = module * z1 * math.cos(alpha) / 2, module * z2 * math.cos(alpha) / 2
    # SLSQPは不合格点も評価する。定義域外で計算を止めず、制約で除外する。
    angle1 = math.acos(min(1.0, base1 / max(tip1, 1e-12)))
    angle2 = math.acos(min(1.0, base2 / max(tip2, 1e-12)))
    approach = sign * z2 * (math.tan(angle2) - math.tan(angle_w)) / (2 * math.pi)
    recess = z1 * (math.tan(angle1) - math.tan(angle_w)) / (2 * math.pi)
    loss_factor = approach**2 + recess**2 - approach - recess + 1
    efficiency = 1 - friction * math.pi * (1 / z1 + sign / z2) * loss_factor
    return Mesh(name, z1, z2, sign, module, center, angle_w, base1, base2,
                tip1, tip2, angle1, angle2, approach, recess, efficiency)


def total_efficiencies(gearbox: Gearbox, eta_a: float, eta_b: float,
                       eta_c: float) -> tuple[float, float]:
    """順駆動:式(64)/(67)、逆駆動:式(75)/(76)。"""
    i1, i2 = gearbox.i1, gearbox.i2
    if i2 < 1:
        forward = ((1 + eta_a * eta_b * i1) * (1 - i2)
                   / ((1 + i1) * (1 - eta_b * eta_c * i2)))
        backward = ((1 + i1) * (eta_b * eta_c - i2)
                    / (eta_c * (eta_a * eta_b + i1) * (1 - i2)))
    elif i2 > 1:
        forward = (eta_c * (eta_b + eta_a * i1) * (1 - i2)
                   / ((1 + i1) * (eta_b * eta_c - i2)))
        backward = ((1 + i1) * eta_a * (1 - eta_b * eta_c * i2)
                    / ((eta_a + eta_b * i1) * (1 - i2)))
    else:
        raise ValueError("I2=1では出力が停止するため最適化できません")
    # 論文の説明に従い、逆駆動不可の領域の負値は0として報告する。
    return forward, max(0.0, backward)


def evaluate(variables, gearbox: Gearbox, friction: float) -> Evaluation:
    """式(77)-(88)を順に計算。歯先径は論文特有の式を忠実に使う。"""
    shifts = shifts_from_variables(variables, gearbox)
    center = float(variables[2])
    ma, mc = gearbox.module_a, gearbox.module_c
    ya = center / ma - (gearbox.zs + gearbox.zp1) / 2  # 式(87)
    tip_s = ma * gearbox.zs / 2 + ma * (1 + ya - shifts.xp1)  # 式(82)
    tip_p1 = ma * gearbox.zp1 / 2 + ma * (1 + min(ya - shifts.xs, shifts.xp1))  # 式(83)
    tip_r1 = ma * gearbox.zr1 / 2 - ma * (1 - shifts.xr1)  # 式(84)
    tip_p2 = mc * gearbox.zp2 / 2 + mc * (1 + shifts.xp2)  # 式(85)
    tip_r2 = mc * gearbox.zr2 / 2 - mc * (1 - shifts.xr2)  # 式(86)
    common = dict(center=center, alpha=gearbox.alpha, friction=friction)
    mesh_a = mesh_evaluation("a", gearbox.zs, gearbox.zp1, 1, ma, tip1=tip_s, tip2=tip_p1, **common)
    mesh_b = mesh_evaluation("b", gearbox.zp1, gearbox.zr1, -1, ma, tip1=tip_p1, tip2=tip_r1, **common)
    mesh_c = mesh_evaluation("c", gearbox.zp2, gearbox.zr2, -1, mc, tip1=tip_p2, tip2=tip_r2, **common)
    forward, backward = total_efficiencies(gearbox, mesh_a.basic_efficiency,
                                          mesh_b.basic_efficiency, mesh_c.basic_efficiency)
    # 式(74)のトルク釣合いから導くと、I2<1の逆効率にはeta_aが掛かる。
    # 印刷された式(75)の値は変更せず、別の名前で両方保存する。
    force_balance_backward = backward * mesh_a.basic_efficiency if gearbox.i2 < 1 else backward
    return Evaluation(center, shifts, (mesh_a, mesh_b, mesh_c), forward, backward,
                      force_balance_backward)


def internal_trochoid_margin(mesh: Mesh) -> float:
    """歯先円交点での歯位相の非重複条件。無転位の歯数差条件は使わない。

    theta1*z1/z2 + inv(alpha_w) - inv(alpha_a2) - theta2 >= 0。
    theta1には外歯のインボリュート角の差を含める。
    """
    a, p, r = mesh.center, mesh.tip_radius1, mesh.tip_radius2
    cosine1 = (r*r - p*p - a*a) / (2*a*p)
    cosine2 = (a*a + r*r - p*p) / (2*a*r)
    if abs(cosine1) > 1 or abs(cosine2) > 1:
        return -1.0  # このモデルでは歯先円交点を持つかみあいだけを扱う。
    theta1 = math.acos(cosine1) + involute(mesh.tip_angle1) - involute(mesh.working_angle)
    theta2 = math.acos(cosine2)
    return (theta1 * mesh.z1 / mesh.z2 + involute(mesh.working_angle)
            - involute(mesh.tip_angle2) - theta2)


def internal_trimming_margin(mesh: Mesh) -> float:
    """KHKの転位歯車にも使う角度式。半径方向組付けの条件。"""
    cosine_p, cosine_r = math.cos(mesh.tip_angle1), math.cos(mesh.tip_angle2)
    ratio = mesh.z1 / mesh.z2
    sine_p2 = (1 - (cosine_p / cosine_r)**2) / (1 - ratio**2)
    sine_r2 = ((cosine_r / cosine_p)**2 - 1) / (1 / ratio**2 - 1)
    if not (0 <= sine_p2 <= 1 and 0 <= sine_r2 <= 1):
        return -1.0
    theta_p, theta_r = math.asin(math.sqrt(sine_p2)), math.asin(math.sqrt(sine_r2))
    return (theta_p + involute(mesh.tip_angle1) - involute(mesh.working_angle)
            - (theta_r + involute(mesh.tip_angle2) - involute(mesh.working_angle)) / ratio)


def constraint_margins(evaluation: Evaluation, gearbox: Gearbox,
                       shift_lower: float, shift_upper: float,
                       contact_lower: float, contact_upper: float,
                       clearance_mm: float, include_trimming: bool) -> dict[str, float]:
    """すべて margin >= 0 が合格。名前を付けて結果の監査を可能にする。"""
    margins = {}
    for name, value in asdict(evaluation.shifts).items():
        margins[f"{name}_lower"] = value - shift_lower
        margins[f"{name}_upper"] = shift_upper - value
    for mesh in evaluation.meshes:
        prefix = mesh.name
        margins[f"{prefix}_tip1_above_base"] = (mesh.tip_radius1 - mesh.base_radius1) / mesh.module
        margins[f"{prefix}_tip2_above_base"] = (mesh.tip_radius2 - mesh.base_radius2) / mesh.module
        margins[f"{prefix}_approach_nonnegative"] = mesh.approach_ratio
        margins[f"{prefix}_recess_nonnegative"] = mesh.recess_ratio
        margins[f"{prefix}_contact_lower"] = mesh.contact_ratio - contact_lower
        margins[f"{prefix}_contact_upper"] = contact_upper - mesh.contact_ratio
        margins[f"{prefix}_basic_efficiency_lower"] = mesh.basic_efficiency
        margins[f"{prefix}_basic_efficiency_upper"] = 1 - mesh.basic_efficiency
        if mesh.sign == -1:
            margins[f"{prefix}_trochoid"] = internal_trochoid_margin(mesh)
            if include_trimming:
                margins[f"{prefix}_trimming"] = internal_trimming_margin(mesh)
    neighbor_distance = 2 * evaluation.center_mm * math.sin(math.pi / gearbox.planet_count)
    for mesh in (evaluation.meshes[1], evaluation.meshes[2]):
        margins[f"{mesh.name}_planet_clearance"] = (neighbor_distance - 2*mesh.tip_radius1 - clearance_mm) / mesh.module
    margins["total_efficiency_lower"] = evaluation.forward_efficiency
    margins["total_efficiency_upper"] = 1 - evaluation.forward_efficiency
    return margins


def reference_center_distances(gearbox: Gearbox) -> dict[str, float]:
    """丸められたTable IIIの転位係数から3つの中心距離を独立に復元。"""
    reference = PAPER_SHIFTS
    centers = {}
    for name, z1, z2, sign, module, relation in (
        ("a", gearbox.zs, gearbox.zp1, 1, gearbox.module_a, reference.xs + reference.xp1),
        ("b", gearbox.zp1, gearbox.zr1, -1, gearbox.module_a, reference.xp1 - reference.xr1),
        ("c", gearbox.zp2, gearbox.zr2, -1, gearbox.module_c, reference.xp2 - reference.xr2),
    ):
        value = involute(gearbox.alpha) + 2 * math.tan(gearbox.alpha) * relation / (z1 + sign*z2)
        angle = angle_from_involute(value)
        centers[name] = module * abs(z1 + sign*z2) * math.cos(gearbox.alpha) / (2*math.cos(angle))
    return centers
