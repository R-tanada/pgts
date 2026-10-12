"""固定モジュールの歯数探索。探索順: S → P1 → R1 → R2 → P2。

CSVは必要条件を通った候補。転位・干渉の成立保証ではありません。
"""
import csv
import math
from pathlib import Path


# 1. 設定（変更する値はここにまとめる）
m_a = 0.8     # S・P1・R1のモジュール [mm]
m_c = 0.8467  # P2・R2のモジュール [mm]
z_r1_max = 90  # R1の最大歯数（この値を含む）
z_r2_max = 90  # R2の最大歯数（この値を含む）
x_min = -2
x_max = 2
z_s_min = 8
z_p1_min = 8
z_p2_min = 8
pressure_angle = 20
planet_count = 3
planet_clearance = 0.0  # 隣接遊星間に要求するすきま [mm]
check_trimming = True  # True: 半径方向の組付け・分離の干渉を判定。False: 判定しない。
reduction_min = 95  # 減速倍率の下限（入力速度 / 出力速度の絶対値）
reduction_max = 100  # 減速倍率の上限。math.infなら上限なし。
# 上下限は含む。回転方向は両方向を許す。

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


def tip_diameter_ranges(module, planet, ring, centers, sun=None):
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
    return planet_tips, ring_tips


def pair_trochoid_possible(module, planet, ring, centers, sun=None):
    planet_tips, ring_tips = tip_diameter_ranges(module, planet, ring, centers, sun)
    return trochoid_possible(module, planet, ring, centers, planet_tips, ring_tips)


# 5. トリミング干渉による絞り込み（半径方向の組付け・分離）
def trimming_possible(module, planet, ring, centers, planet_tips, ring_tips):
    """回避条件の余裕の上限が負なら、範囲全体で不成立なので除外。

    Trueは成立保証ではない。判定式の適用外で証明できない範囲も残す。
    歯切り工具との干渉は対象外。
    """
    bp = module * planet * math.cos(alpha) / 2
    br = module * ring * math.cos(alpha) / 2
    p_min = max(bp, planet_tips[0] / 2)
    p_max = planet_tips[1] / 2
    r_min = max(br, ring_tips[0] / 2)
    r_max = ring_tips[1] / 2
    if p_max <= bp or r_max <= br or centers[0] <= 0:
        return True

    # u = cos(alpha_ap) / cos(alpha_ar) = bp*r / (br*p)
    u_min = bp*r_min / (br*p_max)
    u_max = bp*r_max / (br*p_min)
    q = planet / ring
    sine_p2_min = (1 - u_max*u_max) / (1 - q*q)
    sine_p2_max = (1 - u_min*u_min) / (1 - q*q)
    sine_r2_min = (1/(u_max*u_max) - 1) / (1/(q*q) - 1)
    sine_r2_max = (1/(u_min*u_min) - 1) / (1/(q*q) - 1)
    if sine_p2_max < 0 or sine_p2_min > 1 or sine_r2_max < 0 or sine_r2_min > 1:
        return True  # 解析式で判断できない範囲は残す。

    theta_p_max = math.asin(math.sqrt(max(0.0, min(1.0, sine_p2_max))))
    theta_r_min = math.asin(math.sqrt(max(0.0, min(1.0, sine_r2_min))))
    ap_max = math.acos(bp / p_max)
    ar_min = math.acos(br / r_min)
    aw_max = math.acos(min(1.0, (br - bp) / centers[1]))

    # theta_p + inv(ap) - inv(aw) - (theta_r + inv(ar) - inv(aw))/q >= 0
    # 各項を有利な側へ評価して、余裕の上限を求める。
    margin_max = theta_p_max + involute(ap_max) + (1/q - 1)*involute(aw_max)
    margin_max -= (theta_r_min + involute(ar_min)) / q
    return margin_max >= -tolerance


