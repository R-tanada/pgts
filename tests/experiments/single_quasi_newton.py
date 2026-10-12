"""拡張ラグランジュ法＋L-BFGS-B（準ニュートン法）による単一候補検証。

不等式g>=0を拡張ラグランジュ目的に組み込み、最後は本番と同じ制約で判定。
SLSQPとの一致や、大域最適性を保証するものではない。
"""
if __package__:
    from .common import load_settings, finish, opt, Model
else:
    from common import load_settings, finish, opt, Model


def augmented_objective(objective, margins, multipliers, penalty, np):
    positive = np.maximum(0., multipliers-penalty*margins)
    return objective + np.sum(positive**2-multipliers**2)/(2*penalty)


def optimize(g, config, settings):
    np, scipy, minimize = opt.load_scientific_libraries()
    bounds = opt.variable_bounds(g, config)
    lower = np.array([v[0] for v in bounds])
    width = np.array([v[1]-v[0] for v in bounds])
    rng = np.random.default_rng(config["random_seed"])
    starts = [np.full(3, .5), *rng.uniform(.05, .95, (config["start_count"]-1, 3))]
    trials, accepted = [], []
    count = 42 + 2*config["include_trimming_constraint"]
    for index, start in enumerate(starts):
        u, multipliers, rho = start.copy(), np.zeros(count), settings["initial_penalty"]
        history, cache = [], {}

        def at(v):
            key = tuple(v)
            if key not in cache:
                if len(cache) > 128:
                    cache.clear()
                try:
                    m = Model(g, config["friction_coefficient"])
                    m.calculate(lower+width*v)
                    margins = opt.margins_for(m, config)
                    values = np.array(list(margins.values()))
                    if not np.isfinite(values).all():
                        raise ValueError("評価値が有限ではありません")
                    cache[key] = (m, margins, values)
                except (ValueError, ZeroDivisionError, OverflowError):
                    cache[key] = (None, None, np.full(count, -1e6))
            return cache[key]

        def record(v):
            m, margins, _ = at(v)
            history.append({"iteration": len(history), "variables": (lower+width*v).tolist(),
                            "forward_efficiency": m.forward_efficiency if m else None,
                            "minimum_constraint_margin": min(margins.values()) if margins else None})

        record(u)
        iterations, converged = 0, False
        for outer in range(settings["outer_iterations"]):
            def objective(v):
                m, _, values = at(v)
                return augmented_objective(-m.forward_efficiency if m else 1e6,
                                           values, multipliers, rho, np)
            result = minimize(objective, u, method="L-BFGS-B", bounds=[(0., 1.)]*3,
                              callback=record, options={"maxiter": settings["inner_iterations"],
                              "ftol": config["ftol"], "gtol": settings["optimality_tolerance"]})
            u = result.x
            iterations += result.nit
            m, margins, values = at(u)
            # 箱制約に沿った拡張目的の勾配と相補性を両方確認。
            projected = u-np.clip(u-result.jac, 0., 1.)
            updated = np.maximum(0., multipliers-rho*values)
            if (m is not None and min(values) >= -config["feasibility_tolerance"]
                    and np.max(np.abs(projected)) <= settings["optimality_tolerance"]
                    and np.max(np.abs(updated*values)) <= settings["optimality_tolerance"]):
                converged = True
                break
            multipliers = updated
            rho *= settings["penalty_growth"]
        cache.clear()
        m, margins, values = at(u)
        record(u)
        feasible = m is not None and min(values) >= -config["feasibility_tolerance"]
        trial = {"start_index": index, "final_variables": (lower+width*u).tolist(),
                 "solver_success": converged, "solver_message": "KKT tolerance reached" if converged else "outer iteration limit",
                 "iterations": int(iterations), "outer_iterations": outer+1,
                 "feasible": bool(feasible), "accepted": bool(converged and feasible),
                 "constraint_margins": margins, "history": history}
        trials.append(trial)
        if trial["accepted"]:
            accepted.append((m, margins, index))
    return (max(accepted, key=lambda r: r[0].forward_efficiency) if accepted else None,
            trials, {"numpy": np.__version__, "scipy": scipy.__version__})


def main():
    data, g, config, output = load_settings()
    if not all(opt.fixed_assembly_checks(g).values()):
        raise ValueError("等配組付け条件を満たしません")
    best, trials, versions = optimize(g, config, data["quasi_newton"])
    finish("L-BFGS-B + augmented Lagrangian", data, g, config, best, trials, versions, output/"quasi_newton")


if __name__ == "__main__":
    main()
