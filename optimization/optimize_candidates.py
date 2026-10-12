"""歯数探索CSVの各候補で、固定歯数・固定モジュールの転位を最適化する。

実行: python optimization/optimize_candidates.py
CSVのa_min/a_maxやstatusは事前絞り込みの記録。成立保証として使わない。
"""
import argparse
import csv
import importlib.util
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from itertools import islice
from pathlib import Path

if __package__:
    from .profile_shift_model import (
        Gearbox, Model, angle_from_involute, involute, constraint_margins,
    )
else:
    from profile_shift_model import (
        Gearbox, Model, angle_from_involute, involute, constraint_margins,
    )


def load_scientific_libraries():
    if importlib.util.find_spec("scipy") is None:
        local = Path(__file__).resolve().parent / ".dependencies"
        if local.is_dir():
            sys.path.insert(0, str(local))
    import numpy as np
    import scipy
    from scipy.optimize import minimize
    return np, scipy, minimize


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return validate_config(config)


def validate_config(config):
    keys = {"input_csv", "output_directory", "pressure_angle_deg", "planet_count",
            "friction_coefficient", "shift_lower", "shift_upper",
            "contact_ratio_lower", "contact_ratio_upper", "planet_clearance_mm",
            "include_trimming_constraint", "start_count", "workers", "random_seed",
            "max_iterations", "ftol", "feasibility_tolerance"}
    if set(config) != keys:
        raise ValueError(f"設定キーの不足・余分: {set(config) ^ keys}")
    for name in keys - {"input_csv", "output_directory", "include_trimming_constraint"}:
        value = config[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name}は有限の数値が必要です")
    for name in ("planet_count", "start_count", "workers", "max_iterations", "random_seed"):
        if type(config[name]) is not int or config[name] < (0 if name == "random_seed" else 1):
            raise ValueError(f"{name}の整数設定が不正です")
    if config["planet_count"] < 2 or not 0 < config["pressure_angle_deg"] < 90:
        raise ValueError("遊星数は2以上、圧力角は0度より大きく90度未満にしてください")
    if not 0 < config["friction_coefficient"] < 1:
        raise ValueError("摩擦係数は0より大きく1未満にしてください")
    if not config["shift_lower"] < config["shift_upper"]:
        raise ValueError("転位範囲が不正です")
    if not 0 < config["contact_ratio_lower"] < config["contact_ratio_upper"]:
        raise ValueError("かみあい率範囲が不正です")
    if config["planet_clearance_mm"] < 0 or min(config["ftol"], config["feasibility_tolerance"]) <= 0:
        raise ValueError("すきまは非負、許容誤差は正にしてください")
    if type(config["include_trimming_constraint"]) is not bool:
        raise ValueError("include_trimming_constraintはtrue/falseです")
    for name in ("input_csv", "output_directory"):
        if not isinstance(config[name], str) or not config[name].strip():
            raise ValueError(f"{name}にパスが必要です")
    return config


def read_candidates(path):
    """列の順番に依存せず読む。不正な行も結果に残す。"""
    required = {"ma", "mc", "zs", "zp1", "zr1", "zp2", "zr2"}
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSVの必須列がありません: {sorted(missing)}")
        seen = set()
        for index, row in enumerate(reader, 1):
            if "番号" in (reader.fieldnames or []):
                try:
                    index = int(row["番号"])
                except (ValueError, TypeError) as error:
                    raise ValueError("CSVの番号は正の整数が必要です") from error
                if index < 1 or index in seen:
                    raise ValueError("CSVの番号は正の整数で、重複しない必要があります")
            seen.add(index)
            yield index, row


