"""D5 through the real dock: each way of giving the rain, against an answer known without it."""

import json
import os
import subprocess
from pathlib import Path

from osgeo import gdal, osr
from qgis.core import QgsProject
from qgis.PyQt.QtWidgets import QApplication, QTableWidgetItem

import numpy as np

HOURS = 1.0
RAIN = 60.0
FRAMES = 4
DX = 40.0
FLICKER = 0.02
"""A line whose step-to-step change near the peak passes this share of the peak is noise at a minute's reading."""
LATLON = """
import json, sys
from pyproj import Transformer
t = Transformer.from_crs(sys.argv[1], "EPSG:4326", always_xy=True)
xs, ys = [float(v) for v in sys.argv[2:4]], [float(v) for v in sys.argv[4:6]]
lon, lat = t.transform([xs[0], xs[0], xs[1], xs[1]], [ys[0], ys[1], ys[0], ys[1]])
print(json.dumps([min(lon), min(lat), max(lon), max(lat)]))
"""
CELLS = """
import json, sys, h5py, numpy as np
with h5py.File(sys.argv[1], "r") as f:
    mask = f["mask"][:]; y0 = float(f.attrs["y0"]); dx = float(f.attrs["dx"])
rows = np.nonzero(mask)[0]
print(json.dumps({"north": int(np.count_nonzero(y0 - (rows + 0.5) * dx > float(sys.argv[2]))), "all": int(rows.size), "dx": dx}))
"""
WRITE_DSS = """
import json, sys
import numpy as np
from hecdss import HecDss
from hecdss.gridded_data import GriddedData
path, wkt, rows, columns, left, bottom, split, pixel, depth = sys.argv[1], sys.argv[2], *[int(v) for v in sys.argv[3:8]], float(sys.argv[8]), float(sys.argv[9])
data = np.zeros((rows, columns))
data[rows - split:] = depth  # a DSS grid stores its southern row first
with HecDss(path) as f:
    for k in range(4):
        d, e = f"{k // 4 * 100 + k * 15:04d}", f"{(k + 1) * 15 if k < 3 else 100:04d}"
        name = f"/UTM40/BIDAH/PRECIPITATION/03OCT2021:{d}/03OCT2021:{e}/SYN/"
        grid = GriddedData.create(
            path=name, data=data, numberOfCellsX=columns, numberOfCellsY=rows, lowerLeftCellX=left, lowerLeftCellY=bottom,
            cellSize=pixel, dataUnits="MM", dataType=1, srsName="UTM", srsDefinition=wkt,
        )
        assert f.put(grid) == 0
print(json.dumps({"ok": True}))
"""
HYETOGRAPH = """
import json, sys
from pathlib import Path
import numpy as np, rasterio
from rasterio.transform import from_origin
from wadi2d.config.schema import RunConfig
from wadi2d.forcing import build_storm
cfg = RunConfig.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
step = float(sys.argv[3]); storm = build_storm(cfg)
folder = Path(sys.argv[2]); folder.mkdir(exist_ok=True)
n = int(np.ceil(cfg.storm.duration_min / step))
for k, depth in enumerate(storm.increments(step, n)):
    with rasterio.open(folder / f"r{k:04d}.tif", "w", driver="GTiff", height=2, width=2, count=1, dtype="float64",
                       crs=sys.argv[4], transform=from_origin(*[float(v) for v in sys.argv[5:9]])) as dst:
        dst.write(np.full((2, 2), depth), 1)
print(json.dumps({"frames": n, "total": storm.total_depth}))
"""


def engine(h, code, *args):
    from wadi2d_qgis.protocol import clean_env

    done = subprocess.run(
        [str(h.VENV), "-c", code, *[str(a) for a in args]], capture_output=True, text=True, check=True,
        env=clean_env(dict(os.environ)),
    )  # fmt: skip
    return next(json.loads(s) for s in done.stdout.splitlines() if s.startswith(("{", "[")))


