"""W51 through the real dock: the saved frames drawn at the terrain pixel on the Temporal Controller, on demand.

Bidah at 20 m, maps every 5 minutes. The layer is loaded by its dock button; then a pan, a zoom, five slider positions
and an animation are drawn as QGIS draws them (a map render job on the canvas's own settings, since a minimized
window's canvas draws nothing), each timed; Identify is read through QGIS's own identify tool; and the numbers QGIS
received are checked against the engine's renderer run apart, in another process.
"""

import json
import os
import shutil
import subprocess
import time

from qgis.core import (
    QgsDateTimeRange,
    QgsGeometry,
    QgsIdentifyContext,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
)
from qgis.gui import QgsMapToolIdentify
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface

OUT = os.environ.get("WADI2D_W51_OUT", "")
REFERENCE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import numpy as np
from pathlib import Path
from wadi2d.render.renderer import FrameRenderer
from wadi2d.render.run_source import open_run
from wadi2d.render.view import View
from wadi2d.products.pixels import to_host
requests = json.loads(Path(sys.argv[3]).read_text())
made = FrameRenderer(open_run(Path(sys.argv[2])), "auto")
out = []
for r in requests:
    d = made.draw(r["t"], View.of(r["extent"], r["width"], r["height"]), r["field"], None)
    v = to_host(d.values).astype(np.float32)
    out.append({"frame": d.frame, "detail": d.detail, "pixel_m": d.pixel_m, "values": np.where(np.isnan(v), -9999.0, v).ravel().tolist()})
