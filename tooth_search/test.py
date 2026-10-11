"""歯数探索の構成確認用。ma → S → P1 → R1 → mc → R2 → P2。

CSVは必要条件を通った候補。転位・干渉の成立保証ではありません。
"""
import csv
import math
from pathlib import Path


# 1. 設定。D1/D2は今は基準円直径の上限（肉厚は含めない）。
D1 = 70
D2 = 70
x_min = -2
x_max = 2
z_s_min = 8
z_p1_min = 8
z_p2_min = 8
pressure_angle = 20
planet_count = 3
planet_clearance = 0.0  # 隣接遊星間に要求するすきま [mm]
reduction_min = 100  # 減速倍率の下限（入力速度 / 出力速度の絶対値）
reduction_max = 100  # 上限なし。例えば1000.0にすると1000倍まで。
# 上下限は含む。回転方向は両方向を許す。
# tooth_size = [
#     0.5, 0.5053, 0.5080, 0.5644, 0.635, 0.6366, 0.6684,
#     0.7056, 0.7471, 0.75, 0.7938, 0.7958, 0.8, 0.8467,
#     0.8759, 0.9071, 0.9549, 0.9769, 1.0,
# ]
tooth_size = [0.8, 0.8467
]
alpha = math.radians(pressure_angle)
tolerance = 1e-10


# 2. 作動圧力角と中心間距離
def involute(angle):
    return math.tan(angle) - angle


def angle_from_involute(value):
    if value < 0:
        raise ValueError("インボリュート関数の値は非負である必要があります")
    lower = 0.0
    upper = math.pi / 2 - 1e-8
    for _ in range(60):
        middle = (lower + upper) / 2
        if involute(middle) < value:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2


def working_angle(x1, x2, sign, z1, z2, pressure_angle):
    """x1は外歯、内歯かみ合いのx2はリング。戻り値はラジアン。"""
    angle = math.radians(pressure_angle)
    if sign == 1:
        value = involute(angle) + 2 * (x1 + x2) * math.tan(angle) / (z1 + z2)
    elif sign == -1:
        value = involute(angle) + 2 * (x2 - x1) * math.tan(angle) / (z2 - z1)
    else:
        raise ValueError("signは1または-1です")
    return angle_from_involute(value)


def center_range(module, teeth, shift_lower, shift_upper):
    """teethは歯数和（外歯）または歯数差（内歯）。

    shiftは転位和（外歯）またはリング転位−遊星転位（内歯）。
    invが負となる転位部分を除いた、成立可能な中心距離の範囲。
    """
    value_min = involute(alpha) + 2 * shift_lower * math.tan(alpha) / teeth
    value_max = involute(alpha) + 2 * shift_upper * math.tan(alpha) / teeth
    if value_max < 0:
        return None
    angle_min = angle_from_involute(max(0.0, value_min))
    angle_max = angle_from_involute(value_max)
    base_center = module * teeth * math.cos(alpha) / 2
    return base_center / math.cos(angle_min), base_center / math.cos(angle_max)


def overlap(range1, range2):
    lower = max(range1[0], range2[0])
    upper = min(range1[1], range2[1])
    if lower > upper + tolerance:
        return None
    return lower, max(lower, upper)


def difference_range(centers, maximum, internal_centers):
    """中心距離が重なる歯数差の最小・最大。

    初版は短いforで確認する。途中に不成立の差があっても、
    後で個別にoverlapを確認するので成立候補を落とさない。
    """
    lower = None
    upper = None
    for difference in range(1, maximum + 1):
        if overlap(centers, internal_centers[difference]) is not None:
            if lower is None:
                lower = difference
            upper = difference
    if lower is None:
        return None
    return lower, upper


# 3. 転位が未定でも安全に使える必要条件
def ring_minimum():
    # da_r >= db_r を、最も有利なリング転位x_maxで確認。
    lower = 2 * (1 - x_max) / (1 - math.cos(alpha))
    return max(1, math.ceil(lower - tolerance))


def planet_can_fit(module, teeth, centers, tip_shift_min):
    """最小歯先径でも入らない候補だけを除外。合格は仮判定。

    P1: da=m*(z+2+2*min(ya-xs, xp1))
    P2: da=m*(z+2+2*xp2)
    tip_shift_minはそれぞれの転位項の安全な下限を渡す。
    """
    diameter_min = max(0.0, module * (teeth + 2 + 2 * tip_shift_min))
    neighbor_max = 2 * centers[1] * math.sin(math.pi / planet_count)
    return diameter_min + planet_clearance < neighbor_max + tolerance


