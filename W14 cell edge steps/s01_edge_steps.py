"""Why cell blocks show: surface jump along linked cell edges, before and after making the fill offset continuous."""
import sys
from pathlib import Path
import numpy as np, h5py
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from wadi2d.config.schema import RunConfig
from wadi2d.run import prepare_grid
from wadi2d.products.frames import frame_names, run_maxima
from wadi2d.products.ground import read_cells, face_sills
from wadi2d.products.surface import Neighbours, at_pixels, corner_basis, corner_groups, corner_means, face_links, FILL_STEPS, FILL_TOLERANCE

S = Path(sys.argv[1])
RUN = Path(r"D:\Mojtaba\Renardet\Wadi2D\W13 time step test\runs\cfl_0450")
cfg = RunConfig.model_validate_json((RUN/"config.resolved.json").read_text(encoding="utf-8"))
rule = cfg.outputs.pixels
tables, crs = prepare_grid(cfg, Path(cfg.grid.cache_dir))
res = RUN/"results.h5"
peak = run_maxima(res)
keep = peak["mean_depth"] > rule.cell_depth
cells = read_cells(cfg, tables, keep)
print("cells", cells.rows.size, "k", cells.k)
names = frame_names(res); name = names[int(len(names)*12.3/18)]
with h5py.File(res) as f:
    g = f["maps"][name]; depth, mean = g["depth"][:], g["mean_depth"][:]
print("frame", name)
xp = np
near = Neighbours(np, keep)
take = lambda a, o=0.0: np.append(a[cells.rows, cells.cols], o).astype(np.float32)
zmin = take((tables.zmin - cells.datum).astype(np.float32))
sx, sy = face_sills(tables, cells.datum)
d, h = take(depth), take(mean)
sx, sy = take(sx, np.inf), take(sy, np.inf)
wet = d > 0.0; level = zmin + d
lx = face_links(near, level, d, wet, sx, 1, rule.link_margin, rule.link_ratio)
ly = face_links(near, level, d, wet, sy, 0, rule.link_margin, rule.link_ratio)
groups = corner_groups(near, lx, ly)
levels = corner_means(near, level, wet, groups)
basis = corner_basis(np, cells.k).T
on = np.nonzero(wet[:-1])[0]
ground = cells.ground[on]
print("wet cells", on.size)

def fill(surface, ground, mean_depth):
    relief = ground - surface; pixels = relief.shape[1]; water = mean_depth * pixels
    offset = relief.mean(axis=1) + mean_depth
    moving = np.arange(relief.shape[0]); left = relief
    for _ in range(FILL_STEPS):
        gap = offset[moving, None] - left; under = gap > 0.0
        step = ((gap * under).sum(axis=1) - water[moving]) / np.maximum(under.sum(axis=1), 1).astype(np.float32)
        offset[moving] -= step
        going = step > FILL_TOLERANCE
        if not going.any(): break
        moving, left = moving[going], left[going]
    return offset, np.maximum(offset[:, None] - relief, 0.0)

k = cells.k
def jumps(px, links, axis):
    """Surface jump between the two rows of pixels either side of each face, wet on both sides."""
    wl = (px + ground)
    full = np.full((wet.size - 1, k, k), np.nan, np.float32); full[on] = np.where(px > 0, wl, np.nan).reshape(-1, k, k)
    idx = near.table[(0, -1) if axis == 1 else (-1, 0)][:-1]
    has = idx < wet.size - 1
    here = full[has]; there = full[idx[has]]
    a, b = (here[:, :, 0], there[:, :, -1]) if axis == 1 else (here[:, 0, :], there[:, -1, :])
    j = np.nanmean(np.abs(a - b), axis=1)
    return j, links[:-1][has]

def report(px, tag):
    held = np.abs(px.mean(axis=1) - h[on])
    out = []
    for axis, l in ((1, lx), (0, ly)):
        j, link = jumps(px, l, axis); out.append((j, link))
    j = np.concatenate([o[0] for o in out]); link = np.concatenate([o[1] for o in out])
    ok = np.isfinite(j)
    print(f"{tag:10s} linked faces {int((ok&link).sum()):6d} mean {np.nanmean(j[ok&link]):.3f} p95 {np.nanquantile(j[ok&link],.95):.3f} max {np.nanmax(j[ok&link]):.2f} | unlinked {int((ok&~link).sum()):5d} mean {np.nanmean(j[ok&~link]):.3f} | held err max {held.max():.2e} mean {held.mean():.2e}")

