"""標準・転位なし歯車の解析式による干渉検査。

KHK「内歯車の寸法計算」式4.4〜4.12。1=遊星、2=リング。
トリミングは歯車ペアの半径方向組立を検査し、工具の歯切り可否は扱わない。
切下げは標準ラック創成・歯末係数1の理論限界（式3.6〜3.7）。
"""
from dataclasses import dataclass
from math import acos, asin, ceil, cos, isfinite, pi, sin, sqrt, tan


@dataclass(frozen=True)
class InterferenceCheck:
    key: str
    name: str
    ok: bool | None
    detail: str
    formula: str
    blocks_assembly: bool = True

    def __iter__(self):
        return iter((self.name, self.ok, self.detail))


def _unit(value):
    if not isfinite(value) or value < -1 - 1e-12 or value > 1 + 1e-12:
        raise ValueError('逆三角関数の定義域外')
    return min(1., max(-1., value))


def _asin_sqrt(value):
    if value < -1e-12 or value > 1 + 1e-12:
        raise ValueError('角度を定義できない歯数の組合せ')
    return asin(sqrt(min(1., max(0., value))))


def interference_checks(spec):
    z1, z2 = spec.planet_teeth, spec.ring_teeth
    alpha = spec.pressure_angle_deg * pi / 180
    names = ('インボリュート干渉（遊星–リング）', 'トロコイド干渉（遊星–リング）',
             'トリミング干渉（逃げ干渉）')
    keys = ('involute', 'trochoid', 'trimming')
    formulas = (
        '<i>z</i><sub>p</sub>/<i>z</i><sub>r</sub> ≥ 1 − tan α<sub>ar</sub>/tan α',
        'θ<sub>1</sub>(<i>z</i><sub>p</sub>/<i>z</i><sub>r</sub>) + inv α − inv α<sub>ar</sub> ≥ θ<sub>2</sub>',
        'θ<sub>1</sub> + inv α<sub>ap</sub> − inv α<br>≥ '
        '(<i>z</i><sub>r</sub>/<i>z</i><sub>p</sub>)(θ<sub>2</sub> + inv α<sub>ar</sub> − inv α)',
    )
    checks = []
    try:
        if not (isfinite(alpha) and 0 < alpha < pi/4 and z2 > z1 >= 6 and spec.module > 0):
            raise ValueError('リング歯数 > 遊星歯数、正のモジュール・有効な圧力角が必要')
        # Normalize radii by module. Results must be independent of scale.
        ra1, ra2 = z1/2 + 1, z2/2 - 1
        rb1, rb2 = z1/2 * cos(alpha), z2/2 * cos(alpha)
        a = (z2-z1)/2
        if ra2 <= rb2:
            raise ValueError('リング歯先円が基礎円以下のため、この解析式は適用外')
        aa1, aa2 = acos(_unit(rb1/ra1)), acos(_unit(rb2/ra2))
        inv = lambda angle: tan(angle) - angle
        margin = z1/z2 - 1 + tan(aa2)/tan(alpha)
        checks.append(InterferenceCheck(keys[0], names[0], margin >= -1e-12,
            f'回避条件の余裕：{margin:.6f}（0以上）。リング歯先と遊星歯元を検査。', formulas[0]))
    except (ValueError, ZeroDivisionError) as exc:
        return [InterferenceCheck(key, name, None, str(exc), formula, key != 'trimming')
                for key, name, formula in zip(keys, names, formulas)] + undercut_checks(spec)

    try:
        theta1 = acos(_unit((ra2**2-ra1**2-a*a)/(2*a*ra1))) + inv(aa1)-inv(alpha)
        theta2 = acos(_unit((a*a+ra2**2-ra1**2)/(2*a*ra2)))
        margin = theta1*z1/z2 + inv(alpha)-inv(aa2)-theta2
        checks.append(InterferenceCheck(keys[1], names[1], margin >= -1e-12,
            f'回避条件の角度余裕：{margin:.6f} rad（0以上）。θはKHK式4.9。', formulas[1]))
    except (ValueError, ZeroDivisionError) as exc:
        checks.append(InterferenceCheck(keys[1], names[1], None, str(exc), formulas[1]))

    try:
        theta1 = _asin_sqrt((1-(cos(aa1)/cos(aa2))**2)/(1-(z1/z2)**2))
        theta2 = _asin_sqrt(((cos(aa2)/cos(aa1))**2-1)/((z2/z1)**2-1))
        margin = theta1+inv(aa1)-inv(alpha)-(z2/z1)*(theta2+inv(aa2)-inv(alpha))
        ok = margin >= -1e-12
        detail = f'角度余裕：{margin:.6f} rad。θはKHK式4.12。'
        detail += '半径方向の組立に干渉なし。' if ok else '半径方向の組立不可。軸方向から組み付ける必要があります。'
        checks.append(InterferenceCheck(keys[2], names[2], ok, detail, formulas[2], False))
    except (ValueError, ZeroDivisionError) as exc:
        checks.append(InterferenceCheck(keys[2], names[2], None, str(exc), formulas[2], False))
    return checks + undercut_checks(spec)


def undercut_checks(spec):
    alpha = spec.pressure_angle_deg * pi/180
    if not 0 < alpha < pi/4:
        return [InterferenceCheck('undercut', '切下げ（標準ラック創成）', None,
                                 '圧力角が適用範囲外', '0 &lt; α &lt; 45°', False)]
    limit = 2 / sin(alpha)**2
    checks = []
    for key, name, z in (('s', '太陽', spec.sun_teeth), ('p', '遊星', spec.planet_teeth)):
        checks.append(InterferenceCheck('undercut_' + key, f'切下げ（{name}・標準ラック創成）',
            z >= limit - 1e-12,
            f'理論限界 {limit:.3f} 歯、厳密に回避する整数歯数は {ceil(limit-1e-12)} 歯以上。'
            '切下げ量・工具先端丸み・強度は未評価。',
            f'<i>z</i><sub>{key}</sub> ≥ 2 / sin² α', False))
    return checks