def gearbox_from_row(row, config):
    teeth = {}
    for name in ("zs", "zp1", "zr1", "zp2", "zr2"):
        value = float(row[name])
        if not math.isfinite(value) or value < 1 or not value.is_integer():
            raise ValueError(f"{name}は正の整数が必要です")
        teeth[name] = int(value)
    ma, mc = float(row["ma"]), float(row["mc"])
    if not all(math.isfinite(v) and v > 0 for v in (ma, mc)):
        raise ValueError("ma、mcは正の有限値が必要です")
    if teeth["zr1"] <= teeth["zp1"] or teeth["zr2"] <= teeth["zp2"]:
        raise ValueError("内歯車の歯数は遊星より大きい必要があります")
    return Gearbox(**teeth, module_a=ma, module_c=mc,
                   pressure_angle_deg=config["pressure_angle_deg"],
                   planet_count=config["planet_count"])


def fixed_assembly_checks(g):
    return {
        "first_layer_equal_spacing": (g.zs + g.zr1) % g.planet_count == 0,
        "compound_equal_spacing": (g.zr2*g.zp1 - g.zr1*g.zp2)
        % (g.planet_count * math.gcd(g.zp1, g.zp2)) == 0,
    }


def variable_bounds(g, config):
    """各かみあいの転位和/差の範囲から共通中心距離の区間を再計算。

    区間の重なりだけでは共有P1や干渉の成立は保証しない。
    それらは同じModelに対する制約として同時に評価する。
    """
    lo, hi = config["shift_lower"], config["shift_upper"]
    ranges = []
    for module, teeth, shift_min, shift_max in (
        (g.module_a, g.zs+g.zp1, 2*lo, 2*hi),
        (g.module_a, g.zr1-g.zp1, lo-hi, hi-lo),
        (g.module_c, g.zr2-g.zp2, lo-hi, hi-lo),
    ):
        base = module*teeth*math.cos(g.alpha)/2
        inv_min = involute(g.alpha) + 2*math.tan(g.alpha)*shift_min/teeth
        inv_max = involute(g.alpha) + 2*math.tan(g.alpha)*shift_max/teeth
        if inv_max < 0:
            raise ValueError("転位範囲内で中心距離を定義できません")
        a_min = base/math.cos(angle_from_involute(max(0.0, inv_min)))
        a_max = base/math.cos(angle_from_involute(inv_max))
        # acos端点の微分発散を避ける。長さの尺度に比例させる。
        ranges.append((max(a_min, base*(1+1e-10)), a_max))
    center_lo = max(r[0] for r in ranges)
    center_hi = min(r[1] for r in ranges)
    if center_hi <= center_lo:
        raise ValueError("共通中心距離の探索区間がありません")
    return [(lo, hi), (lo, hi), (center_lo, center_hi)]


def margins_for(model, config):
    return constraint_margins(
        model, model.gearbox, config["shift_lower"], config["shift_upper"],
        config["contact_ratio_lower"], config["contact_ratio_upper"],
        config["planet_clearance_mm"], config["include_trimming_constraint"],
    )


def necessary_recess_margins(g, config, bounds):
    """内歯の遠のきかみあい率が、範囲内のどこかで非負になれるか。

    共通中心距離が大きいほど内歯の転位差は大きくなるので、
    xp1/xp2の上限は中心距離下限とリング転位上限で得られる。
    P1の歯先短縮は無視して大きめに見積もる。別々に最も有利な
    上下限を使うため、合格は成立保証ではなく、不合格だけ確定できる。
    """
    a_lower = bounds[2][0]
    upper = config["shift_upper"]
    m = Model(g, config["friction_coefficient"])
    _, xp1_max, _, xp2_max, _ = m.calculate_shifts([upper, upper, a_lower])
    margins = {}
    for name, module, planet, ring, shift_max in (
        ("b", g.module_a, g.zp1, g.zr1, xp1_max),
        ("c", g.module_c, g.zp2, g.zr2, xp2_max),
    ):
        base = module*planet*math.cos(g.alpha)/2
        tip_upper = module*(planet/2+1+shift_max)
        tip_angle_upper = math.acos(min(1., base/max(tip_upper, 1e-12)))
        base_center = module*(ring-planet)*math.cos(g.alpha)/2
        working_angle_lower = math.acos(min(1., base_center/a_lower))
        margins[f"{name}_recess_upper"] = planet*(
            math.tan(tip_angle_upper)-math.tan(working_angle_lower))/(2*math.pi)
    return margins


