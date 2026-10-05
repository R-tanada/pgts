"""固定歯数での準ニュートン最適化。実行: python optimize_profile_shift_quasi_newton.py

内側: SciPy L-BFGS-B。外側: 不等式の拡張ラグランジュ法。
論文には準ニュートン法の具体的方式・制約処理がなく、ここは独自の選択。
歯形モデル・制約・初期点生成はSLSQP版と共通。論文値を初期点にしない。
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path

import optimize_profile_shift as shared
from profile_shift_model import Gearbox, evaluate

METHOD = "L-BFGS-B + augmented Lagrangian"


def load_settings(path: Path):
    settings = json.loads(path.read_text(encoding="utf-8-sig"))
    expected = {"base_config", "output_directory", "outer_max_iterations",
                "initial_penalty", "penalty_growth", "inner_gtol", "inner_ftol",
                "constraint_buffer"}
    if set(settings) != expected:
        raise ValueError(f"準ニュートン設定キーの不足・余分: {set(settings) ^ expected}")
    for name in expected - {"base_config", "output_directory"}:
        value = settings[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name}は正の有限数が必要です")
    if type(settings["outer_max_iterations"]) is not int or settings["penalty_growth"] <= 1:
        raise ValueError("外側反復数は整数、ペナルティ増倍率は1より大きくしてください")
    for name in ("base_config", "output_directory"):
        if not isinstance(settings[name], str) or not settings[name]:
            raise ValueError(f"{name}は空でない文字列が必要です")
    config = shared.load_config(path.resolve().parent / settings["base_config"])
    config["output_directory"] = settings["output_directory"]
    return config, settings


def augmented_objective(objective, margins, multipliers, penalty, np):
    """g>=0の不等式用。乗数lambda>=0、違反時に目的関数へ罰則を加える。

    L = f + sum((max(0, lambda-rho*g)^2 - lambda^2)/(2*rho))
    非活性制約にも一律に二乗ペナルティを課すことはしない。
    """
    positive = np.maximum(0.0, multipliers - penalty * margins)
    return float(objective + np.sum(positive**2 - multipliers**2) / (2 * penalty))


def optimize(gearbox, config, settings):
    np, scipy, minimize = shared.load_scientific_libraries()
    if not all(shared.fixed_assembly_checks(gearbox).values()):
        raise ValueError("固定歯数が等配条件を満たしません")
    bounds = shared.variable_bounds(gearbox, config)
    lower = np.array([b[0] for b in bounds])
    width = np.array([b[1] - b[0] for b in bounds])

    def decode(point):
        return lower + width * np.asarray(point)

    def state(point):
        evaluation = evaluate(decode(point), gearbox, config["friction_coefficient"])
        margins = shared.margins_for(evaluation, gearbox, config)
        return evaluation, margins

    rng = np.random.default_rng(config["random_seed"])
    starts = [np.full(3, 0.5)]
    starts.extend(rng.uniform(0.05, 0.95, size=(config["start_count"] - 1, 3)))
    trials, accepted = [], []
    for index, start in enumerate(starts):
        point = np.array(start, copy=True)
        history, stages = [], []
        multipliers = np.zeros(len(state(point)[1]))
        penalty = settings["initial_penalty"]
        previous_violation = math.inf
        outer_converged = False

        def record(point, outer_iteration):
            current, margins = state(point)
            minimum = min(margins.values())
            history.append({
                "iteration": len(history), "outer_iteration": outer_iteration,
                "penalty": penalty, "variables": decode(point).tolist(),
                "shifts": asdict(current.shifts),
                "forward_efficiency": current.forward_efficiency,
                "backward_efficiency_printed": current.backward_efficiency,
                "backward_efficiency_force_balance": current.backward_efficiency_force_balance,
                "minimum_constraint_margin": minimum,
                "maximum_constraint_violation": max(0.0, -minimum),
                "feasible": minimum >= -config["feasibility_tolerance"],
            })

        record(point, 0)
        for outer in range(1, settings["outer_max_iterations"] + 1):
            # 内側計算中は乗数とrhoを固定。変えるのは外側反復の境界だけ。
            def objective(candidate):
                current, margins = state(candidate)
                buffered = np.array(list(margins.values())) - settings["constraint_buffer"]
                return augmented_objective(-current.forward_efficiency, buffered,
                                           multipliers, penalty, np)

            result = minimize(
                objective, point, method="L-BFGS-B", jac="3-point",
                bounds=[(0.0, 1.0)] * 3,
                callback=lambda candidate: record(candidate, outer),
                options={"maxiter": config["max_iterations"],
                         "maxfun": 50000, "maxls": 40,
                         "gtol": settings["inner_gtol"], "ftol": settings["inner_ftol"]},
            )
            point = result.x
            record(point, outer)
            final, margins = state(point)
            buffered = np.array(list(margins.values())) - settings["constraint_buffer"]
            updated = np.maximum(0.0, multipliers - penalty * buffered)
            # 可行性だけで止めず、乗数更新の残差（相補性を含む）も確認する。
            residual = float(np.max(np.abs(updated - multipliers)) / penalty)
            violation = max(0.0, -min(margins.values()))
            stages.append({"outer_iteration": outer, "penalty": penalty,
                           "inner_success": bool(result.success), "inner_message": str(result.message),
                           "inner_iterations": int(result.nit), "function_evaluations": int(result.nfev),
                           "maximum_constraint_violation": violation,
                           "multiplier_residual": residual})
            if (result.success and violation <= config["feasibility_tolerance"]
                    and residual <= config["feasibility_tolerance"]):
                outer_converged = True
                break
            multipliers = updated
            if violation > 0.25 * previous_violation:
                penalty *= settings["penalty_growth"]
            previous_violation = violation

        final, margins = state(point)
        feasible = min(margins.values()) >= -config["feasibility_tolerance"]
        trial = {
            "start_index": index, "initial_variables": decode(start).tolist(),
            "final_variables": decode(point).tolist(), "solver_success": outer_converged,
            "solver_message": ("Outer residual and feasibility converged; " if outer_converged
                               else "Outer iteration limit reached; ") + str(result.message),
            "iterations": sum(stage["inner_iterations"] for stage in stages),
            "forward_efficiency": final.forward_efficiency,
            "minimum_constraint_margin": min(margins.values()), "feasible": feasible,
            "history": history, "outer_stages": stages,
        }
        trials.append(trial)
        if outer_converged and feasible and math.isfinite(final.forward_efficiency):
            accepted.append((final, margins, index))
    best = max(accepted, key=lambda row: row[0].forward_efficiency) if accepted else None
    return best, trials, {"scipy": scipy.__version__, "numpy": np.__version__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("quasi_newton_config.json"))
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    config, settings = load_settings(args.config)
    gearbox = Gearbox()
    best, trials, versions = optimize(gearbox, config, settings)
    output = args.config.resolve().parent / config["output_directory"]
    note = "論文は準ニュートン法とのみ記載。L-BFGS-Bと拡張ラグランジュ法は本実装の選択であり、完全再現ではありません。"
    report = shared.write_results(output, gearbox, config, best, trials, versions,
                                  method=METHOD, extra_report={"quasi_newton_settings": settings,
                                                             "paper_method_note": note})
    comparison = output / "comparison.md"
    with comparison.open("a", encoding="utf-8") as stream:
        stream.write("\n## 準ニュートン法の実装\n\n" + note + "\n")
        stream.write("内側でL-BFGS-Bにより拡張ラグランジュ関数を最小化し、外側で乗数と罰則係数を更新します。\n")
    if best is None:
        raise SystemExit(f"収束した可行解なし。試行履歴: {output / 'result.json'}")
    print(f"順効率: {best[0].forward_efficiency:.8%}")
    print(f"逆効率（印刷式）: {best[0].backward_efficiency:.8%}")
    print(f"逆効率（トルク釣合い）: {best[0].backward_efficiency_force_balance:.8%}")
    print(f"転位係数: {asdict(best[0].shifts)}")
    print(f"収束・可行試行: {sum(t['solver_success'] and t['feasible'] for t in trials)}/{len(trials)}")
    print(f"結果: {comparison}")
    if not args.no_plots:
        from learning_plots import generate_learning_graphs
        print(f"グラフ: {generate_learning_graphs(report, output)}")


if __name__ == "__main__":
    main()
