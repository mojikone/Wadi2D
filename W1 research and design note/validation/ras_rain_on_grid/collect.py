"""The per-run tables of the report, printed from the results files, so no figure is copied by hand.

usage: collect.py [names...]
"""

from __future__ import annotations

import json
import sys

import numpy as np

import case

NAMES = sys.argv[1:] or list(case.CONFIGS)


def load(name: str) -> dict | None:
    p = case.HERE / f"results_{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def wall() -> dict:
    out: dict = {"ras": {}, "wadi": {}}
    if (case.HERE / "ras_timing.csv").exists():
        for line in (case.HERE / "ras_timing.csv").read_text().splitlines():
            f = line.split(",")
            out["ras"][f[0].removeprefix("ras_")] = float(f[5])
    if (case.HERE / "wadi_timing.csv").exists():
        for line in (case.HERE / "wadi_timing.csv").read_text().splitlines():
            f = line.split(",")
            out["wadi"][f[0]] = (float(f[2]), float(f[3]), float(f[5]))
    return out


def table(rows: list[list[str]]) -> None:
    print("| " + " | ".join(rows[0]) + " |")
    print("|" + "---|" * len(rows[0]))
    for r in rows[1:]:
        print("| " + " | ".join(r) + " |")
    print()


def main() -> None:
    res = {n: load(n) for n in NAMES}
    res = {k: v for k, v in res.items() if v}
    t = wall()
    names = list(res)
    head = ["", *names]
    hs = next(iter(res.values()))["hms_equiv"]
    print(f"HMS-equivalent: peak {hs['peak']:.1f}, t {hs['t_peak_h']:.2f} h, volume {hs['volume_m3'] / 1e6:.3f} Mm3\n")
    for key in ("axis", "s13_edge"):
        print(f"### Section {key}\n")
        rows = [head]
        for label, f in (
            ("Peak RAS, m3/s", lambda r: f"{r['sections'][key]['ras']['peak']:.1f}"),
            ("Peak Wadi2D, m3/s", lambda r: f"{r['sections'][key]['wadi']['peak']:.1f}"),
            ("**Wadi2D / RAS**", lambda r: f"**{r['sections'][key]['peak_ratio_wadi_over_ras']:.3f}**"),
            ("RAS / HMS-equivalent", lambda r: f"{r['ratios_to_hms'][key]['ras']:.3f}"),
            ("Wadi2D / HMS-equivalent", lambda r: f"{r['ratios_to_hms'][key]['wadi']:.3f}"),
            ("Time of peak RAS, h", lambda r: f"{r['sections'][key]['ras']['t_peak_h']:.2f}"),
            ("Time of peak Wadi2D, h", lambda r: f"{r['sections'][key]['wadi']['t_peak_h']:.2f}"),
            ("Half-rise RAS, h", lambda r: f"{r['sections'][key]['ras']['t_half_rise_h']:.2f}"),
            ("Half-rise Wadi2D, h", lambda r: f"{r['sections'][key]['wadi']['t_half_rise_h']:.2f}"),
            ("Volume RAS, Mm3", lambda r: f"{r['sections'][key]['ras']['volume_m3'] / 1e6:.3f}"),
            ("Volume Wadi2D, Mm3", lambda r: f"{r['sections'][key]['wadi']['volume_m3'] / 1e6:.3f}"),
            ("NSE, RAS as reference", lambda r: f"{r['sections'][key]['nse_ras_as_obs']:.3f}"),
            ("Equivalent lag RAS, min (HMS area)", lambda r: f"{r['sections'][key]['lag_ras_hms_area']['lag_min']:.0f}"),
            ("Equivalent lag Wadi2D, min (HMS area)", lambda r: f"{r['sections'][key]['lag_wadi_hms_area']['lag_min']:.0f}"),
            ("Equivalent lag RAS, min (own area)", lambda r: f"{r['sections'][key]['lag_ras_own_area']['lag_min']:.0f}"),
            ("Equivalent lag Wadi2D, min (own area)", lambda r: f"{r['sections'][key]['lag_wadi_own_area']['lag_min']:.0f}"),
            ("Best-lag fit peak RAS / Wadi2D, m3/s", lambda r: f"{r['sections'][key]['lag_ras_hms_area']['fit_peak']:.0f} / {r['sections'][key]['lag_wadi_hms_area']['fit_peak']:.0f}"),
        ):
            rows.append([label, *[f(res[n]) for n in names]])
        table(rows)
    print("### Levels and extent\n")
    rows = [head]
    cc = lambda r: r["cell_classes"]  # noqa: E731
    for label, f in (
        ("Wadi, >= 0.5 m both, level W-R: mean (rms), cm", lambda r: f"{100 * cc(r)['wadi_deep_both_0.5']['level']['mean']:+.1f} ({100 * cc(r)['wadi_deep_both_0.5']['level']['rms']:.1f})"),
        ("Same, p5 to p95, cm", lambda r: f"{100 * cc(r)['wadi_deep_both_0.5']['level']['p5']:+.0f} to {100 * cc(r)['wadi_deep_both_0.5']['level']['p95']:+.0f}"),
        ("Same, cells", lambda r: f"{cc(r)['wadi_deep_both_0.5']['level']['n']}"),
        ("Gorge wadi part: mean (rms), cm", lambda r: f"{100 * cc(r)['gorge_wadi_deep_both_0.5']['level']['mean']:+.1f} ({100 * cc(r)['gorge_wadi_deep_both_0.5']['level']['rms']:.1f})"),
        ("Fan wadi part: mean (rms), cm", lambda r: f"{100 * cc(r)['fan_wadi_deep_both_0.5']['level']['mean']:+.1f} ({100 * cc(r)['fan_wadi_deep_both_0.5']['level']['rms']:.1f})"),
        ("Hillslope, shallow both, level W-R: mean (rms), cm", lambda r: f"{100 * cc(r)['hill_shallow_both_under_0.5']['level']['mean']:+.1f} ({100 * cc(r)['hill_shallow_both_under_0.5']['level']['rms']:.1f})"),
        ("Same, cells", lambda r: f"{cc(r)['hill_shallow_both_under_0.5']['level']['n']}"),
        ("All hillslope, level W-R: mean (rms), cm", lambda r: f"{100 * cc(r)['hill_all']['level']['mean']:+.1f} ({100 * cc(r)['hill_all']['level']['rms']:.1f})"),
        ("Hillslope max mean depth RAS / Wadi2D, cm", lambda r: f"{100 * cc(r)['hill_all']['ras_mean_depth_mean']:.2f} / {100 * cc(r)['hill_all']['wadi_mean_depth_mean']:.2f}"),
        ("F, cells >= 0.3 m", lambda r: f"{r['extent']['cell_depth>=0.3']['F']:.3f}"),
        ("F, cells >= 1.0 m", lambda r: f"{r['extent']['cell_depth>=1.0']['F']:.3f}"),
        ("F, 0.5 m pixels >= 0.1 m", lambda r: f"{r['extent']['pixel_depth>=0.1']['F']:.3f}"),
        ("F, 0.5 m pixels >= 0.3 m", lambda r: f"{r['extent']['pixel_depth>=0.3']['F']:.3f}"),
        ("F, fan only, 0.5 m pixels >= 0.1 m", lambda r: f"{r['extent']['fan_pixel_depth>=0.1']['F']:.3f}"),
        ("F, fan only, 0.5 m pixels >= 0.3 m", lambda r: f"{r['extent']['fan_pixel_depth>=0.3']['F']:.3f}"),
        ("Pixel area >= 0.3 m, RAS / Wadi2D, km2", lambda r: f"{r['extent']['pixel_depth>=0.3']['ras_km2']:.2f} / {r['extent']['pixel_depth>=0.3']['wadi_km2']:.2f}"),
        ("Stored at the end RAS / Wadi2D, m3", lambda r: f"{r['stored_at_end_m3']['ras']:.0f} / {r['stored_at_end_m3']['wadi']:.0f}"),
    ):
        rows.append([label, *[f(res[n]) for n in names]])
    table(rows)
    print("### Hillslope by relief inside the cell\n")
    rows = [["Relief, m", *names]]
    for lo, hi in ((0, 2), (2, 5), (5, 10), (10, 1000)):
        key = f"hill_relief_{lo}_{hi}m"
        rows.append([f"{lo} to {hi}, mean depth R / W, cm; level W-R, cm", *[
            f"{100 * cc(res[n])[key]['ras_mean_depth']:.2f} / {100 * cc(res[n])[key]['wadi_mean_depth']:.2f}; {100 * cc(res[n])[key]['level_mean']:+.0f}" for n in names]])
    table(rows)
    print("### Forcing, mass, edges, wall time\n")
    rows = [head]
    for label, f in (
        ("Rain RAS, m3", lambda r: f"{r['rain']['ras_m3']:.0f}"),
        ("Rain Wadi2D, m3", lambda r: f"{r['rain']['wadi_m3']:.0f}"),
        ("Wadi2D / RAS", lambda r: f"{r['rain']['wadi_over_ras']:.6f}"),
        ("RAS volume error, %", lambda r: f"{r['ras_volume']['Error Percent']:.4f}"),
        ("Wadi2D balance error", lambda r: f"{r['wadi_attrs']['relative_error']:.1e}"),
        ("Closed edge, deepest over low point, R / W, m", lambda r: f"{r['closed_edges']['ras']['deepest_m']:.2f} / {r['closed_edges']['wadi']['deepest_m']:.2f}"),
        ("Closed edge, largest max mean depth, R / W, m", lambda r: f"{r['closed_edges']['ras']['max_mean_depth_m']:.2f} / {r['closed_edges']['wadi']['max_mean_depth_m']:.2f}"),
        ("Closed edge, cells of mean depth > 0.5 m, R / W", lambda r: f"{r['closed_edges']['ras']['mean_depth_over_0.5m_cells']} / {r['closed_edges']['wadi']['mean_depth_over_0.5m_cells']}"),
        ("Closed edge cells, of all edge cells", lambda r: f"{r['closed_edges']['ras']['cells']}"),
        ("Closed edge, volume at max, R / W, m3", lambda r: f"{r['closed_edges']['ras']['volume_at_max_m3']:.0f} / {r['closed_edges']['wadi']['volume_at_max_m3']:.0f}"),
    ):
        rows.append([label, *[f(res[n]) for n in names]])
    rows.append(["RAS wall, s", *[f"{t['ras'].get(n, float('nan')):.0f}" for n in names]])
    rows.append(["Wadi2D wall, s", *[f"{t['wadi'].get(n, (np.nan,))[-3 if False else 0]:.1f}" for n in names]])
    rows.append(["Wadi2D steps", *[f"{t['wadi'].get(n, (0, 0, 0))[2]:.0f}" for n in names]])
    table(rows)


if __name__ == "__main__":
    main()
