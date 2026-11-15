"""The gain on Block 2's saved runs 3 and 4, estimated: the step times measured on the run's own mesh
(``block2_step_time.py``) applied to the tiles each frame needed (``block2_tiles.py``).

    python block2_estimate.py <step time .json> <out .json> <name>=<tiles .json>=<loop seconds of the saved run> ...

The model of a step, from the timing: the squares cost in proportion to the awake tiles, the strip costs the same
whatever is awake (it is stepped whole). A sleeping tile saves what the timing of "all" against "new" gives per tile.
The frames count a tile as needed when it or a neighbour holds water; the rule as built wakes slightly fewer or more
(the timing's own awake count against the frame's is the correction, taken on the first run named, the one the
timing was made on, and used for the others). An estimate: nothing was rerun.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    timing = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2])
    frames: dict[float, dict[str, dict]] = {}
    for row in timing:
        frames.setdefault(row["frame_t_s"], {})[row["mode"]] = row
    tiles = timing[0]["tiles"]
    saved, strip, per_tile, all_ms, ratio = [], [], [], [], {}
    for t, modes in frames.items():
        asleep = tiles - modes["new"]["awake_tiles"]
        saved.append((modes["all"]["ms_per_step"] - modes["new"]["ms_per_step"]) / asleep)
        strip.append(modes["new"]["ms_per_step"] - modes["squares only"]["ms_per_step"])
        per_tile.append(modes["squares only"]["ms_per_step"] / modes["squares only"]["awake_tiles"])
        all_ms.append(modes["old"]["ms_per_step"])
        ratio[t] = modes["new"]["awake_tiles"]
    saved_ms = sum(saved) / len(saved)
    strip_ms = sum(strip) / len(strip)
    old_ms = sum(all_ms) / len(all_ms)
    report = {
        "from": str(sys.argv[1]), "tiles": tiles, "old_rule_ms_per_step": round(old_ms, 4),
        "saved_ms_per_sleeping_tile": round(saved_ms, 6), "strip_ms_per_step": round(strip_ms, 4),
        "squares_ms_per_awake_tile": round(sum(per_tile) / len(per_tile), 6),
        "strip_share_of_old_step": round(strip_ms / old_ms, 3), "runs": {},
    }  # fmt: skip
    scale = None
    for spec in sys.argv[3:]:
        name, path, loop_s = spec.split("=")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = data["rows"]
        steps = data["steps"]
        if scale is None:  # the rule as built against the frames' count, on the run the timing was made on (the first)
            fix = [ratio[t] / r["needed_tiles"] for t in ratio for r in rows if abs(r["t"] - t) < 1.0 and r["needed_tiles"]]
            scale = sum(fix) / len(fix) if fix else 1.0
        awake = sum(r["steps"] * min(r["needed_tiles"] * scale, tiles) for r in rows) / steps
        new_ms = old_ms - saved_ms * (tiles - awake)
        strip_share = data["needed_strip_cell_steps_share"]
        split_ms = new_ms - strip_ms * (1.0 - strip_share)
        saved_s = (old_ms - new_ms) * steps / 1000.0
        report["runs"][name] = {
            "steps": round(steps), "loop_s_of_the_saved_run": float(loop_s),
            "tiles_ever_wet": data["tiles_ever_wet"], "tiles_ever_needed": data["tiles_ever_needed"],
            "wet_squares_share_of_cell_steps": round(data.get("wet_lattice_cell_steps_share", 0.0), 3),
            "needed_tile_steps_share_by_frames": round(data["needed_tile_steps_share"], 3),
            "rule_as_built_over_frames_count": round(scale, 3),
            "mean_awake_tiles": round(awake, 0), "tile_steps_saved_share": round(1.0 - awake / tiles, 3),
            "step_ms_old": round(old_ms, 3), "step_ms_new": round(new_ms, 3),
            "stepping_time_saved_share": round(1.0 - new_ms / old_ms, 3),
            "seconds_saved": round(saved_s, 0), "share_of_the_saved_loop": round(saved_s / float(loop_s), 3),
            "strip_cell_steps_needed_share": round(strip_share, 3),
            "step_ms_if_the_strip_slept_too": round(split_ms, 3),
            "stepping_time_saved_share_if_the_strip_slept_too": round(1.0 - split_ms / old_ms, 3),
            "band_rule_tile_steps_share": round(data.get("band_rule_tile_steps_share", 0.0), 3),
            "wet_tile_steps_share": round(data.get("wet_tile_steps_share", 0.0), 3),
        }  # fmt: skip
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
