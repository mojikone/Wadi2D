"""``wadi2d render``: the protocol, in process and as the process the plugin starts."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tests.render.conftest import Finished
from wadi2d.render.server import EXIT_NO_RUN, EXIT_OK, serve

REPO = Path(__file__).resolve().parents[2]
RAMP = {"kind": "interpolated", "stops": [[0.0, 0, 0, 255, 0], [1.0, 0, 0, 255, 255]]}


def answers(stream: bytes) -> list[tuple[dict, bytes]]:
    """Every head of a reply stream and the bytes after it."""
    found, at = [], 0
    while at < len(stream):
        end = stream.index(b"\n", at)
        head = json.loads(stream[at:end])
        at = end + 1
        found.append((head, stream[at : at + head["bytes"]]))
        at += head["bytes"]
    return found


def talk(run: Path, requests: list[dict]) -> tuple[int, list[tuple[dict, bytes]]]:
    source = io.BytesIO(b"".join(json.dumps(r).encode() + b"\n" for r in requests))
    sink = io.BytesIO()
    code = serve(run, "cpu", source, sink)
    return code, answers(sink.getvalue())


def test_ready_then_one_answer_a_request(finished: Finished) -> None:
    west, south, east, north = 0.0, 0.0, 0.0, 0.0
    code, got = talk(finished.run, [{"op": "stats"}])
    assert code == EXIT_OK
    ready = got[0][0]
    assert ready["ev"] == "ready" and ready["detail"] == "pixel" and ready["backend"] == "cpu"
    assert len(ready["frames_s"]) == 8 and ready["frames_s"] == sorted(ready["frames_s"])
    west, south, east, north = ready["extent"]
    assert east > west and north > south and ready["crs"]
    assert got[1][0]["ok"] and got[1][0]["drawn"] == 0


def test_image_values_point_and_their_frame(finished: Finished) -> None:
    _code, first = talk(finished.run, [{"op": "stats"}])
    ready = first[0][0]
    extent = ready["extent"]
    t = ready["frames_s"][5] + 10.0
    view = {"t": t, "extent": extent, "width": 120, "height": 60, "field": "depth", "wait_s": None}
    x, y = (extent[0] + extent[2]) / 2.0, (extent[1] + extent[3]) / 2.0
    _code, got = talk(
        finished.run,
        [
            {"op": "image", **view, "ramp": RAMP},
            {"op": "values", **view},
            {"op": "values", **view, "nodata": -9999.0},
            {"op": "point", "t": t, "x": x, "y": y},
            {"op": "image", **view},
            {"op": "nonsense"},
            {"op": "stats"},
        ],
    )
    (image, picture), (values, raw), (filled, raw_filled), (point, _), (refused, _), (unknown, _), (stats, _) = got[1:]
    assert image["ok"] and image["frame"] == 5 and image["t_s"] == ready["frames_s"][5]
    assert len(picture) == 120 * 60 * 4
    depth = np.frombuffer(raw, np.float32).reshape(60, 120)
    assert values["frame"] == 5 and values["detail"] in ("pixel", "cells") and np.isnan(depth).any() and (depth > 0).any()
    same = np.frombuffer(raw_filled, np.float32).reshape(60, 120)
    assert np.array_equal(np.where(np.isnan(depth), -9999.0, depth), same) and filled["ok"]
    alpha = np.frombuffer(picture, np.uint8).reshape(60, 120, 4)[:, :, 3]
    assert np.array_equal(alpha == 0, np.isnan(depth) | (depth <= 0.0))  # a dry pixel is clear, a wet one is not
    assert point["ok"] and point["frame"] == 5 and set(point) >= {"depth", "speed", "hazard", "pixel_m"}
    assert not refused["ok"] and "ramp" in refused["message"]
    assert not unknown["ok"] and "nonsense" in unknown["message"]
    assert stats["drawn"] == 3 and stats["frames"] == [5]


def test_result_lines_are_served_as_wadi2d_lines_gives_them(finished: Finished) -> None:
    from wadi2d.products.result_lines import catalogue, read_line

    _code, first = talk(finished.run, [{"op": "stats"}])
    west, south, east, north = first[0][0]["extent"]
    middle = (west + east) / 2.0
    coordinates = [[middle, south + 10.0], [middle, north - 10.0]]
    _code, got = talk(finished.run, [{"op": "lines"}, {"op": "line", "coordinates": coordinates, "name": "across"}])
    (listed, listed_bytes), (line, line_bytes) = got[1:]
    assert listed["ok"] and json.loads(listed_bytes) == json.loads(json.dumps(catalogue(finished.run)))
    assert line["ok"] and json.loads(line_bytes) == json.loads(json.dumps(read_line(finished.run, coordinates, "across")))


def test_a_folder_with_no_run_says_so_and_ends(tmp_path: Path) -> None:
    code, got = talk(tmp_path, [{"op": "stats"}])
    assert code == EXIT_NO_RUN and got[0][0]["ev"] == "error" and "no finished run" in got[0][0]["message"]


def test_the_process_keeps_its_output_for_the_protocol(finished: Finished) -> None:
    """The real command, real pipes: whatever a library prints must not land between two pictures."""
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    args = [sys.executable, "-m", "wadi2d.engine.cli", "render", str(finished.run), "--backend", "cpu"]
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        ready = json.loads(process.stdout.readline())
        assert ready["ev"] == "ready"
        request = {"op": "values", "t": None, "extent": ready["extent"], "width": 64, "height": 32, "field": "speed"}
        for _ in range(2):
            process.stdin.write(json.dumps(request).encode() + b"\n")
            process.stdin.flush()
            head = json.loads(process.stdout.readline())
            assert head["ok"] and head["bytes"] == 64 * 32 * 4
            assert len(process.stdout.read(head["bytes"])) == head["bytes"]
        process.stdin.write(b'{"op": "quit"}\n')
        process.stdin.flush()
        assert process.wait(timeout=60) == EXIT_OK
        assert process.stdout.read() == b""
    finally:
        if process.poll() is None:
            process.kill()


@pytest.mark.gpu
def test_the_gpu_process_draws(finished: Finished) -> None:
    from wadi2d.products.pixels import array_module

    if array_module("auto") is np:
        pytest.skip("no GPU")
    source = io.BytesIO(b'{"op": "stats"}\n')
    sink = io.BytesIO()
    assert serve(finished.run, "gpu", source, sink) == EXIT_OK
    assert answers(sink.getvalue())[0][0]["backend"] == "gpu"
