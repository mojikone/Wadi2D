"""The timing series of the README, one case after another, each in a fresh process; results appended to a file.

Args: scratch_folder old_package_folder results_file [only]. ``scratch_folder`` holds the cache folders (``cfull_new``
with the store made, ``cfull_base``, ``cground``) and the kept mesh; ``old_package_folder`` is the tree of the commit
before W84 (``git archive 5c7c285 wadi2d``). ``only`` picks the groups to run, a comma list of tables, cold, ground,
strips, strips_old.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEW = HERE.parent.parent
scratch, old, results = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
only = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else {"tables", "cold", "ground", "strips"}
TABLES, GROUND = str(HERE / "time_tables.py"), str(HERE / "time_ground.py")


def run(label: str, package: Path, args: list[str]) -> None:
    env = {**os.environ, "PYTHONPATH": str(package)}
    t0 = time.perf_counter()
    done = subprocess.run([sys.executable, *args], env=env, capture_output=True, text=True, cwd=str(NEW))
    lines = [
        line
        for line in done.stdout.splitlines()
        if line.startswith(("squares", "strips", "{", "ground in", "tables in", "hashed"))
    ]
    if done.returncode:
        lines.append("FAILED: " + done.stderr.strip().splitlines()[-1])
    with open(results, "a", encoding="utf-8") as f:
        f.write(f"## {label} ({time.perf_counter() - t0:.0f} s)\n" + "\n".join(lines) + "\n")
    print(label, "done", flush=True)


if "tables" in only:
    for workers in (16, 8, 4, 1):
        run(
            f"tables old w={workers}",
            old,
            [TABLES, "squares", "full", "1", str(scratch / "cfull_base"), "--workers", str(workers)],
        )
        run(
            f"tables new warm w={workers}",
            NEW,
            [TABLES, "squares", "full", "1", str(scratch / "cfull_new"), "--workers", str(workers)],
        )
    run(
        "tables new warm w=32",
        NEW,
        [TABLES, "squares", "full", "1", str(scratch / "cfull_new"), "--workers", "32"],
    )
if "cold" in only:
    cold = scratch / "cfull_cold"
    shutil.rmtree(cold, ignore_errors=True)
    run(
        "tables new cold w=16",
        NEW,
        [
            TABLES,
            "squares",
            "full",
            "1",
            str(cold),
            "--workers",
            "16",
            "--hash",
            str(scratch / "sqfull_cold.json"),
        ],
    )
    for workers in (
        8,
        4,
        1,
    ):  # the store's first fill alone, at fewer threads: the domain mask of a fresh folder
        shutil.rmtree(cold, ignore_errors=True)
        run(
            f"tables new cold w={workers}",
            NEW,
            [TABLES, "squares", "full", "1", str(cold), "--workers", str(workers)],
        )
    shutil.rmtree(cold, ignore_errors=True)
if "ground" in only:
    held = str(scratch / "cground")
    for workers in (16, 8, 4, 1):
        run(f"ground old w={workers}", old, [GROUND, held, "none", str(workers)])
        run(f"ground new warm w={workers}", NEW, [GROUND, held, held, str(workers)])
    cold = scratch / "cground_cold"
    shutil.rmtree(cold, ignore_errors=True)
    run("ground new cold w=16", NEW, [GROUND, held, str(cold), "16"])
    shutil.rmtree(cold, ignore_errors=True)
if "strips" in only:
    mesh = ["--mesh", str(scratch / "mesh_full.pkl")]
    run(
        "strips new warm w=16",
        NEW,
        [
            TABLES,
            "strips",
            "full",
            "1",
            str(scratch / "cfull_new"),
            "--workers",
            "16",
            "--hash",
            str(scratch / "stfull_new.json"),
            *mesh,
        ],
    )
    if "strips_old" in only:
        run(
            "strips old w=16",
            old,
            [
                TABLES,
                "strips",
                "full",
                "1",
                str(scratch / "cfull_base"),
                "--workers",
                "16",
                "--hash",
                str(scratch / "stfull_base.json"),
                *mesh,
            ],
        )
