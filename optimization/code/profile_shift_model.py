"""論文の転位歯車モデル。角度はラジアン、長さはmmで計算する。

使い方:
    gearbox = Gearbox()
    model = Model(gearbox, friction=0.1)
    model.calculate([1.0, 0.5, 21.0])  # xr1, xr2, 共通中心間距離
    print(model.forward_efficiency)

calculate()は計算結果を返さず、selfの変数に保存する。
歯先径は論文の式(82)-(86)。P1の歯先半径は式(83)で求め、両かみ合いで共通に使う。
"""
import math
from fractions import Fraction


class Gearbox:
    """歯数、モジュール、圧力角を保存する。初期値はTable III。

    条件を変える場合は Gearbox(zs=..., ...) として作り直す。
    alpha、i1、i2なども__init__で一緒に計算するため。
    """

    def __init__(self, zs=12, zp1=39, zr1=90, zp2=32, zr2=81,
                 module_a=0.8, module_c=0.8467,
                 pressure_angle_deg=20.0, planet_count=3):
        self.zs = zs
        self.zp1 = zp1
        self.zr1 = zr1
        self.zp2 = zp2
        self.zr2 = zr2
        self.module_a = module_a
        self.module_c = module_c
        self.pressure_angle_deg = pressure_angle_deg
        self.planet_count = planet_count

        self.alpha = math.radians(pressure_angle_deg)
        self.i1 = zr1 / zs
        self.i2 = zr1 * zp2 / (zr2 * zp1)
        # Fractionは整数の比を丸めずに保存するために使う。
        self.speed_ratio = Fraction(
            zs * (zr2 * zp1 - zr1 * zp2),
            zr2 * zp1 * (zs + zr1),
        )

    def to_dict(self):
        """ファイル保存用。普通の辞書を返す。"""
        return {
            "zs": self.zs, "zp1": self.zp1, "zr1": self.zr1,
            "zp2": self.zp2, "zr2": self.zr2,
            "module_a": self.module_a, "module_c": self.module_c,
            "pressure_angle_deg": self.pressure_angle_deg,
            "planet_count": self.planet_count,
        }


class ProfileShifts:
    """5つの転位係数を名前付きで保存するだけのクラス。"""

    def __init__(self, xs, xp1, xr1, xp2, xr2):
        self.xs = xs
        self.xp1 = xp1
        self.xr1 = xr1
        self.xp2 = xp2
        self.xr2 = xr2

    def to_dict(self):
        return {"xs": self.xs, "xp1": self.xp1, "xr1": self.xr1,
                "xp2": self.xp2, "xr2": self.xr2}


class Mesh:
    """1組のかみ合いを計算する。signは外歯同士で+1、内歯で-1。"""

    def __init__(self, name, z1, z2, sign, module, center,
                 tip1, tip2, alpha, friction):
        self.name = name
        self.z1 = z1
        self.z2 = z2
        self.sign = sign
        self.module = module
        self.center = center
        self.tip_radius1 = tip1
        self.tip_radius2 = tip2

        # 式(81): 作動圧力角と基礎円半径
        self.working_angle = working_angle(z1, z2, sign, module, center, alpha)
        self.base_radius1 = module * z1 * math.cos(alpha) / 2
        self.base_radius2 = module * z2 * math.cos(alpha) / 2

        # 最適化の途中には不合格点も現れる。acosの範囲を保ち、制約で除外する。
        self.tip_angle1 = math.acos(min(1.0, self.base_radius1 / max(tip1, 1e-12)))
        self.tip_angle2 = math.acos(min(1.0, self.base_radius2 / max(tip2, 1e-12)))

        # 式(79)、(80): 近寄りかみ合い率と遠のきかみ合い率
        self.approach_ratio = sign * z2 * (
            math.tan(self.tip_angle2) - math.tan(self.working_angle)
        ) / (2 * math.pi)
        self.recess_ratio = z1 * (
            math.tan(self.tip_angle1) - math.tan(self.working_angle)
        ) / (2 * math.pi)
        self.contact_ratio = self.approach_ratio + self.recess_ratio

        # 式(78)、(77): かみ合い損失と基礎効率
        approach = self.approach_ratio
        recess = self.recess_ratio
        loss_factor = approach**2 + recess**2 - approach - recess + 1
        self.basic_efficiency = 1 - friction * math.pi * (1 / z1 + sign / z2) * loss_factor

    def to_dict(self):
        """従来のグラフ・JSONと同じ項目で保存する。"""
        return {
            "name": self.name, "z1": self.z1, "z2": self.z2,
            "sign": self.sign, "module": self.module, "center": self.center,
            "working_angle": self.working_angle,
            "base_radius1": self.base_radius1, "base_radius2": self.base_radius2,
            "tip_radius1": self.tip_radius1, "tip_radius2": self.tip_radius2,
            "tip_angle1": self.tip_angle1, "tip_angle2": self.tip_angle2,
            "approach_ratio": self.approach_ratio, "recess_ratio": self.recess_ratio,
            "basic_efficiency": self.basic_efficiency,
        }


