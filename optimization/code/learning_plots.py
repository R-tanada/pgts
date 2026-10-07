"""最適化の学習用グラフ。計算モデル・ソルバーとは別モジュールにする。

PNG/SVGと、説明・反復ステップ操作を備えたオフラインHTMLを出力する。
単独実行: python learning_plots.py --result optimization_output/result.json
"""
from __future__ import annotations

import argparse
import base64
import html
import importlib.util
import json
import math
import os
import sys
from pathlib import Path

from profile_shift_model import Gearbox, Model, constraint_margins


def plotting_libraries():
    if importlib.util.find_spec("matplotlib") is None:
        local = Path(__file__).resolve().parent.parent / ".dependencies"
        if local.is_dir():
            sys.path.insert(0, str(local))
    os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent.parent / "tmp" / "matplotlib"))
    try:
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError as error:
        raise RuntimeError("グラフには requirements-optimization.txt のインストールが必要です") from error
    font_path = Path("C:/Windows/Fonts/meiryo.ttc")
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font_path)).get_name()
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.grid": True,
                         "grid.alpha": 0.18, "axes.unicode_minus": False,
                         "savefig.facecolor": "white"})
    return np, plt


class LearningPlotter:
    def __init__(self, report: dict, output: Path):
        if report["status"] != "success":
            raise ValueError("収束した可行解のない結果から学習グラフは作成しません")
        self.report, self.output = report, output
        self.figures = output / "figures"
        self.figures.mkdir(parents=True, exist_ok=True)
        self.np, self.plt = plotting_libraries()
        self.gearbox = Gearbox(**report["gearbox"])
        self.config = report["settings"]
        self.best = report["best"]
        self.reference = report["reference_common_center_evaluation"]
        self.trials = report["trials"]
        self.selected = self.trials[report["selected_trial"]]
        shifts = self.best["shifts"]
        self.variables = [shifts["xr1"], shifts["xr2"], self.best["center_mm"]]
        self.entries = []

    def save(self, figure, stem, title, explanation):
        figure.savefig(self.figures / f"{stem}.png", dpi=150)
        figure.savefig(self.figures / f"{stem}.svg")
        self.plt.close(figure)
        self.entries.append({"stem": stem, "title": title, "explanation": explanation})

    def margins(self, result):
        c = self.config
        return constraint_margins(result, self.gearbox, c["shift_lower"], c["shift_upper"],
                                  c["contact_ratio_lower"], c["contact_ratio_upper"],
                                  c["planet_clearance_mm"], c["include_trimming_constraint"])

    def point(self, variables):
        """断面の評価。定義域外・特異点はNaNとして描画から除外する。"""
        try:
            result = Model(self.gearbox, self.config["friction_coefficient"])
            result.calculate(variables)
            feasible = min(self.margins(result).values()) >= -self.config["feasibility_tolerance"]
            value = result.forward_efficiency * 100
            return (value, feasible) if math.isfinite(value) else (math.nan, False)
        except (ValueError, ZeroDivisionError, OverflowError):
            return math.nan, False

    def variable_ranges(self):
        # 最適化時と同じ数学的な区間。実装の重複を避ける。
        from optimize_profile_shift import variable_bounds
        return variable_bounds(self.gearbox, self.config)

    def convergence(self):
        figure, axes = self.plt.subplots(2, 1, figsize=(10, 7), layout="constrained", sharex=True)
        tolerance = self.config["feasibility_tolerance"]
        for trial in self.trials:
            history = trial["history"]
            iterations = [row["iteration"] for row in history]
            selected = trial["start_index"] == self.report["selected_trial"]
            success = trial["solver_success"] and trial["feasible"]
            color = "#1769aa" if selected else ("#9fa9b3" if success else "#d77b69")
            width = 2.5 if selected else 1.0
            style = "-" if success else "--"
            axes[0].plot(iterations, [100*row["forward_efficiency"] for row in history],
                         color=color, lw=width, ls=style)
            axes[1].plot(iterations, [max(row["maximum_constraint_violation"], tolerance/10) for row in history],
                         color=color, lw=width, ls=style)
        for feasible, marker, color, label in ((True, "o", "#1b8d60", "採用試行の可行点"),
                                               (False, "x", "#bb4338", "採用試行の不可行点")):
            points = [row for row in self.selected["history"] if row["feasible"] == feasible]
            axes[0].scatter([p["iteration"] for p in points], [100*p["forward_efficiency"] for p in points],
                            s=20, marker=marker, color=color, label=label, zorder=4)
        axes[0].axhline(100*self.reference["forward_efficiency"], color="#684ea0", ls=":", label="Table III転位のモデル評価")
        axes[0].set_ylabel("順効率 η [%]（式64）")
        axes[0].legend(loc="lower right", fontsize=9)
        axes[0].set_title("初期値ごとの目的関数と制約違反の推移")
        axes[1].set_yscale("log")
        axes[1].axhline(tolerance, color="black", ls=":", label="可行性の許容誤差")
        axes[1].set_ylabel("最大制約違反（正規化余裕の負側）")
        axes[1].set_xlabel("反復（0は初期点）")
        axes[1].legend(fontsize=9)
        self.save(figure, "01_convergence", "1. 収束と可行性",
                  f"{self.report['method']}の反復履歴です。効率が高くても赤い×の点は制約に違反しています。"
                  "青は採用試行、灰は他の成功試行、赤い破線は不採用試行。効率が毎回単調に上がるとは限りません。"
                  "最大違反のゼロは対数表示のため許容誤差の1/10に置いています。")

    def variables_history(self):
        figure, axes = self.plt.subplots(2, 1, figsize=(10, 7), layout="constrained", sharex=True)
        history = self.selected["history"]
        iterations = [p["iteration"] for p in history]
        ranges = self.variable_ranges()
        for index, label in enumerate(("xr1", "xr2", "共通中心距離")):
            lower, upper = ranges[index]
            values = [(p["variables"][index] - lower)/(upper-lower) for p in history]
            axes[0].plot(iterations, values, label=label, marker=".")
        axes[0].set_ylabel("独立変数の正規化値 [0,1]")
        axes[0].set_title("3つの独立変数から5つの転位係数を求める")
        axes[0].legend(ncol=3)
        for name in ("xs", "xp1", "xr1", "xp2", "xr2"):
            axes[1].plot(iterations, [p["shifts"][name] for p in history], label=name)
        for bound in (self.config["shift_lower"], self.config["shift_upper"]):
            axes[1].axhline(bound, ls=":", color="black")
        axes[1].set_ylabel("転位係数 x [-]")
        axes[1].set_xlabel("反復")
        axes[1].legend(ncol=5)
        self.save(figure, "02_variables", "2. 独立変数と従属変数",
                  "最適化で直接動かすのはxr1・xr2・中心距離の3つです。xs・xp1・xp2は式88で決まります。"
                  "上図は尺度をそろえた独立変数、下図は実際の5つの転位係数。終了時のxr1は上限制約に到達します。")

    def objective_surfaces(self):
        np = self.np
        ranges = self.variable_ranges()
        pairs = ((0, 1), (0, 2), (1, 2))
        labels = ("xr1 [-]", "xr2 [-]", "共通中心距離 [mm]")
        data = []
        for ix, iy in pairs:
            x = np.linspace(*ranges[ix], 65)
            y = np.linspace(*ranges[iy], 65)
            values = np.full((len(y), len(x)), np.nan)
            feasible = np.zeros_like(values, dtype=bool)
            for row, yy in enumerate(y):
                for col, xx in enumerate(x):
                    variables = list(self.variables)
                    variables[ix], variables[iy] = float(xx), float(yy)
                    values[row, col], feasible[row, col] = self.point(variables)
            data.append((x, y, values, feasible))
        valid_values = [values[feasible] for _, _, values, feasible in data if feasible.any()]
        if not valid_values:
            raise ValueError("目的関数断面に可行な格子点がありません")
        all_values = np.concatenate(valid_values)
        levels = np.linspace(float(all_values.min()), float(all_values.max()) + 1e-8, 18)
        figure, axes = self.plt.subplots(1, 3, figsize=(15, 5), layout="constrained")
        for axis, (ix, iy), (x, y, values, feasible) in zip(axes, pairs, data):
            axis.set_facecolor("#e5e7eb")
            contour = axis.contourf(x, y, np.ma.masked_where(~feasible, values), levels=levels, cmap="viridis")
            if feasible.any() and (~feasible).any():
                axis.contour(x, y, feasible.astype(float), levels=[0.5], colors="black", linewidths=0.8)
            axis.scatter([self.variables[ix]], [self.variables[iy]], marker="*", s=150,
                         color="#e45138", edgecolors="white", linewidths=0.7, clip_on=False, zorder=5)
            fixed = ({0, 1, 2} - {ix, iy}).pop()
            axis.set_title(f"{labels[fixed]} = {self.variables[fixed]:.4f} に固定")
            axis.set_xlabel(labels[ix])
            axis.set_ylabel(labels[iy])
        figure.colorbar(contour, ax=axes, label="可行領域の順効率 η [%]", shrink=0.85)
        figure.suptitle("目的関数の2次元断面：灰色は不可行、★は最適解")
        self.save(figure, "03_objective_surfaces", "3. 目的関数と可行領域",
                  "3変数のうち1つを最適値に固定した断面です。色は可行な点の順効率、灰色は制約違反。"
                  "★が境界にあるのは、勾配がゼロになる点ではなく制約で改善が止まる点が解になるためです。"
                  "3次元全体の大域最適性を証明する図ではありません。")

    def local_sensitivity(self):
        np = self.np
        figure, axes = self.plt.subplots(1, 3, figsize=(15, 4.5), layout="constrained")
        labels = ("xr1 [-]", "xr2 [-]", "共通中心距離 [mm]")
        for index, axis in enumerate(axes):
            lower, upper = self.variable_ranges()[index]
            span = (upper - lower) * 0.18
            x = np.linspace(max(lower, self.variables[index]-span), min(upper, self.variables[index]+span), 180)
            evaluated = []
            for value in x:
                variables = list(self.variables)
                variables[index] = float(value)
                evaluated.append(self.point(variables))
            y = np.array([point[0] for point in evaluated])
            feasible = np.array([point[1] for point in evaluated])
            axis.plot(x, np.where(~feasible, y, np.nan), color="#9ca3af", ls="--", label="不可行")
            axis.plot(x, np.where(feasible, y, np.nan), color="#1769aa", label="可行")
            axis.scatter([self.variables[index]], [100*self.best["forward_efficiency"]], marker="*", s=120,
                         color="#e45138", clip_on=False, zorder=5)
            axis.set_xlabel(labels[index])
            axis.set_ylabel("順効率 η [%]")
            axis.legend(fontsize=9)
        figure.suptitle("最適解近傍の1変数感度（他の2変数は固定）")
        self.save(figure, "04_local_sensitivity", "4. 感度と境界解",
                  "1つの変数だけを変えたときの効率です。xr1は上限で止まるため、最適値で傾きがゼロでなくても問題ありません。"
                  "xr2や中心距離は内点の山の頂上に近づきます。灰色の高効率点を選べない理由は制約違反です。")

    def efficiency_comparison(self):
        np = self.np
        figure, axis = self.plt.subplots(figsize=(10, 5.5), layout="constrained")
        x = np.arange(3)
        paper = self.report["paper_measured_efficiencies"]
        forward = [paper["forward"], self.reference["forward_efficiency"], self.best["forward_efficiency"]]
        backward = [paper["backward"], self.reference["backward_efficiency"], self.best["backward_efficiency"]]
        for offset, values, color, label in ((-0.105, forward, "#1769aa", "順効率（式64）"),
                                             (0.105, backward, "#218b65", "逆効率（式75）")):
            bars = axis.bar(x+offset, np.array(values)*100, width=0.20, color=color, label=label)
            axis.bar_label(bars, fmt="%.3f", fontsize=9, padding=3)
        axis.set_xticks(x, ["Table IV\n実測値", "Table III転位\nモデル計算", "最適化した転位\nモデル計算"])
        axis.set_ylim(0, max(max(forward), max(backward))*100 + 12)
        axis.set_ylabel("効率 [%]")
        axis.set_title(f"順効率・逆効率：モデルの μ={self.config['friction_coefficient']} は仮定値")
        axis.legend(loc="lower right", fontsize=9)
        self.save(figure, "05_efficiency_comparison", "5. 論文の実測値との比較",
                  "実測値はTable IVの順89.0%・逆85.3%。計算値は同じ歯面摩擦係数を仮定したモデル予測です。"
                  "逆効率は分子にeta_aを含む式75で、式74のトルク釣合いとも一致します。"
                  "実測との差は最適化の誤差だけを意味せず、摩擦係数やモデル化の差も含みます。")

    def active_constraints(self):
        margins = sorted(self.report["constraint_margins"].items(), key=lambda pair: pair[1])[:14]
        figure, axis = self.plt.subplots(figsize=(11, 6), layout="constrained")
        names, values = zip(*margins)
        colors = ["#e45138" if value <= self.config["feasibility_tolerance"] else "#1769aa" for value in values]
        axis.barh(names, values, color=colors)
        axis.scatter(values, names, color=colors, s=25, zorder=3)
        axis.invert_yaxis()
        axis.set_xscale("symlog", linthresh=1e-5)
        axis.axvline(0, color="black", lw=0.8)
        axis.set_xlabel("制約余裕 margin（非負が合格、symlog表示）")
        axis.set_title("最適解で余裕の小さい14条件：赤は活性制約")
        for row, value in enumerate(values):
            axis.annotate(f"{value:.2e}", (value, row), xytext=(6, 0), textcoords="offset points", va="center", fontsize=9)
        axis.margins(x=0.35)
        self.save(figure, "06_active_constraints", "6. 活性制約",
                  "余裕がほぼ0の条件が活性制約です。xr1_upperはx_r1≤2が効いていることを表します。"
                  "他の条件には余裕が残っています。余裕の尺度は条件ごとに正規化が異なるため、感度や重要度の順位ではありません。"
                  "全制約はresult.jsonに保存しています。")

    def friction_sensitivity(self):
        np = self.np
        friction = np.linspace(0.02, 0.20, 140)
        results = []
        for value in friction:
            result = Model(self.gearbox, float(value))
            result.calculate(self.variables)
            results.append(result)
        figure, axis = self.plt.subplots(figsize=(10, 5.5), layout="constrained")
        axis.plot(friction, [100*e.forward_efficiency for e in results], color="#1769aa", label="順効率：式64")
        axis.plot(friction, [100*e.backward_efficiency for e in results], color="#218b65", label="逆効率：式75")
        for key, color, label in (("forward", "#1769aa", "実測順89.0%"), ("backward", "#218b65", "実測逆85.3%")):
            axis.axhline(100*self.report["paper_measured_efficiencies"][key], ls=":", color=color, label=label)
        axis.axvline(self.config["friction_coefficient"], color="black", ls="-.", label="計算に使用したμ")
        axis.set_xlabel("歯面摩擦係数 μ [-]")
        axis.set_ylabel("効率 [%]")
        axis.set_title("モデル仮定の感度：転位係数・中心距離を最適値に固定")
        axis.legend(fontsize=9)
        self.save(figure, "07_friction_sensitivity", "7. 摩擦係数の仮定の影響",
                  "最適化した形状を固定してμだけを動かしています。各μで再最適化した図ではありません。"
                  "水平線は論文の実測値ですが、交点を選んでμを合わせる処理は行っていません。"
                  "仮定パラメータによって効率予測が変わることを確認できます。")

    def contact_and_loss(self):
        np = self.np
        figure, axes = self.plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
        x = np.arange(3)
        ratios = (list(self.report["paper_contact_ratios"].values()),
                  [mesh["approach_ratio"]+mesh["recess_ratio"] for mesh in self.reference["meshes"]],
                  [mesh["approach_ratio"]+mesh["recess_ratio"] for mesh in self.best["meshes"]])
        for offset, values, label, color in zip((-0.23, 0, 0.23), ratios,
                                               ("Table III記載", "Table III転位を式で評価", "最適化結果"),
                                               ("#8d95a0", "#684ea0", "#1769aa")):
            bars = axes[0].bar(x+offset, values, width=0.22, label=label, color=color)
            axes[0].bar_label(bars, fmt="%.3f", fontsize=8, padding=2)
        axes[0].set_xticks(x, ["a: S-P1", "b: P1-R1", "c: P2-R2"])
        axes[0].axhline(self.config["contact_ratio_lower"], color="black", ls=":")
        axes[0].axhline(self.config["contact_ratio_upper"], color="black", ls=":")
        axes[0].set_ylabel("かみあい率 ε [-]")
        axes[0].set_title("かみあい率と表の不一致")
        axes[0].legend(fontsize=8, loc="lower left")
        losses = [100*(1-mesh["basic_efficiency"]) for mesh in self.best["meshes"]]
        losses.append(100*(1-self.best["forward_efficiency"]))
        bars = axes[1].bar(["a", "b", "c", "全体"], losses,
                           color=["#1769aa", "#1769aa", "#1769aa", "#e45138"])
        axes[1].bar_label(bars, fmt="%.3f", padding=3)
        axes[1].set_ylabel("1 − 効率 [%]")
        axes[1].set_title("小さなかみあい損失と全体の損失")
        axes[1].margins(y=0.2)
        self.save(figure, "08_contact_and_loss", "8. かみあい率と損失の増幅",
                  "a/cのかみあい率は表に近い一方、bは論文の式と表で差があります。この差を隠していません。"
                  "右図では、各対の小さな基礎損失に比べ全体の損失が大きいことが分かります。"
                  "遊星歯車の内部の相対動力を介するため、各損失率を単純に足したものが全体損失になるわけではありません。")

    def write_gallery(self):
        """外部通信なしのHTML。初期値と反復を選んで軌跡を操作できる。"""
        selected = self.report["selected_trial"]
        options = "".join(f'<option value="{t["start_index"]}" {"selected" if t["start_index"] == selected else ""}>'
                          f'初期値 {t["start_index"]+1}: {"収束・可行" if t["solver_success"] and t["feasible"] else "不採用"}</option>' for t in self.trials)
        sections = []
        for entry in self.entries:
            encoded = base64.b64encode((self.figures / f'{entry["stem"]}.png').read_bytes()).decode("ascii")
            sections.append(f'<section id="{entry["stem"]}"><h2>{html.escape(entry["title"])}</h2>'
                            f'<p>{html.escape(entry["explanation"])}</p>'
                            f'<img src="data:image/png;base64,{encoded}" alt="{html.escape(entry["title"])}" loading="lazy"></section>')
        # JSONはユーザー入力を含み得るため、script終端文字をエスケープする。
        data = json.dumps(self.trials, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
        document = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>転位最適化をグラフで学ぶ</title>
<style>body{font-family:system-ui,'Meiryo',sans-serif;color:#182537;background:#f7f9fc;margin:0}main{max-width:1180px;margin:auto;padding:24px}h1{font-size:28px}h2{font-size:21px}p{line-height:1.8}section{margin:28px 0;padding:22px;background:white;border:1px solid #dce2eb;border-radius:8px}img{max-width:100%;height:auto}label{display:inline-flex;align-items:center;gap:10px;margin:10px 20px 10px 0}select,input{font:inherit}input{width:min(320px,50vw)}svg{width:100%;height:auto;background:#fff}#step-state{white-space:pre-wrap;font-variant-numeric:tabular-nums;line-height:1.8}a{color:#1769aa}nav{display:flex;flex-wrap:wrap;gap:12px}.note{border-left:4px solid #c77419;padding-left:12px}table{border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ddd}@media(max-width:600px){main{padding:12px}section{padding:12px}h1{font-size:23px}}</style></head><body><main>
<h1>転位最適化をグラフで学ぶ</h1><p>目的関数は式(64)の順効率だけ。手法：__METHOD__。</p>
<p class="note">論文の実測効率はTable IVに記載（順89.0%、逆85.3%）。提供PDFにはTable Vがありません。μ=__MU__は仮定値で、実測へのフィットは行っていません。</p>
<nav>__NAV__</nav><section><h2>反復を1ステップずつ見る</h2>
<label>初期値<select id="trial">__OPTIONS__</select></label><label>反復<input type="range" id="iteration" min="0" step="1" value="0"></label>
<svg id="trace" viewBox="0 0 900 330" role="img" aria-label="選択した初期値の順効率の軌跡"></svg>
<div id="step-state" aria-live="polite"></div><p>青は可行、赤は不可行。反復0は初期点です。効率の値だけでなく、制約違反も見てください。</p></section>
__SECTIONS__<p>PNG/SVGはfiguresフォルダにも保存されています。詳細な数値はresult.jsonを参照してください。</p>
<script>const trials=__DATA__;const selector=document.getElementById('trial'),slider=document.getElementById('iteration'),svg=document.getElementById('trace'),state=document.getElementById('step-state');
function draw(reset){const t=trials[Number(selector.value)],history=t.history;if(reset){slider.max=history.length-1;slider.value=0;}const i=Number(slider.value),p=history[i];
const values=history.map(v=>100*v.forward_efficiency),mn=Math.min(...values),mx=Math.max(...values),pad=Math.max(0.1,(mx-mn)*0.08),lo=mn-pad,hi=mx+pad;
const x=j=>75+j/Math.max(1,history.length-1)*770,y=v=>270-(v-lo)/(hi-lo)*220;
let marks='<rect x="75" y="50" width="770" height="220" fill="none" stroke="#b9c2cf"/>';
for(let k=0;k<5;k++){const v=lo+(hi-lo)*k/4;marks+=`<line x1="75" y1="${y(v)}" x2="845" y2="${y(v)}" stroke="#e5e9ef"/><text x="66" y="${y(v)+4}" text-anchor="end" font-size="13">${v.toFixed(2)}</text>`;}
marks+='<text x="450" y="317" text-anchor="middle" font-size="15">反復</text><text x="20" y="165" transform="rotate(-90 20 165)" text-anchor="middle" font-size="15">順効率 [%]</text>';
marks+=`<polyline fill="none" stroke="#9ca3af" stroke-width="1.5" points="${history.map((v,j)=>`${x(j)},${y(100*v.forward_efficiency)}`).join(' ')}"/>`;
history.slice(0,i+1).forEach((v,j)=>{marks+=`<circle cx="${x(j)}" cy="${y(100*v.forward_efficiency)}" r="${j===i?6:3}" fill="${v.feasible?'#1769aa':'#c54b3f'}"/>`;});
marks+=`<text x="75" y="292" text-anchor="middle" font-size="13">0</text><text x="845" y="292" text-anchor="middle" font-size="13">${history.length-1}</text>`;svg.innerHTML=marks;
state.textContent=`反復 ${i} / ${history.length-1}  |  ${p.feasible?'可行':'不可行'}\n順効率 ${(100*p.forward_efficiency).toFixed(6)}%  |  最大制約違反 ${p.maximum_constraint_violation.toExponential(3)}\nxr1=${p.variables[0].toFixed(6)}, xr2=${p.variables[1].toFixed(6)}, 中心距離=${p.variables[2].toFixed(6)} mm\nxs=${p.shifts.xs.toFixed(6)}, xp1=${p.shifts.xp1.toFixed(6)}, xp2=${p.shifts.xp2.toFixed(6)}\n試行終了状態: ${t.solver_message}`;}
selector.addEventListener('change',()=>draw(true));slider.addEventListener('input',()=>draw(false));draw(true);</script></main></body></html>"""
        replacements = {"__METHOD__": html.escape(self.report["method"]),
                        "__MU__": str(self.config["friction_coefficient"]), "__OPTIONS__": options,
                        "__NAV__": "".join(f'<a href="#{entry["stem"]}">{html.escape(entry["title"])}</a>' for entry in self.entries),
                        "__SECTIONS__": "".join(sections), "__DATA__": data}
        for placeholder, value in replacements.items():
            document = document.replace(placeholder, value)
        (self.output / "learning_graphs.html").write_text(document, encoding="utf-8")
        (self.output / "figures_index.json").write_text(json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8")

    def generate(self):
        for method in (self.convergence, self.variables_history, self.objective_surfaces,
                       self.local_sensitivity, self.efficiency_comparison,
                       self.active_constraints, self.friction_sensitivity, self.contact_and_loss):
            method()
        self.write_gallery()
        return self.output / "learning_graphs.html"


def generate_learning_graphs(report, output):
    return LearningPlotter(report, output).generate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, default=Path(__file__).resolve().parent.parent / "optimization_output" / "result.json")
    args = parser.parse_args()
    report = json.loads(args.result.read_text(encoding="utf-8"))
    print(generate_learning_graphs(report, args.result.resolve().parent))


if __name__ == "__main__":
    main()
