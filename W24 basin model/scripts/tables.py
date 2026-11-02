"""`results/validation.json` as the Markdown tables of the README, printed."""

from __future__ import annotations

import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results" / "validation.json"
DAMS = ("Faydh 01", "Bidah 03", "R5A", "R2A", "Z4C")


def row(*cells: object) -> str:
    return "| " + " | ".join(str(cell) for cell in cells) + " |"


def percent(value: float, reference: float) -> str:
    return f"{100.0 * (value / reference - 1.0):+.1f}"


def main() -> None:
    out = json.loads(RESULTS.read_text(encoding="utf-8"))
    user = out["as_a_user_would"]
    first = user["10.0"]
    print("### Areas\n")
    print(
        row(
            "Site",
            "HMS km2",
            "Generated km2",
            "%",
            "Aligned km2",
            "%",
            "Design line: nodes, sum km2",
            "Across the line km2",
            "%",
        )
    )
    print(row(*["---"] * 9))
    for dam in DAMS:
        hms = first["areas"][dam]["hms"]
        made = first["areas"][dam]["generated"]
        aligned = out["aligned"]["areas"][dam]["generated"]
        line = out["design_lines"][dam]
        print(
            row(
                dam, f"{hms:.2f}", f"{made:.2f}", percent(made, hms), f"{aligned:.2f}", percent(aligned, hms),
                f"{line['nodes']}, {line['sum_km2']:.2f}", f"{line['line_km2']:.2f}", percent(line["line_km2"], hms),
            )
        )  # fmt: skip
    print("\n### Peaks at 100 yr by threshold\n")
    head = ["Threshold km2", "Subbasins", "Reaches", *(f"{d} ratio, time h" for d in DAMS)]
    print(row(*head))
    print(row(*["---"] * len(head)))
    hms_cells = [
        f"{first['peaks'][d]['hms']:.0f} m3/s at {first['peaks'][d]['hms_time_h']:.2f}" for d in DAMS
    ]
    print(row("HMS", 18, 8, *hms_cells))
    for threshold, run in user.items():
        cells = [f"{run['peaks'][d]['ratio']:.2f}, {run['peaks'][d]['time_h']:.2f}" for d in DAMS]
        print(row(threshold, run["subbasins"], run["reaches"], *cells))
    print("\n### Attribution, aligned model, peak ratio to HMS\n")
    print(row("Taken from HMS", *DAMS))
    print(row(*["---"] * 6))
    for case, peaks in out["aligned"]["attribution"].items():
        print(row(case, *(f"{peaks[d]['ratio']:.2f}" for d in DAMS)))
    print("\n### Subbasins\n")
    head = ["HMS", "Twin", "Shared", "IoU", "Area HMS", "Area", "CN HMS", "CN", "Lag HMS", "Lag"]
    head += ["L HMS", "L", "Path S HMS", "Path S", "10-85 HMS", "10-85", "Land S HMS", "Land S"]
    print(row(*head))
    print(row(*["---"] * len(head)))
    for item in out["aligned"]["subbasins"]:
        print(
            row(
                item["name"], item["twin"], item["shared"], item["iou"], f"{item['area_hms']:.2f}",
                f"{item['area']:.2f}", item["cn_hms"], item["cn"], item["lag_hms"], item["lag"],
                item["length_hms"], item["length"], item["path_slope_hms"], item["path_slope"],
                item["slope_10_85_hms"], item["slope_10_85"], item["land_slope_hms"], item["land_slope"],
            )
        )  # fmt: skip
    rows = out["aligned"]["subbasins"]
    ratios = sorted(item["lag"] / item["lag_hms"] for item in rows)
    print(f"\nlag ratio {ratios[0]:.2f} to {ratios[-1]:.2f}, median {ratios[len(ratios) // 2]:.2f}")
    print("\n### Reaches\n")
    head = ["HMS", "Twins", "L HMS", "L", "%", "S HMS", "S", "%", "b HMS", "b", "z HMS", "z"]
    print(row(*head))
    print(row(*["---"] * len(head)))
    for item in out["aligned"]["reaches"]:
        length = item["length"] or float("nan")
        slope = item["slope"] or float("nan")
        print(
            row(
                item["name"], " ".join(item["twins"]), item["length_hms"], item["length"],
                percent(length, item["length_hms"]), item["slope_hms"], item["slope"],
                percent(slope, item["slope_hms"]), item["width_hms"], item["width"], item["side_hms"], item["side"],
            )
        )  # fmt: skip
    print("\nHMS lag over Kirpich", out["hms_lag_over_kirpich"])
    print("\nnotes", out["aligned"]["notes"], "elements", out["aligned"]["elements"])
    print("unassigned", first["unassigned_km2"])


if __name__ == "__main__":
    main()
