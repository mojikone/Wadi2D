"""Print what an .npz holds (read only)."""

import sys

import numpy as np

for path in sys.argv[1:]:
    with np.load(path, allow_pickle=False) as f:
        for k in f.files:
            a = f[k]
            extra = f" sum={a.sum()}" if a.dtype == bool or a.ndim == 0 else ""
            print(path.split("/")[-1], k, a.shape, a.dtype, extra, a if a.size < 8 else "")
