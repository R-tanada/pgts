
import time
import numpy as np
import pyvista as pv

# ==========================================
# ウィンドウ設定
# ==========================================
plotter = pv.Plotter(window_size=(1100, 750))
plotter.set_background("white")

# ==========================================
# モデル作成
# ==========================================
cube = pv.Cube(
    x_length=1.5,
    y_length=1.5,
    z_length=1.5
).triangulate()

sphere = pv.Sphere(
    radius=0.4,
    theta_resolution=48,
    phi_resolution=48
)

cube_original = cube.points.copy()
sphere_original = sphere.points.copy()

# 描画
plotter.add_mesh(
    cube,
    color="royalblue",
    smooth_shading=True,
    copy_mesh=False
)

plotter.add_mesh(
    sphere,
    color="tomato",
    smooth_shading=True,
    copy_mesh=False
)

# カメラ
plotter.camera_position = [
    (6, 6, 5),
    (0, 0, 0),
    (0, 0, 1)
]

plotter.enable_trackball_style()

# ==========================================
# アニメーション
# ==========================================
start_time = time.perf_counter()

def animate(obj, event):
    t = time.perf_counter() - start_time

    # 立方体の回転
    angle = t * 1.5

    c = np.cos(angle)
    s = np.sin(angle)

    R = np.array([
        [c, -s, 0],
        [s,  c, 0],
        [0,  0, 1]
    ])

    cube.points = cube_original @ R.T

    # 球の公転
    radius = 2.5

    x = radius * np.cos(t)
    y = radius * np.sin(t)
    z = 0.7 * np.sin(2 * t)

    sphere.points = sphere_original + [x, y, z]

    # 更新通知
    cube.Modified()
    sphere.Modified()

    # 再描画
    plotter.render()

# ==========================================
# タイマーイベント登録
# ==========================================
plotter.iren.add_observer(
    "TimerEvent",
    animate
)

# ウィンドウを非ブロッキングで開く
plotter.show(
    auto_close=False,
    interactive_update=True
)

# タイマー生成
timer_id = plotter.iren.create_timer(
    duration=16,
    repeating=True
)

# イベントループ
try:
    while plotter.ren_win is not None:
        plotter.update()
        time.sleep(0.001)

except KeyboardInterrupt:
    pass

finally:
    plotter.close()
