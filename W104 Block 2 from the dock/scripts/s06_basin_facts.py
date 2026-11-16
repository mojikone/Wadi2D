"""What a generated basin of W104 holds above each dam, against W79's HMS Basin 3 (his file, read only): subbasins,
their lags, the reaches' Manning n and lengths. Usage: ``s06_basin_facts.py <basin.json> [out.json]``.

Basin 3's figures (W79 README and his HMS project): S1 to S18 above the five dams, 18 subbasins; reach n 0.1 (W1).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DAMS = ("Bidah 03", "Faydh 01", "R5A", "R2A", "Z4C")


def value(e, key):
    p = e["parameters"].get(key)
    return p.get("value") if isinstance(p, dict) else p


def main() -> None:
    path = Path(sys.argv[1])
    m = json.loads(path.read_text(encoding="utf-8"))
    els = {e["name"]: e for e in m["elements"]}

    def below(name):
        out, n = [], els[name]["downstream"]
        while n is not None:
            out.append(n)
            n = els[n]["downstream"]
        return out

    facts = {"analysis": m.get("analysis"), "counts": {}}
    for e in m["elements"]:
        facts["counts"][e["kind"]] = facts["counts"].get(e["kind"], 0) + 1
    for dam in [d for d in DAMS if d in els] + [n for n in els if "HAT" in n or "outfall" in n.lower()]:
        subs = [e for e in m["elements"] if e["kind"] == "subbasin" and dam in below(e["name"])]
        reaches = [e for e in m["elements"] if e["kind"] == "reach" and dam in below(e["name"])]
        lags = sorted(value(e, "lag_minutes") or 0 for e in subs)
        facts[dam] = {
            "kind": els[dam]["kind"],
            "drainage_area_km2": value(els[dam], "drainage_area_km2"),
            "subbasins": len(subs),
            "subbasin_km2_mean": round(sum(value(e, "area_km2") or 0 for e in subs) / max(len(subs), 1), 2),
            "lag_min_range": [round(lags[0], 1), round(lags[-1], 1)] if lags else None,
            "reaches": len(reaches),
            "reach_length_km": round(sum(value(e, "length_m") or 0 for e in reaches) / 1000.0, 1),
            "reach_manning_n": sorted({round(value(e, "manning_n") or 0, 3) for e in reaches}),
        }
    text = json.dumps(facts, indent=1)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