def write_netcdf(path, depths, lon, lat, minutes, classic=False):
    """A file from the real NetCDF library behind GDAL: (time, lat, lon), latitude rising, as many products lay it out."""
    options = ["FORMAT=NC"] if classic else ["FORMAT=NC4"]
    ds = gdal.GetDriverByName("netCDF").CreateMultiDimensional(str(path), [], options)
    root = ds.GetRootGroup()
    float64 = gdal.ExtendedDataType.Create(gdal.GDT_Float64)
    float32 = gdal.ExtendedDataType.Create(gdal.GDT_Float32)
    text = gdal.ExtendedDataType.CreateString()

    def coordinate(name, kind, direction, values, units):
        dim = root.CreateDimension(name, kind, direction, len(values))
        var = root.CreateMDArray(name, [dim], float64)
        var.Write(np.asarray(values, np.float64))
        var.CreateAttribute("units", [], text).WriteString(units)
        return dim, var

    dt, _ = coordinate("time", "TEMPORAL", "", minutes, "minutes since 2021-10-03 00:00:00")
    dy, _ = coordinate("lat", "HORIZONTAL_Y", "NORTH", lat, "degrees_north")
    dx, _ = coordinate("lon", "HORIZONTAL_X", "EAST", lon, "degrees_east")
    rain = root.CreateMDArray("precipitation", [dt, dy, dx], float32)
    rain.CreateAttribute("units", [], text).WriteString("mm")
    rain.Write(np.asarray(depths, np.float32))
    ds = None


def write_stack(folder, west, north, pixel, frames, wkt):
    folder.mkdir(exist_ok=True)
    for k, data in enumerate(frames):
        ds = gdal.GetDriverByName("GTiff").Create(str(folder / f"rain_{k + 1}.tif"), data.shape[1], data.shape[0], 1, gdal.GDT_Float32)
        ds.SetGeoTransform((west, pixel, 0.0, north, 0.0, -pixel))
        ds.SetProjection(wkt)
        ds.GetRasterBand(1).WriteArray(data)
        ds = None


def choose(storm, kind):
    storm.kind.setCurrentIndex(storm.kind.findData(kind))


def type_rows(pair, rows):
    pair.table.setRowCount(0)
    for row in rows:
        pair.add_button.click()
        n = pair.table.rowCount() - 1
        for m, value in enumerate(row):
            pair.table.setItem(n, m, QTableWidgetItem(str(value)))


def roughness(folder, name):
    """Step-to-step change near the peak, m3/s: a line that flickers has no fair raw peak."""
    rows = [line.split(",") for line in (Path(folder) / "series" / f"line_{name}.csv").read_text().splitlines()[1:]]
    flow = np.abs(np.array([float(r[1]) for r in rows]))
    near = flow[max(int(flow.argmax()) - 120, 0) : int(flow.argmax()) + 120]
    return float(np.sqrt(np.mean(np.diff(near) ** 2)))


def job_of(folder):
    return json.loads((Path(folder) / "job.json").read_text(encoding="utf-8"))


def rain_of(h, folder):
    done = h.events(folder, "done")
    return done[-1].get("balance", {}) if done else {}


