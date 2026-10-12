# 歯数探索と転位最適化

## 本番の計算

```powershell
python tooth_search/tooth_search.py
python optimization/optimize_candidates.py
```

歯数探索の条件は `tooth_search/tooth_search.py`、最適化条件は `optimization/optimization_config.json` で指定します。標準で4候補並列、候補ごとに12初期値です。

歯数探索CSVの列順は番号、ma、mc、zs、zp1、zr1、zp2、zr2、減速比です。番号は最適化結果にも引き継ぐため、候補を抜き出して再計算しても照合できます。


候補CSVは必要条件の事前絞り込みです。最適化では固定歯数・固定モジュールのもとで共有転位・共通中心距離、遊星間すきま、内歯インボリュート・トロコイド干渉、ON/OFF設定によるトリミングなどを同時判定します。S–P1のインボリュート干渉、外径、強度、切下げ、歯先厚さは対象外です。

結果は `optimization/output/results.csv` と `summary.json`。CSVの列順は番号、最適化判定（収束/未収束）、5歯数、減速比、順効率（％）、逆効率（％）、3かみ合い率、5転位です。減速比は入力速度/出力速度の絶対値です。詳しくは [候補最適化の説明](optimization/CANDIDATE_OPTIMIZATION.md) を参照してください。

## 単一組合せの確認

条件は **本番と別の `tests/experiments/config.json`** で指定します。

```powershell
python tests/experiments/single_slsqp.py
python tests/experiments/single_quasi_newton.py
python tests/experiments/check_efficiency.py
python tests/experiments/plots.py
```

SLSQPは本番と同じ関数・モデル・制約を使い、反復履歴を記録します。準ニュートン法は拡張ラグランジュ法で不等式を扱い、内側にL-BFGS-Bを使います。最終制約、投影勾配、相補性を確認します。収束が成立しなければ未成立と表示し、可行解や大域解の保証にはしません。

効率確認は任意の5転位を補正せずに代入します。`evaluation.center_mm` がnullならS–P1の転位和から中心距離を復元し、各かみあいからの復元中心距離との整合も表示します。歯数、モジュール、転位、中心距離は共通設定から変更できます。

出力先は `tests/experiments/output/slsqp/`、`quasi_newton/`、`efficiency/`。`plots.enabled` がtrueなら最適化実行時に8種類の検証図と `verification_graphs.html` を作成します。未成立の場合は最終評価点の図を最適解と区別します。本番の設定・結果は上書きしません。

## 自動テストと依存関係

```powershell
python -m unittest discover -s tests/automated
python -m pip install -r requirements.txt
```

依存関係をインストールしたPython環境を使ってください。この作業環境では `optimization/.dependencies/` を代替のライブラリ保存先として使います。`.venv/` とともに実行環境なので削除対象外です。

`references/` は論文資料です。旧コード・旧結果・実行ファイル・一時作業は現行構成から除きます。`artifacts/` は別の作業の資料として維持しています。
