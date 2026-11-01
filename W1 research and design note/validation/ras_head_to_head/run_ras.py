"""Run one text-built project through Ras.exe -c and append its timing to ras_timing.csv.

usage: run_ras.py FOLDER [--version 6.6]
"""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

import h5py

HERE = Path(__file__).resolve().parent
RAS = r"C:\Program Files (x86)\HEC\HEC-RAS\{}\Ras.exe"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--version", default="6.6")
    a = ap.parse_args()
    d = (HERE / a.folder).resolve()
    t0 = time.perf_counter()
    with open(d / "ras_stdout.txt", "w") as out:
        rc = subprocess.run(
            [RAS.format(a.version), "-c", str(d / "Fan.prj"), str(d / "Fan.p01")],
            stdout=out,
            stderr=subprocess.STDOUT,
            check=False,
        ).returncode
    wall = time.perf_counter() - t0
    with h5py.File(d / "Fan.p01.hdf", "r") as f:
        s = f["Results/Unsteady/Summary"].attrs
        eq = f["Plan Data/Plan Parameters"].attrs["2D Equation Set"][0].decode()
        cores = int(f["Plan Data/Plan Parameters"].attrs["2D Cores (per mesh)"][0])
        va = f["Results/Unsteady/Summary/Volume Accounting"].attrs
        ver = f.attrs["File Version"].decode()
        line = (
            f"{a.folder},{ver},{eq},{cores},{rc},{wall:.1f},{s['Computation Time Total'].decode()},"
            f"{s['Solution'].decode()},{float(va['Error Percent']):.5f}"
        )
    with open(HERE / "ras_timing.csv", "a") as out:
        out.write(line + "\n")
    print(line)


if __name__ == "__main__":
    main()
