"""Settings of b, c and the triangles with the polygon form of the section test."""
import sys
sys.path.insert(0, ".")
from concurrent.futures import ProcessPoolExecutor
from options import run
V = {
 "b s2": ("b", dict(sheet=2)), "b s3": ("b", dict(sheet=3)), "b s3 sm8": ("b", dict(sheet=3, smooth=8)),
 "c s2": ("c", dict(sheet=2)), "c s3": ("c", dict(sheet=3)), "c s1 nosk": ("c", dict(sheet=1, skew=False)), "c s3 nosk": ("c", dict(sheet=3, skew=False)),
 "P s3": ("P", dict(sheet=3)),
 "t20 s1": ("tri", dict(sheet=1, h=20.)), "t20 s3": ("tri", dict(sheet=3, h=20.)), "t26 s3": ("tri", dict(sheet=3, h=26.3)),
}
CASES = [(45.,3,0.,0.),(45.,3,0.,5.),(45.,3,0.,10.),(45.,3,2.,5.),(30.,3,0.,0.),(30.,3,2.,0.),(22.5,3,0.,0.),(15.,3,0.,0.),(0.,3,0.,0.)]
def job(a):
    n, c = a
    opt, kw = V[n]
    return n, c, run(opt, *c, **dict(kw))
if __name__ == "__main__":
    jobs = [(n, c) for n in V for c in CASES]
    out = {}
    with ProcessPoolExecutor(11) as ex:
        for n, c, r in ex.map(job, jobs):
            out[(n, c)] = r
    print(f"{'':11s}", " ".join(f"{c[0]:>5.1f}/{int(c[2])}/{int(c[3]):<2d}" for c in CASES))
    for title, key, f in (("strip %", "err_strip", "+9.2f"), ("Manning %", "err", "+9.2f"), ("dt", "dt", "9.3f"), ("Q %", "qerr", "+9.2f")):
        print(title)
        for n in V:
            print(f"{n:11s}", " ".join(format(out[(n, c)][key], f) for c in CASES))
    r = out[("t20 s3", CASES[1])]
    print({k: r.get(k) for k in ("nelem","nfaces","clipped_dn","neg_dn","steiner","unresolved","skew_max","area_min","dn_min")})
    r = out[("t26 s3", CASES[1])]
    print({k: r.get(k) for k in ("nelem","nfaces","clipped_dn","neg_dn","steiner","unresolved","skew_max","area_min","dn_min")})
