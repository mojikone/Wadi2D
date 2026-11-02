"""D1 through the real dock: the saved frames as a mesh layer that moves with the Temporal Controller."""

import json
import math
import os
import subprocess

from qgis.core import QgsDateTimeRange, QgsMeshDatasetIndex, QgsProject, QgsTemporalNavigationObject
from qgis.PyQt.QtWidgets import QDockWidget
from qgis.utils import iface

COUNT = """
import json, sys, h5py, numpy as np
from wadi2d.config.schema import Pixels
FLOOR = Pixels().depth_floor
with h5py.File(sys.argv[1], "r") as f:
    names = sorted(f["maps"]); mask = f["mask"][:]
    out = []
    for n in names:
        d = f["maps"][n]["depth"][:][mask]
        wet = d >= FLOOR
        out.append([float(n[1:]), int(wet.sum()), float(d.max())])
print(json.dumps({"frames": out, "cells": int(mask.sum())}))
"""


def engine_says(h, folder):
    from wadi2d_qgis.protocol import clean_env

    args = [str(h.VENV), "-c", COUNT, str(folder / "results.h5")]
    done = subprocess.run(args, capture_output=True, text=True, check=True, env=clean_env(dict(os.environ)))
    return json.loads(done.stdout)


def frames_layer(h, run):
    found = [n.layer() for n in h.group_of(run).findLayers() if n.layer().name() == "Flood over time, cells"]
    return found[0] if found else None


def group_of(layer, name):
    provider = layer.dataProvider()
    for g in range(provider.datasetGroupCount()):
        if provider.datasetGroupMetadata(QgsMeshDatasetIndex(g, 0)).name().lower().startswith(name):
            return g
    return -1


def wet_count(layer, group, frame):
    provider = layer.dataProvider()
    values = provider.datasetValues(QgsMeshDatasetIndex(group, frame), 0, provider.faceCount())
    wet, top = 0, 0.0
    for k in range(provider.faceCount()):
        v = values.value(k).scalar()
        if not math.isnan(v):
            wet += 1
            top = max(top, v)
    return wet, top