made.close()
print(json.dumps(out))
"""


def reference(h, run, requests):
    from wadi2d_qgis.protocol import clean_env

    path = h.P / "reference_requests.json"
    path.write_text(json.dumps(requests), encoding="utf-8")
    args = [str(h.VENV), "-c", REFERENCE, str(h.REPO), str(run), str(path)]
    done = subprocess.run(args, capture_output=True, text=True, env=clean_env(dict(os.environ)), timeout=600)
    if done.returncode != 0:
        raise RuntimeError(done.stderr[-2000:])
    return json.loads(done.stdout)


def slider_layer_of(h, run):
    found = [n.layer() for n in h.group_of(run).findLayers() if n.layer().name() == "Flood over time, pixels"]
    return found[0] if found else None


def draw(layers, extent, size, when, name=None, folder=None):
    """One drawing as the canvas makes it, timed; the picture saved when named."""
    settings = QgsMapSettings()
    settings.setLayers(layers)
    settings.setDestinationCrs(layers[0].crs())
    settings.setOutputSize(QSize(*size))
    settings.setBackgroundColor(QColor("white"))
    settings.setExtent(extent)
    if when is not None:
        settings.setIsTemporal(True)
        settings.setTemporalRange(when)
    start = time.perf_counter()
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    seconds = time.perf_counter() - start
    image = job.renderedImage()
    if name:
        image.save(str(folder / f"{name}.png"))
    return seconds, image


def wet_share(image):
    """Share of pixels a blue drawing over white has tinted: how much water is on the picture."""
    wet, total = 0, 0
    for y in range(0, image.height(), 4):
        for x in range(0, image.width(), 4):
            colour = QColor(image.pixel(x, y))
            total += 1
            wet += colour.blue() > colour.red() + 10
    return wet / max(total, 1)


def inside_wet(values, width, height, reach):
    """The deepest pixel whose square of 2 reach + 1 pixels is all wet: water away from any edge."""
    best, found = -1.0, 0
    for i, value in enumerate(values):
        if value <= best:
            continue
        r, c = divmod(i, width)
        if reach <= r < height - reach and reach <= c < width - reach and all(
            values[(r + dr) * width + c + dc] > 0.0 for dr in range(-reach, reach + 1) for dc in range(-reach, reach + 1)
        ):
            best, found = value, i
    return found


def scenario(h):
    shots = h.P / "w51_shots"
    shots.mkdir(exist_ok=True)
    ground = h.Bidah()
    dock = yield from h.open_dock()
    from wadi2d_qgis import render_client
    from wadi2d_qgis.slider_layer import BANDS, at_seconds

    panel = dock.panel
    times = {}

    h.log("=== 1 a Bidah run at 20 m with maps every five minutes")
    h.check("no pixel slider button before a run", not panel.pixel_frames_button.isEnabled())
    h.set_rain_job(dock, ground, "pixels", dx=20.0, rain=60.0, hours=1.0, sim_hours=2.0)
    panel.maps.setCurrentIndex(1)
    yield from h.run(dock)
    run = h.RUNS / "pixels"
    h.check("finished", h.events(run, "done")[-1]["code"] == 0, panel.message.text())
    h.check("pixel slider button after a run", panel.pixel_frames_button.isEnabled())

    h.log("=== 2 one click: the layer")
    start = time.perf_counter()
    panel.pixel_frames_button.click()
    yield lambda: panel.pixel_frames_button.isEnabled() and "Starting" not in panel.message.text()
    times["open_s"] = round(time.perf_counter() - start, 2)
    h.check("says how to use it", "Temporal Controller" in panel.message.text(), panel.message.text())
    h.log(f"dock: {panel.message.text()}")
    layer = slider_layer_of(h, "pixels")
    h.check("a valid layer", layer is not None and layer.isValid())
    provider = layer.dataProvider()
    info = provider.info
    h.check("our provider", layer.providerType() == "wadi2d_slider", layer.providerType())
    h.check("three bands, depth first", provider.bandCount() == 3 and provider.generateBandName(1).startswith("Depth"))
    h.check("drawn at the pixel", info["detail"] == "pixel" and info["pixel_m"] <= 5.0, (info["detail"], info["pixel_m"]))
    h.check("the layer is temporal", layer.temporalProperties().isActive())
    h.check("in the DEM's CRS", layer.crs() == ground.crs, layer.crs().authid())
    h.check("styled as the depth of record", layer.renderer().type() == "singlebandpseudocolor", layer.renderer().type())
    tree = QgsProject.instance().layerTreeRoot().findLayer(layer)
    h.check("in the run's group", tree is not None and tree.parent().name() == "pixels")
    frames = info["frames_s"]
    h.check("every saved map", len(frames) >= 20, len(frames))
    controller = iface.mapCanvas().temporalController()
    h.check("controller reaches the last map", controller.totalFrameCount() >= len(frames), (controller.totalFrameCount(), len(frames)))
    h.log(f"backend {info['backend']}, {len(frames)} frames, {info['dx']} m cells, {info['pixel_m']} m pixels, opened in {times['open_s']} s")
    client = render_client.existing(run)

    def last():
        head, _ = client.ask({"op": "stats"})
        return head["last"]

    h.log("=== 3 the numbers QGIS receives are the engine's renderer, run apart")
    extent = ground.domain.extent()
    middle = extent.center()
    import struct

    across = [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()]
    head, payload = client.ask({"op": "values", "t": frames[len(frames) // 2], "extent": across, "width": 400, "height": 400, "field": "depth", "nodata": -1.0})
    deepest = inside_wet(struct.unpack(f"{400 * 400}f", payload), 400, 400, 3)
    row, col = divmod(deepest, 400)
    centre = QgsPointXY(extent.xMinimum() + (col + 0.5) * extent.width() / 400, extent.yMaximum() - (row + 0.5) * extent.height() / 400)
    h.log(f"views centred on the deepest water of the middle map, at {centre.x():.0f}, {centre.y():.0f}")
    box = [centre.x() - 600.0, centre.y() - 400.0, centre.x() + 600.0, centre.y() + 400.0]
    rect = QgsRectangle(*box)
    from wadi2d_qgis.slider_layer import seconds_at

    controller.setCurrentFrameNumber(len(frames) // 2)
    t_canvas = seconds_at(iface.mapCanvas().temporalRange().begin())
    block = provider.block(1, rect, 480, 320)  # no time of its own from Python: the map the canvas shows
    got = [block.value(r, c) for r in range(320) for c in range(480)]
    ref = reference(h, run, [{"t": t_canvas, "extent": box, "width": 480, "height": 320, "field": "depth"}])[0]
    h.check("a request with no time draws the canvas's map", ref["frame"] == len(frames) // 2, (t_canvas, ref["frame"]))
    worst = max(abs(a - b) for a, b in zip(got, ref["values"]))
    h.check("the layer's depth is the engine's, to 1e-4 m", worst < 1e-4, (worst, ref["detail"], ref["pixel_m"]))
    h.check("wet somewhere in that window", sum(v > 0 for v in got) > 100, sum(v > 0 for v in got))

    h.log("=== 4 a full drawing, a pan, a zoom, five slider positions, as the canvas draws them")
    size = (1920, 1080)
    t_mid = frames[len(frames) // 2]

    def at(t):
        return QgsDateTimeRange(at_seconds(t), at_seconds(t + 300.0))

    def view(cx, cy, width_m):
        half_w, half_h = width_m / 2.0, width_m / 2.0 * size[1] / size[0]
        return QgsRectangle(cx - half_w, cy - half_h, cx + half_w, cy + half_h)

    whole = view(middle.x(), middle.y(), max(extent.width(), extent.height() * size[0] / size[1]))
    for name, rectangle in (
        ("whole", whole),
        ("pan", view(middle.x() + 800.0, middle.y() + 300.0, whole.width())),
        ("zoom_3km", view(centre.x(), centre.y(), 3000.0)),
        ("zoom_500m", view(centre.x(), centre.y(), 500.0)),
    ):
        first, _ = draw([layer], rectangle, size, at(t_mid))
        again, image = draw([layer], rectangle, size, at(t_mid))
        drawn = last()
        draw([layer, ground.dem], rectangle, size, at(t_mid), f"{name}", shots)
        times[name] = {"first_s": round(first, 3), "again_s": round(again, 3), **{k: drawn[k] for k in ("detail", "pixel_m", "pending", "ms")}}
        h.log(f"{name}: first {first:.3f} s, again {again:.3f} s, {drawn}")
        h.check(f"{name}: drawn", drawn["frame"] == len(frames) // 2 and wet_share(image) > 0.0, drawn)
    h.check("the 500 m window is at the terrain pixel", times["zoom_500m"]["detail"] == "pixel", times["zoom_500m"])

    h.log("=== 5 five slider positions on the 3 km view, and stepping as an animation")
    rect3 = view(centre.x(), centre.y(), 3000.0)
    picks = [0, len(frames) // 4, len(frames) // 2, 3 * len(frames) // 4, len(frames) - 1]
    seen = []
    slider = []
    for k in picks:
        when = QgsDateTimeRange(at_seconds(frames[k] + 60.0), at_seconds(frames[k] + 360.0))
        seconds, image = draw([layer, ground.dem], rect3, size, when, f"slider_{k:02d}", shots)
        drawn = last()
        slider.append({"frame": k, "s": round(seconds, 3), "ms_engine": drawn["ms"], "wet": round(wet_share(image), 4)})
        seen.append(drawn["frame"])
        h.check(f"slider at {frames[k] + 60:.0f} s shows map {k}, the last at or before it", drawn["frame"] == k, drawn)
    times["slider"] = slider
    h.check("the flood moves between positions", len({s["wet"] for s in slider}) >= 3, [s["wet"] for s in slider])
    step = []
    for k in range(len(frames)):
        seconds, _ = draw([layer], rect3, size, controller.dateTimeRangeForFrameNumber(k))
        step.append(seconds)
    times["animation"] = {"frames": len(step), "mean_s": round(sum(step) / len(step), 3), "max_s": round(max(step), 3)}
    h.log(f"animation over {len(step)} controller frames: mean {times['animation']['mean_s']} s, max {times['animation']['max_s']} s")
    h.check("every controller frame draws in under a second", max(step) < 1.0, times["animation"])

    h.log("=== 6 the canvas itself on the controller")
    canvas = iface.mapCanvas()
    canvas.setExtent(rect3)
    for k in (2, 9, 16):
        controller.setCurrentFrameNumber(k)
        h.check(f"canvas time follows the controller at frame {k}", canvas.temporalRange().begin() == controller.dateTimeRangeForFrameNumber(k).begin())

    h.log("=== 7 Identify: QGIS's own tool, at the terrain pixel")
    head, payload = client.ask({"op": "values", "t": frames[picks[2]], "extent": [rect3.xMinimum(), rect3.yMinimum(), rect3.xMaximum(), rect3.yMaximum()], "width": 600, "height": 338, "field": "depth", "nodata": -9999.0})  # 5 m a pixel: drawn at the pixel
    import struct

    values = struct.unpack(f"{600 * 338}f", payload)
    wet = inside_wet(values, 600, 338, 2)
    row, col = divmod(wet, 600)
    point = QgsPointXY(rect3.xMinimum() + (col + 0.5) * rect3.width() / 600, rect3.yMaximum() - (row + 0.5) * rect3.height() / 338)
    canvas.setExtent(rect3)
    controller.setCurrentFrameNumber(picks[2])  # the canvas shows map 12; Identify must read that one
    t_canvas = seconds_at(canvas.temporalRange().begin())
    tool = QgsMapToolIdentify(canvas)
    context = QgsIdentifyContext()
    context.setTemporalRange(at(frames[picks[2]]))
    from wadi2d_qgis import slider_layer

    slider_layer.recent.clear()
    h.log(f"canvas {canvas.width()} x {canvas.height()}, extent {canvas.extent().toString(1)}")
    found = tool.identify(QgsGeometry.fromPointXY(point), QgsMapToolIdentify.LayerSelection, [layer], QgsMapToolIdentify.RasterLayer, context)
    reading = found[0].mAttributes if found else {}
    h.log(f"what the tool asked: {list(slider_layer.recent)}")
    asked = [r for r in slider_layer.recent if r.get("identify")]
    h.check("the tool asked the provider once, at the slider's map", len(asked) == 1 and abs(asked[0]["t"] - t_canvas) < 300.0, (asked, t_canvas))
    # QGIS moves the point to the centre of the screen pixel under it: compare at that point
    at_x, at_y = (asked[0]["x"], asked[0]["y"]) if asked else (point.x(), point.y())
    direct, _ = client.ask({"op": "point", "t": t_canvas, "x": at_x, "y": at_y})
    h.log(f"identify at {point.x():.1f}, {point.y():.1f}: {reading}; engine {direct}")
    from qgis.core import Qgis

    own = provider.identify(point, Qgis.RasterIdentifyFormat.Value).results()
    one = provider.block(1, QgsRectangle(point.x() - 0.1, point.y() - 0.1, point.x() + 0.1, point.y() + 0.1), 1, 1).value(0, 0)
    by_frame = {k: client.ask({"op": "point", "t": frames[k], "x": point.x(), "y": point.y()})[0]["depth"] for k in range(len(frames))}
    h.log(f"provider identify {own}; one-pixel block {one}; by frame {by_frame}; tool layer {found[0].mLayer.name() if found else None}")
    named = {key.split(",")[0].lower(): value for key, value in reading.items()}
    try:
        depth_read = float(str(named.get("depth", "nan")))
    except ValueError:
        depth_read = float("nan")
    h.check("Identify gives depth, speed and class", {"depth", "speed", "hazard class"} <= set(named), list(reading))
    h.check("Identify reads the slider's map at the pixel", direct["depth"] is not None and abs(depth_read - direct["depth"]) < 1e-3, (depth_read, direct["depth"], direct["frame"]))
    h.check("one band each", [b[0] for b in BANDS] == ["depth", "speed", "hazard"])

    h.log("=== 8 the highest of the maps never passes the record")
    with_record = h.add_raster(run / "pixels" / "pixel_depth.tif", "record depth")
    rec = with_record.extent()
    sample = QgsRectangle(centre.x() - 400.0, centre.y() - 300.0, centre.x() + 400.0, centre.y() + 300.0)
    sample = sample.intersect(rec)
    pixel = info["pixel_m"]
    width, height = round(sample.width() / pixel), round(sample.height() / pixel)
    sample = QgsRectangle(sample.xMinimum(), sample.yMaximum() - height * pixel, sample.xMinimum() + width * pixel, sample.yMaximum())
    record = with_record.dataProvider().block(1, sample, width, height)
    over = 0.0
    for k in range(len(frames)):
        head, payload = client.ask({"op": "values", "t": frames[k], "extent": [sample.xMinimum(), sample.yMinimum(), sample.xMaximum(), sample.yMaximum()], "width": width, "height": height, "field": "depth", "nodata": 0.0})
        values = struct.unpack(f"{width * height}f", payload)
        for i in range(0, width * height, 7):
            r, c = divmod(i, width)
            rv = record.value(r, c)
            rv = 0.0 if record.isNoData(r, c) else rv
            over = max(over, values[i] - rv)
    h.check("no saved map stands above the record anywhere sampled", over <= 2e-4, over)

    h.log("=== 9 timings")
    h.log("TIMES " + json.dumps(times))
    (h.P / "w51_times.json").write_text(json.dumps(times, indent=1), encoding="utf-8")
    if OUT:
        import pathlib

        target = pathlib.Path(OUT)
        target.mkdir(parents=True, exist_ok=True)
        for picture in shots.glob("*.png"):
            shutil.copy(picture, target / picture.name)
        shutil.copy(h.P / "w51_times.json", target / "dock_times.json")