def internal_involute_possible(module, planet, ring, centers):
    """最も有利な歯先径・角度でも干渉する候補だけを除外。

    各限界値が同時に実現するとは限らないので合格は仮判定。
    """
    base_radius = module * ring * math.cos(alpha) / 2
    tip_radius_max = module * (ring / 2 - 1 + x_max)
    if tip_radius_max < base_radius - tolerance:
        return False
    tip_angle_max = math.acos(min(1.0, base_radius / tip_radius_max))
    base_center = module * (ring - planet) * math.cos(alpha) / 2
    working_min = math.acos(min(1.0, base_center / centers[0]))
    # 除算せずに書くのでalpha_w=0でも扱える。
    return (ring - planet) * math.tan(working_min) <= ring * math.tan(tip_angle_max) + tolerance


# 4. トロコイド干渉による、歯数段階の絞り込み
def division_range(numerator_min, numerator_max, denominator_min, denominator_max):
    """分母が正のときの割り算の範囲。分子が負でも扱える。"""
    values = [numerator_min / denominator_min, numerator_min / denominator_max,
              numerator_max / denominator_min, numerator_max / denominator_max]
    return min(values), max(values)


def trochoid_possible(module, planet, ring, centers, planet_tips, ring_tips):
    """許容範囲のどこでもトロコイド回避が不可能ならFalse。

    歯先直径と中心距離の範囲から、回避条件の余裕の上限を求める。
    上限が負なら除外できる。Trueは非干渉の保証ではない。
    各値の相関を緩めて計算するので、成立する候補を落とさない。
    解析式の定義域外を含み、除外を証明できない場合も残す。
    """
    a_min, a_max = centers
    bp = module * planet * math.cos(alpha) / 2
    br = module * ring * math.cos(alpha) / 2
    p_min = max(bp, planet_tips[0] / 2)
    p_max = planet_tips[1] / 2
    r_min = max(br, ring_tips[0] / 2)
    r_max = ring_tips[1] / 2
    if p_max <= bp or r_max <= br or a_min <= 0:
        return True  # ここでは解析式の適用外。非干渉と断定しない。

    # cos(theta1) = (r²-p²-a²)/(2ap)
    cos1_min, cos1_max = division_range(
        r_min*r_min - p_max*p_max - a_max*a_max,
        r_max*r_max - p_min*p_min - a_min*a_min,
        2*a_min*p_min, 2*a_max*p_max)
    # cos(theta2) = (a²+r²-p²)/(2ar)
    cos2_min, cos2_max = division_range(
        a_min*a_min + r_min*r_min - p_max*p_max,
        a_max*a_max + r_max*r_max - p_min*p_min,
        2*a_min*r_min, 2*a_max*r_max)
    if cos1_max < -1 or cos1_min > 1 or cos2_max < -1 or cos2_min > 1:
        return True  # 歯先円交点の式で判定できない範囲は残す。
    theta1_max = math.acos(max(-1.0, min(1.0, cos1_min)))
    theta2_min = math.acos(max(-1.0, min(1.0, cos2_max)))
    ap_max = math.acos(bp / p_max)
    ar_min = math.acos(br / r_min)
    aw_max = math.acos(min(1.0, (br - bp) / a_max))

    # 元の回避式を展開:
    # q*theta1 + q*inv(ap) + (1-q)*inv(aw) - inv(ar) - theta2 >= 0
    q = planet / ring
    margin_max = q*theta1_max + q*involute(ap_max) + (1-q)*involute(aw_max)
    margin_max -= involute(ar_min) + theta2_min
    return margin_max >= -tolerance


def pair_trochoid_possible(module, planet, ring, centers, sun=None):
    """P1ならsunを渡し、minを含む歯先径の上下限を使う。"""
    shift_min = x_min
    shift_max = x_max
    if sun is not None:
        ya_min = centers[0] / module - (sun + planet) / 2
        ya_max = centers[1] / module - (sun + planet) / 2
        shift_min = min(ya_min - x_max, x_min)
        shift_max = min(ya_max - x_min, x_max)
    planet_tips = (module*(planet+2+2*shift_min), module*(planet+2+2*shift_max))
    ring_tips = (module*(ring-2+2*x_min), module*(ring-2+2*x_max))
    return trochoid_possible(module, planet, ring, centers, planet_tips, ring_tips)


