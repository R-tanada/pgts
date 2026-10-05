# 遊星歯車の歯数探索・転位最適化

このフォルダを作業ディレクトリとして、以下のコマンドを実行してください。

| フォルダ | 内容 |
|---|---|
| `code/` | Pythonコード、JSON設定、依存パッケージ一覧 |
| `tests/` | 歯形モデル・最適化・HTMLの検証コード |
| `docs/` | 各実装の使い方、数式、制約、注意点 |
| `references/` | 論文PDF |
| `tooth_search_output/` | 歯数探索のCSVと集計 |
| `optimization_output/` | SLSQPの結果・グラフ、±2と±0.9の比較 |
| `quasi_newton_output/` | 準ニュートン法の結果・グラフ |
| `tmp/` | PDF抽出・描画などの作業用データ |
| `.dependencies/` | 作業環境用の科学計算ライブラリ |

## 実行

```powershell
# 歯数探索
python code/tooth_search.py

# 固定歯数の転位最適化（SLSQP）
python code/optimize_profile_shift.py

# 転位範囲±2と±0.9の比較
python code/optimize_profile_shift.py --compare-limits

# 固定歯数の転位最適化（準ニュートン法）
python code/optimize_profile_shift_quasi_newton.py

# Pythonテスト
python -m unittest discover -s tests -p "test_*.py"

# HTMLの操作確認（Node.js）
node tests/test_learning_gallery.cjs
node tests/test_learning_gallery.cjs quasi_newton_output
```

通常のPython環境で必要なライブラリを準備する場合:

```powershell
python -m pip install -r code/requirements-optimization.txt
```

設定ファイルは `code/search_config.json`、`code/optimization_config.json`、
`code/quasi_newton_config.json` です。出力の相対パスは設定ファイルの場所を基準にします。
既存の結果ファイルは移動時に再計算せず保存しました。

## 解説とグラフ

- [歯数探索](docs/TOOTH_SEARCH.md)
- [SLSQPによる最適化](docs/OPTIMIZATION.md)
- [準ニュートン法による最適化](docs/QUASI_NEWTON.md)
- [SLSQPの学習用グラフ](optimization_output/learning_graphs.html)
- [転位範囲の比較](optimization_output/limits_comparison.html)
- [準ニュートン法の学習用グラフ](quasi_newton_output/learning_graphs.html)

効率モデルと論文の表の不一致など、モデルの限界は各解説と結果レポートに記載しています。
