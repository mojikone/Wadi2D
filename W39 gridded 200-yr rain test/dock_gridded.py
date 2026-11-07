"""W39 through the real dock on Bidah 03 at 30 m: the owner's RP200 rain grids, NetCDF and DSS, in full 2D and in the
hybrid on a basin generated from the DEM; then the HMS project's PMP storm through the dock's HMS route.

The rules were fixed before the runs and are the constants below. The file's own depth over the domain is computed
outside the engine first (rain_volume.py), and the same for every subbasin once the basin exists.
Runs 1g, 2g and 6g are twins without losses: the engine books rain after losses, so only a run without losses shows the
gross rain the rule is about.
"""

import csv
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

DX = 30.0
HOURS = 30.0
THRESHOLD_KM2 = 2.0
LINE = "Bidah 03"
GRID = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Grid")
FILES = {
    "nc": GRID / "netCDF" / "Precipitation_RP200_10min.nc",
    "dss": GRID / "DSS" / "Precipitation_RP200_10min.dss",
}
PMP_MET = "FM_PMP.met"
PMP_RASTER = "Clip_PMP_823mm_21c_27032024.tif"
S13_CN, S13_IA_MM, S13_KM2 = 87.6, 7.2, 20.971
SAME_VOLUME = 1e-3
"""DSS against NetCDF: the water the rain put on the domain, each mode."""
SAME_PEAK = 5e-3
"""DSS against NetCDF: the Bidah 03 peak, each mode."""
MASS = 1e-6
"""Relative mass error of every run."""
VOLUME = 1e-2
"""A run's gross rain against the file's own depth over the domain, area-weighted."""
POLYGON = 1e-2
"""A lumped subbasin's runoff volume against the SCS excess of its own polygon mean."""
RUN_LIMIT = 3000
HERE = Path(__file__).resolve().parent
VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")
CN100 = """
import sys, json, numpy as np, rasterio
from rasterio.transform import from_origin
west, south, east, north = [float(v) for v in sys.argv[2:6]]
w, hgt = int((east - west) / 100) + 1, int((north - south) / 100) + 1
with rasterio.open(sys.argv[1], "w", driver="GTiff", height=hgt, width=w, count=1, dtype="float32", crs="EPSG:32640",
                   transform=from_origin(west, north, 100.0, 100.0)) as d:
    d.write(np.full((hgt, w), 100.0, np.float32), 1)
print(json.dumps({"ok": True}))
"""


def venv(h, *args):
    """The engine's python, on this checkout: QGIS must not load a second HDF5 library."""
    import sys

    if str(h.REPO / "plugin") not in sys.path:
        sys.path.insert(0, str(h.REPO / "plugin"))
    from wadi2d_qgis.protocol import clean_env

    env = clean_env(dict(os.environ))
    env["PYTHONPATH"] = str(h.REPO)
    done = subprocess.run([str(h.VENV), *[str(a) for a in args]], capture_output=True, text=True, env=env)
    if done.returncode:
        raise RuntimeError(done.stderr[-3000:])
    return json.loads(next(s for s in reversed(done.stdout.splitlines()) if s.startswith("{")))


def table(path):
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0], np.array([[float(v) for v in r] for r in rows[1:]])


def hydrograph(path, column):
    head, data = table(path)
    t, q = data[:, 0], data[:, head.index(column)]
    k = int(np.argmax(np.abs(q)))
    volume = float(np.sum(0.5 * (q[1:] + q[:-1]) * np.diff(t)))
    return {
        "peak_m3s": float(abs(q[k])),
        "peak_h": float(t[k] / 3600.0),
        "volume_m3": volume,
        "end_m3s": float(q[-1]),
    }


def scs_excess(p_mm, cn, ia_mm=None):
    s = (1000.0 / cn - 10.0) * 25.4
    ia = 0.2 * s if ia_mm is None else ia_mm
    return 0.0 if p_mm <= ia else (p_mm - ia) ** 2 / (p_mm - ia + s)


