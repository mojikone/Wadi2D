"""What the coarse reads cost that W84 left alone: the aligned mesh's analysis raster and its own domain mask.

No args. ``breaklines.window.read_window`` on W79's Block 2 job at 0.5 m: a domain mask through a plain
``RasterBed`` and ``read_coarse``, GDAL's average of the whole window down to the analysis pixel; both decode the
window again whatever the chunk store holds.
"""

import time

import wadi2d.breaklines.window as window_mod
from wadi2d.run import load_job

JOB = r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways\jobs\run1_full_2d_aligned.json"
cfg = load_job(JOB)
d = cfg.model_dump()
d["terrain"]["pixel_stride"] = 1
cfg = type(cfg).model_validate(d)

spent: dict[str, float] = {}


def timed(name: str) -> None:
    f = getattr(window_mod, name)

    def wrap(*a, **k):
        t0 = time.perf_counter()
        try:
            return f(*a, **k)
        finally:
            spent[name] = spent.get(name, 0.0) + time.perf_counter() - t0

    setattr(window_mod, name, wrap)


timed("domain_mask")
timed("read_coarse")
t0 = time.perf_counter()
win = window_mod.read_window(cfg)
print(
    "read_window",
    round(time.perf_counter() - t0, 1),
    "s:",
    {k: round(v, 1) for k, v in spent.items()},
    "analysis raster",
    win.z.shape,
)
