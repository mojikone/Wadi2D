"""The real depth-area studies: mode (c) and mode (b) at the five dam-site storm areas, run through `wadi2d arf`.

Mode (b): all 18 subbasins lumped, hydrographs at their outlets, reaches and plain in 2D. S13's outlet lies on the
Bidah axis by the accumulation rule, so it moves to the wadi above the dam, as in the first run.
"""
import json
import sys

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import ACC, OUT, SITES, job, write_job

AREAS = list(SITES.values())
tag = sys.argv[1] if len(sys.argv) > 1 else "050"
raster = str(OUT / "manning" / f"hills_{tag}.tif")
arf = {"areas_km2": AREAS, "accumulation": str(ACC), "accumulation_units": "cells"}
c = job(f"arf_c20_h{tag}", 20.0, area=None, duration_s=129600.0, manning_raster=raster, extra={"arf": arf})
write_job(c, f"arf_c20_h{tag}")
for n_tag, n in (("n040", 0.04), ("n100", 0.1)):
    b = job(f"arf_b20_{n_tag}", 20.0, area=None, mode="b", duration_s=129600.0, manning=n, extra={"arf": arf})
    for s in b["hydrology"]["subbasins"]:
        if s["name"] == "S13":
            s["outlet"] = [438130.0, 2726810.0]
    write_job(b, f"arf_b20_{n_tag}")
c10 = job(f"c10_A74_h{tag}", 10.0, area=74.304, duration_s=129600.0, manning_raster=raster)
write_job(c10, f"c10_A74_h{tag}")
print(json.dumps(AREAS))
