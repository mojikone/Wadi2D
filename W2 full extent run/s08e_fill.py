"""Fill the open sea, where the fine zoom has no tiles, from a coarser zoom, then write the base back."""
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

Image.MAX_IMAGE_PIXELS = None
B = Path(__file__).resolve().parent / "terrain" / "background"
base = np.asarray(Image.open(B / "base.png").convert("RGB")).astype("float32")
low = Image.open(B / "low.png").convert("RGB").resize((base.shape[1], base.shape[0]), Image.BICUBIC)
low = np.asarray(low).astype("float32")
gap = base.sum(axis=2) == 0
gap = ndimage.binary_opening(gap, iterations=2)
print("gap %", round(float(gap.mean()) * 100, 2), "low still black %", round(float((low[gap].sum(axis=1) < 3).mean()) * 100, 2))
held = np.nan_to_num(low[gap].mean(axis=0))
sea = float(np.median(low[gap].sum(axis=1))) / 3
print("sea rgb", held.round(1), sea)
base[gap] = low[gap]
Image.fromarray(base.astype("uint8")).save(B / "base.png")
(B / "low.png").unlink()
(B / "low.json").unlink()
