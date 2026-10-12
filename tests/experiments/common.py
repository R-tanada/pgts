"""確認用コードの共通設定・保存。本番の設定や出力は変更しない。"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from optimization import optimize_candidates as opt
from optimization.profile_shift_model import Gearbox, Model, center_for_external_shift_sum


def load_settings(path=None):
    path = Path(path or Path(__file__).with_name("config.json")).resolve()
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    # 本番と同じ入力検証を使い、値は確認用JSONからのみ取得する。
    defaults = {"input_csv": "unused", "output_directory": "unused", "workers": 1,
                "pressure_angle_deg": data["gearbox"]["pressure_angle_deg"],
                "planet_count": data["gearbox"]["planet_count"]}
    config = dict(defaults, **data["optimization"])
    opt.validate_config(config)
    quasi = data["quasi_newton"]
    for name in ("outer_iterations", "inner_iterations"):
        if type(quasi[name]) is not int or quasi[name] < 1:
            raise ValueError(f"{name}は1以上の整数です")
    for name in ("initial_penalty", "penalty_growth", "optimality_tolerance"):
        if not math.isfinite(quasi[name]) or quasi[name] <= (1 if name == "penalty_growth" else 0):
            raise ValueError(f"{name}が不正です")
    if type(data["plots"]["enabled"]) is not bool or type(data["plots"]["grid_count"]) is not int or data["plots"]["grid_count"] < 3:
        raise ValueError("plotsにはenabledの真偽値と3以上のgrid_countが必要です")
    g = data["gearbox"]
    opt.gearbox_from_row({"zs": g["zs"], "zp1": g["zp1"], "zr1": g["zr1"],
                         "zp2": g["zp2"], "zr2": g["zr2"],
                         "ma": g["module_a"], "mc": g["module_c"]}, config)
    if config["start_count"] < 1 or config["max_iterations"] < 1:
        raise ValueError("初期値数・反復数は1以上です")
    if not config["shift_lower"] < config["shift_upper"] or config["feasibility_tolerance"] <= 0:
        raise ValueError("転位範囲・許容誤差が不正です")
    output = (path.parent/data["output_directory"]).resolve()
    # 本番の設定・出力先への誤書込みを防ぐ。
    tests_root = ROOT/"tests"
    if not output.is_relative_to(tests_root):
        raise ValueError("確認用出力先はtests/内に指定してください")
    return data, Gearbox(**g), config, output


def save_report(report, output):
    output.mkdir(parents=True, exist_ok=True)
    (output/"result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def optimization_report(method, g, config, best, trials, versions):
    selected = best[2] if best else max(range(len(trials)), key=lambda i:
        min((trials[i].get("constraint_margins") or {"invalid": -1e6}).values()))
    if best:
        m, margins, _ = best
    else:
        m = Model(g, config["friction_coefficient"])
        try:
            m.calculate(trials[selected]["final_variables"])
            margins = opt.margins_for(m, config)
        except (ValueError, ZeroDivisionError, OverflowError):
            m, margins = None, None
    return {"method": method, "status": "success" if best else "no_converged_feasible_solution",
            "gearbox": g.to_dict(), "settings": config, "library_versions": versions,
            "best": m.to_dict() if best else None, "plot_evaluation": m.to_dict() if m else None,
            "constraint_margins": margins, "selected_trial": selected, "trials": trials}


def print_result(report):
    value = report["best"]
    print("状態:", report["status"])
    if value:
        print("転位:", value["shifts"])
        print("共通中心距離 [mm]:", value["center_mm"])
        print(f"順効率: {value['forward_efficiency']:.6%}、逆効率: {value['backward_efficiency']:.6%}")
    print("収束した可行解:", sum(t["accepted"] for t in report["trials"]), "/", len(report["trials"]))


def finish(method, data, g, config, best, trials, versions, output):
    report = optimization_report(method, g, config, best, trials, versions)
    save_report(report, output)
    if data["plots"]["enabled"]:
        from tests.experiments.plots import generate_graphs
        generate_graphs(report, output, data["plots"]["grid_count"])
    print_result(report)
    print("結果:", output)
    return report
