"""収束・断面・制約・効率モデルの検証グラフ。"""
import html
import json
import math
import os
from pathlib import Path
if __package__:
    from .common import Model, Gearbox, opt
else:
    from common import Model, Gearbox, opt


def generate_graphs(report, output, grid_count=35):
    np, _, _ = opt.load_scientific_libraries()
    os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).parent/"output/.matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font = Path("C:/Windows/Fonts/meiryo.ttc")
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    output = Path(output)
    figures = output/"figures"
    figures.mkdir(parents=True, exist_ok=True)
    entries = []
    g, c = Gearbox(**report["gearbox"]), report["settings"]
    evaluated = report["plot_evaluation"]
    labels = ["xr1", "xr2", "共通中心距離 [mm]"]

    def save(fig, stem, title):
        fig.savefig(figures/f"{stem}.png", dpi=130, bbox_inches="tight")
        fig.savefig(figures/f"{stem}.svg", bbox_inches="tight")
        plt.close(fig)
        entries.append((stem, title))

    def point(v):
        try:
            m = Model(g, c["friction_coefficient"])
            m.calculate(v)
            margins = opt.margins_for(m, c)
            return 100*m.forward_efficiency, min(margins.values()) >= -c["feasibility_tolerance"]
        except (ValueError, ZeroDivisionError, OverflowError):
            return math.nan, False

    fig, axes = plt.subplots(2, 1, figsize=(9, 6), layout="constrained")
    for t in report["trials"]:
        hist = t.get("history", [])
        axes[0].plot([r["iteration"] for r in hist], [100*r["forward_efficiency"] if r["forward_efficiency"] is not None else math.nan for r in hist])
        axes[1].plot([r["iteration"] for r in hist], [max(1e-12, -(r["minimum_constraint_margin"] or 0)) if r["minimum_constraint_margin"] is not None else math.nan for r in hist])
    axes[0].set_ylabel("順効率 [%]")
    axes[1].set_ylabel("最大制約違反")
    axes[1].set_yscale("log")
    axes[1].set_xlabel("反復")
    save(fig, "01_convergence", "収束と制約違反")
    if evaluated:
        shifts = evaluated["shifts"]
        v = [shifts["xr1"], shifts["xr2"], evaluated["center_mm"]]
        bounds = opt.variable_bounds(g, c)
        selected = report["trials"][report["selected_trial"]]
        hist = selected.get("history", [])
        fig, axes = plt.subplots(3, 1, figsize=(9, 7), layout="constrained")
        for i, ax in enumerate(axes):
            ax.plot([r["iteration"] for r in hist], [r["variables"][i] for r in hist])
            ax.set_ylabel(labels[i])
        save(fig, "02_variables", "採用試行の変数推移（未成立時は制約違反最小の試行）")
        fig, axes = plt.subplots(1, 3, figsize=(15, 4), layout="constrained")
        for ax, (ix, iy) in zip(axes, [(0, 1), (0, 2), (1, 2)]):
            xx, yy = np.linspace(*bounds[ix], grid_count), np.linspace(*bounds[iy], grid_count)
            z, feasible = np.full((len(yy), len(xx)), np.nan), np.zeros((len(yy), len(xx)), dtype=bool)
            for row, y in enumerate(yy):
                for col, x in enumerate(xx):
                    values = list(v)
                    values[ix], values[iy] = x, y
                    z[row, col], feasible[row, col] = point(values)
            ax.set_facecolor("#dedede")
            masked = np.ma.masked_where(~feasible | ~np.isfinite(z), z)
            if masked.count():
                image = ax.contourf(xx, yy, masked, levels=18, cmap="viridis")
                fig.colorbar(image, ax=ax, label="順効率 [%]")
            if feasible.any() and (~feasible).any():
                ax.contour(xx, yy, feasible.astype(float), levels=[.5], colors="black")
            ax.scatter([v[ix]], [v[iy]], marker="*", color="red", clip_on=False, zorder=5)
            fixed = ({0, 1, 2}-{ix, iy}).pop()
            ax.set(xlabel=labels[ix], ylabel=labels[iy], title=f"{labels[fixed]}={v[fixed]:.5g}")
        save(fig, "03_surfaces", "2変数断面：灰色は制約違反。固定値は最終評価点")
        fig, axes = plt.subplots(1, 3, figsize=(15, 4), layout="constrained")
        for i, ax in enumerate(axes):
            xx = np.linspace(*bounds[i], 160)
            samples = []
            for x in xx:
                values = list(v)
                values[i] = x
                samples.append(point(values))
            eta = np.array([r[0] for r in samples])
            feasible = np.array([r[1] for r in samples])
            ax.plot(xx, np.where(~feasible, eta, np.nan), "--", color="gray", label="不可行")
            ax.plot(xx, np.where(feasible, eta, np.nan), label="可行")
            ax.scatter([v[i]], [100*evaluated["forward_efficiency"]], marker="*", color="red", clip_on=False, zorder=5)
            ax.set(xlabel=labels[i], ylabel="順効率 [%]")
            ax.legend()
        save(fig, "04_slices", "1変数断面：残り2変数を最終評価点で固定")
        fig, ax = plt.subplots(figsize=(8, 4), layout="constrained")
        initial = hist[0]["forward_efficiency"] if hist else None
        ax.bar(["初期点", "最終点"], [100*initial if initial is not None else math.nan, 100*evaluated["forward_efficiency"]])
        ax.set_ylabel("順効率 [%]")
        save(fig, "05_efficiency", "初期点と最終点のモデル効率")
        margins = report["constraint_margins"]
        fig, ax = plt.subplots(figsize=(10, 10), layout="constrained")
        names = list(margins)
        ax.barh(names, list(margins.values()), color=["red" if x < -c["feasibility_tolerance"] else "steelblue" for x in margins.values()])
        ax.axvline(0, color="black")
        save(fig, "06_constraints", "全制約の余裕（尺度は各式に依存）")
        fig, ax = plt.subplots(figsize=(8, 4), layout="constrained")
        friction = np.linspace(.01, .2, 60)
        eta = []
        for mu in friction:
            m = Model(g, mu)
            m.calculate(v)
            eta.append(100*m.forward_efficiency)
        ax.plot(friction, eta)
        ax.set(xlabel="摩擦係数", ylabel="順効率 [%]")
        save(fig, "07_friction", "形状を固定した摩擦係数感度（再最適化なし）")
        fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
        meshes = evaluated["meshes"]
        axes[0].bar([m["name"] for m in meshes], [m["approach_ratio"] for m in meshes], label="近寄り")
        axes[0].bar([m["name"] for m in meshes], [m["recess_ratio"] for m in meshes], bottom=[m["approach_ratio"] for m in meshes], label="遠のき")
        axes[0].set_ylabel("かみあい率")
        axes[0].legend()
        axes[1].bar([m["name"] for m in meshes], [100*m["basic_efficiency"] for m in meshes])
        axes[1].set_ylabel("基礎効率 [%]")
        save(fig, "08_meshes", "各かみあいのかみあい率・基礎効率")
    parts = [f'<h1>{html.escape(report["method"])}</h1>', f'<p>状態：{report["status"]}。未成立時の最終点を最適解として扱わないでください。</p>']
    for stem, title in entries:
        parts.append(f'<h2>{html.escape(title)}</h2><img style="max-width:100%" src="figures/{stem}.png">')
    (output/"verification_graphs.html").write_text('<!doctype html><meta charset="utf-8">'+''.join(parts), encoding="utf-8")
    return output/"verification_graphs.html"


if __name__ == "__main__":
    from tests.experiments.common import load_settings
    data, _, _, output = load_settings()
    for method in ("slsqp", "quasi_newton"):
        path = output/method/"result.json"
        if path.exists():
            print(generate_graphs(json.loads(path.read_text(encoding="utf-8")), path.parent, data["plots"]["grid_count"]))
