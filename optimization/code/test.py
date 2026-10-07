from profile_shift_model import Gearbox, Model

gearbox = Gearbox()  # 論文Table IIIの固定歯数
model = Model(gearbox, friction=0.1)

variables = []
model.calculate()