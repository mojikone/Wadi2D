"""Does the crest hold? PMP reruns with lines on the crest alone, either side of the spillway; closure of every dam run.

Closure: what crossed the axis against what left through the boundaries. Water that went round the dam shows as a
boundary outflow larger than the axis volume, plus rain-free cells below the dam filling.
"""
import json
import shapely
import sys

import numpy as np
from shapely.ops import substring

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import OUT, write_job
from dams import DAM_LIST, tied

index = json.loads((OUT / "dam_jobs.json").read_text(encoding="utf-8"))
names = []
for name, info in index.items():
    if info["tag"] != "PMP":
        continue
    dam = DAM_LIST[info["dam"]]
    j = json.loads((OUT / "jobs" / f"{name}.json").read_text(encoding="utf-8"))
    line = shapely.LineString(tied(dam)[0])
    a = line.project(shapely.Point(dam.spillway[0]))
    b = line.project(shapely.Point(dam.spillway[1]))
    lo, hi = min(a, b) - 2.5 * info["dx"], max(a, b) + 2.5 * info["dx"]
    j["outputs"]["lines"].append({"name": "crest_before", "coordinates": [tuple(c) for c in substring(line, 0.0, lo).coords]})
    j["outputs"]["lines"].append({"name": "crest_after", "coordinates": [tuple(c) for c in substring(line, hi, line.length).coords]})
    write_job(j, f"{name}_split")
    names.append(f"{name}_split")
print(" ".join(names))
