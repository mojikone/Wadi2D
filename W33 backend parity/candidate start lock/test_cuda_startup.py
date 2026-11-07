"""Engines that start the GPU at the same moment all run (W33: one of two crashed, 5 pairs of 5, before the lock)."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import pytest
from wadi2d.solver.gpu.startup import _StartLock

RACERS = 3
ROUNDS = 4
FIRST_TOUCH = "from wadi2d.solver.gpu.startup import cuda_device_count; print(cuda_device_count())"
ROOT = Path(__file__).resolve().parents[2]


def race(code: str) -> list[subprocess.CompletedProcess]:
    done: dict[int, subprocess.CompletedProcess] = {}

    def go(k: int) -> None:
        done[k] = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)

    threads = [threading.Thread(target=go, args=(k,)) for k in range(RACERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return list(done.values())


@pytest.mark.gpu
def test_processes_that_start_the_gpu_together_all_survive() -> None:
    for _ in range(ROUNDS):
        for result in race(FIRST_TOUCH):
            assert result.returncode == 0, result.stderr[-2000:]
            assert int(result.stdout.strip().splitlines()[-1]) > 0


def test_the_start_lock_is_exclusive_and_a_hung_holder_does_not_block_forever(tmp_path: Path) -> None:
    path = tmp_path / "start.lock"
    with _StartLock(path) as first:
        assert first.held
        with _StartLock(path, wait_limit_s=0.2) as second:
            assert not second.held
    with _StartLock(path) as again:
        assert again.held
