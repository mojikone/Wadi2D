"""Summary of one exported case: max of each column, and a few rows around a given step."""

import sys
from pathlib import Path

import numpy as np

path = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures" / f"{sys.argv[1]}.csv"
names = path.read_text(encoding="utf-8").splitlines()[0].split(",")
data = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
for k, name in enumerate(names):
    print(f"{name:15s} min {data[:, k].min():14.6f} max {data[:, k].max():14.6f} argmax {np.argmax(data[:, k])}")
rows = [int(r) for r in sys.argv[2:]]
if rows:
    print(" ".join(f"{n:>13s}" for n in names))
    for r in rows:
        print(" ".join(f"{v:13.6f}" for v in data[r]))