surface = at_pixels(np, levels, on, basis)
offset, px = fill(surface, ground, h[on])
report(px, "now")
pics = {"now": px}

f = (np.arange(k, dtype=np.float32) + 0.5) / k - 0.5
w1 = np.stack([(0.5 - f) ** 2 / 2, 0.75 - f ** 2, (0.5 + f) ** 2 / 2])  # (3, k), neighbour -1, 0, +1
OFF = [(dj, di) for dj in (-1, 0, 1) for di in (-1, 0, 1)]
basis9 = np.stack([np.outer(w1[dj + 1], w1[di + 1]).ravel() for dj, di in OFF]).astype(np.float32)  # (9, k*k)
print("basis sums to", basis9.sum(axis=0).min(), basis9.sum(axis=0).max(), "own share of cell mean", basis9[4].mean())
corners = dict(zip([(-1, -1), (-1, 1), (1, -1), (1, 1)], groups))
linkmap = {}
for (sy, sx), (side_x, side_y, diagonal) in corners.items():
    linkmap[(0, sx)] = side_x; linkmap[(sy, 0)] = side_y; linkmap[(sy, sx)] = diagonal

def spline(c):
    """The offset at every pixel of the wet cells; an unlinked neighbour reads as this cell."""
    field = np.zeros(wet.size, np.float32); field[on] = c
    parts = []
    for dj, di in OFF:
        if (dj, di) == (0, 0):
            parts.append(field)
        else:
            parts.append(np.where(linkmap[(dj, di)], near.at(field, dj, di), field))
    return at_pixels(np, parts, on, basis9.T.T if False else basis9)

def band_basis(b):
    t = (np.arange(k, dtype=np.float32) + 0.5) / k  # 0..1 across the cell
    edge = np.minimum(t, 1 - t)
    x = np.clip(edge / b, 0, 1)
    own = 0.5 + 0.5 * x * x * (3 - 2 * x)
    left = np.where(t < 0.5, 1 - own, 0.0); right = np.where(t >= 0.5, 1 - own, 0.0)
    w = np.stack([left, own, right])
    return np.stack([np.outer(w[dj + 1], w[di + 1]).ravel() for dj, di in OFF]).astype(np.float32)

def run(tag, base, passes=4, relax=1.0):
    global basis9
    basis9 = base
    print(tag, "own share", float(base[4].mean()))
    c = offset.copy()
    for p in range(1, passes + 1):
        delta, px = fill(surface + spline(c), ground, h[on])
        c = c + relax * delta
        report(px, f"{tag} {p}")
    pics[f"{tag}"] = px
    return px

spline_basis = basis9
run("spline", spline_basis, 3)
run("b.25", band_basis(0.25), 3)
run("b.35", band_basis(0.35), 3)
px = run("b.5", band_basis(0.5), 3)
d0 = pics["b.35"]
wetnow = pics["now"] > 0.05
print("b.35 pixel depth change p50 %.3f p99 %.3f, wet pixels %d -> %d" % (np.median(np.abs(d0-pics['now'])[wetnow]), np.quantile(np.abs(d0-pics['now'])[wetnow], .99), wetnow.sum(), (d0 > 0.05).sum()))
pass
rows, cols = cells.rows, cells.cols
gridx0, gridy0 = tables.grid.x0, tables.grid.y0
dx = tables.grid.dx
b = (435025, 2725115, 435375, 2725465)
j0, j1 = int((gridy0 - b[3]) // dx), int((gridy0 - b[1]) // dx) + 1
i0, i1 = int((b[0] - gridx0) // dx), int((b[2] - gridx0) // dx) + 1
fig, ax = plt.subplots(1, 3, figsize=(20, 7))
for a, key in zip(ax, ("now", "b.25", "b.35")):
    img = np.full(((j1 - j0) * k, (i1 - i0) * k), np.nan, np.float32)
    v = pics[key].reshape(-1, k, k)
    for c, ci in enumerate(on):
        r, q = rows[ci], cols[ci]
        if j0 <= r < j1 and i0 <= q < i1:
            img[(r - j0) * k:(r - j0 + 1) * k, (q - i0) * k:(q - i0 + 1) * k] = np.where(v[c] > 0.05, v[c], np.nan)
    a.imshow(img, cmap="turbo", vmin=0, vmax=2.1, interpolation="nearest"); a.set_title(key)
fig.savefig(S/"blocks.png", dpi=90, bbox_inches="tight")