class Model:
    """固定した歯車仕様で、転位と中心間距離を変えて効率を計算する。"""

    def __init__(self, gearbox, friction=0.1):
        self.gearbox = gearbox
        self.friction = friction
        # 結果はcalculate()を呼んだ後に読む。
        self.center_mm = None
        self.shifts = None
        self.meshes = []
        self.forward_efficiency = None
        self.backward_efficiency = None
        self.backward_efficiency_force_balance = None

    def calculate(self, variables):
        """最適化用。転位係数を求めてから効率を計算する。"""
        xs, xp1, xr1, xp2, xr2 = self.calculate_shifts(variables)
        center = float(variables[2])
        self.calculate_efficiency(xs, xp1, xr1, xp2, xr2, center)

    def calculate_shifts(self, variables):
        """決定変数[xr1, xr2, center]から5つの転位係数を返す。

        戻り値はxs, xp1, xr1, xp2, xr2の5つの数値。モデルの状態は変更しない。
        """
        g = self.gearbox
        xr1 = float(variables[0])
        xr2 = float(variables[1])
        center = float(variables[2])

        # 1. 各かみ合いの作動圧力角を求める。共通のcenterを使用。
        angle_a = working_angle(g.zs, g.zp1, 1, g.module_a, center, g.alpha)
        angle_b = working_angle(g.zp1, g.zr1, -1, g.module_a, center, g.alpha)
        angle_c = working_angle(g.zp2, g.zr2, -1, g.module_c, center, g.alpha)

        # 2. 式(88): 転位和・転位差から残り3つの転位係数を計算。
        ka = (g.zs + g.zp1) * (involute(angle_a) - involute(g.alpha)) / (2 * math.tan(g.alpha))
        kb = (g.zp1 - g.zr1) * (involute(angle_b) - involute(g.alpha)) / (2 * math.tan(g.alpha))
        kc = (g.zp2 - g.zr2) * (involute(angle_c) - involute(g.alpha)) / (2 * math.tan(g.alpha))
        xp1 = xr1 + kb
        xs = ka - xp1
        xp2 = xr2 + kc
        return xs, xp1, xr1, xp2, xr2

    def calculate_efficiency(self, xs, xp1, xr1, xp2, xr2, center):
        """指定した5つの転位係数と中心間距離で効率を計算し、selfに保存する。

        転位係数を逆算・補正せず、そのまま代入する確認用の入口。
        任意の転位係数とcenterの組み合わせが幾何学的に整合するとは限らない。
        """
        g = self.gearbox
        self.shifts = ProfileShifts(xs, xp1, xr1, xp2, xr2)
        self.center_mm = center

        # 1. 式(82)-(87): 歯先「半径」を計算（論文の直径を2で割る）。
        ma = g.module_a
        mc = g.module_c
        ya = center / ma - (g.zs + g.zp1) / 2
        tip_s = ma * g.zs / 2 + ma * (1 + ya - xp1)
        tip_p1 = ma * g.zp1 / 2 + ma * (1 + min(ya - xs, xp1))
        tip_r1 = ma * g.zr1 / 2 - ma * (1 - xr1)
        tip_p2 = mc * g.zp2 / 2 + mc * (1 + xp2)
        tip_r2 = mc * g.zr2 / 2 - mc * (1 - xr2)

        # 2. S-P1、P1-R1、P2-R2のかみ合いを計算。
        mesh_a = Mesh("a", g.zs, g.zp1, 1, ma, center, tip_s, tip_p1, g.alpha, self.friction)
        mesh_b = Mesh("b", g.zp1, g.zr1, -1, ma, center, tip_p1, tip_r1, g.alpha, self.friction)
        mesh_c = Mesh("c", g.zp2, g.zr2, -1, mc, center, tip_p2, tip_r2, g.alpha, self.friction)
        self.meshes = [mesh_a, mesh_b, mesh_c]

        # 3. 各かみ合いの基礎効率から、減速機全体の効率を求める。
        forward, backward = total_efficiencies(
            g, mesh_a.basic_efficiency, mesh_b.basic_efficiency, mesh_c.basic_efficiency
        )
        self.forward_efficiency = forward
        self.backward_efficiency = backward
        # 式(75)には既にeta_aが含まれる。二重に掛けない。
        # 旧コードとの互換用の名前も、同じ正しい逆効率を保持する。
        self.backward_efficiency_force_balance = backward

    def to_dict(self):
        """結果保存用。計算を理解する際は後回しでよい。"""
        mesh_data = []
        for mesh in self.meshes:
            mesh_data.append(mesh.to_dict())
        return {
            "center_mm": self.center_mm,
            "shifts": self.shifts.to_dict(),
            "meshes": mesh_data,
            "forward_efficiency": self.forward_efficiency,
            "backward_efficiency": self.backward_efficiency,
            "backward_efficiency_force_balance": self.backward_efficiency_force_balance,
        }


