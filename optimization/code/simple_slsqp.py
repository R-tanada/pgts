"""論文Table IIIの歯数を固定し、初期値1つから式(64)の順効率を最大化。

optimize_profile_shift.pyと同じフォルダで使用: python simple_slsqp.py
"""
from pathlib import Path

from optimize_profile_shift import (
    load_scientific_libraries, load_config, variable_bounds, margins_for,
)
from profile_shift_model import Gearbox, Model

_, _, minimize = load_scientific_libraries()
config = load_config(Path(__file__).with_name("optimization_config.json"))
gearbox = Gearbox()  # 論文Table IIIの固定歯数
model = Model(gearbox, friction=config["friction_coefficient"])


def objective(x):
    """x = [xr1, xr2, 共通中心間距離(mm)]。順効率を最大化するため負号を付ける。"""
    model.calculate(x)
    return -model.forward_efficiency


def constraints(x):
    """5歯車の転位範囲・かみ合い率・干渉など。各値が0以上なら合格。"""
    model.calculate(x)
    return list(margins_for(model, gearbox, config).values())


initial_guess = [1.0, 0.5, 21.0]  # 初期値はこの1点だけ

result = minimize(
    fun=objective,
    x0=initial_guess,
    method="SLSQP",  # 逐次二次計画法
    bounds=variable_bounds(gearbox, config),
    # constraints={"type": "ineq", "fun": constraints},
    options={"maxiter": 1000, "ftol": 1e-11},
)

model.calculate(result.x)
print("収束したか:", result.success, result.message)
print("制約を満たすか:", min(constraints(result.x)) >= -config["feasibility_tolerance"])
print("転位係数:", model.shifts.to_dict())
print("共通中心間距離 [mm]:", model.center_mm)
print(f"順効率: {model.forward_efficiency:.6%}")
