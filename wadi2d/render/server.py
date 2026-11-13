"""``wadi2d render <run>``: one process, kept open, that answers one drawing at a time over its standard streams.

It first says a line of JSON: ``{"ev": "ready", ...}`` with the frames, the extent, the CRS and how fine the run can be
drawn, after any ``{"ev": "wait", "message": ...}`` lines, or ``{"ev": "error", ...}`` and ends. Then each request is one
line of JSON and each answer one line of JSON followed by ``bytes`` raw bytes:

- ``{"op": "image", "t": seconds, "extent": [xmin, ymin, xmax, ymax], "width": w, "height": h, "field": "depth",
  "ramp": {...}, "wait_s": 0.4}``: a picture, 4 bytes a pixel, rows from the north (:mod:`wadi2d.render.colour`).
  ``t`` null is the last frame. ``wait_s`` null waits for the ground however long it takes; left out, it is the job's.
- ``{"op": "values", ...}``: the same without a ramp: float32 values, NaN where dry.
- ``{"op": "point", "t": seconds, "x": x, "y": y}``: depth, speed and class under a point, no bytes.
- ``{"op": "stats"}``: what was drawn so far. ``{"op": "quit"}``, or the end of the input, ends the process.

An answer carries ``frame`` and ``t_s`` (the saved map shown: the last at or before ``t``), ``detail`` (``pixel`` or
``cells``), ``pixel_m`` (metres one value covers) and ``pending`` (tiles of ground still being read: ask again for the
finer picture). A request that cannot be answered gets ``{"ok": false, "message": ...}`` and the process goes on.
Nothing is written into the run folder.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from wadi2d.products.pixels import to_host
from wadi2d.render.colour import to_bgra
from wadi2d.render.renderer import Drawn, FrameRenderer
from wadi2d.render.run_source import open_run
from wadi2d.render.view import View

EXIT_OK, EXIT_NO_RUN = 0, 3
UNSET = "unset"


def _ready(renderer: FrameRenderer) -> dict:
    source = renderer.source
    store = renderer.store
    return {
        "ev": "ready",
        "frames_s": source.times.tolist(),
        "extent": list(source.extent()),
        "crs": source.crs,
        "dx": source.dx,
        "pixel_m": store.pixel if store is not None else source.dx,
        "detail": source.detail,
        "note": source.note,
        "backend": renderer.backend,
        "cell_pixels": source.cfg.outputs.slider.cell_pixels,
        "depth_floor": source.cfg.outputs.pixels.depth_floor,
    }


class Server:
    def __init__(self, renderer: FrameRenderer) -> None:
        self.renderer = renderer
        self.drawn = 0
        self.spent_ms = 0.0
        self.frames: set[int] = set()
        self.last: dict = {}

    def _draw(self, request: dict) -> Drawn:
        view = View.of(request["extent"], request["width"], request["height"])
        wait_s = request.get("wait_s", UNSET)
        if wait_s == UNSET:
            wait_s = self.renderer.source.cfg.outputs.slider.ground_wait_s
        return self.renderer.draw(request.get("t"), view, request.get("field", "depth"), wait_s)

    def _head(self, drawn: Drawn, width: int, height: int) -> dict:
        self.frames.add(drawn.frame)
        return {
            "ok": True,
            "width": width,
            "height": height,
            "frame": drawn.frame,
            "t_s": drawn.t_s,
            "detail": drawn.detail,
            "pixel_m": drawn.pixel_m,
            "pending": drawn.pending,
            "backend": self.renderer.backend,
            "note": self.renderer.note,
        }

    def image(self, request: dict) -> tuple[dict, bytes]:
        if "ramp" not in request:
            raise ValueError("a picture needs a ramp: the colours are the asker's to choose")
        drawn = self._draw(request)
        picture = to_host(to_bgra(self.renderer.xp, drawn.values, request["ramp"]))
        return self._head(drawn, picture.shape[1], picture.shape[0]), np.ascontiguousarray(picture).tobytes()

    def values(self, request: dict) -> tuple[dict, bytes]:
        drawn = self._draw(request)
        values = np.ascontiguousarray(to_host(drawn.values), np.float32)
        return self._head(drawn, values.shape[1], values.shape[0]), values.tobytes()

    def point(self, request: dict) -> tuple[dict, bytes]:
        return {"ok": True, **self.renderer.point(request.get("t"), float(request["x"]), float(request["y"]))}, b""

    def stats(self, _request: dict) -> tuple[dict, bytes]:
        store = self.renderer.store
        found = {
            "ok": True,
            "drawn": self.drawn,
            "mean_ms": round(self.spent_ms / self.drawn, 2) if self.drawn else 0.0,
            "frames": sorted(self.frames),
            "last": self.last,
            "ground_tiles": len(store.tiles) if store is not None else 0,
            "ground_mb": round(store.held / 1024.0**2, 1) if store is not None else 0.0,
            "ground_reads": store.read_count if store is not None else 0,
            "backend": self.renderer.backend,
        }
        return found, b""

    def answer(self, request: dict) -> tuple[dict, bytes]:
        op = request.get("op")
        call = {"image": self.image, "values": self.values, "point": self.point, "stats": self.stats}.get(op)
        if call is None:
            return {"ok": False, "message": f"no operation {op!r}"}, b""
        start = time.perf_counter()
        try:
            head, payload = call(request)
        except Exception as error:  # one drawing that cannot be made must not end the process the next one needs
            return {"ok": False, "message": f"{type(error).__name__}: {error}"}, b""
        head["ms"] = round((time.perf_counter() - start) * 1000.0, 2)
        if op in ("image", "values"):
            self.drawn += 1
            self.spent_ms += head["ms"]
            self.last = {key: head[key] for key in ("frame", "detail", "pixel_m", "pending", "ms", "width", "height")}
        return head, payload


def serve(run: Path, backend: str | None, source_in, sink) -> int:
    """Answer requests read from ``source_in`` on ``sink``, both binary, until told to quit or the input ends."""

    def send(head: dict, payload: bytes = b"") -> None:
        sink.write(json.dumps({**head, "bytes": len(payload)}).encode("utf-8") + b"\n")
        if payload:
            sink.write(payload)
        sink.flush()

    try:
        source = open_run(run, lambda text: send({"ev": "wait", "message": text}))
        renderer = FrameRenderer(source, backend or "auto")
    except (ValueError, OSError, RuntimeError) as error:
        send({"ev": "error", "message": str(error)})
        return EXIT_NO_RUN
    server = Server(renderer)
    send(_ready(renderer))
    try:
        for line in iter(source_in.readline, b""):
            if not line.strip():
                continue
            try:
                request = json.loads(line)
            except ValueError:
                send({"ok": False, "message": "a request is one line of JSON"})
                continue
            if not isinstance(request, dict) or request.get("op") == "quit":
                break
            send(*server.answer(request))
    finally:
        renderer.close()
    return EXIT_OK
