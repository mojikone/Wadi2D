"""W85 step 2: the ground under a limiting cell, read from the DEM at the pixel.

    python s02_ground.py <dem> <out folder> x,y[,name] ...

For each point: the 20 m cell that holds it and a ring of two cells round it, the lowest and highest pixel, how much
of the cell lies more than 5 m below its median, and a picture.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.windows import from_bounds

DX = 20.0
RING = 2


def main() -> None:
    dem, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dem) as src:
        print("pixel", src.res, "nodata", src.nodata, "dtype", src.dtypes[0])
        for n, arg in enumerate(sys.argv[3:]):
            parts = arg.split(",")
            x, y = float(parts[0]), float(parts[1])
            name = parts[2] if len(parts) > 2 else f"cell{n + 1}"
            half = DX * (RING + 0.5)
            win = from_bounds(x - half, y - half, x + half, y + half, src.transform)
            z = src.read(1, window=win, masked=True).astype(np.float64)
            k = round(DX / src.res[0])
            own = z[RING * k : (RING + 1) * k, RING * k : (RING + 1) * k]
            med = float(np.ma.median(own))
            low = own < med - 5.0
            print(
                f"\n{name} ({x:.0f}, {y:.0f}): cell min {own.min():.2f} median {med:.2f} max {own.max():.2f} m,"
                f" masked {int(np.ma.getmaskarray(own).sum())} px; {int(low.sum())} px ({100.0 * low.mean():.1f} %)"
                f" lie over 5 m below the median, lowest {med - own.min():.1f} m below it"
            )
            whole = z < med - 5.0
            print(
                f"   in the 5 x 5 cells round it: {int(whole.sum())} px over 5 m below, window min {z.min():.2f} max {z.max():.2f}"
            )
            rows = np.nonzero(whole.any(axis=1))[0]
            cols = np.nonzero(whole.any(axis=0))[0]
            if rows.size:
                print(
                    f"   the low patch spans {(rows.max() - rows.min() + 1) * src.res[0]:.1f} m north to south and"
                    f" {(cols.max() - cols.min() + 1) * src.res[0]:.1f} m east to west"
                )
            vals = np.sort(own.compressed())
            print(
                "   cell percentiles 0, 1, 5, 10, 50, 90, 100:",
                np.round(np.percentile(vals, [0, 1, 5, 10, 50, 90, 100]), 2),
            )
            fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
            ext = (x - half, x + half, y - half, y + half)
            im = axes[0].imshow(z, extent=ext, cmap="terrain")
            fig.colorbar(im, ax=axes[0], label="ground, m")
            for a in range(2 * RING + 2):
                axes[0].axvline(x - half + a * DX, color="k", lw=0.4)
                axes[0].axhline(y - half + a * DX, color="k", lw=0.4)
            axes[0].set_title(f"{name}: DEM at {src.res[0]} m, 20 m cells")
            mid = z.shape[0] // 2
            row = int(np.argmin(z.min(axis=1)))
            axes[1].plot(
                np.arange(z.shape[1]) * src.res[0],
                z[row],
                label=f"west to east through the lowest pixel (row {row})",
            )
            col = int(np.argmin(z.min(axis=0)))
            axes[1].plot(
                np.arange(z.shape[0]) * src.res[0],
                z[:, col],
                label=f"north to south through it (column {col})",
            )
            axes[1].plot(
                np.arange(z.shape[1]) * src.res[0],
                z[mid],
                lw=0.6,
                label="west to east through the cell centre",
            )
            axes[1].set_xlabel("m")
            axes[1].set_ylabel("ground, m")
            axes[1].legend(fontsize=7)
            fig.tight_layout()
            fig.savefig(out / f"ground_{name}.png", dpi=110)
            plt.close(fig)


if __name__ == "__main__":
    main()