# 5. 具体的な転位・中心距離が決まった後の干渉判定
def internal_interference(module, planet, ring, center, planet_tip, ring_tip):
    """実際の歯先直径を受け取って3種類を判定する。

    P1のplanet_tipにはminを含む実際の歯先径を渡す。
    歯数探索だけでは転位が未定なので、この関数はまだ呼ばない。
    解析式の定義域外はNone（判定できない）。
    """
    result = {"involute": None, "trochoid": None, "trimming": None}
    p = planet_tip / 2
    r = ring_tip / 2
    bp = module * planet * math.cos(alpha) / 2
    br = module * ring * math.cos(alpha) / 2
    base_center = br - bp
    if ring <= planet or center <= 0 or p <= bp or r <= br or center < base_center:
        return result
    ap = math.acos(bp / p)
    ar = math.acos(br / r)
    aw = math.acos(base_center / center)
    result["involute"] = (ring - planet) * math.tan(aw) <= ring * math.tan(ar) + tolerance

    cosine1 = (r*r - p*p - center*center) / (2*center*p)
    cosine2 = (center*center + r*r - p*p) / (2*center*r)
    if -1 <= cosine1 <= 1 and -1 <= cosine2 <= 1:
        theta1 = math.acos(cosine1) + involute(ap) - involute(aw)
        theta2 = math.acos(cosine2)
        margin = theta1 * planet / ring + involute(aw) - involute(ar) - theta2
        result["trochoid"] = margin >= -tolerance

    ratio = planet / ring
    sine_p2 = (1 - (math.cos(ap) / math.cos(ar))**2) / (1 - ratio**2)
    sine_r2 = ((math.cos(ar) / math.cos(ap))**2 - 1) / (1 / ratio**2 - 1)
    if 0 <= sine_p2 <= 1 and 0 <= sine_r2 <= 1:
        theta_p = math.asin(math.sqrt(sine_p2))
        theta_r = math.asin(math.sqrt(sine_r2))
        margin = theta_p + involute(ap) - involute(aw)
        margin -= (theta_r + involute(ar) - involute(aw)) / ratio
        result["trimming"] = margin >= -tolerance
    return result


def reduction_ratio(sun, planet1, ring1, planet2, ring2):
    """R1固定・S入力・R2出力の減速倍率。出力停止ならNone。

    出力/入力 = zs*(zr2*zp1-zr1*zp2) / (zr2*zp1*(zs+zr1))
    減速倍率はその逆数の絶対値。転位や中心距離には依存しない。
    """
    numerator = sun * (ring2*planet1 - ring1*planet2)
    denominator = ring2 * planet1 * (sun + ring1)
    if numerator == 0:
        return None
    return denominator / abs(numerator)


