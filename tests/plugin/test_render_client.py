# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The plugin's end of ``wadi2d render`` against the real engine: start, ask from several threads, fail in words."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import numpy as np
import pytest
from wadi2d_qgis import render_client
from wadi2d_qgis.protocol import render_args

from tests.render.conftest import finished  # noqa: F401 - the fixture: a small finished run with saved maps

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def engine_text(tmp_path_factory) -> str:
    """This checkout's engine, as the dock checks start it: the venv's own install may be another checkout."""
    shim = tmp_path_factory.mktemp("render_engine") / "engine.py"
    shim.write_text(
        f"import sys\nsys.path.insert(0, {str(ROOT)!r})\nfrom wadi2d.engine.cli import main\nraise SystemExit(main())\n",
        encoding="utf-8",
    )
    return f'"{sys.executable}" "{shim}"'


def test_render_arguments() -> None:
    assert render_args("run") == ["render", "run"]
    assert render_args("run", "cpu") == ["render", "run", "--backend", "cpu"]


def test_a_client_starts_answers_from_threads_and_closes(finished, engine_text) -> None:  # noqa: F811
    client = render_client.RenderClient(engine_text, finished.run, "cpu").start()
    try:
        assert client.wait_ready(300), client.error
        ready = client.ready
        assert ready["detail"] == "pixel" and len(ready["frames_s"]) == 8
        request = {"op": "values", "t": ready["frames_s"][5], "extent": ready["extent"], "width": 50, "height": 25}
        heads, errors = [], []

        def ask(field: str) -> None:
            try:
                head, payload = client.ask({**request, "field": field, "nodata": -9999.0})
                heads.append((field, head, np.frombuffer(payload, np.float32)))
            except Exception as problem:  # noqa: BLE001
                errors.append(problem)

        threads = [threading.Thread(target=ask, args=(field,)) for field in ("depth", "speed", "hazard") * 3]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(120)
        assert not errors and len(heads) == 9
        for field, head, values in heads:
            assert head["ok"] and head["frame"] == 5 and values.size == 50 * 25, field
            assert (values == -9999.0).any() and (values > 0).any()
        same = [values for field, _head, values in heads if field == "depth"]
        assert all(np.array_equal(same[0], other) for other in same[1:])
        head, payload = client.ask({"op": "lines"})
        assert head["ok"] and isinstance(json.loads(payload), dict)
    finally:
        client.close()
    assert not client.alive
    with pytest.raises(render_client.RenderError):
        client.ask({"op": "stats"})


def test_a_folder_with_no_run_fails_in_words(tmp_path, engine_text) -> None:
    client = render_client.RenderClient(engine_text, tmp_path).start()
    try:
        assert not client.wait_ready(300)
        assert client.settled and "no finished run" in client.error
        with pytest.raises(render_client.RenderError, match="no finished run"):
            client.ask({"op": "stats"})
    finally:
        client.close()


def test_one_process_a_run(finished, engine_text) -> None:  # noqa: F811
    try:
        first = render_client.client_for(finished.run, engine_text, "cpu")
        assert render_client.client_for(str(finished.run), engine_text, "cpu") is first
        assert render_client.existing(finished.run) is first
        assert first.wait_ready(300)
        first.close()
        again = render_client.client_for(finished.run, engine_text, "cpu")
        assert again is not first and again.wait_ready(300)
    finally:
        render_client.close_all()
    assert render_client.existing(finished.run) is None