def optimize(g, config, capture_history=False):
    np, scipy, minimize = load_scientific_libraries()
    bounds = variable_bounds(g, config)
    if min(necessary_recess_margins(g, config, bounds).values()) < -config["feasibility_tolerance"]:
        raise ValueError("転位・中心距離の全探索範囲で、内歯の遠のきかみあい率が非負になりません")
    lower = np.array([b[0] for b in bounds])
    width = np.array([b[1]-b[0] for b in bounds])

    def decode(u):
        return lower + width*np.asarray(u)

    # 目的関数と制約で同じ点を評価するときは結果を再利用する。
    cache = {}

    def at(u):
        key = tuple(float(v) for v in u)
        if key not in cache:
            # 有限差分で目的関数と制約が同じ点を何度も呼ぶため、
            # 直近の複数点を保存する。評価点や探索条件は変更しない。
            if len(cache) >= 128:
                cache.clear()
            try:
                model = Model(g, config["friction_coefficient"])
                model.calculate(decode(u))
                margins = margins_for(model, config)
                if not all(math.isfinite(v) for v in margins.values()):
                    raise ValueError("評価値が有限ではありません")
                cache[key] = (model, margins)
            except (ValueError, ZeroDivisionError, OverflowError):
                cache[key] = (None, None)
        return cache[key]

    constraint_count = 42 + (2 if config["include_trimming_constraint"] else 0)

    def objective(u):
        model, _ = at(u)
        return -model.forward_efficiency if model else 1e6

    def constraints(u):
        _, margins = at(u)
        return (np.array(list(margins.values())) if margins is not None
                else np.full(constraint_count, -1e6))

    rng = np.random.default_rng(config["random_seed"])
    starts = [np.full(3, .5)]
    starts.extend(rng.uniform(.05, .95, (config["start_count"]-1, 3)))
    trials, accepted = [], []
    for index, start in enumerate(starts):
        history = []

        def record(u):
            model, margins = at(u)
            minimum = min(margins.values()) if margins else None
            history.append({"iteration": len(history), "variables": decode(u).tolist(),
                            "forward_efficiency": model.forward_efficiency if model else None,
                            "minimum_constraint_margin": minimum})

        if capture_history:
            record(start)
        result = minimize(objective, start, method="SLSQP", bounds=[(0., 1.)]*3,
                          constraints={"type": "ineq", "fun": constraints},
                          callback=record if capture_history else None,
                          options={"maxiter": config["max_iterations"], "ftol": config["ftol"]})
        # ソルバーのsuccessだけで採用しない。最終点の全制約を再計算。
        cache.clear()
        model, margins = at(result.x)
        if capture_history:
            record(result.x)
        feasible = margins is not None and min(margins.values()) >= -config["feasibility_tolerance"]
        adopted = bool(result.success and feasible)
        trial = {"start_index": index, "initial_variables": decode(start).tolist(),
                 "final_variables": decode(result.x).tolist(), "solver_success": bool(result.success),
                 "solver_message": str(result.message), "iterations": int(result.nit),
                 "feasible": feasible, "accepted": adopted,
                 "forward_efficiency": model.forward_efficiency if model else None,
                 "constraint_margins": margins,
                 "violated_constraints": ({k: v for k, v in margins.items()
                                           if v < -config["feasibility_tolerance"]} if margins else None)}
        trials.append(trial)
        if capture_history:
            trial["history"] = history
        if adopted:
            accepted.append((model, margins, index))
    best = max(accepted, key=lambda item: item[0].forward_efficiency) if accepted else None
    return best, trials, {"numpy": np.__version__, "scipy": scipy.__version__}


