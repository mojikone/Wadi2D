import sys, os, re, collections
lines = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
print("total", len(lines))
c = collections.Counter(); keep = []
for l in lines:
    p = l.split("\\")
    c["\\".join(p[:3])] += 1
    if re.search(r"grid|hrap|shg|radar|qpe|mrms|nexrad|stage|persiann|imerg|gpm|era5|chirps|wrf|gfs|ecmwf|gsmap|cmorph|rainfall|precip", l, re.I): keep.append(l)
for k, v in c.most_common(14): print(v, k)
print("named like grids:", len(keep))
for k in keep[:30]:
    try: print(os.path.getsize(k)//1024, "KB", k[:140])
    except OSError: print("?", k[:140])
