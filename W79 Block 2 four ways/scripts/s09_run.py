"""Run one rerun job on the GPU, one job at a time: wait until no other engine run (another worker's, W82's) and no
other worker's driver holds the GPU, then ``wadi2d run``, then ``s04_check.py``.

Usage: s09_run.py <run number>. Writes runs/<name>.log (the engine's progress lines, each stamped with the seconds since
the start), runs/<name>.memory.tsv (the run's memory and the card's, every 5 s), runs/<name>.wait.json (how long it
waited and for what) and runs/<name>.wall.json (start, end, exit code).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w79 import JOBS, REPO, RUN_NAMES, RUNS, write_json  # noqa: E402

POLL_S = 60.0
BUSY = ("wadi2d.engine.cli run", "wadi2d.exe run", "wadi2d.exe\" run", "wadi2d.exe\" products", "wadi2d.exe\" frames", "block2.py\" run", "race.py", "s08_tables.py")
"""Command lines that hold or are about to hold the GPU: an engine run, or another worker's driver that starts them;
and this folder's own table build, which writes the cache the run reads."""


def busy() -> list[str]:
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name like 'python%' or Name like 'wadi2d%'\" | "
        "ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True).stdout
    me = str(Path(__file__).name)
    return [line for line in out.splitlines() if any(b in line for b in BUSY) and me not in line]


GPU_BUSY_PERCENT = 30
GPU_QUIET_SAMPLES = 3
"""Another worker's short GPU tests run through pytest, which ``busy`` does not name: the card must also read under
this utilisation in this many samples, 10 s apart, before a run starts."""


def gpu_percent() -> float:
    out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.split(",")
    return float(out[0]) if out and out[0].strip() else 0.0


def gpu_memory_gb() -> float:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.strip()
    return float(out) / 1024.0 if out else 0.0


def gpu_quiet() -> bool:
    for _ in range(GPU_QUIET_SAMPLES):
        if gpu_percent() > GPU_BUSY_PERCENT:
            return False
        time.sleep(10.0)
    return True


def watched(command: list[str], log_path: Path, marker: str, sample_path: Path) -> int:
    """The command with each line of its output stamped with the seconds since its start, and the memory of its
    processes (working set and commit, GB, summed over those whose command line holds ``marker``) and of the card
    sampled every 5 s."""
    import threading

    from s10_products import memory

    t0 = time.time()
    done = threading.Event()

    def sample() -> None:
        with sample_path.open("w", encoding="utf-8") as f:
            f.write("\t".join(("t_s", "working_set_gb", "commit_gb", "gpu_gb")) + "\n")
            while not done.is_set():
                ws, commit = memory(marker)
                row = (f"{time.time() - t0:.0f}", f"{ws:.2f}", f"{commit:.2f}", f"{gpu_memory_gb():.2f}")
                f.write("\t".join(row) + "\n")
                f.flush()
                done.wait(5.0)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(REPO))
        for line in proc.stdout:
            log.write(f"{time.time() - t0:9.1f} {line}")
            log.flush()
        code = proc.wait()
    done.set()
    thread.join()
    return code


def main(number: int) -> None:
    name = RUN_NAMES[number]
    t0 = time.time()
    seen = set()
    while True:
        others = busy()
        if not others and gpu_quiet():
            break
        if others:
            seen.update(o[:200] for o in others)
        else:
            seen.add("the card busy (another worker's GPU test)")
        time.sleep(POLL_S)
    write_json(RUNS / f"{name}.wait.json", {"waited_s": time.time() - t0, "for": sorted(seen)})
    exe = REPO / ".venv" / "Scripts" / "wadi2d.exe"
    start = time.time()
    command = [str(exe), "run", str(JOBS / f"{name}.json"), "--out", str(RUNS / name), "--backend", "gpu"]
    code = watched(command, RUNS / f"{name}.log", f"*run *{name}.json", RUNS / f"{name}.memory.tsv")
    write_json(RUNS / f"{name}.wall.json", {"start": start, "end": time.time(), "wall_s": time.time() - start,
                                            "exit": code})
    if code == 0:
        subprocess.run([sys.executable, str(Path(__file__).with_name("s04_check.py")), str(number)], cwd=str(REPO),
                       stdout=(RUNS / f"{name}.check.txt").open("w", encoding="utf-8"), stderr=subprocess.STDOUT)
    print(json.dumps({"run": number, "exit": code, "wall_s": time.time() - start}))


if __name__ == "__main__":
    main(int(sys.argv[1]))
