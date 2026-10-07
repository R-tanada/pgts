# 歯車モデルの読み方

`code/profile_shift_model.py` は、普通の `class` と `__init__`、変数への代入、
関数で書いています。`@dataclass`、`@property`、関数から結果クラスを返す処理はありません。

## 最初に読む例

`code` フォルダの中のPythonファイルから次のように使います。

```python
from profile_shift_model import Gearbox, Model

gearbox = Gearbox()                 # Table IIIの歯数・モジュールを保存
model = Model(gearbox, friction=0.1) # 計算に使う仕様と摩擦係数を保存

model.calculate([1.0, 0.5, 21.0])  # xr1, xr2, 共通中心間距離[mm]

print(model.shifts.xs)              # 従属変数として計算した太陽歯車の転位係数
print(model.forward_efficiency)    # 順効率（0〜1）
print(model.meshes[0].contact_ratio) # S-P1のかみ合い率
```

`self` は、そのクラスから作った個々のオブジェクトを表します。
`self.friction = friction` は、渡された摩擦係数をオブジェクト内に保存する代入です。
`model.calculate(...)` は、計算結果を `model` の中に保存します。
`result = model.calculate(...)` として返り値を受け取る必要はありません。

別の候補を計算すると、そのmodelの結果は更新されます。以前の候補の結果も
残したい場合は別のModelを作るか、`model.to_dict()` で辞書に保存してください。
結果を読む前にはcalculateまたはcalculate_efficiencyを呼びます。

## 転位係数を直接代入する

最適化せずに数式を確認する場合は、calculate_efficiencyを使います。
5つの転位係数を逆算せず、指定した数値のまま効率を計算します。

```python
model.calculate_efficiency(
    xs=0.476, xp1=0.762, xr1=2.000, xp2=0.536, xr2=1.210,
    center=21.26791100127434,
)
print(model.forward_efficiency)
```

実行用の短い例は `code/check_efficiency.py` にあります。
中心間距離も作動圧力角・歯先径の計算に必要なので、引数で明示します。
転位係数と中心間距離を任意に与えた場合、中心距離一致や歯厚の整合性は
自動では保証されません。この入口は指定値をそのまま式に代入するためのものです。
論文の表は丸められているため、例ではS-P1の転位和から中心間距離を求めます。
従来のcalculateはxp2を約0.537037に再計算しますが、直接代入では0.536を保持するため、
両者の効率はわずかに異なります。

転位の変換だけを確認する場合は、5つの数値を受け取れます。

```python
xs, xp1, xr1, xp2, xr2 = model.calculate_shifts([1.0, 0.5, 21.0])
```

calculate_shiftsはモデルの状態を変更しません。

## 各クラス

| クラス | 役割 |
|---|---|
| `Gearbox` | 歯数・モジュール・圧力角を保存する |
| `Model` | 転位・歯先径・3つのかみ合い・減速機効率を順番に計算する |
| `ProfileShifts` | 5つの転位係数を保存する |
| `Mesh` | 1組のかみ合い率と基礎効率を計算して保存する |

Modelのcalculateは、calculate_shiftsとcalculate_efficiencyを順番に呼ぶだけです。
前者が以下の1〜2、後者が3〜5を担当します。

1. 共通中心間距離から作動圧力角を計算。
2. 式(88)から残りの転位係数を計算。
3. 式(82)-(87)から歯先半径を計算。
4. Meshで各かみ合い率と基礎効率を計算。
5. total_efficienciesで順効率・逆効率を計算。

`total_efficiencies` の返り値は2つの数値です。その他の補助関数も数値や辞書を返します。
`to_dict()` はグラフやJSONへの保存用です。最初は読み飛ばしてかまいません。

Gearboxは作成時に速度比なども計算します。歯数を変更するときは、後から
`gearbox.zs = ...` と代入せず `Gearbox(zs=...)` で作り直します。

## 最適化とのつながり

`code/simple_slsqp.py` の目的関数は次の2行が中心です。

```python
def objective(x):
    model.calculate(x)
    return -model.forward_efficiency
```

SciPyが候補xを渡すたびにモデルを更新し、順効率のマイナスという数値だけを返します。
制約関数も毎回calculateを呼び、最新の候補について制約を計算します。
共通中心間距離の扱いと式(83)のminは従来と同じです。
逆効率は分子にeta_aを含む式(75)を使います。
旧名backward_efficiency_force_balanceは互換用に残し、backward_efficiencyと同じ値を保持します。
