import sys, os, re
lines = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
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
stuck = os.path.getsize(sys.argv[2])
done = sum(1 for s, _ in todo if s < stuck)
print("candidates", len(todo), "finished before the stall", done, "stalled on size", stuck, "largest unscanned", todo[-1][0] if todo else None)
print("stalled file:", next((c[-100:] for s, c in todo if s == stuck), "?"))
print("wrf_dss files not reached:", sum(1 for s, c in todo if s >= stuck and "wrf" in c.lower()))
