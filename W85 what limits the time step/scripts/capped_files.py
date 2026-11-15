"""Run test files one at a time, each in its own process under the memory cap of ``capped_pytest.py``.

    python capped_files.py <limit GB> <log file> <test file> [<test file> ...]

CPU only (the GPU is hidden), four Numba threads, GPU-marked tests deselected. One line per file in the log: its
pytest summary, or the first MemoryError line when the cap stopped an allocation.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    limit, log = sys.argv[1], Path(sys.argv[2])
    env = os.environ | {"CUDA_VISIBLE_DEVICES": "-1", "NUMBA_NUM_THREADS": "4"}
    capped = str(Path(__file__).with_name("capped_pytest.py"))
    with log.open("w", encoding="utf-8") as out:
        for target in sys.argv[3:]:
            t0 = time.time()
            done = subprocess.run(
                [sys.executable, capped, limit, "-q", "-m", "not gpu", target],
                capture_output=True,
                text=True,
                env=env,
            )
            lines = [ln for ln in done.stdout.splitlines() if ln.strip()]
            memory = [ln.strip() for ln in lines if "MemoryError" in ln or "Unable to allocate" in ln]
            failed = [ln.strip() for ln in lines if ln.startswith("FAILED")]
            last = lines[-1].strip() if lines else done.stderr.strip()[-200:]
            out.write(f"{target}: {last} [{time.time() - t0:.0f} s]\n")
            for ln in (failed + memory[:2])[:6]:
                out.write(f"    {ln[:240]}\n")
            out.flush()


if __name__ == "__main__":
    main()
