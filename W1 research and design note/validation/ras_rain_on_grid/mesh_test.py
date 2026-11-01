"""Which staircase perimeters RAS's mesh generator accepts: small shapes on the 20 m lattice, no flow to speak of.

usage: mesh_test.py SHAPE      runs Ras.exe on the shape and prints the cell count or the mesh error
"""

from __future__ import annotations

import subprocess
import sys

import h5py
import numpy as np
from scipy import ndimage

import case
import ras_text
import s01_domain

X0, Y0, DX = case.X0 + 7000 * 1, case.Y0 - 800.0, 20.0
X0 = case.X0 + 350 * DX
RAS = r"C:\Program Files (x86)\HEC\HEC-RAS\6.6\Ras.exe"


def shape(name: str) -> np.ndarray:
    m = np.ones((12, 12), bool)
    if name == "square":
        pass
    elif name == "lshape":
        m[:6, :6] = False
    elif name == "notch":
        m[0:3, 5:7] = False
    elif name == "stairs":
        for j in range(12):
            m[j, : max(0, 11 - j - 1)] = False
    elif name == "spike":
        m[:, :] = False
        m[4:, :] = True
        m[1:4, 6] = True
    elif name == "neck":
        m[:] = False
        m[0:5, 0:12] = True
        m[7:12, 0:12] = True
        m[5:7, 6] = True
    elif name == "real_crop":
        full = np.load(case.HERE / "mask_20m.npy")
        return full[60:120, 100:180]
    elif name == "real_open":
        return opened()
    else:
        raise ValueError(name)
    return m


def opened() -> np.ndarray:
    full = np.load(case.HERE / "mask_20m.npy")
    o = ndimage.binary_opening(full, structure=np.ones((2, 2), bool))
    lab, n = ndimage.label(o)
    return lab == 1 + int(np.argmax(ndimage.sum(o, lab, range(1, n + 1))))


def main() -> None:
    name = sys.argv[1]
    m = shape(name)
    ring = s01_domain.pull_in(s01_domain.ring_of(m, DX, X0, Y0))
    j, i = np.nonzero(m)
    seeds = np.column_stack((X0 + (i + 0.5) * DX, Y0 - (j + 0.5) * DX))
    p = ras_text.Project(
        name="Mesh", title=f"mesh test {name}", perimeter=ring, seeds=seeds, dx=DX, manning=0.05,
        rain_interval="5MIN", rain_mm=np.zeros(13), duration_h=1, equation=2, cores=2, step="10SEC",
        map_interval="5MIN", terrain_rel=r"..\..\ras_terrain\Terrain.hdf",
    )  # fmt: skip
    folder = case.HERE / "mesh_test" / name
    ras_text.write(p, folder)
    with open(folder / "ras_stdout.txt", "w") as out:
        subprocess.run([RAS, "-c", str(folder / "Mesh.prj"), str(folder / "Mesh.p01")], stdout=out, stderr=subprocess.STDOUT, check=False)
    err = folder / "Mesh.p01.data_errors.txt"
    if err.exists():
        print(name, "cells", m.sum(), "ring", len(ring), "ERROR:", err.read_text()[:300].replace("\n", " "))
        return
    with h5py.File(folder / "Mesh.g01.hdf", "r") as f:
        g = f["Geometry/2D Flow Areas/Mesh"]
        c = int(f["Geometry/2D Flow Areas/Attributes"]["Cell Count"][0])
        a = g["Cells Surface Area"][:c]
    print(name, "cells", m.sum(), "ring", len(ring), "RAS cells", c, "area min, max", float(a.min()), float(a.max()))


if __name__ == "__main__":
    main()
