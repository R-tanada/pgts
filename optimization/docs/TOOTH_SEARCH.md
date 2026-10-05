※ フォルダ整理後: コードと設定は code/、論文は references/ にあります。コマンドはプロジェクトのルートで実行してください。

# 無転位・標準平歯車の3K歯数探索

固定歯数での転位係数最適化は、別の `optimize_profile_shift.py` で実装しています。使い方と数式は [OPTIMIZATION.md](OPTIMIZATION.md) を参照してください。

`tooth_search.py` は、指定した歯数範囲から、7種類の制約を満たす組み合わせをCSVに保存します。Python 3.10以上、追加パッケージ不要です。

## 前提

- 論文のType-I構成: 太陽歯車S入力、内歯車R1固定、内歯車R2出力。
- P1とP2は一体の複合遊星。すべての複合遊星は同じ相対歯位相で製作し、全体として回転して歯合わせする。
- 無転位、標準平歯車、圧力角20度、歯末のたけ1m。圧力角や歯形の変更には判定式の見直しが必要。
- S・P1・R1はモジュールm1、P2・R2はm2。両層のモジュールは異なっていてもよい。
- 切下げの最小歯数判定は行わない。S-P1のインボリュート干渉は別の条件として判定する。

## 設定と実行

`search_config.json` の `tooth_ranges` で、sun、planet1、ring1、planet2、ring2それぞれのminimumとmaximumを設定します。上限・下限を含みます。

その他の設定:

| キー | 意味 |
|---|---|
| module1_mm / module2_mm | 各層のモジュール [mm] |
| planet_count | 等間隔に配置する複合遊星の個数。2以上 |
| reduction_min / reduction_max | 減速倍率の範囲 `abs(入力速度/出力速度)` |
| direction | same:同方向、opposite:逆方向、both:両方 |
| planet_clearance_mm | 隣接遊星の歯先円間に要求するすきま [mm] |
| output_csv | 出力ファイル。相対パスは設定ファイルのフォルダが基準 |

既定の探索範囲は動作例であり、論文の試作歯数ではありません。

```powershell
python code/tooth_search.py
python code/tooth_search.py --config code/search_config.json
python -m unittest discover -s tests -p "test_tooth_search.py"
```

同じ出力パスへの再実行は結果を上書きします。旧版の `tooth_candidates.csv` は今回の出力ではありません。

## 判定条件

### 1. 減速比

論文の式(44)-(46):

```text
I1 = zr1 / zs
I2 = zr1*zp2 / (zr2*zp1)
G  = (1-I2) / (1+I1)   # 出力速度 / 入力速度（符号付き）
reduction_min <= abs(1/G) <= reduction_max
```

G=0は除外。方向も判定します。速度比はFractionで計算し、範囲の端点を含めます。

### 2. 中心間距離

無転位なので、以下の標準中心距離を等しくします。

```text
a_SP1 = m1*(zs+zp1)/2
a_P1R1 = m1*(zr1-zp1)/2
a_P2R2 = m2*(zr2-zp2)/2
a_SP1 = a_P1R1 = a_P2R2 > 0
```

この等式から `zr1=zs+2*zp1` と `zr2=zp2+(m1/m2)*(zs+zp1)` を計算して列挙します。R1/R2も指定した歯数範囲内で整数であることを確認します。5重ループを省略しているだけで、この中心距離条件を満たす歯数の組み合わせを落としません。小範囲で5重総当たりと照合しています。

### 3. 拘束かみ合い・等配

N個の同じ複合遊星について、次の2式が整数であることを確認します。

```text
(zs + zr1) / N
(zr2*zp1 - zr1*zp2) / (N*gcd(zp1,zp2))
```

第一層だけでなく、P1/P2の歯位相を含めた条件です。第二式は、隣の等配位置でP1の歯ピッチ単位の回転によってP2も歯合わせできる条件から導いています。各遊星のP1/P2を別々の位相で製作する構成や不等配は扱いません。直接の歯位相探索との照合テストがあります。

### 4. 外径干渉

各層で隣接遊星の歯先円が重ならず、指定すきまを確保すること。

```text
neighbor_distance = 2*a*sin(pi/N)
neighbor_distance - m1*(zp1+2) > planet_clearance_mm
neighbor_distance - m2*(zp2+2) > planet_clearance_mm
```

接触も除外します。別の軸方向位置にあるP1とP2の間の干渉は判定しません。ハブ、軸、筐体などの形状も対象外です。

### 5. インボリュート干渉

S-P1は作用線上の接触区間が両歯車の基礎円外にある条件を使います。P1-R1とP2-R2はKHKの内歯かみあい回避式を使います。内歯車の歯先が基礎円より内側の場合は、この解析式の適用範囲外として除外します。

### 6. トロコイド干渉

**標準20度に対する保守的な十分条件 `zr-zp > 9` を使います。厳密な限界式ではありません。** 歯数差9以下で実際には干渉しない一部の歯数対も除外されます。すべての幾何学的に非干渉な候補を網羅する検索ではなく、この十分条件を満たす候補の検索です。

### 7. トリミング

KHKの角度式でP1-R1、P2-R2を判定します。半径方向の組付け・分離を妨げる干渉を除外します。工具との干渉を判定するにはピニオンカッタの歯数・転位などが必要で、今回の対象には含めません。KHKの内歯車カタログの許容遊星歯数と境界を照合しています。

## 出力

`standard_tooth_candidates.csv` に全判定を通過した歯数、厳密速度比G_exact、速度比G、減速倍率、回転方向、中心距離、両層の遊星間すきまを保存します。候補0件でもヘッダーを保存します。

同名の `.summary.json` に実行時の設定と候補件数を保存します。不合格件数は中心距離で先に絞った候補について、最初に不合格となった条件だけの集計です。中心距離を満たさない組み合わせは列挙せず、集計に含めません。

判定関数を制約ごとに分けているので、変更する式の関数を追えば条件を確認できます。強度、効率最適化、かみあい率、加工工具・実形状・公差の評価は今回の範囲外です。

## 参照資料

- Matsuki, Nagano, Fujimoto (2019), *Bilateral Drive Gear—A Highly Backdrivable Reduction Gearbox for Robotic Actuators*, DOI: 10.1109/TMECH.2019.2946403。references/ 内の論文PDF。速度比と中心距離条件の根拠。
- [KHK: 内歯車の寸法計算](https://www.khkgears.co.jp/gear_technology/basic_guide/khk362/)
- [KHK-USA: Internal ring gears – design and considerations](https://khkgears.us/media/beqhhrye/gear-solutions_khk_internal-ring-gears-design-and-considerations.pdf) — 内歯かみあいの干渉条件。トリミングはEquation 8/9。
- [KHK: Internal Gears Technical Information](https://khkgears.net/pdf/internal-tech.pdf) — インボリュートとトリミングの許容歯数の検証。
