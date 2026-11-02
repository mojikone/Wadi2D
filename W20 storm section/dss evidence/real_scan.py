"""Copy candidate files to scratch (originals never opened by hecdss) and report grid records and extents."""
import sys, os, re, shutil, collections, pathlib, numpy as np, random
from hecdss import HecDss
lines = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
scratch = pathlib.Path(sys.argv[2])
cand = [l for l in lines if re.search(r"wrf|raingrid|radar|qpe|mrms|persiann|imerg|gpm|era5|chirps|gfs|gsmap|cmorph", l, re.I) and not l.lower().endswith("griddata.dss")]
print("candidates", len(cand))
groups = collections.defaultdict(list)
for c in cand: groups[os.path.dirname(c)].append(c)
print("folders", len(groups))
picked = []
for folder, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    items = sorted(items, key=lambda p: os.path.getsize(p) if os.path.exists(p) else 0)
    picked.extend(items[:2])
picked = picked[:int(sys.argv[3])]
for i, src in enumerate(picked):
    try: size = os.path.getsize(src)
    except OSError: continue
    if size > 80_000_000: print("skip big", size//1000000, src[-70:]); continue
    dst = scratch / f"r{i}.dss"
    shutil.copy2(src, dst)
    head = open(dst, "rb").read(24)
    ver = head[16:20]
    if not ver.startswith(b"7"):
        print(f"[{i}] DSS {ver} {size//1024} KB {src[-90:]}"); continue
    try:
        h = HecDss(str(dst)); cat = h.get_catalog()
        grids = [p for p in cat.uncondensed_paths if "grid" in str(cat.get_record_type(p)).lower()]
        ext = collections.Counter(); unit = collections.Counter(); null = collections.Counter(); kinds = collections.Counter(); edge = collections.Counter()
        step = max(1, len(grids)//200)
        for p in grids[::step]:
            g = h.get(p)
            if g is None: continue
            ext[(g.lowerLeftCellX, g.lowerLeftCellY, g.numberOfCellsX, g.numberOfCellsY)] += 1
            unit[g.dataUnits] += 1; null[g.nullValue] += 1; kinds[(g.type, g.data_type)] += 1
        print(f"[{i}] {size//1024} KB, {len(cat.uncondensed_paths)} records, {len(grids)} grids; {src[-80:]}")
        if grids:
            print("    first", grids[0]); print("    last ", grids[-1])
            print("    extents", ext.most_common(4), "distinct", len(ext)); print("    units", dict(unit), "null", dict(null), "kinds", dict(kinds))
            print("    x0,y0", g.xCoordOfGridCellZero, g.yCoordOfGridCellZero, "cell", g.cellSize, "srs", (g.srsDefinition or "")[:70])
        h.close()
    except Exception as e:
        print(f"[{i}] failed {e}", src[-70:])
