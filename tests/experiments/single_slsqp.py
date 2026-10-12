"""1組の歯数・モジュールで本番と同じSLSQPを検証する。"""
if __package__:
    from .common import load_settings, finish, opt
else:
    from common import load_settings, finish, opt


def main():
    data, g, config, output = load_settings()
    if not all(opt.fixed_assembly_checks(g).values()):
        raise ValueError("等配組付け条件を満たしません")
    best, trials, versions = opt.optimize(g, config, capture_history=True)
    finish("SLSQP", data, g, config, best, trials, versions, output/"slsqp")


if __name__ == "__main__":
    main()
