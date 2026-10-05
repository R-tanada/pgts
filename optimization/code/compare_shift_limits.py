"""転位範囲±2.0と±0.9を独立に最適化し、数値と全8図を並べる。"""
from __future__ import annotations

import argparse
import base64
import csv
import html
import json
from pathlib import Path

from optimize_profile_shift import load_config, optimize, write_results
from profile_shift_model import Gearbox, PAPER_SHIFTS


def run_comparison(config, output, with_plots=True):
    gearbox = Gearbox()
    reports = []
    for limit in (2.0, 0.9):
        settings = dict(config, shift_lower=-limit, shift_upper=limit)
        best, trials, versions = optimize(gearbox, settings)
        folder = output / f"limit_{limit:.1f}"
        report = write_results(folder, gearbox, settings, best, trials, versions)
        if report["status"] != "success":
            raise RuntimeError(f"±{limit}で収束した可行解がありません。{folder / 'result.json'} を確認してください")
        reports.append(report)
    rows = []
    quantities = [(name, getattr(PAPER_SHIFTS, name), lambda r, n=name: r["best"]["shifts"][n])
                  for name in ("xs", "xp1", "xr1", "xp2", "xr2")]
    quantities += [
        ("center_mm", None, lambda r: r["best"]["center_mm"]),
        ("forward_percent_eq64", 89.0, lambda r: 100*r["best"]["forward_efficiency"]),
        ("backward_percent_printed_eq75", 85.3, lambda r: 100*r["best"]["backward_efficiency"]),
        ("backward_percent_force_balance", 85.3, lambda r: 100*r["best"]["backward_efficiency_force_balance"]),
    ]
    for name, reference, getter in quantities:
        wide, narrow = (getter(report) for report in reports)
        rows.append({"quantity": name, "paper": reference, "limit_2.0": wide,
                     "limit_0.9": narrow, "difference_0.9_minus_2.0": narrow-wide})
    with (output / "limits_comparison.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {"status": "success", "limits": [2.0, 0.9], "comparison": rows,
               "objective_equation": "64", "friction_coefficient": config["friction_coefficient"],
               "note": "同じ歯数・摩擦係数・制約・初期値数・乱数シード。各範囲内で独立に探索。論文の転位は±0.9では不可行。"}
    (output / "limits_comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 転位範囲の比較", "", summary["note"], "",
             "効率の論文値はTable IVの実測値、転位はTable III。μは仮定値です。",
             "", "| 量 | 論文 | ±2.0 | ±0.9 | 差（0.9−2.0） |", "|---|---:|---:|---:|---:|"]
    for row in rows:
        paper = "—" if row["paper"] is None else f'{row["paper"]:.6f}'
        lines.append(f'| {row["quantity"]} | {paper} | {row["limit_2.0"]:.6f} | {row["limit_0.9"]:.6f} | {row["difference_0.9_minus_2.0"]:+.6f} |')
    (output / "limits_comparison.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    if with_plots:
        generate_comparison_graphs(reports, rows, output)
    return reports, rows


def generate_comparison_graphs(reports, rows, output):
    from learning_plots import LearningPlotter
    plotters = [LearningPlotter(report, output/f"limit_{limit:.1f}")
                for report, limit in zip(reports, (2.0, 0.9))]
    ranges = [plotter.variable_ranges() for plotter in plotters]
    common_ranges = [(min(r[i][0] for r in ranges), max(r[i][1] for r in ranges)) for i in range(3)]
    methods = ("convergence", "variables_history", "objective_surfaces", "local_sensitivity",
               "efficiency_comparison", "active_constraints", "friction_sensitivity", "contact_and_loss")
    for plotter in plotters:
        plotter.defer_saving = True
        plotter.comparison_ranges = common_ranges
        for method in methods:
            getattr(plotter, method)()
    # 対応する数値軸を同じ範囲に揃えてから保存。条件名の軸は各ケースのまま。
    for stem in plotters[0].pending_figures:
        figures = [p.pending_figures[stem] for p in plotters]
        for axes in zip(*(figure.axes for figure in figures)):
            xlim = (min(a.get_xlim()[0] for a in axes), max(a.get_xlim()[1] for a in axes))
            ylim = (min(a.get_ylim()[0] for a in axes), max(a.get_ylim()[1] for a in axes))
            for axis in axes:
                axis.set_xlim(xlim)
                if stem != "06_active_constraints":
                    axis.set_ylim(ylim)
        for plotter, figure in zip(plotters, figures):
            figure.savefig(plotter.figures/f"{stem}.png", dpi=150)
            figure.savefig(plotter.figures/f"{stem}.svg")
            plotter.plt.close(figure)
    for plotter in plotters:
        plotter.write_gallery()
    table = ['<table><tr><th>量</th><th>±2.0</th><th>±0.9</th><th>差</th></tr>']
    for row in rows:
        table.append(f'<tr><td>{html.escape(row["quantity"])}</td><td>{row["limit_2.0"]:.6f}</td><td>{row["limit_0.9"]:.6f}</td><td>{row["difference_0.9_minus_2.0"]:+.6f}</td></tr>')
    table.append('</table>')
    sections = []
    for entry in plotters[0].entries:
        images = []
        for plotter, limit in zip(plotters, (2.0, 0.9)):
            encoded = base64.b64encode((plotter.figures/f'{entry["stem"]}.png').read_bytes()).decode("ascii")
            images.append(f'<div><h3>転位範囲 ±{limit}</h3><img src="data:image/png;base64,{encoded}" alt="±{limit}: {html.escape(entry["title"])}"></div>')
        note = entry["explanation"]
        if entry["stem"] == "04_local_sensitivity":
            note = "比較では共通の絶対変数範囲を使います。他の2変数は各ケースの最適値に固定。灰色は不可行。"
        if entry["stem"] == "02_variables":
            note += " 独立変数の正規化はそれぞれの探索区間が基準です。実転位の図で絶対値を比較してください。"
        sections.append(f'<section><h2>{html.escape(entry["title"])}</h2><p>{html.escape(note)}</p><div class="pair">{"".join(images)}</div></section>')
    document = '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>転位範囲の比較</title><style>body{font-family:system-ui,Meiryo,sans-serif;background:#f7f9fc;color:#182537;margin:0}main{max-width:1800px;margin:auto;padding:24px}section{background:white;padding:20px;margin:24px 0}p{line-height:1.8}.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}img{width:100%;height:auto}table{border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ccc}a{color:#1769aa}@media(max-width:900px){.pair{grid-template-columns:1fr}main{padding:12px}}</style><main><h1>転位範囲 ±2.0 / ±0.9 の比較</h1><p>目的関数は式64。摩擦係数・歯数・他の制約は同一。両ケースを独立に最適化しています。対応する数値軸と目的関数断面の色尺度は共通です。表の転位は±0.9の範囲外なので、比較用の参照値として扱います。</p><p><a href="limit_2.0/learning_graphs.html">±2.0の反復スライダー</a> ／ <a href="limit_0.9/learning_graphs.html">±0.9の反復スライダー</a></p>'+''.join(table)+''.join(sections)+'</main></html>'
    (output/"limits_comparison.html").write_text(document, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("optimization_config.json"))
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    output = args.config.resolve().parent/config["output_directory"]
    output.mkdir(parents=True, exist_ok=True)
    _, rows = run_comparison(config, output, not args.no_plots)
    for row in rows:
        print(f'{row["quantity"]}: ±2.0={row["limit_2.0"]:.6f}, ±0.9={row["limit_0.9"]:.6f}')
    print(output/"limits_comparison.html")


if __name__ == "__main__":
    main()