def scenario(h):
    ground = h.Bidah()
    dock = yield from h.open_dock()
    storm = dock.storm
    extent = ground.domain.extent()
    wkt = ground.crs.toWkt()

    h.log("=== the section")
    h.check("storm comes after hydrology", dock.sections.index(storm) == dock.sections.index(dock.hydrology) + 1)
    h.check("steady rain is the start", storm.kind.currentData() == "uniform", storm.kind.currentText())
    h.check("no HMS choice without a project", storm.kind.findData("hms") < 0)
    h.check("units come from the engine", storm.units.count() == 4, storm.units.count())
    h.check("sections renumbered", dock.panel.title() == "8. Run" and dock.boundaries.title() == "6. Boundaries", dock.panel.title())
    h.widget_shot("storm_start", storm)

    h.log("=== 1 steady rain, the known answer")
    h.set_rain_job(dock, ground, "steady", dx=DX, rain=RAIN, hours=HOURS, sim_hours=1.2, pixels=False)
    yield from h.run(dock)
    base = h.RUNS / "steady"
    plain = rain_of(h, base)
    h.check("steady job as before", job_of(base)["storm"] == {"kind": "uniform", "depth_mm": RAIN, "duration_min": 60.0}, job_of(base)["storm"])
    h.check("steady ran", plain.get("rain_m3", 0) > 0, plain)
    h.log(f"steady peaks {h.peaks(base)} rain {plain.get('rain_m3')}")

    h.log("=== 2 hyetograph typed in the table")
    choose(storm, "hyetograph")
    type_rows(storm.hyetograph, [(15, 15), (30, 15), (45, 15), (60, 15)])
    h.widget_shot("hyetograph", storm)
    dock.panel.folder.setFilePath(str(h.RUNS / "hyetograph"))
    yield from h.run(dock)
    table = rain_of(h, h.RUNS / "hyetograph")
    written = job_of(h.RUNS / "hyetograph")["storm"]
    h.check("table reached the job", written["hyetograph_mm"] == [15.0] * 4 and written["hyetograph_min"][-1] == 60.0, written)
    h.check("hyetograph rain equals steady", abs(table["rain_m3"] / plain["rain_m3"] - 1.0) < 1e-5, table["rain_m3"])
    h.check("hyetograph water equals steady", abs(table["outflow_m3"] / max(plain["outflow_m3"], 1.0) - 1.0) < 1e-3, table["outflow_m3"])

    h.log("=== 3 a bad table is refused in words")
    type_rows(storm.hyetograph, [(30, 10), (15, 5)])
    dock.panel.run_button.click()
    yield lambda: "rise" in dock.panel.message.text()
    h.check("bad table refused", "must rise" in dock.panel.message.text(), dock.panel.message.text())

    h.log("=== 4 pasted from a spreadsheet")
    QApplication.clipboard().setText("End\tDepth\n20\t20\n40\t20\n60\t20\n")
    storm.hyetograph.paste_button.click()
    h.check("paste fills the table", storm.hyetograph.rows() == [(20.0, 20.0), (40.0, 20.0), (60.0, 20.0)], storm.hyetograph.rows())

    h.log("=== 5 design storm with area reduction")
    choose(storm, "hypothetical")
    storm.design_depth.setValue(100.0)
    storm.design_hours.setValue(HOURS)
    type_rows(storm.pattern, [(0, 0), (50, 50), (100, 100)])
    storm.storm_area.setValue(100.0)
    type_rows(storm.arf, [(100, 0.6), (1000, 0.5)])
    h.widget_shot("design", storm)
    dock.panel.folder.setFilePath(str(h.RUNS / "design"))
    yield from h.run(dock)
    design = rain_of(h, h.RUNS / "design")
    h.check("100 mm at 0.6 is 60 mm", abs(design["rain_m3"] / plain["rain_m3"] - 1.0) < 1e-5, design["rain_m3"])
    h.check("design job keeps its table", job_of(h.RUNS / "design")["storm"]["arf"]["factors"] == [0.6, 0.5])

    h.log("=== 6 NetCDF-4 from the real library, in lat/lon, on UTM cells")
    box = engine(h, LATLON, ground.crs.authid(), extent.xMinimum() - 2000, extent.xMaximum() + 2000, extent.yMinimum() - 2000, extent.yMaximum() + 2000)
    lon = np.linspace(box[0], box[2], 6)
    lat = np.linspace(box[1], box[3], 5)
    minutes = [15.0, 30.0, 45.0, 60.0]
    nc = h.P / "rain_nc4.nc"
    write_netcdf(nc, np.full((FRAMES, lat.size, lon.size), RAIN / FRAMES), lon, lat, minutes)
    choose(storm, "gridded")
    storm.rain_file.setFilePath(str(nc))
    yield lambda: storm.rain_label.text() and "Reading" not in storm.rain_label.text()
    h.widget_shot("gridded", storm)
    h.log(f"rain label: {storm.rain_label.text()}")
    h.check("the engine says what the file holds", storm.rain_label.text().startswith("4 frames of 15 min"), storm.rain_label.text())
    h.check("first period is dated", "2021-10-03 00:00:00" in storm.rain_label.text(), storm.rain_label.text())
    dock.panel.folder.setFilePath(str(h.RUNS / "nc4"))
    yield from h.run(dock)
    nc4 = rain_of(h, h.RUNS / "nc4")
    h.check("NetCDF-4 rain equals steady", abs(nc4["rain_m3"] / plain["rain_m3"] - 1.0) < 1e-4, nc4["rain_m3"])

    h.log("=== 7 classic NetCDF from the real library")
    classic = h.P / "rain_classic.nc"
    write_netcdf(classic, np.full((FRAMES, lat.size, lon.size), RAIN / FRAMES), lon, lat, minutes, classic=True)
    storm.rain_file.setFilePath(str(classic))
    yield lambda: storm.rain_label.text() and "Reading" not in storm.rain_label.text()
    h.check("classic file read", storm.rain_label.text().startswith("4 frames of 15 min"), storm.rain_label.text())
    dock.panel.folder.setFilePath(str(h.RUNS / "classic"))
    yield from h.run(dock)
    h.check("classic rain equals steady", abs(rain_of(h, h.RUNS / "classic")["rain_m3"] / plain["rain_m3"] - 1.0) < 1e-4)

    h.log("=== 8 a start date cuts the rain")
    storm.start.setText("2021-10-03T00:30:00")
    storm.start.editingFinished.emit()
    yield lambda: "2021-10-03 00:30:00" in storm.rain_label.text()
    dock.panel.folder.setFilePath(str(h.RUNS / "cut"))
    yield from h.run(dock)
    cut = rain_of(h, h.RUNS / "cut")
    h.check("half the rain is left", abs(cut["rain_m3"] / plain["rain_m3"] - 0.5) < 1e-3, cut["rain_m3"])
    storm.start.clear()

    h.log("=== 9 a GeoTIFF folder, rain on the north only: does it fall where the grid says")
    middle = 0.5 * (extent.yMinimum() + extent.yMaximum())
    west, top, pixel = extent.xMinimum() - 1000.0, extent.yMaximum() + 1000.0, 500.0
    rows = int((top - extent.yMinimum() + 1000.0) / pixel) + 1
    columns = int((extent.xMaximum() + 1000.0 - west) / pixel) + 1
    split = int(round((top - middle) / pixel))
    middle = top - split * pixel
    frame = np.zeros((rows, columns), np.float32)
    frame[:split] = RAIN / FRAMES
    folder = h.P / "rain_tifs"
    write_stack(folder, west, top, pixel, [frame] * FRAMES, wkt)
    storm.is_folder.setCurrentIndex(1)
    storm.rain_file.setFilePath(str(folder))
    storm.period.setValue(15.0)
    storm.period.editingFinished.emit()
    yield lambda: "Reading" not in storm.rain_label.text() and "frames" in storm.rain_label.text()
    dock.panel.pixels.setChecked(True)
    dock.panel.folder.setFilePath(str(h.RUNS / "north"))
    yield from h.run(dock)
    run = h.RUNS / "north"
    north = rain_of(h, run)
    cells = engine(h, CELLS, run / "results.h5", middle)
    share = cells["north"] / cells["all"]
    h.log(f"north cells {cells}, share {share:.4f}")
    h.check("rain only on the wet half", abs(north["rain_m3"] / (plain["rain_m3"] * share) - 1.0) < 2e-2, north["rain_m3"])
    h.check("the run says nothing odd", not [e for e in h.events(run, "warn") if "rain:" in e.get("message", "")], h.events(run, "warn"))
    layers = [n.layer() for n in h.group_of("north").findLayers()]
    depth = [ly for ly in layers if "depth" in ly.name().lower()]
    h.render("north_only", depth[:1] + [ground.dem], ground.domain.extent().center(), 60000)

    h.log("=== 9b a DSS file, the same rain, stored south row first")
    left, bottom = int(west // pixel), int(extent.yMinimum() // pixel) - 2
    high = int(np.ceil(top / pixel))
    dss = h.P / "rain.dss"
    engine(h, WRITE_DSS, dss, wkt, high - bottom, columns, left, bottom, split, pixel, RAIN / FRAMES)
    dsouth = high * pixel - split * pixel
    storm.is_folder.setCurrentIndex(0)
    storm.period.setValue(0.0)
    storm.rain_file.setFilePath(str(dss))
    yield lambda: "Reading" not in storm.rain_label.text() and storm.rain_label.text()
    h.log(f"rain label: {storm.rain_label.text()}")
    h.check("DSS frames read", storm.rain_label.text().startswith("4 frames of 15 min"), storm.rain_label.text())
    dock.panel.pixels.setChecked(False)
    dock.panel.folder.setFilePath(str(h.RUNS / "dss"))
    yield from h.run(dock)
    run = h.RUNS / "dss"
    from_dss = rain_of(h, run)
    cells = engine(h, CELLS, run / "results.h5", dsouth)
    h.log(f"dss cells {cells}")
    h.check("DSS rain on the north only", abs(from_dss["rain_m3"] / (plain["rain_m3"] * cells["north"] / cells["all"]) - 1.0) < 2e-2, from_dss["rain_m3"])
    storm.is_folder.setCurrentIndex(1)
    storm.rain_file.setFilePath(str(folder))
    storm.period.setValue(15.0)
    storm.period.editingFinished.emit()
    yield lambda: "Reading" not in storm.rain_label.text() and "frames" in storm.rain_label.text()

    h.log("=== 10 gridded rain on a mesh")
    dock.panel.pixels.setChecked(False)
    dock.mesh.enabled.setChecked(True)
    dock.mesh.coarse.setValue(DX * 4.0)
    dock.terrain.dx.setValue(DX / 2.0)
    write_stack(folder, west, top, pixel, [np.full((rows, columns), RAIN / FRAMES, np.float32)] * FRAMES, wkt)
    dock.panel.folder.setFilePath(str(h.RUNS / "mesh"))
    yield from h.run(dock)
    meshed = rain_of(h, h.RUNS / "mesh")
    h.check("mesh run ended", h.events(h.RUNS / "mesh", "done")[-1].get("code") == 0, dock.panel.message.text())
    h.check("mesh mass closes", abs(meshed.get("relative_error", 1.0)) < 1e-4, meshed.get("relative_error"))
    h.check("mesh rain near steady", abs(meshed["rain_m3"] / plain["rain_m3"] - 1.0) < 0.02, meshed["rain_m3"])
    dock.mesh.enabled.setChecked(False)
    dock.mesh.local_steps.setChecked(False)
    dock.terrain.dx.setValue(DX)

    h.log("=== 11 a file that is not rain says so")
    storm.is_folder.setCurrentIndex(0)
    bad = h.P / "bad.nc"
    bad.write_bytes(b"nothing here")
    storm.rain_file.setFilePath(str(bad))
    yield lambda: "could not be read" in storm.rain_label.text()
    h.check("bad file named plainly", "not a NetCDF file" in storm.rain_label.text(), storm.rain_label.text())

    yield from lumped(h, dock, ground, storm)
    QgsProject.instance().setDirty(False)


def lumped(h, dock, ground, storm):
    """Block 2 hybrid twice: the HMS storm, then the same rain as frames. Lumped and 2D must both take it."""
    h.log("=== 12 the HMS storm, then the same rain as frames")
    from qgis.core import QgsVectorLayer  # noqa: F401

    hills = h.BLOCK / "HEC_HMS_Block_02"
    domain = h.add_vector(h.VALIDATION / "domain.geojson", "domain block 2", ground.crs)
    jobs = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    outlets = h.add_vector(h.geojson("outs", [h.line(k["coordinates"], kind="normal", value=0.008) for k in jobs["boundaries"]]), "block outlets", ground.crs)
    lines = h.add_vector(h.geojson("dams", [h.line(k["coordinates"], name=k["name"]) for k in jobs["outputs"]["lines"]]), "block dams", ground.crs)
    t, y = dock.terrain, dock.hydrology
    t.domain.setLayer(domain)
    t.dx.setValue(40.0)
    y.folder.setFilePath(str(hills))
    yield lambda: y.files["basin"].count() > 0
    y.files["met"].setCurrentText("FM_100yr.met")
    h.check("a rain the user chose stays", storm.kind.currentData() == "gridded", storm.kind.currentText())
    h.check("an HMS project offers its storm", storm.kind.findData("hms") >= 0)
    choose(storm, "hms")
    h.widget_shot("hms", storm)
    dock.boundaries.layer.setLayer(outlets)
    dock.points.layer.setLayer(lines)
    dock.points.name.setField("name")
    dock.panel.duration.setValue(30.0)
    dock.panel.folder.setFilePath(str(h.RUNS / "hms"))
    yield from h.run(dock, 2400)
    first = h.RUNS / "hms"
    done = h.events(first, "done")
    h.check("HMS run ended", done and done[-1].get("code") == 0, dock.panel.message.text())
    peaks = h.peaks(first)
    h.log(f"HMS peaks {peaks}")
    box = domain.extent()
    pixel = max(box.width(), box.height()) / 2.0 + 2000.0
    made = engine(h, HYETOGRAPH, first / "config.resolved.json", h.P / "rain_block2", 5.0, ground.crs.authid(), box.xMinimum() - 1000.0, box.yMaximum() + 1000.0, pixel, pixel)
    h.log(f"frames {made}")
    choose(storm, "gridded")
    storm.is_folder.setCurrentIndex(1)
    storm.rain_file.setFilePath(str(h.P / "rain_block2"))
    storm.period.setValue(5.0)
    storm.period.editingFinished.emit()
    yield lambda: "Reading" not in storm.rain_label.text() and "frames" in storm.rain_label.text()
    h.log(f"rain label: {storm.rain_label.text()}")
    h.check("the label follows the last reading", "of 5 min" in storm.rain_label.text(), storm.rain_label.text())
    dock.panel.folder.setFilePath(str(h.RUNS / "hms_frames"))
    yield from h.run(dock, 2400)
    second = h.RUNS / "hms_frames"
    done = h.events(second, "done")
    h.check("frames run ended", done and done[-1].get("code") == 0, dock.panel.message.text())
    h.check("the storm in the job is the frames", job_of(second)["storm"]["kind"] == "gridded", job_of(second)["storm"]["kind"])
    h.check("the control file still sets the time", job_of(second)["run"]["duration_s"] == job_of(first)["run"]["duration_s"])
    again = h.peaks(second)
    h.log(f"frames peaks {again}")
    steady, flicker = {}, {}
    for name, peak in peaks.items():
        if peak > 1.0:
            rough = roughness(first, name)
            (flicker if rough > FLICKER * peak else steady)[name] = again[name] / peak - 1.0
            h.log(f"{name}: raw {peak} and {again[name]}, step change near the peak {rough:.1f} m3/s")
    worst = max(abs(v) for v in steady.values())
    h.check("every steady line as the HMS storm", worst < 0.005, f"worst {worst:.4%}, {len(steady)} lines")
    h.check("no dam line flickers", not [k for k in flicker if not k.endswith("_ring")], sorted(flicker))
    h.log(f"flickering lines, raw peak not a fair reading: { {k: round(v, 4) for k, v in flicker.items()} }")
    a, b = h.events(first, "done")[-1]["balance"], h.events(second, "done")[-1]["balance"]
    h.check("hills took the same water", abs(b["inflow_m3"] / a["inflow_m3"] - 1.0) < 1e-3, (a["inflow_m3"], b["inflow_m3"]))
    h.check("plain took the same rain", abs(b["rain_m3"] / a["rain_m3"] - 1.0) < 1e-3, (a["rain_m3"], b["rain_m3"]))
