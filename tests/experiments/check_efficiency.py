"""任意の5転位を直接指定して、効率・かみあい率・幾何整合を確認。"""
import csv
import math
if __package__:
    from .common import load_settings, save_report, Model, opt, center_for_external_shift_sum
else:
    from common import load_settings, save_report, Model, opt, center_for_external_shift_sum
from optimization.profile_shift_model import angle_from_involute, involute


def evaluate_design(g, config, shifts, center=None):
    if center is None:
        center = center_for_external_shift_sum(g, shifts["xs"]+shifts["xp1"])
    m = Model(g, config["friction_coefficient"])
    m.calculate_efficiency(**shifts, center=center)
    centers = {}
    for mesh, relation in zip(m.meshes, (shifts["xs"]+shifts["xp1"], shifts["xp1"]-shifts["xr1"], shifts["xp2"]-shifts["xr2"])):
        inv = involute(g.alpha) + 2*math.tan(g.alpha)*relation/(mesh.z1+mesh.sign*mesh.z2)
        angle = angle_from_involute(inv)
        centers[mesh.name] = mesh.module*abs(mesh.z1+mesh.sign*mesh.z2)*math.cos(g.alpha)/(2*math.cos(angle))
    error = max(abs(a-center) for a in centers.values())
    return {"gearbox": g.to_dict(), "settings": config, "evaluation": m.to_dict(),
            "reconstructed_centers_mm": centers, "maximum_center_error_mm": error,
            "center_consistent": error <= 1e-7*max(1., abs(center)),
            "constraint_margins": opt.margins_for(m, config)}


def main():
    data, g, config, output = load_settings()
    direct = dict(data["evaluation"])
    center = direct.pop("center_mm")
    report = evaluate_design(g, config, direct, center)
    output /= "efficiency"
    save_report(report, output)
    rows = []
    for mesh in report["evaluation"]["meshes"]:
        row = {"mesh": mesh["name"], "basic_efficiency_percent": 100*mesh["basic_efficiency"],
               "approach_ratio": mesh["approach_ratio"], "recess_ratio": mesh["recess_ratio"],
               "contact_ratio": mesh["approach_ratio"]+mesh["recess_ratio"],
               "working_angle_deg": math.degrees(mesh["working_angle"])}
        rows.append(row)
        print(row)
    with (output/"meshes.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    evaluation = report["evaluation"]
    print(f"順効率: {evaluation['forward_efficiency']:.6%}、逆効率: {evaluation['backward_efficiency']:.6%}")
    print("中心距離の整合:", report["center_consistent"], "最大差 [mm]:", report["maximum_center_error_mm"])
    print("指定転位を補正せずに評価しています。結果:", output)


if __name__ == "__main__":
    main()
