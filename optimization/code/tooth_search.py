#  -*- coding: utf-8 -*-
"""無転位・標準20度平歯車の3K Type-I歯数探索。

S入力 / R1固定 / R2出力。P1とP2は同じ軸に固定した複合遊星。
設定: search_config.json。実行: python tooth_search.py
数式の出典と判定範囲は README.md を参照。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Iterator


PRESSURE_ANGLE = math.radians(20.0)
NUMERIC_TOLERANCE = 1e-10


@dataclass(frozen=True)
class ToothRange:
    """上限・下限の両端を含む歯数範囲。"""
    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        if type(self.minimum) is not int or type(self.maximum) is not int:
            raise ValueError("歯数の上限・下限は整数で指定してください")
        if not 1 <= self.minimum <= self.maximum:
            raise ValueError("歯数は 1 <= minimum <= maximum が必要です")

    def __contains__(self, teeth: int) -> bool:
        return self.minimum <= teeth <= self.maximum

    def values(self) -> range:
        return range(self.minimum, self.maximum + 1)


@dataclass(frozen=True)
class Settings:
    sun: ToothRange
    planet1: ToothRange
    ring1: ToothRange
    planet2: ToothRange
    ring2: ToothRange
    module1: Fraction
    module2: Fraction
    planet_count: int
    reduction_min: Fraction
    reduction_max: Fraction
    direction: str
    planet_clearance_mm: float


@dataclass(frozen=True)
class ToothCounts:
    zs: int
    zp1: int
    zr1: int
    zp2: int
    zr2: int


@dataclass(frozen=True)
class StandardGear:
    """標準歯車の半径。内歯車の歯先は基準円の内側にある。"""
    teeth: int
    module: float
    internal: bool = False

    @property
    def pitch_radius(self) -> float:
        return self.module * self.teeth / 2

    @property
    def base_radius(self) -> float:
        return self.pitch_radius * math.cos(PRESSURE_ANGLE)

    @property
    def tip_radius(self) -> float:
        addendum = -self.module if self.internal else self.module
        return self.pitch_radius + addendum

    @property
    def tip_angle(self) -> float:
        # 基礎円より内側の歯先には、この解析式を適用できない。
        if self.tip_radius < self.base_radius:
            raise ValueError("歯先円が基礎円より小さいため解析式の適用範囲外")
        return math.acos(self.base_radius / self.tip_radius)


def involute(angle: float) -> float:
    """inv(alpha) = tan(alpha) - alpha。角度はラジアン。"""
    return math.tan(angle) - angle


def speed_ratio(teeth: ToothCounts) -> Fraction:
    """論文の式(44)-(46): 符号付き出力速度 / 入力速度。"""
    numerator = teeth.zs * (teeth.zr2 * teeth.zp1 - teeth.zr1 * teeth.zp2)
    denominator = teeth.zr2 * teeth.zp1 * (teeth.zs + teeth.zr1)
    return Fraction(numerator, denominator)


def satisfies_reduction_ratio(teeth: ToothCounts, settings: Settings) -> bool:
    ratio = speed_ratio(teeth)
    if ratio == 0:
        return False
    if settings.direction == "same" and ratio < 0:
        return False
    if settings.direction == "opposite" and ratio > 0:
        return False
    return settings.reduction_min <= abs(1 / ratio) <= settings.reduction_max


def center_distances(teeth: ToothCounts, settings: Settings) -> tuple[Fraction, ...]:
    """無転位なので標準中心距離を使う。分数で等値を厳密に判定。"""
    sun_planet = settings.module1 * (teeth.zs + teeth.zp1) / 2
    planet1_ring1 = settings.module1 * (teeth.zr1 - teeth.zp1) / 2
    planet2_ring2 = settings.module2 * (teeth.zr2 - teeth.zp2) / 2
    return sun_planet, planet1_ring1, planet2_ring2


def satisfies_center_distance(teeth: ToothCounts, settings: Settings) -> bool:
    distance1, distance2, distance3 = center_distances(teeth, settings)
    return distance1 > 0 and distance1 == distance2 == distance3


def satisfies_equal_spacing(teeth: ToothCounts, settings: Settings) -> bool:
    """同一歯位相で製作した複合遊星をN個、等間隔に配置する条件。

    第1層: (zs + zr1) / N が整数。
    内歯車2枚: (zr2*zp1 - zr1*zp2) / (N*gcd(zp1,zp2)) が整数。
    各複合遊星は全体として回転して歯合わせできるものとする。
    """
    count = settings.planet_count
    first_layer_ok = (teeth.zs + teeth.zr1) % count == 0
    phase_difference = teeth.zr2 * teeth.zp1 - teeth.zr1 * teeth.zp2
    compound_ok = phase_difference % (count * math.gcd(teeth.zp1, teeth.zp2)) == 0
    return first_layer_ok and compound_ok


def planet_tip_clearances(teeth: ToothCounts, settings: Settings) -> tuple[float, float]:
    center = float(center_distances(teeth, settings)[0])
    neighbor_distance = 2 * center * math.sin(math.pi / settings.planet_count)
    diameter1 = float(settings.module1) * (teeth.zp1 + 2)
    diameter2 = float(settings.module2) * (teeth.zp2 + 2)
    return neighbor_distance - diameter1, neighbor_distance - diameter2


def satisfies_outside_diameter(teeth: ToothCounts, settings: Settings) -> bool:
    """各層の隣接遊星の歯先円の間に、指定すきまを確保する。"""
    # 歯先円の接触も不合格。P1とP2は別の軸方向位置にある。
    return all(gap > settings.planet_clearance_mm
               for gap in planet_tip_clearances(teeth, settings))


def satisfies_external_involute(sun: StandardGear, planet: StandardGear) -> bool:
    """S-P1の作用線の接触区間が、両歯車の基礎円外にあること。

    切下げの最小歯数判定とは別の、相手歯先との干渉判定。
    """
    center = sun.pitch_radius + planet.pitch_radius
    tangent_length = center * math.sin(PRESSURE_ANGLE)
    sun_tip_length = math.sqrt(sun.tip_radius**2 - sun.base_radius**2)
    planet_tip_length = math.sqrt(planet.tip_radius**2 - planet.base_radius**2)
    return max(sun_tip_length, planet_tip_length) <= tangent_length + NUMERIC_TOLERANCE


def satisfies_internal_involute(planet: StandardGear, ring: StandardGear) -> bool:
    """KHK: zp/zr >= 1 - tan(alpha_ar)/tan(alpha_w)。"""
    if ring.tip_radius < ring.base_radius:
        return False  # 解析式の適用範囲外は合格として扱わない。
    lower_limit = 1 - math.tan(ring.tip_angle) / math.tan(PRESSURE_ANGLE)
    return planet.teeth / ring.teeth >= lower_limit - NUMERIC_TOLERANCE


def satisfies_trochoid(planet: StandardGear, ring: StandardGear) -> bool:
    """標準20度の保守的な十分条件。KHK: zr - zp > 9。

    厳密な限界式ではない。歯数差9以下の一部の非干渉対も除外する。
    """
    return ring.teeth - planet.teeth > 9


def satisfies_trimming(planet: StandardGear, ring: StandardGear) -> bool:
    """KHKのトリミング回避式。半径方向の組付け・分離を判定。

    theta_p + inv(alpha_ap) - inv(alpha_w)
      >= (zr/zp) * (theta_r + inv(alpha_ar) - inv(alpha_w))
    切削工具との干渉は、工具の歯数・転位が別途必要なので対象外。
    """
    if ring.tip_radius < ring.base_radius:
        return False
    angle_p, angle_r = planet.tip_angle, ring.tip_angle
    cosine_p, cosine_r = math.cos(angle_p), math.cos(angle_r)
    tooth_ratio = planet.teeth / ring.teeth
    sine_p_squared = (1 - (cosine_p / cosine_r)**2) / (1 - tooth_ratio**2)
    sine_r_squared = ((cosine_r / cosine_p)**2 - 1) / (1 / tooth_ratio**2 - 1)
    if not all(-NUMERIC_TOLERANCE <= value <= 1 + NUMERIC_TOLERANCE
               for value in (sine_p_squared, sine_r_squared)):
        return False
    theta_p = math.asin(math.sqrt(min(1.0, max(0.0, sine_p_squared))))
    theta_r = math.asin(math.sqrt(min(1.0, max(0.0, sine_r_squared))))
    left = theta_p + involute(angle_p) - involute(PRESSURE_ANGLE)
    right = (theta_r + involute(angle_r) - involute(PRESSURE_ANGLE)) / tooth_ratio
    return left >= right - NUMERIC_TOLERANCE


@lru_cache(maxsize=16384)
def internal_mesh_failure(planet_teeth: int, ring_teeth: int, module: Fraction) -> str | None:
    """同じ内歯かみあい対の繰り返し計算を避ける。"""
    if ring_teeth <= planet_teeth:
        return "ring_not_larger_than_planet"
    planet = StandardGear(planet_teeth, float(module))
    ring = StandardGear(ring_teeth, float(module), internal=True)
    if not satisfies_internal_involute(planet, ring):
        return "involute"
    if not satisfies_trochoid(planet, ring):
        return "trochoid"
    if not satisfies_trimming(planet, ring):
        return "trimming"
    return None


def first_failed_constraint(teeth: ToothCounts, settings: Settings) -> str | None:
    """最初に不合格となる条件名。全条件を満たす場合はNone。"""
    if not satisfies_reduction_ratio(teeth, settings):
        return "reduction_ratio"
    if not satisfies_center_distance(teeth, settings):
        return "center_distance"
    if not satisfies_equal_spacing(teeth, settings):
        return "equal_spacing"
    if not satisfies_outside_diameter(teeth, settings):
        return "outside_diameter"
    sun = StandardGear(teeth.zs, float(settings.module1))
    planet1 = StandardGear(teeth.zp1, float(settings.module1))
    if not satisfies_external_involute(sun, planet1):
        return "involute_S_P1"
    for label, planet, ring, module in (
        ("P1_R1", teeth.zp1, teeth.zr1, settings.module1),
        ("P2_R2", teeth.zp2, teeth.zr2, settings.module2),
    ):
        failure = internal_mesh_failure(planet, ring, module)
        if failure:
            return f"{failure}_{label}"
    return None


def enumerate_center_matched_teeth(settings: Settings) -> Iterator[ToothCounts]:
    """中心距離の等式からR1/R2を計算する、漏れのない列挙。

    5重ループを避けるだけで、各歯車の指定上下限は必ず確認する。
    """
    for zs in settings.sun.values():
        for zp1 in settings.planet1.values():
            zr1 = zs + 2 * zp1
            if zr1 not in settings.ring1:
                continue
            ring2_difference = settings.module1 * (zs + zp1) / settings.module2
            if ring2_difference.denominator != 1:
                continue
            for zp2 in settings.planet2.values():
                zr2 = zp2 + int(ring2_difference)
                if zr2 in settings.ring2:
                    yield ToothCounts(zs, zp1, zr1, zp2, zr2)


def load_settings(path: Path) -> tuple[Settings, dict]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    allowed = {"tooth_ranges", "module1_mm", "module2_mm", "planet_count",
               "reduction_min", "reduction_max", "direction", "planet_clearance_mm",
               "output_csv"}
    if set(raw) != allowed:
        raise ValueError(f"設定キーの不足または余分: {set(raw) ^ allowed}")
    ranges = raw["tooth_ranges"]
    names = ("sun", "planet1", "ring1", "planet2", "ring2")
    if set(ranges) != set(names):
        raise ValueError("tooth_rangesにはsun, planet1, ring1, planet2, ring2が必要です")
    settings = Settings(
        **{name: ToothRange(**ranges[name]) for name in names},
        module1=Fraction(str(raw["module1_mm"])),
        module2=Fraction(str(raw["module2_mm"])),
        planet_count=raw["planet_count"],
        reduction_min=Fraction(str(raw["reduction_min"])),
        reduction_max=Fraction(str(raw["reduction_max"])),
        direction=raw["direction"],
        planet_clearance_mm=float(raw["planet_clearance_mm"]),
    )
    if min(settings.module1, settings.module2) <= 0:
        raise ValueError("モジュールは正の値が必要です")
    if type(settings.planet_count) is not int or settings.planet_count < 2:
        raise ValueError("planet_countは2以上の整数が必要です")
    if not 1 < settings.reduction_min <= settings.reduction_max:
        raise ValueError("減速倍率は 1 < reduction_min <= reduction_max が必要です")
    if settings.direction not in ("same", "opposite", "both"):
        raise ValueError("directionはsame, opposite, bothのいずれかです")
    if not math.isfinite(settings.planet_clearance_mm) or settings.planet_clearance_mm < 0:
        raise ValueError("planet_clearance_mmは有限の非負値が必要です")
    if not isinstance(raw["output_csv"], str) or not raw["output_csv"]:
        raise ValueError("output_csvにはファイル名が必要です")
    return settings, raw


def save_candidates(settings: Settings, output: Path) -> Counter:
    """全合格候補を逐次保存。メモリに全候補を溜めない。"""
    output.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["zs", "zp1", "zr1", "zp2", "zr2", "G_exact", "G",
                         "reduction_abs", "direction", "center_distance_mm",
                         "planet1_tip_clearance_mm", "planet2_tip_clearance_mm"])
        for teeth in enumerate_center_matched_teeth(settings):
            counts["center_matched_combinations"] += 1
            failure = first_failed_constraint(teeth, settings)
            if failure:
                counts[f"rejected_{failure}"] += 1
                continue
            ratio = speed_ratio(teeth)
            gaps = planet_tip_clearances(teeth, settings)
            writer.writerow([*asdict(teeth).values(), str(ratio), float(ratio),
                             float(abs(1 / ratio)), "same" if ratio > 0 else "opposite",
                             float(center_distances(teeth, settings)[0]), *gaps])
            counts["accepted"] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=Path(__file__).with_name("search_config.json"))
    args = parser.parse_args()
    try:
        settings, raw = load_settings(args.config)
    except (ValueError, TypeError, KeyError, OSError, ZeroDivisionError) as error:
        parser.error(str(error))
    output = args.config.resolve().parent / raw["output_csv"]
    summary_path = output.with_suffix(".summary.json")
    if output.resolve() in (args.config.resolve(), Path(__file__).resolve()):
        parser.error("output_csvに設定ファイルやコード自身は指定できません")
    if summary_path.resolve() == args.config.resolve():
        parser.error("集計ファイルが設定ファイルと同じパスになります")
    counts = save_candidates(settings, output)
    summary = {"settings": raw, "counts": dict(counts),
               "notes": ["無転位・標準20度。切下げは未判定。",
                         "トロコイド判定は歯数差>9の保守的な十分条件。",
                         "不合格件数は最初に不合格になった条件のみを集計。"]}
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"合格候補: {counts['accepted']} 件")
    print(f"CSV: {output}")
    print(f"設定・判定集計: {summary_path}")


if __name__ == "__main__":
    main()
