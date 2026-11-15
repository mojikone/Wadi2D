"""The tables of ``results/block2_study.json`` as Markdown, for the README. Usage: ``python block2_tables.py``."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PERIODS = ("2", "100", "200", "10000")
PERIOD_WORDS = {"2": "2 yr", "100": "100 yr", "200": "200 yr", "10000": "10,000 yr"}
DRY = "dry"


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def main() -> None:
    data = json.loads((HERE / "results" / "block2_study.json").read_text(encoding="utf-8"))
    points, parts = data["points"], []
    cunge, fixed, diff = data["muskingum_cunge"], data["muskingum_fixed"], data["difference_fixed"]
    own = data["hms_own_200yr"]
    alone = data["reaches_alone"]
    names = list(alone["200"])

    rows = []
    for point in points:
        c, m, d = cunge["200"][point], fixed["200"][point], diff["200"][point]
        hms = f"{own[point]['peak_m3s']:,.1f} at {own[point]['peak_h']:.2f}" if point in own else "not an analysis point"
        rows.append([
            point, hms, f"{c['peak_m3s']:,.1f} at {c['peak_h']:.2f}", f"{m['peak_m3s']:,.1f} at {m['peak_h']:.2f}",
            f"{d['peak_percent']:+.2f}", f"{d['time_min']:+.0f}",
        ])
    parts.append("### 200 yr, K and X at each reach's 200-yr peak\n\n" + table(
        ["Point", "HMS's own, m3/s at h", "Muskingum-Cunge here", "Muskingum", "Peak, %", "Time to peak, min"], rows))

    rows = []
    for point in points:
        row = [point]
        for period in PERIODS:
            d = diff[period][point]
            row.append(f"{cunge[period][point]['peak_m3s']:,.1f}")
            row.append(f"{d['peak_percent']:+.1f} % / {d['time_min']:+.0f} min")
        rows.append(row)
    header = ["Point"]
    for period in PERIODS:
        header += [f"{PERIOD_WORDS[period]} MC peak, m3/s", f"{PERIOD_WORDS[period]} Muskingum"]
    parts.append("### The same K and X at other floods: Muskingum less Muskingum-Cunge, peak and time to peak\n\n"
                 + table(header, rows))

    rows = []
    for name in names:
        p = data["proposals_at_peak"][name]
        peak = data["reach_peaks_200yr"][name]
        row = [name, f"{peak['inflow_peak_m3s']:,.0f}", f"{p['k_hours']:g}", f"{p['x']:g}", str(p["subreaches"]),
               f"{p['celerity_ms']:.2f}"]
        for period in PERIODS:
            r = alone[period][name]
            row.append(DRY if r is None else f"{r['inflow_peak_m3s']:,.0f}: {r['peak_percent']:+.1f} %, "
                       f"{r['muskingum_lag_min'] - r['cunge_lag_min']:+.0f} min")
        rows.append(row)
    parts.append(
        "### Reaches alone: each Muskingum reach on the Muskingum-Cunge run's own inflow\n\n"
        + table(["Reach", "200-yr peak in, m3/s", "K, h", "X", "Subreaches", "Wave speed, m/s",
                 "2 yr: peak in, m3/s: outflow peak, lag of the peak", "100 yr", "200 yr", "10,000 yr"], rows))

    rows = []
    for name in names:
        row = [name]
        for period in PERIODS:
            r = alone[period][name]
            row.append(DRY if r is None else f"{r['cunge_lag_min']:.0f} / {r['muskingum_lag_min']:.0f}")
            row.append(DRY if r is None else f"{r['cunge_out_over_in']:.4f} / {r['muskingum_out_over_in']:.4f}")
        rows.append(row)
    header = ["Reach"]
    for period in PERIODS:
        header += [f"{PERIOD_WORDS[period]} lag MC / M, min", f"{PERIOD_WORDS[period]} out/in MC / M"]
    parts.append("### Lag of the peak through each reach, and volume out over volume in (48 h window)\n\n"
                 + table(header, rows))

    limbs = data.get("limbs_200yr", {})
    if limbs:
        offsets = list(next(iter(limbs.values())))
        rows = [
            [name, *(f"{v[o]['cunge_m3s']:,.0f} / {v[o]['muskingum_m3s']:,.0f}" for o in offsets)]
            for name, v in limbs.items()
        ]
        parts.append(
            "### 200 yr, the two outflow hydrographs of a reach round the Muskingum-Cunge peak, MC / Muskingum, m3/s\n\n"
            + table(["Reach", *(f"{int(o):+d} min" for o in offsets)], rows))

    cases = list(data["sensitivity_200yr"])
    rows = []
    for point in points:
        row = [point, f"{diff['200'][point]['peak_percent']:+.2f} % / {diff['200'][point]['time_min']:+.0f}"]
        for case in cases:
            d = data["sensitivity_200yr"][case][point]
            row.append(f"{d['peak_percent']:+.2f} % / {d['time_min']:+.0f}")
        rows.append(row)
    parts.append("### 200 yr sensitivity: peak and time to peak against Muskingum-Cunge, % / min\n\n"
                 + table(["Point", "As proposed", *cases], rows))

    rows = []
    for name in names[:8]:
        at_peak, at_half, blind = (data[key][name] for key in ("proposals_at_peak", "proposals_at_half_peak", "proposals_by_kirpich"))
        lag = alone["200"][name]["cunge_lag_min"]
        rows.append([
            name, f"{lag:.0f}", f"{at_peak['k_hours'] * 60:.0f} / {at_peak['x']:g} / {at_peak['subreaches']}",
            f"{at_half['k_hours'] * 60:.0f} / {at_half['x']:g} / {at_half['subreaches']}",
            f"{blind['k_hours'] * 60:.0f} / {blind['x']:g} / {blind['subreaches']}",
        ])
    parts.append(
        "### K in minutes / X / subreaches of the hill reaches, by how they were derived\n\n"
        + table(["Reach", "Muskingum-Cunge lag of the 200-yr peak, min", "Cunge at the 200-yr peak",
                 "Cunge at half the peak", "Kirpich on the reach, X default"], rows))
    cost = data["microseconds_per_route_R1"]
    parts.append(f"One route of R1's 48 h series: Muskingum-Cunge {cost['muskingum_cunge']:.0f} microseconds, "
                 f"Muskingum {cost['muskingum']:.0f}.")

    proposals = data["proposals_at_peak"]
    negative = sorted(name for name, p in proposals.items() if p["x_cunge"] is not None and p["x_cunge"] < 0.0)
    lowered = sorted(name for name, p in proposals.items() if "lowered" in p["words"])
    index = sorted(name for name, p in proposals.items() if p["basis"] == "index celerity")
    lowest = min(v["lowest_outflow_m3s"] for period in fixed.values() for v in period.values())
    parts.append(
        f"Reaches proposed for: {len(proposals)}. Not stable at the step: {len(data['unstable'])} "
        f"({', '.join(data['unstable'])}). Cunge's X below zero, set to 0: {len(negative)} ({', '.join(negative)}). "
        f"X lowered for the step: {len(lowered)} ({', '.join(lowered)}). No flood at 200 yr, proposed at the index "
        f"celerity: {len(index)} ({', '.join(index)}). Lowest outflow of any element in any Muskingum run: "
        f"{lowest:.3g} m3/s. X cut on recounting the subreaches: K x 0.7 {len(data['x_cut_at_k_0.7'])}, "
        f"K x 1.3 {len(data['x_cut_at_k_1.3'])}. Run time of the whole study: {data['seconds']:.0f} s."
    )
    text = "\n\n".join(parts) + "\n"
    (HERE / "results" / "block2_study.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