def optimize_candidate(index, row, config):
    record = {"candidate_index": index, "input_row": row, "trials": [], "best": None}
    try:
        g = gearbox_from_row(row, config)
        record["gearbox"] = g.to_dict()
        record["speed_ratio"] = float(g.speed_ratio)
        record["speed_ratio_exact"] = str(g.speed_ratio)
        record["reduction_abs"] = float(abs(1/g.speed_ratio)) if g.speed_ratio else None
        checks = fixed_assembly_checks(g)
        record["fixed_assembly_checks"] = checks
        if not all(checks.values()):
            record.update(status="assembly_rejected", reason="固定歯数が等配の組付け条件を満たしません")
            return record
        if g.i2 == 1:
            record.update(status="stationary_output", reason="I2=1で出力が停止します")
            return record
        record["variable_bounds"] = variable_bounds(g, config)
        possible = necessary_recess_margins(g, config, record["variable_bounds"])
        record["necessary_recess_margins"] = possible
        if min(possible.values()) < -config["feasibility_tolerance"]:
            record.update(status="geometry_rejected",
                          reason="内歯の遠のきかみあい率が全探索範囲で負になるため、制約を満たす解がありません")
            return record
        best, trials, versions = optimize(g, config)
        record.update(trials=trials, library_versions=versions,
                      converged_feasible_count=sum(t["accepted"] for t in trials))
        if best:
            model, margins, selected = best
            record.update(status="success", best=model.to_dict(),
                          constraint_margins=margins, selected_trial=selected)
        else:
            record.update(status="no_converged_feasible_solution",
                          reason="全試行で収束と全制約充足を同時に満たす解が得られませんでした")
    except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as error:
        record.update(status="candidate_rejected", reason=str(error))
    return record


def batch_candidate(index, row, config):
    """並列実行でも、全試行の巨大なデータをプロセス間で渡さない。"""
    report = optimize_candidate(index, row, config)
    trials = report.pop("trials")
    report["trial_count"] = len(trials)
    # 不成立候補は、最終制約違反が最も小さい試行の情報を残す。
    evaluated = [t for t in trials if t["constraint_margins"] is not None]
    nearest = max(evaluated, key=lambda t: min(t["constraint_margins"].values())) if evaluated else None
    diagnostic = trials[report["selected_trial"]] if report["best"] is not None else nearest
    report["diagnostic_trial"] = diagnostic["start_index"] if diagnostic else None
    report["solver_message"] = diagnostic["solver_message"] if diagnostic else ""
    if report["best"] is None and nearest:
        report["constraint_margins"] = nearest["constraint_margins"]
    return report


def candidate_reports(candidates, config, workers):
    if workers == 1:
        for index, row in candidates:
            yield batch_candidate(index, row, config)
        return
    # 候補単位で並列計算し、先行投入は並列数の2倍までにする。
    with ProcessPoolExecutor(max_workers=workers) as executor:
        pending = set()

        def submit_next():
            try:
                index, row = next(candidates)
            except StopIteration:
                return False
            pending.add(executor.submit(batch_candidate, index, row, config))
            return True

        for _ in range(2*workers):
            if not submit_next():
                break
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                pending.remove(future)
                yield future.result()
                submit_next()