def pair_trimming_possible(module, planet, ring, centers, sun=None):
    planet_tips, ring_tips = tip_diameter_ranges(module, planet, ring, centers, sun)
    return trimming_possible(module, planet, ring, centers, planet_tips, ring_tips)


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
def search(output_path):
    if not 0 < reduction_min <= reduction_max or not math.isfinite(reduction_min):
        raise ValueError("減速倍率は0 < reduction_min <= reduction_maxにしてください")
    if not isinstance(z_r1_max, int) or not isinstance(z_r2_max, int):
        raise ValueError("リングの最大歯数は整数で指定してください")
    if z_r1_max <= z_p1_min or z_r2_max <= z_p2_min:
        raise ValueError("リングの最大歯数は遊星の最小歯数より大きくしてください")

    num = 0
    z_r_min = ring_minimum()

    # 準備: 内歯かみ合いの「歯数差 → 中心距離範囲」を保存する。
    table_a = {}
    for difference in range(1, z_r1_max + 1):
        table_a[difference] = center_range(
            m_a, difference, x_min - x_max, x_max - x_min)
    table_c = {}
    for difference in range(1, z_r2_max + 1):
        table_c[difference] = center_range(
            m_c, difference, x_min - x_max, x_max - x_min)

    # SからP1を絞るための、全歯数共通の広い作動圧力角範囲。
    alpha_min = math.cos(working_angle(
        x_max, x_max, 1, z_s_min, z_p1_min, pressure_angle))
    beta_min = math.cos(working_angle(
        x_min, x_max, -1, 0, 1, pressure_angle))
    s_a = alpha_min
    t_a = 1 / beta_min

    with open(output_path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow([
            "番号", "ma", "mc", "zs", "zp1", "zr1", "zp2", "zr2", "減速比"])

        # ① Sを選び、中心距離条件からP1の範囲を絞る。
        for z_s in range(z_s_min, z_r1_max + 1):
            p1_lower = max(
                z_p1_min,
                math.ceil((s_a*z_r_min - z_s) / (1+s_a) - tolerance))
            p1_upper = min(
                z_r1_max - 1,
                math.floor((t_a*z_r1_max - z_s) / (1+t_a) + tolerance))

            # ② P1を選び、S–P1の中心距離範囲を求める。
            for z_p1 in range(p1_lower, p1_upper + 1):
                centers_a = center_range(
                    m_a, z_s + z_p1, 2*x_min, 2*x_max)
                if centers_a is None:
                    continue
                ya_min = centers_a[0] / m_a - (z_s + z_p1) / 2
                tip_shift_min = min(ya_min - x_max, x_min)
                if not planet_can_fit(m_a, z_p1, centers_a, tip_shift_min):
                    continue

                # ③ R1の範囲を絞り、第一層の等配に合う歯数だけ列挙する。
                differences = difference_range(
                    centers_a, z_r1_max - z_p1, table_a)
                if differences is None:
                    continue
                r1_lower = max(z_r_min, z_p1 + differences[0])
                r1_upper = min(z_r1_max, z_p1 + differences[1])
                r1_start = r1_lower + (-z_s - r1_lower) % planet_count

                for z_r1 in range(r1_start, r1_upper + 1, planet_count):
                    centers_ab = overlap(
                        centers_a, table_a[z_r1 - z_p1])
                    if centers_ab is None:
                        continue
                    if not internal_involute_possible(
                            m_a, z_p1, z_r1, centers_ab):
                        continue
                    ya_min = centers_ab[0] / m_a - (z_s + z_p1) / 2
                    tip_shift_min = min(ya_min - x_max, x_min)
                    if not planet_can_fit(
                            m_a, z_p1, centers_ab, tip_shift_min):
                        continue
                    if not pair_trochoid_possible(
                            m_a, z_p1, z_r1, centers_ab, z_s):
                        continue
                    if check_trimming:
                        if not pair_trimming_possible(
                                m_a, z_p1, z_r1, centers_ab, z_s):
                            continue

                    # ④ 共通中心距離から第二層の歯数差を絞り、R2を選ぶ。
                    differences = difference_range(
                        centers_ab, z_r2_max - z_p2_min, table_c)
                    if differences is None:
                        continue
                    r2_lower = max(z_r_min, z_p2_min + differences[0])

                    for z_r2 in range(r2_lower, z_r2_max + 1):
                        p2_lower = max(z_p2_min, z_r2 - differences[1])
                        p2_upper = z_r2 - differences[0]

                        # ⑤ P2を選び、複合遊星の等配と減速倍率を確認する。
                        for z_p2 in range(p2_lower, p2_upper + 1):
                            phase = z_r2*z_p1 - z_r1*z_p2
                            divisor = planet_count * math.gcd(z_p1, z_p2)
                            if phase % divisor != 0:
                                continue
                            reduction = reduction_ratio(
                                z_s, z_p1, z_r1, z_p2, z_r2)
                            if reduction is None:  # 出力停止
                                continue
                            if reduction < reduction_min or reduction > reduction_max:
                                continue

                            # ⑥ 全かみ合いに共通する中心距離と、干渉を確認する。
                            centers_abc = overlap(
                                centers_ab, table_c[z_r2 - z_p2])
                            if centers_abc is None:
                                continue
                            if not planet_can_fit(
                                    m_c, z_p2, centers_abc, x_min):
                                continue
                            if not internal_involute_possible(
                                    m_c, z_p2, z_r2, centers_abc):
                                continue
                            if not pair_trochoid_possible(
                                    m_c, z_p2, z_r2, centers_abc):
                                continue
                            if not pair_trochoid_possible(
                                    m_a, z_p1, z_r1, centers_abc, z_s):
                                continue

                            if check_trimming:
                                if not pair_trimming_possible(
                                        m_c, z_p2, z_r2, centers_abc):
                                    continue
                                if not pair_trimming_possible(
                                        m_a, z_p1, z_r1, centers_abc, z_s):
                                    continue

                            # 転位の具体値による全条件の同時成立確認は別段階。
                            writer.writerow([
                                num + 1, m_a, m_c, z_s, z_p1, z_r1, z_p2, z_r2, reduction])
                            num += 1
    return num


if __name__ == "__main__":
    output = Path(__file__).with_name("tooth_search_candidates.csv")
    count = search(output)
    print("探索候補数（成立保証ではありません）:", count)
    print("保存先:", output)
