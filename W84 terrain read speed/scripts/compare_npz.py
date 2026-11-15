"""Two saved sets of arrays, compared to the byte. Args: a.npz b.npz. Exit 1 on any difference."""

import sys

import numpy as np

a, b = np.load(sys.argv[1]), np.load(sys.argv[2])
names = sorted(set(a.files) | set(b.files))
bad = 0
total = 0
for name in names:
    if name not in a.files or name not in b.files:
        print("only in one:", name)
        bad += 1
        continue
    x, y = a[name], b[name]
    same = x.shape == y.shape and x.dtype == y.dtype and x.tobytes() == y.tobytes()
    total += x.nbytes
    if not same:
        bad += 1
        print("DIFFERENT:", name, x.shape, y.shape, x.dtype, y.dtype)
print(f"{len(names)} arrays, {total / 2**20:.1f} MB, {bad} different")
sys.exit(1 if bad else 0)