PAPER_SHIFTS = ProfileShifts(xs=0.476, xp1=0.762, xr1=2.000, xp2=0.536, xr2=1.210)
PAPER_CONTACT_RATIOS = {"a": 1.232, "b": 1.420, "c": 1.565}
PAPER_MEASURED_EFFICIENCIES = {"forward": 0.890, "backward": 0.853}


def involute(angle):
    return math.tan(angle) - angle


def angle_from_involute(value):
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


def center_for_external_shift_sum(gearbox, shift_sum):
    """式(88)、(81)。外歯かみあいの転位和から中心距離を求める。"""
    tooth_sum = gearbox.zs + gearbox.zp1
    value = involute(gearbox.alpha) + 2 * math.tan(gearbox.alpha) * shift_sum / tooth_sum
    angle = angle_from_involute(value)
    return gearbox.module_a * tooth_sum * math.cos(gearbox.alpha) / (2 * math.cos(angle))


def working_angle(z1, z2, sign, module,
                  center, alpha):
    base_center = module * abs(z1 + sign * z2) * math.cos(alpha) / 2
    if center < base_center:
        raise ValueError("中心距離が基礎円接線の限界より小さい")
    return math.acos(min(1.0, base_center / center))


def total_efficiencies(gearbox, eta_a, eta_b,
                       eta_c):
    """順駆動:式(64)/(67)、逆駆動:式(75)/(76)。"""
    i1, i2 = gearbox.i1, gearbox.i2
    if i2 < 1:
        forward = ((1 + eta_a * eta_b * i1) * (1 - i2)
                   / ((1 + i1) * (1 - eta_b * eta_c * i2)))
        backward = ((1 + i1) * eta_a * (eta_b * eta_c - i2)
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


def internal_trochoid_margin(mesh):
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


def internal_trimming_margin(mesh):
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


def constraint_margins(evaluation, gearbox,
                       shift_lower, shift_upper,
                       contact_lower, contact_upper,
                       clearance_mm, include_trimming):
    """すべて margin >= 0 が合格。名前を付けて結果の監査を可能にする。"""
    margins = {}
    for name, value in evaluation.shifts.to_dict().items():
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


def reference_center_distances(gearbox):
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
