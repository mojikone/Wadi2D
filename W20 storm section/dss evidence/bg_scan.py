"""Every plausibly gridded DSS file on the PC: do extents ever differ between records of one series? Copies only."""
import sys, os, re, shutil, collections, pathlib, json, time
from hecdss import HecDss
lines = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
tmp = pathlib.Path(sys.argv[2]); report = open(sys.argv[3], "w", encoding="utf-8", buffering=1)
pat = r"grid|hrap|shg|radar|qpe|mrms|nexrad|persiann|imerg|gpm|era5|chirps|wrf|gfs|ecmwf|gsmap|cmorph|rainfall|shaheen|storm|spatial"
cand = [l for l in lines if re.search(pat, l, re.I) and not l.lower().endswith("griddata.dss")]
seen = set(); todo = []
for c in cand:
    try: s = os.path.getsize(c)
    except OSError: continue
    if s < 40_000 or s > 60_000_000: continue
    key = (os.path.basename(c).lower(), s)
    if key in seen: continue
    seen.add(key); todo.append((s, c))
todo.sort()
print("to scan", len(todo), file=report)
t0 = time.time(); stats = collections.Counter()
for s, c in todo:
    if time.time() - t0 > float(sys.argv[4]): print("TIME UP", stats, file=report); break
    dst = tmp / "s.dss"
    try:
        shutil.copy2(c, dst)
        ver = open(dst, "rb").read(20)[16:18]
        if ver != b"7-": stats["dss6"] += 1; print("DSS6", s, c, file=report); continue
        h = HecDss(str(dst)); cat = h.get_catalog()
        grids = [p for p in cat.uncondensed_paths if "grid" in str(cat.get_record_type(p)).lower()]
        if not grids: stats["no grids"] += 1; h.close(); continue
        series = collections.defaultdict(list)
        for p in grids:
            q = p.split("/"); series[(q[1], q[2], q[3], q[6])].append(p)
        for k, ps in series.items():
            ext = collections.Counter()
            for p in ps[:: max(1, len(ps)//60)]:
                g = h.get(p)
                if g is not None: ext[(g.lowerLeftCellX, g.lowerLeftCellY, g.numberOfCellsX, g.numberOfCellsY)] += 1
            stats["series"] += 1
            if len(ext) > 1: stats["VARYING"] += 1
            print(("VARYING " if len(ext) > 1 else "same ") + json.dumps({"file": c, "series": k, "n": len(ps), "extents": ext.most_common(5)}), file=report)
        h.close()
    except Exception as e:
        stats["failed"] += 1; print("FAILED", c[-90:], repr(e)[:90], file=report)
    finally:
        try: os.remove(dst)
        except OSError: pass
print("END", stats, file=report)
