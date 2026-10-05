※ フォルダ整理後: コードと設定は code/、論文は references/ にあります。コマンドはプロジェクトのルートで実行してください。

# 固定歯数の準ニュートン最適化

```console
python code/optimize_profile_shift_quasi_newton.py
```

準ニュートン版のコードは `optimize_profile_shift_quasi_newton.py`、設定は
`quasi_newton_config.json`。出力先は `quasi_newton_output` です。
`--no-plots` で計算と結果保存だけを行えます。必要なライブラリは既存版と同じです。

## 論文との関係

論文のIV節は準ニュートン法の使用を述べていますが、BFGSかL-BFGSか、
制約の変換方法、停止条件などの詳細は明記されていません。
本実装は **L-BFGS-B + 不等式の拡張ラグランジュ法** を採用しました。
著者の実装を完全に再現したものではありません。
SLSQPも内部で準ニュートン更新を使用しますが、新版はSLSQPを呼び出しません。

Table IIIの歯数を固定し、独立変数は `[xr1, xr2, center_mm]` です。
従属転位を共通中心距離から計算するため、中心距離一致は常に保たれます。
目的関数は式(64)の順効率のマイナスのみです。
逆効率は印刷式(75)と式(74)のトルク釣合いによる値を両方報告します。
Table IIIの転位係数・かみ合い率と、Table IVの実測効率を比較します。

モデル、制約、摩擦係数、12個の初期点の生成はSLSQP版と共通です。
摩擦係数0.1は仮定で、論文値へのフィットはしていません。
歯形・加工・歯先の最小歯厚などのモデルの限界も既存版と同じです。

## 制約の扱い

各非線形制約を `g_i(u) >= 0` と表します。変数uは0〜1に正規化し、
その範囲はL-BFGS-Bのboundsで扱います。非線形制約は直接渡せないため、
内側で次の拡張ラグランジュ関数を最小化します。

```text
f(u) = -forward_efficiency(u)
L(u, lambda, rho)
  = f(u) + sum((max(0, lambda_i - rho*g_i(u))**2 - lambda_i**2)/(2*rho))
```

非活性の制約まで常に二乗するのではなく、乗数と違反に応じた罰則です。
内側計算中はlambdaとrhoを固定し、外側反復で更新します。

```text
lambda_new = max(0, lambda - rho*g)
```

違反が前の外側反復の1/4まで減っていない場合はrhoを5倍にします。
初期rhoは10、外側反復上限は20。内側はL-BFGS-B、3点数値差分です。
非線形制約には2e-8の小さなバッファを置き、実際の余裕で最終可行性を確認します。
直接boundsで固定される境界ではバッファを満たせない場合もあるため、
最終判定は許容誤差1e-7で行います。

内側が正常終了し、実際の最大制約違反と
`max(abs(lambda_new-lambda))/rho` が1e-7以下なら外側を終了します。
有限の効率、外側収束、最終制約の再確認を満たした試行だけを採用します。
数値差分・相対目的関数変化による内側停止を使っており、厳密なKKT条件や
大域最適性の証明ではありません。

## 設定と出力

`base_config` は既存の `optimization_config.json` を参照します。
歯車の制約や摩擦係数はこのファイルを変更します。準ニュートン専用の停止条件は
`quasi_newton_config.json` に分離しています。

- `result.json`: 最適解、全試行、各反復、外側反復の罰則係数・残差・終了状態。
- `comparison.md`, `comparison.csv`: 論文の転位係数・かみ合い率との比較。
- `efficiency_comparison.csv`: 論文の実測順効率・逆効率との比較。
- `learning_graphs.html`: 初期点選択・反復スライダーと8種類のグラフ。
- `figures`: PNGとSVG。

グラフの反復軸は全外側段階を通した内側反復の記録順です。
各外側段階の最終点も記録するので、同じ座標が続く場合があります。
外側段階は履歴の `outer_iteration`、`penalty` と `outer_stages` で確認できます。

検証:

```console
python -m unittest discover -s tests -p "test_*.py"
```