def scenario(h):
    ground = h.Bidah()
    dock = yield from h.open_dock()
    panel = dock.panel

    h.log("=== 1 a uniform run")
    h.check("no button before a run", not panel.frames_button.isEnabled())
    h.set_rain_job(dock, ground, "uniform", rain=60.0, hours=1.0, sim_hours=2.0)
    panel.maps.setCurrentIndex(1)  # every five minutes
    yield from h.run(dock)
    folder = h.RUNS / "uniform"
    h.check("finished", h.events(folder, "done")[-1]["code"] == 0, panel.message.text())
    h.check("button after a run", panel.frames_button.isEnabled())
    expected = engine_says(h, folder)
    h.check("nothing exported until asked", not (folder / "frames.nc").exists())

    panel.frames_button.click()
    yield lambda: panel.frames_button.isEnabled() and "Writing" not in panel.message.text() and "Reading" not in panel.message.text()
    h.check("says how to use it", "Temporal Controller" in panel.message.text(), panel.message.text())
    h.check("the file is there", (folder / "frames.nc").is_file(), (folder / "frames.nc").stat().st_size)
    layer = frames_layer(h, "uniform")
    h.check("a valid mesh layer", layer is not None and layer.isValid())
    provider = layer.dataProvider()
    h.check("one face per cell", provider.faceCount() == expected["cells"], (provider.faceCount(), expected["cells"]))
    names = sorted(provider.datasetGroupMetadata(QgsMeshDatasetIndex(g, 0)).name() for g in range(provider.datasetGroupCount()))
    h.log(f"groups {names}")
    h.check("depth, speed, hazard", len(names) == 3 and all(group_of(layer, k) >= 0 for k in ("depth", "speed", "hazard")), names)
    count = len(expected["frames"])
    h.check("every saved frame", provider.datasetCount(0) == count, (provider.datasetCount(0), count))
    h.check("the layer is temporal", layer.temporalProperties().isActive())
    span = layer.temporalProperties().timeExtent()
    h.check("runs for the run's time", span.begin().secsTo(span.end()) == round(expected["frames"][-1][0] - expected["frames"][0][0]), span.begin().secsTo(span.end()))
    h.check("in the DEM's CRS", layer.crs() == ground.crs, layer.crs().authid())
    tree = QgsProject.instance().layerTreeRoot().findLayer(layer)
    h.check("on top of the run's group", tree.parent().name() == "uniform" and tree.parent().children()[0] == tree)
    h.check("maximum maps switched off under it", not h.group_of("uniform").findGroup("Flood maps").itemVisibilityChecked())

    h.log("=== 2 what QGIS reads is what the engine saved")
    depth = group_of(layer, "depth")
    worst = 0.0
    for frame in (1, count // 2, count - 1):
        t, wet, top = expected["frames"][frame]
        seen, seen_top = wet_count(layer, depth, frame)
        h.check(f"frame at {t:.0f} s: wet cells", seen == wet, (seen, wet))
        worst = max(worst, abs(seen_top - top))
    h.check("deepest cell in those frames", worst < 1e-3, worst)

    h.log("=== 3 the Temporal Controller drives it")
    controller = iface.mapCanvas().temporalController()
    h.check("set to animate", controller.navigationMode() == QgsTemporalNavigationObject.Animated, controller.navigationMode())
    h.check("one step per frame", controller.totalFrameCount() in (count, count - 1, count + 1), (controller.totalFrameCount(), count))
    shown = [d.objectName() for d in iface.mainWindow().findChildren(QDockWidget) if d.isVisible() and "emporal" in (d.objectName() + d.windowTitle())]
    h.check("the panel is open", bool(shown), shown)
    controller.setCurrentFrameNumber(count // 2)
    h.check("canvas moves with it", iface.mapCanvas().temporalRange().begin() == controller.dateTimeRangeForFrameNumber(count // 2).begin())
    begin = span.begin()

    def at(seconds):
        return QgsDateTimeRange(begin.addSecs(seconds), begin.addSecs(seconds + 60))

    first = expected["frames"][0][0]
    h.log(f"first frame at {first:.0f} s, last at {expected['frames'][-1][0]:.0f} s")
    h.check("the first frame is where the slider starts", begin.toSecsSinceEpoch() % 86400 == round(first), begin.toString())
    picked = layer.datasetIndexAtTime(at(round(expected["frames"][5][0] - first) + 1), depth).dataset()
    h.check("a time picks its frame", picked == 5, picked)

    for name, frame in (("early", 2), ("middle", count // 2), ("late", count - 1)):
        h.render(f"{name}", [layer, ground.dem], ground.domain.extent().center(), 40000, temporal=begin.addSecs(frame * 300))
    settings = layer.rendererSettings()
    settings.setActiveScalarDatasetGroup(group_of(layer, "hazard"))
    layer.setRendererSettings(settings)
    h.render("hazard", [layer, ground.dem], ground.domain.extent().center(), 40000, temporal=begin.addSecs((count // 2) * 300))

    h.log("=== 4 a second click reuses the file")
    stamp = (folder / "frames.nc").stat().st_mtime_ns
    panel.frames_button.click()
    yield lambda: panel.frames_button.isEnabled() and "Temporal Controller" in panel.message.text()
    h.check("file not rewritten", (folder / "frames.nc").stat().st_mtime_ns == stamp)

    h.log("=== 5 a run with no saved maps says so")
    h.set_rain_job(dock, ground, "no_maps", sim_hours=0.02, pixels=False)
    panel.maps.setCurrentIndex(0)
    yield from h.run(dock)
    panel.message.clear()
    panel.frames_button.click()
    yield lambda: panel.frames_button.isEnabled() and "Writing" not in panel.message.text() and panel.message.text()
    h.check("too few frames says so", "needs two" in panel.message.text(), panel.message.text())

    h.log("=== 6 a mesh: the real tiles in time")
    m = dock.mesh
    m.setCollapsed(False)
    h.set_rain_job(dock, ground, "mesh", dx=10.0, sim_hours=1.0, pixels=False)
    m.enabled.setChecked(True)
    m.coarse.setValue(40.0)
    panel.maps.setCurrentIndex(1)
    yield from h.run(dock)
    folder = h.RUNS / "mesh"
    start = h.events(folder, "start")[-1]
    panel.message.clear()
    panel.frames_button.click()
    yield lambda: panel.frames_button.isEnabled() and "Temporal Controller" in panel.message.text()
    layer = frames_layer(h, "mesh")
    provider = layer.dataProvider()
    h.check("mesh: one face per real cell", provider.faceCount() == start["cells"], (provider.faceCount(), start["cells"]))
    h.check("mesh: three datasets in time", provider.datasetGroupCount() == 3 and provider.datasetCount(0) >= 12, provider.datasetCount(0))
    h.render("mesh", [layer, ground.dem], ground.domain.extent().center(), 40000, temporal=layer.temporalProperties().timeExtent().end())
    m.enabled.setChecked(False)