def run_batch(input_csv, output, config, limit=None, workers=None):
    if workers is None:
        workers = config["workers"]
    if type(workers) is not int or workers < 1:
        raise ValueError("workersは1以上の整数です")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    best_overall = None
    successful_count = converged_count = trial_count = 0
    fields = ["番号", "最適化判定", "zs", "zp1", "zr1", "zp2", "zr2",
              "減速比", "順効率（％）", "逆効率（％）",
              "かみ合い率_S-P1", "かみ合い率_P1-R1", "かみ合い率_P2-R2",
              "xs", "xp1", "xr1", "xp2", "xr2"]
    with (output/"results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        csv.DictWriter(stream, fieldnames=fields).writeheader()
    candidates = read_candidates(input_csv)
    if limit is not None:
        candidates = islice(candidates, limit)
    for report in candidate_reports(iter(candidates), config, workers):
        index, raw = report["candidate_index"], report["input_row"]
        best = report["best"]
        successful_count += report["status"] == "success"
        converged_count += report.get("converged_feasible_count", 0)
        trial_count += report["trial_count"]
        row = {"番号": index, "最適化判定": "収束" if best else "未収束",
               **{k: raw.get(k) for k in ("zs", "zp1", "zr1", "zp2", "zr2")},
               "減速比": report.get("reduction_abs"),
               "順効率（％）": 100*best["forward_efficiency"] if best else None,
               "逆効率（％）": 100*best["backward_efficiency"] if best else None}
        for name, label in (("a", "S-P1"), ("b", "P1-R1"), ("c", "P2-R2")):
            mesh = next((m for m in best["meshes"] if m["name"] == name), None) if best else None
            row[f"かみ合い率_{label}"] = mesh["approach_ratio"] + mesh["recess_ratio"] if mesh else None
        row.update({name: best["shifts"][name] if best else None
                    for name in ("xs", "xp1", "xr1", "xp2", "xr2")})
        rows.append(row)
        if best and (best_overall is None or
                     (best["forward_efficiency"], -index) >
                     (best_overall["best"]["forward_efficiency"], -best_overall["candidate_index"])):
            best_overall = report
        # 完了分はCSVで確認できるが、次回実行時は最初から計算する。
        with (output/"results.csv").open("a", encoding="utf-8", newline="") as stream:
            csv.DictWriter(stream, fieldnames=fields).writerow(row)
        print(f"候補 {index}: {report['status']}、収束した可行解 {report.get('converged_feasible_count', 0)}/{report['trial_count']}", flush=True)
    rows.sort(key=lambda row: row["番号"])
    with (output/"results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {"input_csv": str(Path(input_csv).resolve()), "settings": config,
               "processed_count": len(rows), "successful_candidate_count": successful_count,
               "converged_feasible_trial_count": converged_count,
               "trial_count": trial_count, "limit": limit, "workers": workers,
               "best_candidate_index": best_overall["candidate_index"] if best_overall else None,
               "best": best_overall["best"] if best_overall else None,
               "note": "非成立は大域的な実行可能解不存在の証明ではありません。S-P1のインボリュート干渉、歯強度、外径は対象外。"}
    (output/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("optimization_config.json"))
    parser.add_argument("--input", type=Path, help="候補CSV（指定時は実行ディレクトリ基準）")
    parser.add_argument("--output", type=Path, help="出力先（指定時は実行ディレクトリ基準）")
    parser.add_argument("--limit", type=int, help="動作確認用に先頭N候補だけ処理")
    parser.add_argument("--workers", type=int, help="同時に計算する候補数（省略時はconfigのworkers）")
    parser.add_argument("--starts", type=int, help="候補ごとの初期値数（configより優先）")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limitは1以上です")
    if (args.workers is not None and args.workers < 1) or (args.starts is not None and args.starts < 1):
        parser.error("--workersと--startsは1以上です")
    try:
        config = load_config(args.config)
        if args.workers is not None:
            config["workers"] = args.workers
        if args.starts is not None:
            config["start_count"] = args.starts
        load_scientific_libraries()
        root = args.config.resolve().parent
        source = args.input or root/config["input_csv"]
        output = args.output or root/config["output_directory"]
        summary = run_batch(source, output, config, args.limit)
    except (ValueError, OSError, ImportError) as error:
        parser.error(str(error))
    print(f"成立した候補: {summary['successful_candidate_count']}/{summary['processed_count']}")
    print(f"収束して制約を満たした試行: {summary['converged_feasible_trial_count']}/{summary['trial_count']}")
    print(f"結果: {output.resolve()}")


if __name__ == "__main__":
    main()
