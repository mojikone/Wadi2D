"""What makes a run's results.h5 large, and what other storage of the same numbers would take: read only.

    python s07_results_size.py RUN OUT.json [--maps N]

Every field of N saved maps (spread over the run) is written again into a scratch file with each layout below and
the bytes are counted; the figures are scaled to all the run's maps. Lossless layouts give back every bit (checked);
the lossy ones are reported with their largest error and are not proposed for the record.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

import h5py
import numpy as np

LAYOUTS = {
    "as_written_gzip1": dict(compression="gzip", compression_opts=1),
    "shuffle_gzip1": dict(compression="gzip", compression_opts=1, shuffle=True),
    "shuffle_gzip4": dict(compression="gzip", compression_opts=4, shuffle=True),
    "shuffle_lzf": dict(compression="lzf", shuffle=True),
}
LATTICE_CHUNK = (128, 128)
STRIP_CHUNKS = {"as_written": (1, 128), "wide": (1, 65536)}


def field_bytes(values: np.ndarray, chunks, layout: dict) -> tuple[int, float, bool]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "f.h5"
        began = time.time()
        with h5py.File(path, "w") as f:
            f.create_dataset("v", data=values, chunks=chunks, **layout)
        written = time.time() - began
        with h5py.File(path, "r") as f:
            same = bool(np.array_equal(f["v"][:], values, equal_nan=True))
        return path.stat().st_size, written, same


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--maps", type=int, default=4)
    args = parser.parse_args()
    results = args.run / "results.h5"
    report: dict = {"run": str(args.run)}
    with h5py.File(results, "r") as f:
        names = list(f["maps"])
        report["maps"] = len(names)
        report["file_gb"] = round(results.stat().st_size / 2**30, 2)
        stored: dict = {}

        def tally(name, obj):
            if isinstance(obj, h5py.Dataset):
                top = name.split("/")[0]
                field = name.split("/")[-1] if top == "maps" else top
                stored[field] = stored.get(field, 0) + obj.id.get_storage_size()

        f.visititems(tally)
        report["stored_gb_by_field"] = {k: round(v / 2**30, 3) for k, v in sorted(stored.items(), key=lambda kv: -kv[1])}
        mask = f["mask"][:]
        report["lattice_cells"] = int(mask.size)
        report["active_cells"] = int(mask.sum())
        picks = [names[int(i)] for i in np.linspace(0, len(names) - 1, args.maps)]
        totals: dict = {}
        for name in picks:
            group = f["maps"][name]
            for field in group:
                values = group[field][:]
                strip = field.startswith("strip_")
                chunk_sets = STRIP_CHUNKS if strip else {"as_written": LATTICE_CHUNK}
                for chunk_name, chunks in chunk_sets.items():
                    for layout_name, layout in LAYOUTS.items():
                        size, seconds, same = field_bytes(values, chunks, layout)
                        key = f"{'strip' if strip else 'lattice'}:{chunk_name}:{layout_name}"
                        held = totals.setdefault(key, {"bytes": 0, "seconds": 0.0, "lossless": True})
                        held["bytes"] += size
                        held["seconds"] += seconds
                        held["lossless"] &= same
                if not strip:  # the record's depth and speed in millimetres as 16-bit integers: lossy, for scale
                    scaled = np.clip(np.round(values * 1000.0), 0, 65535).astype(np.uint16)
                    size, _s, _same = field_bytes(scaled, LATTICE_CHUNK, LAYOUTS["shuffle_gzip4"])
                    held = totals.setdefault("lattice:as_written:uint16_mm_lossy", {"bytes": 0, "seconds": 0.0, "lossless": False})
                    held["bytes"] += size
                    held["max_error"] = max(held.get("max_error", 0.0), float(np.abs(scaled / 1000.0 - values).max()))
        scale = len(names) / len(picks)
        report["all_maps_gb"] = {
            key: {"gb": round(v["bytes"] * scale / 2**30, 2), "write_s_per_map": round(v["seconds"] / len(picks), 2),
                  "lossless": v["lossless"], **({"max_error": round(v["max_error"], 5)} if "max_error" in v else {})}
            for key, v in totals.items()
        }  # fmt: skip
    args.out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