def safe(name):
    """A name as the series files spell it."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "unnamed"


def choose(storm, kind):
    storm.kind.setCurrentIndex(storm.kind.findData(kind))


def value(element, key):
    return element["parameters"][key]["value"]


def ratio(a, b):
    return a / b - 1.0 if b else float("inf")


def scenario(h):
    h.TOTAL_LIMIT = 14400.0
    h.STEP_LIMIT = 3600.0
    if not h.VENV.is_file():  # a worktree has no venv of its own; the project's runs this checkout's code
        h.VENV = VENV
    ground = h.Bidah()
    record = {"runs": {}}
    keep = h.P / "keep"
    keep.mkdir(exist_ok=True)

    h.log("=== 0 the files' own rain, outside the engine, before any run")
    before = h.P / "rain_before.json"
    venv(h, HERE / "rain_volume.py", before)
    rain = json.loads(before.read_text(encoding="utf-8"))
    record["rain_before"] = rain
    for key in ("nc", "dss"):
        d = rain[key]["domain"]
        h.log(
            f"{key}: {rain[key]['frames']} frames, {d['mean_mm']:.3f} mm over the domain, {d['volume_m3']:.0f} m3"
        )
    h.log(f"DSS row order: {rain['dss_order_used']} {rain['dss_orientation']}")
    h.log(
        f"PMP {rain['pmp']['file']}: {rain['pmp']['domain']['mean_mm']:.2f} mm over the domain; ARF at 300 km2 {rain['tables']['arf_at_300']:.4f}"
    )
    h.check(
        "the DSS row order is settled by the NetCDF",
        rain["dss_orientation"][rain["dss_order_used"]]["correlation"] > 0.999,
        rain["dss_orientation"],
    )

    lines = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))["outputs"][
        "lines"
    ]
    coordinates = next(k["coordinates"] for k in lines if k["name"] == LINE)
    line = h.add_vector(
        h.geojson("bidah_line", [h.line(coordinates, name=LINE)]), "Bidah 03 line", ground.crs
    )
    cn = h.add_raster(h.BLOCK / "HEC_HMS_Block_02" / "Hydrology Data" / "CN_Include_Hill_Area.tif", "cn")
    box_ = ground.domain.extent()
    cn100_path = h.DATA / "cn100.tif"
    venv(
        h,
        "-c",
        CN100,
        cn100_path,
        box_.xMinimum() - 1000,
        box_.yMinimum() - 1000,
        box_.xMaximum() + 1000,
        box_.yMaximum() + 1000,
    )
    cn100 = h.add_raster(cn100_path, "cn 100")
    dock = yield from h.open_dock()
    hy, storm, box = dock.hydrology, dock.storm, dock.hydrology.basin

    def setup(folder):
        h.set_rain_job(dock, ground, folder, dx=DX, rain=10.0, hours=1.0, sim_hours=HOURS, pixels=False)
        dock.points.layer.setLayer(line)
        dock.points.name.setField("name")

    def grid_file(key):
        choose(storm, "gridded")
        storm.is_folder.setCurrentIndex(0)
        storm.rain_file.setFilePath(str(FILES[key]))
        yield lambda: storm.rain_label.text() and "Reading" not in storm.rain_label.text()
        text = storm.rain_label.text()
        h.log(f"rain label {key}: {text}")
        h.check(f"{key}: the dock reads 144 frames of 10 min", text.startswith("144 frames of 10 min"), text)
        h.widget_shot(f"storm_{key}", storm)

    def run_one(name, mode, rain_key, losses):
        dock.panel.folder.setFilePath(str(h.RUNS / name))
        yield from h.run(dock, RUN_LIMIT)
        out = h.RUNS / name
        done = h.events(out, "done")
        ok = bool(done) and done[-1].get("code") == 0
        h.check(f"{name}: the run finished", ok, dock.panel.message.text()[:300])
        entry = {"mode": mode, "rain": rain_key, "losses": losses, "finished": ok}
        if ok:
            b = done[-1]["balance"]
            entry["balance"] = b
            entry["line"] = hydrograph(out / "series" / "line_Bidah_03.csv", "discharge_m3s")
            entry["warnings"] = [e["message"] for e in h.events(out, "warn")]
            nets = sorted((out / "series").glob("network_*.csv"))
            entry["network"] = {p.stem[8:]: hydrograph(p, "outflow_m3s") for p in nets}
            job = json.loads((out / "job.json").read_text(encoding="utf-8"))
            entry["job_storm"] = job.get("storm")
            entry["duration_h"] = (
                json.loads((out / "config.resolved.json").read_text(encoding="utf-8"))["run"]["duration_s"]
                / 3600.0
            )
            h.check(
                f"{name}: mass error under {MASS:g}", abs(b["relative_error"]) < MASS, b["relative_error"]
            )
            h.log(
                f"{name}: line {entry['line']}, rain {b['rain_m3']:.0f}, inflow {b['inflow_m3']:.0f}, error {b['relative_error']:.2e}"
            )
            for w in entry["warnings"]:
                h.log(f"  warn: {w[:300]}")
            target = keep / name
            target.mkdir(exist_ok=True)
            for f in [out / "job.json", out / "series" / "line_Bidah_03.csv", *nets]:
                shutil.copy2(f, target / f.name)
            (target / "done.json").write_text(json.dumps(done[-1], indent=2), encoding="utf-8")
            depth = h.add_raster(out / "maps" / "max_depth.tif", f"{name} max depth")
            h.render(name, [line, depth, ground.dem], ground.domain.extent().center(), 40000)
        record["runs"][name] = entry
        (h.P / "w39_summary.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        return entry

    h.log("=== 1, 2 full 2D, rain-on-grid everywhere with the project CN grid")
    setup("full_nc")
    hy.cn.raster.setLayer(cn)
    for key in ("nc", "dss"):
        yield from grid_file(key)
        yield from run_one(f"full_{key}", "full 2D", key, "CN grid")
    runs = record["runs"]
    if runs["full_nc"].get("finished"):
        job = runs["full_nc"]["job_storm"]
        h.check(
            "the job carries the file as gridded rain, no area reduction",
            job["kind"] == "gridded" and not job.get("arf") and not job.get("storm_area_km2"),
            job,
        )

    h.log("=== 1g, 2g full 2D without losses: the gross rain")
    hy.cn.raster.setLayer(None)
    hy.cn.box.setValue(hy.cn.box.minimum())
    for key in ("nc", "dss"):
        yield from grid_file(key)
        yield from run_one(f"gross_{key}", "full 2D", key, "none")
    cells = h.RUNS / "gross_nc" / "results.h5"

    h.log("=== 3, 4 hybrid: the basin generated from the DEM, every subbasin lumped")
    hy.cn.raster.setLayer(cn)
    yield from grid_file("nc")
    dock.panel.folder.setFilePath(str(h.RUNS / "hybrid_nc"))
    box.setChecked(True)
    box.threshold.setValue(THRESHOLD_KM2)
    box.generate_button.click()
    yield lambda: box.generate_button.isEnabled()
    h.log(f"basin: {box.summary.text()}")
    h.check("a basin was generated", box.model is not None, box.summary.text())
    model = box.model
    subs = [e for e in model["elements"] if e["kind"] == "subbasin"]
    modes = {
        hy.table.item(r, 0).text(): hy.table.cellWidget(r, 1).currentText()
        for r in range(hy.table.rowCount())
    }
    h.check(
        "every subbasin lumped by default",
        set(modes.values()) == {"lumped"} and len(modes) == len(subs),
        modes,
    )
    h.check(
        f"the design line {LINE} is a junction of the basin",
        any(e["name"] == LINE for e in model["elements"]),
        [e["name"] for e in model["elements"] if e["kind"] != "subbasin"],
    )
    record["basin"] = {
        "summary": box.summary.text(), "lag_method": box.lag.currentData(),
        "elements": [{k: e.get(k) for k in ("name", "kind", "downstream", "missing")} | {"parameters": {p: v.get("value") for p, v in e.get("parameters", {}).items()}} for e in model["elements"]],
        "routes": model.get("routes"),
    }  # fmt: skip
    group = h.group_of("Wadi2D basin")
    layers = [n.layer() for n in group.findLayers()] if group else []
    h.render("basin", [*layers, line, ground.dem], ground.domain.extent().center(), 40000, size=(1200, 1000))
    h.widget_shot("hydrology_generated", hy)
    gpkg = h.RUNS / "hybrid_nc" / "wadi2d_basin" / "basin.gpkg"
    after = h.P / "rain_after.json"
    venv(h, HERE / "rain_volume.py", after, "--cells", cells, "--basin", gpkg)
    record["rain_after"] = json.loads(after.read_text(encoding="utf-8"))
    for key in ("nc", "dss"):
        if key == "dss":
            yield from grid_file(key)
        yield from run_one(f"hybrid_{key}", "hybrid", key, "CN grid")

    h.log("=== 5, 6, 6g the HMS project's PMP storm through the HMS route")
    box.setChecked(False)
    hy.folder.setFilePath(str(h.BLOCK / "HEC_HMS_Block_02"))
    yield lambda: hy.files["basin"].count() > 0
    h.check(f"{PMP_MET} is offered", hy.files["met"].findText(PMP_MET) >= 0)
    hy.files["met"].setCurrentText(PMP_MET)
    choose(storm, "hms")
    h.check("the storm is the HMS project's", storm.kind.currentData() == "hms", storm.kind.currentText())
    h.widget_shot("storm_hms", storm)

    def set_modes(lumped):
        for r in range(hy.table.rowCount()):
            hy.table.cellWidget(r, 1).setCurrentText(
                "lumped" if hy.table.item(r, 0).text() in lumped else "2d"
            )

    hy.cn.raster.setLayer(cn)
    set_modes({"S13"})
    h.widget_shot("hydrology_hms", hy)
    yield from run_one("pmp_hybrid", "hybrid (HMS S13 lumped)", "pmp", "CN grid, S13 its HMS CN")
    set_modes(set())
    yield from run_one("pmp_full", "full 2D", "pmp", "CN grid")
    hy.cn.raster.setLayer(cn100)
    yield from run_one("pmp_gross", "full 2D", "pmp", "none (CN 100 raster)")
    hy.cn.raster.setLayer(cn)

    rules(h, record)
    (h.P / "w39_summary.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def rules(h, record):
    """The rules fixed before the runs, and the figures reported without a pass mark."""
    h.log("=== rules")
    runs, rain = record["runs"], record.get("rain_after", record["rain_before"])
    found = record["rules"] = {}
    for mode, nc, dss, water in (
        ("full 2D", "full_nc", "full_dss", ("rain_m3",)),
        ("full 2D without losses", "gross_nc", "gross_dss", ("rain_m3",)),
        ("hybrid", "hybrid_nc", "hybrid_dss", ("rain_m3", "inflow_m3")),
    ):
        if not (runs.get(nc, {}).get("finished") and runs.get(dss, {}).get("finished")):
            h.check(f"{mode}: both runs finished", False)
            continue
        a = sum(runs[nc]["balance"][k] for k in water)
        b = sum(runs[dss]["balance"][k] for k in water)
        files = ratio(rain["dss"]["domain"]["volume_m3"], rain["nc"]["domain"]["volume_m3"])
        found[f"{mode} volume"] = {
            "nc_m3": a,
            "dss_m3": b,
            "dss_over_nc": ratio(b, a),
            "files_dss_over_nc": files,
        }
        h.check(
            f"{mode}: DSS and NetCDF water within {SAME_VOLUME:.1%}",
            abs(ratio(b, a)) < SAME_VOLUME,
            f"{ratio(b, a):+.4%}; the files alone {files:+.4%}",
        )
        if mode != "full 2D without losses":
            p, q = runs[nc]["line"]["peak_m3s"], runs[dss]["line"]["peak_m3s"]
            found[f"{mode} peak"] = {"nc": p, "dss": q, "dss_over_nc": ratio(q, p)}
            h.check(
                f"{mode}: DSS and NetCDF Bidah 03 peak within {SAME_PEAK:.1%}",
                abs(ratio(q, p)) < SAME_PEAK,
                f"{p:.2f} and {q:.2f}, {ratio(q, p):+.4%}",
            )
    for key in ("nc", "dss"):
        run = runs.get(f"gross_{key}", {})
        if run.get("finished") and "cells" in rain[key]:
            got = run["balance"]["rain_m3"]
            want = rain[key]["domain"]["volume_m3"]
            on_cells = rain[key]["cells"]["volume_m3"]
            found[f"gross {key}"] = {
                "run_m3": got,
                "domain_m3": want,
                "cells_m3": on_cells,
                "run_over_domain": ratio(got, want),
                "run_over_cells": ratio(got, on_cells),
            }
            h.check(
                f"{key}: the run's rain is the file's own depth over the domain within {VOLUME:.0%}",
                abs(ratio(got, want)) < VOLUME,
                f"{ratio(got, want):+.4%} (over the active cells {ratio(got, on_cells):+.4%})",
            )
    for key in ("nc", "dss"):
        run = runs.get(f"hybrid_{key}", {})
        if not run.get("finished") or "subbasins" not in rain[key]:
            continue
        worst, rows = 0.0, {}
        for e in record["basin"]["elements"]:
            if (
                e["kind"] != "subbasin"
                or safe(e["name"]) not in run["network"]
                or e["name"] not in rain[key]["subbasins"]
            ):
                h.log(f"  not compared: {e['name']}") if e["kind"] == "subbasin" else None
                continue
            p = rain[key]["subbasins"][e["name"]]["mean_mm"]
            area = e["parameters"]["area_km2"]
            want = scs_excess(p, e["parameters"]["curve_number"]) / 1000.0 * area * 1e6
            got = run["network"][safe(e["name"])]["volume_m3"]
            rows[e["name"]] = {
                "polygon_mean_mm": p,
                "cn": e["parameters"]["curve_number"],
                "area_km2": area,
                "want_m3": want,
                "run_m3": got,
                "error": ratio(got, want),
                "end_m3s": run["network"][e["name"]]["end_m3s"],
            }
            worst = max(worst, abs(ratio(got, want)))
        found[f"hybrid {key} subbasins"] = rows
        h.check(
            f"hybrid {key}: every lumped subbasin runs off its own polygon mean within {POLYGON:.0%}",
            rows and worst < POLYGON,
            f"worst {worst:+.4%} of {len(rows)}",
        )
    pmp = runs.get("pmp_gross", {})
    factor = rain["tables"]["arf_at_300"] * rain["tables"]["pmp_pattern_end_percent"] / 100.0
    if pmp.get("finished") and "cells" in rain["pmp"]:
        got = pmp["balance"]["rain_m3"]
        want = rain["pmp"]["domain"]["volume_m3"] * factor
        raw = rain["pmp"]["domain"]["volume_m3"] * rain["tables"]["pmp_pattern_end_percent"] / 100.0
        found["gross pmp"] = {
            "run_m3": got,
            "domain_x_arf_m3": want,
            "domain_no_arf_m3": raw,
            "cells_x_arf_m3": rain["pmp"]["cells"]["volume_m3"] * factor,
            "run_over_domain_x_arf": ratio(got, want),
            "run_over_domain_no_arf": ratio(got, raw),
        }
        h.check(
            f"PMP: the run's rain is the raster's depth over the domain x the pattern x the met's ARF within {VOLUME:.0%}",
            abs(ratio(got, want)) < VOLUME,
            f"{ratio(got, want):+.4%}; without the ARF {ratio(got, raw):+.4%}",
        )
    hyb = runs.get("pmp_hybrid", {})
    if hyb.get("finished") and "S13" in hyb["network"]:
        got = hyb["network"]["S13"]["volume_m3"]
        rows = {}
        for how in ("S13_centres", "S13"):
            p = rain["pmp"][how]["mean_mm"] * factor
            want = scs_excess(p, S13_CN, S13_IA_MM) / 1000.0 * S13_KM2 * 1e6
            rows[how] = {"depth_mm": p, "want_m3": want, "run_m3": got, "error": ratio(got, want)}
        found["pmp S13"] = rows
        h.check(
            f"PMP: S13 lumped runs off the raster's polygon mean (cell centres, as HMS) x ARF within {POLYGON:.0%}",
            abs(rows["S13_centres"]["error"]) < POLYGON,
            f"{rows['S13_centres']['error']:+.4%}; area-weighted {rows['S13']['error']:+.4%}",
        )
    h.log(json.dumps(found, indent=1)[:6000])
