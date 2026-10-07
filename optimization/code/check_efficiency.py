"""転位係数を直接代入して効率を確認する。最適化は実行しない。

実行: python check_efficiency.py（SciPy不要）
"""
from profile_shift_model import Gearbox, Model, center_for_external_shift_sum

gearbox = Gearbox()
model = Model(gearbox, friction=0.13)

# 確認したい5つの転位係数をここに書く。例は論文Table III。
xs = 0.476
xp1 = 0.762
xr1 = 2.000
xp2 = 0.536
xr2 = 1.210

# 効率計算には中心間距離も必要。今回はS-P1の転位和から求める。
# 任意の中心間距離を確認するなら、例えば center = 21.267911 と書く。
# 表は丸められているため、他のかみ合いの復元中心間距離とは微小差がある。
center = center_for_external_shift_sum(gearbox, xs + xp1)

model.calculate_efficiency(xs, xp1, xr1, xp2, xr2, center)

print("代入した転位係数:", model.shifts.to_dict())
print("共通中心間距離 [mm]:", model.center_mm)
for mesh in model.meshes:
    print(f"かみ合い{mesh.name}: かみ合い率={mesh.contact_ratio:.6f}, 基礎効率={mesh.basic_efficiency:.6%}")
print(f"順効率（式64）: {model.forward_efficiency:.6%}")
print(f"逆効率（式75）: {model.backward_efficiency:.6%}")
