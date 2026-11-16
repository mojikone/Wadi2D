"""Where the dock's own way would put Hybrid Lumped's entries: W79 run 3 with its six hand-placed inflows taken out and
the lumped water kept on the network (hydrology.lumped_entry: network, W88). Read only; no grid, no solver."""

import json
import math
import sys

import rasterio

from wadi2d import run as R
from wadi2d.config.schema import RunConfig
from wadi2d.engine.network_entries import hms_icons, route_on_network

JOB = r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways\jobs\rerun2_run3_hybrid_aligned.json"

job = json.load(open(JOB, encoding="utf-8"))
hand = {i["element"]: (i["x"], i["y"]) for i in job["hydrology"]["inflows"]}
job["hydrology"]["inflows"] = []
job["hydrology"]["lumped_entry"] = "network"
cfg = RunConfig.model_validate(job)
with rasterio.open(cfg.terrain.dem) as dem:
    crs = dem.crs.to_wkt()
basin, hms_basin, _cut = R._lumped_basin(cfg, crs)
out = route_on_network(cfg, basin, hms_icons(hms_basin))
for inflow in out.hydrology.inflows:
    near = hand.get(inflow.element)
    gap = math.hypot(inflow.x - near[0], inflow.y - near[1]) if near else None
    print(inflow.name, "|", inflow.element, round(inflow.x, 2), round(inflow.y, 2), inflow.enters, "hand", near, "gap", gap)
carried = [s.name for s in out.hydrology.subbasins if s.mode == "lumped" and s.outlet is None]
print(len(carried), carried)
sys.exit(0)
