"""What RAS does with a Precipitation Hydrograph: units, which interval a value belongs to, the shape inside it.

A 500 x 500 m square on the Fan terrain, 50 m cells, walls all round, three pulses on a 5 min table, cumulative depth
written every minute. Run with: grammar_test.py build; run_ras.py grammar_test Gram; grammar_test.py read
"""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np

import ras_text

HERE = Path(__file__).resolve().parent
FOLDER = HERE / "grammar_test"
X0, Y0, SIDE, DX = 437999.98973783385, 2727999.893463373, 500.0, 50.0
RAIN = np.zeros(25)  # 2 h at 5 min
RAIN[3], RAIN[4], RAIN[10] = 6.0, 12.0, 30.0


def build() -> None:
    x1, y1 = X0 + SIDE, Y0 - SIDE
    n = round(SIDE / DX)
    xs = X0 + (np.arange(n) + 0.5) * DX
    ys = Y0 - (np.arange(n) + 0.5) * DX
    xx, yy = np.meshgrid(xs, ys)
    p = ras_text.Project(
        name="Gram", title="Precipitation grammar test",
        perimeter=np.array([[X0, Y0], [x1, Y0], [x1, y1], [X0, y1], [X0, Y0]]),
        seeds=np.column_stack([xx.ravel(), yy.ravel()]), dx=DX, manning=0.05,
        rain_interval="5MIN", rain_mm=RAIN, duration_h=2, equation=2, cores=4, step="10SEC", map_interval="1MIN",
        terrain_rel=r"..\..\ras_head_to_head\ras_common\Terrain\Terrain.hdf",
        extra_outputs=["Cell Cumulative Precipitation Depth", "Cell Precipitation Rate"],
    )  # fmt: skip
    ras_text.write(p, FOLDER)


def read() -> None:
    base = "Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series"
    with h5py.File(FOLDER / "Gram.p01.hdf", "r") as f:
        ts = f[base]
        t = ts["Time"][:] * 1440.0
        g = ts["2D Flow Areas/Gram"]
        print(list(g.keys()))
        for k in ("Cell Cumulative Precipitation Depth", "Cell Precipitation Rate"):
            if k in g:
                a = g[k][:]
                print(k, a.shape, g[k].attrs.get("Units"), "spread at the end", a[-1].min(), a[-1].max())
                c = a[:, 0]
                for tt, v in zip(t, c, strict=True):
                    if tt <= 70:
                        print(f"  t {tt:5.1f} min  {v:.4f}")
        va = f["Results/Unsteady/Summary/Volume Accounting"].attrs
        print({k: (v.decode() if isinstance(v, bytes) else v) for k, v in va.items()})
        for k, v in f["Results/Unsteady/Summary/Volume Accounting"].items():
            print(k, v.attrs if hasattr(v, "attrs") else v)
        print(f["Geometry/2D Flow Areas/Attributes"][()])


if __name__ == "__main__":
    {"build": build, "read": read}[sys.argv[1]]()
