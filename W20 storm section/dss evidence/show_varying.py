import json, sys
for l in open(sys.argv[1], encoding="utf-8"):
    if l.startswith("VARYING "):
        j = json.loads(l[8:])
        print(j["file"]); print("series", j["series"], "records", j["n"]); print("extents", j["extents"])
