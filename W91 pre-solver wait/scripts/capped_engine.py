"""The engine's command line under a commit cap: ``python capped_engine.py <GB> <wadi2d args ...>``.

The cap is W85's (``scripts/capped_pytest.py`` there): a job object with a per-process commit limit, so a runaway
allocation fails at its own line and the machine never sees it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W85 what limits the time step\scripts")
from capped_pytest import cap_memory  # noqa: E402

def _peaks_every(seconds: float, path: Path) -> None:
    """This process's peak working set and peak commit, GB, rewritten into ``path`` every ``seconds``: the run is
    stopped from outside at the solver's first step, and the venv's launcher is not the process that holds the memory."""
    import ctypes
    import threading
    import time
    from ctypes import wintypes

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from s01_cold_build import _Counters

    psapi = ctypes.WinDLL("psapi")
    k32 = ctypes.WinDLL("kernel32")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]

    def loop() -> None:
        while True:
            c = _Counters()
            c.cb = ctypes.sizeof(c)
            psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
            path.write_text(f"{c.PeakWorkingSetSize / 2**30:.2f}\t{c.PeakPagefileUsage / 2**30:.2f}\n", encoding="utf-8")
            time.sleep(seconds)

    threading.Thread(target=loop, daemon=True).start()


if __name__ == "__main__":
    cap_memory(float(sys.argv[1]))
    out = Path(sys.argv[sys.argv.index("--out") + 1])
    _peaks_every(2.0, out.parent / f"{out.name}.peak.tsv")
    sys.argv = ["wadi2d", *sys.argv[2:]]
    sys.path.pop(0)  # this folder; the engine's code comes from PYTHONPATH (this checkout's, or a copy of another)
    from wadi2d.engine.cli import main

    print(f"# engine code: {Path(sys.modules['wadi2d.engine.cli'].__file__).parents[2]}", flush=True)

    raise SystemExit(main())
