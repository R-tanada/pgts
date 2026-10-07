"""固定歯数(Table III)の転位最適化と論文値の比較。

実行: python optimize_profile_shift.py
設定: optimization_config.json。手法: SciPyのSLSQP（複数初期値）。
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sys
from pathlib import Path

from profile_shift_model import (
    Gearbox, PAPER_CONTACT_RATIOS, PAPER_SHIFTS, PAPER_MEASURED_EFFICIENCIES, center_for_external_shift_sum,
    constraint_margins, Model, reference_center_distances,
)


def load_scientific_libraries():
    """通常のインストールを優先。Codex作業用.dependenciesにも対応。"""
    if importlib.util.find_spec("scipy") is None:
        local_packages = Path(__file__).resolve().parent.parent / ".dependencies"
        if local_packages.is_dir():
            sys.path.insert(0, str(local_packages))
    try:
        import numpy as np
        import scipy
        from scipy.optimize import minimize
    except ImportError as error:
        raise RuntimeError("python -m pip install -r requirements-optimization.txt を実行してください") from error
    return np, scipy, minimize


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    keys = {"friction_coefficient", "shift_lower", "shift_upper", "contact_ratio_lower",
            "contact_ratio_upper", "planet_clearance_mm", "include_trimming_constraint",
            "start_count", "random_seed", "max_iterations", "ftol",
            "feasibility_tolerance", "output_directory"}
    if set(config) != keys:
        raise ValueError(f"設定キーの不足・余分: {set(config) ^ keys}")
    for key in keys - {"output_directory", "include_trimming_constraint"}:
        if isinstance(config[key], bool) or not isinstance(config[key], (float, int)) or not math.isfinite(config[key]):
            raise ValueError(f"{key}は有限の数値が必要です")
    for key in ("start_count", "max_iterations", "random_seed"):
        if type(config[key]) is not int or config[key] < (0 if key == "random_seed" else 1):
            raise ValueError(f"{key}の整数設定が不正です")
    if not 0 < config["friction_coefficient"] < 1:
        raise ValueError("摩擦係数は0より大きく1未満にしてください")
    if not config["shift_lower"] < config["shift_upper"]:
        raise ValueError("転位係数の下限は上限より小さくしてください")
    if not 0 < config["contact_ratio_lower"] < config["contact_ratio_upper"]:
        raise ValueError("かみあい率の上下限が不正です")
    if min(config["ftol"], config["feasibility_tolerance"]) <= 0 or config["planet_clearance_mm"] < 0:
        raise ValueError("許容誤差は正、遊星間すきまは非負にしてください")
    if type(config["include_trimming_constraint"]) is not bool:
        raise ValueError("include_trimming_constraintはtrueまたはfalseが必要です")
    if not isinstance(config["output_directory"], str) or not config["output_directory"]:
        raise ValueError("output_directoryを指定してください")
    return config


def margins_for(evaluation, gearbox, config):
    return constraint_margins(
        evaluation, gearbox, config["shift_lower"], config["shift_upper"],
        config["contact_ratio_lower"], config["contact_ratio_upper"],
        config["planet_clearance_mm"], config["include_trimming_constraint"],
    )


def variable_bounds(gearbox: Gearbox, config: dict):
    """転位和の上限から中心距離の上限を導く。論文値で範囲を絞らない。"""
    cosine = math.cos(gearbox.alpha)
    base_centers = (
        gearbox.module_a * (gearbox.zs + gearbox.zp1) * cosine / 2,
        gearbox.module_a * (gearbox.zr1 - gearbox.zp1) * cosine / 2,
        gearbox.module_c * (gearbox.zr2 - gearbox.zp2) * cosine / 2,
    )
    # acosの端点の導関数が発散するため、基礎円限界のすぐ外側にする。
    center_lower = max(base_centers) + 1e-7
    center_upper = center_for_external_shift_sum(gearbox, 2 * config["shift_upper"])
    if center_upper <= center_lower:
        raise ValueError("この転位範囲では共通中心距離の探索区間がありません")
    shift_bounds = (config["shift_lower"], config["shift_upper"])
    return [shift_bounds, shift_bounds, (center_lower, center_upper)]


def fixed_assembly_checks(gearbox: Gearbox) -> dict:
    count = gearbox.planet_count
    first = (gearbox.zs + gearbox.zr1) % count == 0
    phase = gearbox.zr2 * gearbox.zp1 - gearbox.zr1 * gearbox.zp2
    compound = phase % (count * math.gcd(gearbox.zp1, gearbox.zp2)) == 0
    return {"first_layer_equal_spacing": first, "compound_equal_spacing": compound}


def optimize(gearbox: Gearbox, config: dict):
    np, scipy, minimize = load_scientific_libraries()
    assembly = fixed_assembly_checks(gearbox)
    if not all(assembly.values()):
        raise ValueError("固定歯数が等配条件を満たしません")
    bounds = variable_bounds(gearbox, config)
    lower = np.array([pair[0] for pair in bounds])
    width = np.array([pair[1] - pair[0] for pair in bounds])

    # 3変数を[0,1]に正規化し、転位とmmの尺度差を解消する。
    def decode(normalized):
        return lower + width * np.asarray(normalized)

    def objective(normalized):
        model = Model(gearbox, config["friction_coefficient"])
        model.calculate(decode(normalized))
        return -model.forward_efficiency

    def constraints(normalized):
        result = Model(gearbox, config["friction_coefficient"])
        result.calculate(decode(normalized))
        return np.array(list(margins_for(result, gearbox, config).values()))

    # 論文の転位係数を参照せず、独立した固定シードで初期点を生成。
    rng = np.random.default_rng(config["random_seed"])
    starts = [np.full(3, 0.5)]
    starts.extend(rng.uniform(0.05, 0.95, size=(config["start_count"] - 1, 3)))
    trials, accepted = [], []
    for index, start in enumerate(starts):
        history = []

        def record_iteration(normalized):
            current = Model(gearbox, config["friction_coefficient"])
            current.calculate(decode(normalized))
            current_margins = margins_for(current, gearbox, config)
            minimum_margin = min(current_margins.values())
            history.append({
                "iteration": len(history), "variables": decode(normalized).tolist(),
                "shifts": current.shifts.to_dict(),
                "forward_efficiency": current.forward_efficiency,
                "backward_efficiency": current.backward_efficiency,
                "backward_efficiency_force_balance": current.backward_efficiency_force_balance,
                "minimum_constraint_margin": minimum_margin,
                "maximum_constraint_violation": max(0.0, -minimum_margin),
                "feasible": minimum_margin >= -config["feasibility_tolerance"],
            })

        record_iteration(start)
        result = minimize(objective, start, method="SLSQP",
                          bounds=[(0.0, 1.0)] * 3,
                          constraints={"type": "ineq", "fun": constraints},
                          callback=record_iteration,
                          options={"maxiter": config["max_iterations"], "ftol": config["ftol"]})
        final = Model(gearbox, config["friction_coefficient"])
        final.calculate(decode(result.x))
        if history[-1]["variables"] != decode(result.x).tolist():
            record_iteration(result.x)
        margins = margins_for(final, gearbox, config)
        feasible = min(margins.values()) >= -config["feasibility_tolerance"]
        trial = {
            "start_index": index, "initial_variables": decode(start).tolist(),
            "final_variables": decode(result.x).tolist(), "solver_success": bool(result.success),
            "solver_message": str(result.message), "iterations": int(result.nit),
            "forward_efficiency": final.forward_efficiency,
            "minimum_constraint_margin": min(margins.values()), "feasible": feasible,
            "history": history,
        }
        trials.append(trial)
        # 制約を再評価し、収束した可行解だけを採用する。
        if result.success and feasible and math.isfinite(final.forward_efficiency):
            accepted.append((final, margins, index))
    if not accepted:
        return None, trials, {"scipy": scipy.__version__, "numpy": np.__version__}
    best = max(accepted, key=lambda item: item[0].forward_efficiency)
    return best, trials, {"scipy": scipy.__version__, "numpy": np.__version__}


def comparison_rows(best):
    rows = []
    for name, paper_value in PAPER_SHIFTS.to_dict().items():
        actual = getattr(best.shifts, name)
        rows.append({"parameter": name, "paper": paper_value,
                     "optimized": actual, "difference": actual - paper_value})
    for mesh in best.meshes:
        reference = PAPER_CONTACT_RATIOS[mesh.name]
        rows.append({"parameter": f"contact_ratio_{mesh.name}", "paper": reference,
                     "optimized": mesh.contact_ratio, "difference": mesh.contact_ratio - reference})
    return rows


def efficiency_comparison_rows(best):
    """モデル予測とTable IVの実測値の比較。差の単位はpercentage points。"""
    rows = []
    for label, actual, paper in (
        ("forward_eq64", best.forward_efficiency, PAPER_MEASURED_EFFICIENCIES["forward"]),
        ("backward_eq75", best.backward_efficiency, PAPER_MEASURED_EFFICIENCIES["backward"]),
    ):
        rows.append({"quantity": label, "paper_measured_percent": 100*paper,
                     "calculated_percent": 100*actual, "difference_pp": 100*(actual-paper)})
    return rows


def write_results(output: Path, gearbox: Gearbox, config: dict,
                  best_record, trials, versions, method="SLSQP", extra_report=None) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    center_reference = reference_center_distances(gearbox)
    # 共通中心距離を厳密に保つためaの復元値を使い、従属転位は再計算。
    reference_variables = [PAPER_SHIFTS.xr1, PAPER_SHIFTS.xr2, center_reference["a"]]
    reference = Model(gearbox, config["friction_coefficient"])
    reference.calculate(reference_variables)
    report = {
        "status": "success" if best_record else "no_converged_feasible_solution",
        "method": method, "gearbox": gearbox.to_dict(), "settings": config,
        "library_versions": versions, "speed_ratio_exact": str(gearbox.speed_ratio),
        "reduction_abs": float(abs(1 / gearbox.speed_ratio)),
        "fixed_assembly_checks": fixed_assembly_checks(gearbox),
        "paper_shifts": PAPER_SHIFTS.to_dict(),
        "paper_contact_ratios": PAPER_CONTACT_RATIOS,
        "paper_measured_efficiencies": PAPER_MEASURED_EFFICIENCIES,
        "paper_efficiency_table": "Table IV (Table V is absent in the supplied PDF)",
        "objective_equation": "64" if gearbox.i2 < 1 else "67",
        "reference_center_distances_mm": center_reference,
        "reference_common_center_evaluation": reference.to_dict(),
        "reference_constraint_margins": margins_for(reference, gearbox, config),
        "trials": trials,
        "limitations": [
            "摩擦係数の数値は論文に見つからないため設定値を使う。論文へのフィットはしない。",
            "Table IIIの転位・モジュールは丸められ、3つの復元中心距離に微小差がある。",
            "歯先径は論文式(82)-(86)。表のかみあい率と完全には一致しない。",
            f"{method}は局所法。複数初期値で確認するが大域最適性の証明ではない。",
            "切下げ、歯強度・許容トルク、加工工具との干渉、実歯形の検証は対象外。",
            "論文の実測順駆動効率89.0%は、この計算モデルの予測値と別である。",
            "逆効率は分子にeta_aを含む式(75)。式(74)のトルク釣合いによる独立計算とも一致する。",
        ],
    }
    if best_record:
        best, margins, trial_index = best_record
        rows = comparison_rows(best)
        efficiency_rows = efficiency_comparison_rows(best)
        successful_count = sum(trial["solver_success"] and trial["feasible"] for trial in trials)
        report.update({"best": best.to_dict(), "constraint_margins": margins,
                       "selected_trial": trial_index, "comparison": rows,
                       "efficiency_comparison": efficiency_rows})
        with (output / "efficiency_comparison.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(efficiency_rows[0]))
            writer.writeheader()
            writer.writerows(efficiency_rows)
        with (output / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["parameter", "paper", "optimized", "difference"])
            writer.writeheader()
            writer.writerows(rows)
        lines = ["# 固定歯数の転位最適化結果", "",
                 f"{method}、初期値{len(trials)}点。摩擦係数 μ={config['friction_coefficient']}（仮定）。",
                 f"収束した可行解: {successful_count}/{len(trials)}試行。成功した試行だけから目的関数が最良の解を採用。",
                 f"減速倍率: {report['reduction_abs']:.8f}、共通中心距離: {best.center_mm:.8f} mm。",
                 f"予測順駆動効率: {best.forward_efficiency:.6%}。予測逆駆動効率（式75）: {best.backward_efficiency:.6%}。",
                 "", "| 量 | 論文Table III | 計算値 | 差（計算−論文） |",
                 "|---|---:|---:|---:|"]
        lines.extend(f"| {row['parameter']} | {row['paper']:.6f} | {row['optimized']:.6f} | {row['difference']:+.6f} |" for row in rows)
        lines += ["", "## 順効率・逆効率と実測値の比較", "",
                  "目的関数は式(64)の順効率だけです。固定歯数ではI2<1です。",
                  "提供PDFにはTable Vがなく、対象の実測値はTable IVにあります。",
                  "| 量 | Table IV実測 [%] | 計算 [%] | 差 [ポイント] |",
                  "|---|---:|---:|---:|"]
        lines.extend(f"| {row['quantity']} | {row['paper_measured_percent']:.3f} | {row['calculated_percent']:.6f} | {row['difference_pp']:+.6f} |" for row in efficiency_rows)
        lines += ["", "式(75)は `(1+I1)*eta_a*(eta_b*eta_c-I2) / (eta_c*(eta_a*eta_b+I1)*(1-I2))` です。",
                  "分子のeta_aは論文に記載されています。式(74)のトルク釣合いとも一致します。",
                  "以前の『印刷式ではeta_aが欠ける』という説明と逆効率93.216316%は誤りでした。実測値へのフィットはしていません。"]
        lines += ["", "## 論文値を同じモデルで評価した場合", "",
                  "Table IIIの外歯かみあいから復元した中心距離を使い、中心距離一致を保って従属変数を再計算しています。",
                  f"予測順駆動効率: {reference.forward_efficiency:.6%}。",
                  f"復元中心距離: {center_reference}。",
                  "", "| かみあい | 論文のかみあい率 | 論文転位からのモデル評価 |",
                  "|---|---:|---:|"]
        lines.extend(f"| {mesh.name} | {PAPER_CONTACT_RATIOS[mesh.name]:.6f} | {mesh.contact_ratio:.6f} |" for mesh in reference.meshes)
        lines += ["", "## 判定と限界", "",
                  f"最小制約余裕: {min(margins.values()):.3e}（許容誤差{config['feasibility_tolerance']}）。",
                  "転位上下限、中心距離一致、かみあい率、作用線の基礎円外接触、トロコイド、遊星間すきまを判定。",
                  "トリミングを制約に含めるかは設定で選択可能です。",
                  ""]
        lines.extend(f"- {note}" for note in report["limitations"])
        (output / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        # 過去の成功結果と今回の失敗を混同しないよう、状態をレポートに明記。
        (output / "comparison.md").write_text("# 最適化未成立\n\n収束した可行解がありません。result.jsonの各試行を確認してください。\n", encoding="utf-8")
        (output / "comparison.csv").write_text("parameter,paper,optimized,difference\n", encoding="utf-8-sig")
    if extra_report:
        report.update(extra_report)
    (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("optimization_config.json"))
    parser.add_argument("--no-plots", action="store_true", help="学習用グラフを生成しない")
    parser.add_argument("--compare-limits", action="store_true", help="転位範囲±2.0と±0.9を並べて比較")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.compare_limits:
            from compare_shift_limits import run_comparison
            output = args.config.resolve().parent / config["output_directory"]
            output.mkdir(parents=True, exist_ok=True)
            run_comparison(config, output, with_plots=not args.no_plots)
            print(f"範囲比較: {output / 'limits_comparison.md'}")
            if not args.no_plots:
                print(f"比較グラフ: {output / 'limits_comparison.html'}")
            return
        gearbox = Gearbox()
        best, trials, versions = optimize(gearbox, config)
        output = args.config.resolve().parent / config["output_directory"]
        report = write_results(output, gearbox, config, best, trials, versions)
    except (ValueError, OSError, RuntimeError) as error:
        parser.error(str(error))
    if report["status"] != "success":
        print(f"収束した可行解なし。詳細: {output / 'result.json'}")
        raise SystemExit(1)
    print(f"予測順駆動効率: {best[0].forward_efficiency:.6%}")
    print(f"逆効率（式75）: {best[0].backward_efficiency:.6%}")
    for name, value in best[0].shifts.to_dict().items():
        print(f"{name}: {value:.8f} (Table III: {getattr(PAPER_SHIFTS, name):.3f})")
    print(f"結果: {output / 'comparison.md'}")
    if not args.no_plots:
        from learning_plots import generate_learning_graphs
        try:
            gallery = generate_learning_graphs(report, output)
        except (RuntimeError, ValueError, OSError) as error:
            print(f"最適化結果は保存済みですが、グラフ生成に失敗しました: {error}", file=sys.stderr)
            raise SystemExit(2)
        print(f"学習用グラフ: {gallery}")


if __name__ == "__main__":
    main()
