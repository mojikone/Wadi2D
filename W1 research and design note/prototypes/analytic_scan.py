"""Run every analytic case on one backend and print the errors. Used to set honest test limits."""
import sys
import time
import warnings

warnings.simplefilter("ignore")
sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\tests\solver")
import harness  # noqa: E402

from wadi2d.config.schema import Numerics  # noqa: E402
from wadi2d.validation import UniformGrid, compare  # noqa: E402
from wadi2d.validation.cases import dam_break, lake_at_rest, macdonald, thacker  # noqa: E402

backend = sys.argv[1] if len(sys.argv) > 1 else "gpu"
loose = Numerics(sheet_flow=False, e_wet=1e-5, h_cfl=1e-4, dt_every=1, dt_max=60.0)
sheet = Numerics(e_wet=1e-5, h_cfl=1e-4, dt_every=1, dt_max=60.0)


def show(name, case, k=1, num=loose, **kw):
    t0 = time.time()
    r = harness.run(case, k=k, num=num, backend=backend, **kw)
    rep = compare(r.state, case, kw.get("t_end", case.t_end))
    print(
        f"{name:22s} h rmse {rep.depth_rmse:.4f} l1 {rep.depth_l1:.4f} linf {rep.depth_linf:.3f}  q rmse {rep.discharge_rmse:.4f}  "
        f"F {rep.f_statistic:.3f} vol {rep.volume_error:+.1e} steps {r.wall_steps} {time.time() - t0:.1f}s {'PASS' if rep.passed else 'FAIL ' + '; '.join(rep.failures)}"
    )


g200 = UniformGrid.square(4.0, 200)
show("stoker x", dam_break.build_stoker(UniformGrid(0.0, 0.0, 0.5, 400, 8)))
show("stoker y", dam_break.build_stoker(UniformGrid(0.0, 0.0, 0.5, 8, 400), axis="y"))
show("ritter x", dam_break.build_ritter(UniformGrid(0.0, 0.0, 0.5, 400, 8)))
show("thacker planar k1", thacker.build_planar(g200))
show("thacker planar k4", thacker.build_planar(g200), k=4)
show("thacker curved k1", thacker.build_curved(g200))
show("thacker curved k4", thacker.build_curved(g200), k=4)
show("lake bump", lake_at_rest.build_bump(UniformGrid.square(10.0, 100)), t_end=5.0)
show("lake rough k4", lake_at_rest.build_rough(UniformGrid.square(10.0, 100)), k=4, t_end=5.0)
show("lake slope k4", lake_at_rest.build_slope(UniformGrid.square(10.0, 100)), k=4, t_end=5.0)
g5 = UniformGrid(0.0, 0.0, 5.0, 200, 4)
for v in (macdonald.Variant.SUBCRITICAL, macdonald.Variant.SUPERCRITICAL, macdonald.Variant.JUMP):
    show(f"macdonald {v.name}", macdonald.build_macdonald(g5, v))
