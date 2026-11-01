"""Where the 2 m flood-fill at FSL differs from the reservoir polygon; volume inside the polygon from the DEM."""
import sys

import numpy as np
import rasterio
import rasterio.features
import shapefile
import shapely
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from scipy import ndimage
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import BLOCK, DAMS, DEM, OUT
from dams import DAM_LIST
from s10_eav import dam_box

r = shapefile.Reader(str(DAMS / "Reservoirs.shp"))
shapes = [shapely.geometry.shape(s.__geo_interface__) for s in r.shapes()]
polys = {"Bidah 03": shapes[0], "Faydh 01": shapes[1]}
fig, axs = plt.subplots(1, 2, figsize=(18, 9))
for ax, (name, dam) in zip(axs, DAM_LIST.items()):
    b = dam_box(dam)
    with rasterio.open(DEM) as src:
        w = from_bounds(*b, src.transform).round_offsets().round_lengths()
        s = 4
        h, wd = int(w.height // s), int(w.width // s)
        w = rasterio.windows.Window(w.col_off, w.row_off, wd * s, h * s)
        z = src.read(1, window=w, out_shape=(h, wd), masked=True).astype(np.float64).filled(np.nan)
        t0 = src.window_transform(w)
    pix = 2.0
    t = from_origin(t0.c, t0.f, pix, pix)
    poly = polys[name]
    inp = rasterio.features.geometry_mask([poly], z.shape, t, invert=True)
    e = dam.eav()
    print(name, "polygon area", poly.area / 1e6)
    for lv in (dam.fsl - 15, dam.fsl - 10, dam.fsl - 5, dam.fsl - 2, dam.fsl):
        m = inp & (z < lv)
        print(f"  z {lv}: in polygon DEM(0.5 m file) A {m.sum()*4/1e6:.3f} V {(lv-z)[m].sum()*4/1e6:.3f} | EAV A {np.interp(lv,e[:,1],e[:,0])/1e6:.3f} V {np.interp(lv,e[:,1],e[:,2])/1e6:.3f}")
    # also the 2 m NSA DEM and the 5 m one in the polygon
    for label, path in (("NSA 2 m", BLOCK / "Terrain" / "NSA_Batinah_2m.tif"), ("GGC 5 m", BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif"), ("NSA 5 m", BLOCK / "Terrain" / "NSA_Batinah_5m.tif")):
        with rasterio.open(path) as src:
            w2 = from_bounds(*poly.bounds, src.transform).round_offsets().round_lengths()
            a = src.read(1, window=w2, masked=True).astype(np.float64).filled(np.nan)
            tt = src.window_transform(w2)
            res = src.res[0]
        im = rasterio.features.geometry_mask([poly], a.shape, tt, invert=True)
        lv = dam.fsl
        m = im & (a < lv)
        print(f"  {label} at FSL: min {np.nanmin(a[im]):.2f} A {m.sum()*res*res/1e6:.3f} V {(lv-a)[m].sum()*res*res/1e6:.3f}")
    ext = (t.c, t.c + z.shape[1] * pix, t.f - z.shape[0] * pix, t.f)
    ax.imshow(np.clip(z, dam.fsl - 20, dam.fsl + 15), extent=ext, cmap="terrain")
    wet = z < dam.fsl
    lab, _ = ndimage.label(wet)
    col = int((dam.pool_point[0] - t.c) / pix)
    row = int((t.f - dam.pool_point[1]) / pix)
    conn = lab == lab[row, col]
    ax.contour(conn[::-1].astype(float), levels=[0.5], extent=ext, colors="b", linewidths=0.6)
    x, y = poly.exterior.xy
    ax.plot(x, y, "r", lw=0.8)
    for c in dam.crest_lines:
        c = np.array(c)
        ax.plot(c[:, 0], c[:, 1], "k", lw=1)
    c = np.array(dam.spillway)
    ax.plot(c[:, 0], c[:, 1], "y", lw=3)
    ax.plot(*dam.pool_point, "w*")
    ax.set_xlim(poly.bounds[0] - 300, poly.bounds[2] + 300)
    ax.set_ylim(poly.bounds[1] - 300, poly.bounds[3] + 300)
    ax.set_title(name)
fig.tight_layout()
fig.savefig(OUT / "scripts" / "res_map.png", dpi=70)