# 6. 探索本体。importするだけでは探索が始まらない。
def search(modules, diameter1, diameter2, output_path):
    if not 0 < reduction_min <= reduction_max or not math.isfinite(reduction_min):
        raise ValueError("減速倍率は0 < reduction_min <= reduction_maxにしてください")
    num = 0
    z_r_min = ring_minimum()

    # 歯数差ごとの内歯中心距離範囲を一度計算し、辞書に保存。
    internal_tables = {}
    for module in modules:
        table = {}
        maximum = math.floor(max(diameter1, diameter2) / module + tolerance)
        for difference in range(1, maximum + 1):
            table[difference] = center_range(module, difference, x_min - x_max, x_max - x_min)
        internal_tables[module] = table

    with open(output_path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["ma", "mc", "zs", "zp1", "zr1", "zr2", "zp2", "reduction", "a_min", "a_max", "status"])

        for m_a in modules:
            z_r1_max = math.floor(diameter1 / m_a + tolerance)
            table_a = internal_tables[m_a]
            # 全歯数共通の広いcos範囲。元のS→P1の絞り込み。
            alpha_min = math.cos(working_angle(x_max, x_max, 1, z_s_min, z_p1_min, pressure_angle))
            beta_min = math.cos(working_angle(x_min, x_max, -1, 0, 1, pressure_angle))
            s_a = alpha_min
            t_a = 1 / beta_min

            for z_s in range(z_s_min, z_r1_max + 1):
                p1_lower = max(z_p1_min, math.ceil((s_a * z_r_min - z_s) / (1 + s_a) - tolerance))
                p1_upper = min(z_r1_max - 1, math.floor((t_a * z_r1_max - z_s) / (1 + t_a) + tolerance))

                for z_p1 in range(p1_lower, p1_upper + 1):
                    centers_a = center_range(m_a, z_s + z_p1, 2*x_min, 2*x_max)
                    if centers_a is None:
                        continue
                    ya_min = centers_a[0] / m_a - (z_s + z_p1) / 2
                    tip_shift_min = min(ya_min - x_max, x_min)
                    if not planet_can_fit(m_a, z_p1, centers_a, tip_shift_min):
                        continue

                    differences = difference_range(centers_a, z_r1_max - z_p1, table_a)
                    if differences is None:
                        continue
                    r1_lower = max(z_r_min, z_p1 + differences[0])
                    r1_upper = min(z_r1_max, z_p1 + differences[1])
                    # 第一層の等配。開始値を合わせ、N刻みでR1を列挙。
                    r1_start = r1_lower + (-z_s - r1_lower) % planet_count

                    for z_r1 in range(r1_start, r1_upper + 1, planet_count):
                        centers_ab = overlap(centers_a, table_a[z_r1 - z_p1])
                        if centers_ab is None:
                            continue
                        if not internal_involute_possible(m_a, z_p1, z_r1, centers_ab):
                            continue
                        # R1で狭まった中心距離を使い、P1を再確認。
                        ya_min = centers_ab[0] / m_a - (z_s + z_p1) / 2
                        tip_shift_min = min(ya_min - x_max, x_min)
                        if not planet_can_fit(m_a, z_p1, centers_ab, tip_shift_min):
                            continue
                        if not pair_trochoid_possible(m_a, z_p1, z_r1, centers_ab, z_s):
                            continue

                        for m_c in modules:
                            z_r2_max = math.floor(diameter2 / m_c + tolerance)
                            table_c = internal_tables[m_c]
                            differences = difference_range(centers_ab, z_r2_max - z_p2_min, table_c)
                            if differences is None:
                                continue
                            r2_lower = max(z_r_min, z_p2_min + differences[0])

                            for z_r2 in range(r2_lower, z_r2_max + 1):
                                p2_lower = max(z_p2_min, z_r2 - differences[1])
                                p2_upper = z_r2 - differences[0]

                                for z_p2 in range(p2_lower, p2_upper + 1):
                                    # 同じP1/P2相対位相を持つ複合遊星の等配。
                                    phase = z_r2*z_p1 - z_r1*z_p2
                                    divisor = planet_count * math.gcd(z_p1, z_p2)
                                    if phase % divisor != 0:
                                        continue
                                    # 全歯数が揃ったので、重い干渉計算の前に減速倍率を確認。
                                    reduction = reduction_ratio(z_s, z_p1, z_r1, z_p2, z_r2)
                                    if reduction is None:  # 出力が停止する組合せ
                                        continue
                                    if reduction < reduction_min or reduction > reduction_max:
                                        continue
                                    centers_abc = overlap(centers_ab, table_c[z_r2 - z_p2])
                                    if centers_abc is None:
                                        continue
                                    if not planet_can_fit(m_c, z_p2, centers_abc, x_min):
                                        continue
                                    if not internal_involute_possible(m_c, z_p2, z_r2, centers_abc):
                                        continue
                                    if not pair_trochoid_possible(m_c, z_p2, z_r2, centers_abc):
                                        continue
                                    # 第二層で中心距離が狭まったので第一層も再確認。
                                    if not pair_trochoid_possible(m_a, z_p1, z_r1, centers_abc, z_s):
                                        continue
                                    # 転位を具体的に決める詳細判定とトリミングは未接続。
                                    writer.writerow([m_a, m_c, z_s, z_p1, z_r1, z_r2, z_p2, reduction,
                                                     centers_abc[0], centers_abc[1], "転位・干渉の詳細判定待ち"])
                                    num += 1
            print("ma =", m_a, "まで終了。累計候補数 =", num)
    return num


if __name__ == "__main__":
    output = Path(__file__).with_name("candidates.csv")
    count = search(tooth_size, D1, D2, output)
    print("探索候補数（成立保証ではありません）:", count)
    print("保存先:", output)
