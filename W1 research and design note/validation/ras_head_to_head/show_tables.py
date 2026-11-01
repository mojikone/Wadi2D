import json,sys
for fn in sys.argv[1:]:
    d=json.load(open(fn)); print("=====",fn,d["ras"],d["dx"],d["cells"],"faces",d["faces_compared"])
    for k,v in d.items():
        if isinstance(v,dict) and "n" in v:
            print(f"{k:50s} n={v['n']:8d} mean={v['mean']:8.3f} rms={v['rms']:8.3f} p5={v['p5']:8.3f} p50={v['p50']:8.3f} p95={v['p95']:8.3f} p99={v['p99']:8.3f}")
    for n,x in d["face_invert_rule"].items(): print("  rule",n,{a:round(b,2) for a,b in x.items()})
    for k,v in d["K_wadi_over_K_ras_by_mean_face_depth"].items(): print("  K",k,{a:round(b,3) for a,b in v.items() if a in("n","p5","p50","p95")})
