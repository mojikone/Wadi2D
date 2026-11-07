"""The p01 variants set against ``gpu``: steps, the dam lines and rings (raw peak and 15-minute peak), the lumped network.

usage: python compare_p01.py [variant ...]   (default: every variant in results_p01.json)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "gpu"


def rel(a: float, b: float) -> float:
    return a / b - 1.0 if b else 0.0


def main(names: list[str]) -> None:
    results = json.loads((HERE / "results_p01.json").read_text(encoding="utf-8"))
    base = results[BASE]
    names = names or [n for n in results if n != BASE]
    table = {}
    for name in names:
        other = results[name]
        lines = {
            line: {
                "peak": rel(other["lines"][line]["peak"], b["peak"]),
                "peak_15min": rel(other["lines"][line]["peak_15min"], b["peak_15min"]),
                "volume": rel(other["lines"][line]["volume_m3"], b["volume_m3"]),
            }
            for line, b in base["lines"].items()
        }
        net = [abs(rel(other["network"][k], v)) for k, v in base["network"].items() if v]
        table[name] = {"steps": other["steps"] - base["steps"], "lines": lines, "network_worst": max(net, default=0.0)}
        print(f"\n{name} against {BASE}: steps {other['steps']} vs {base['steps']}, lumped network worst {max(net, default=0.0):.1e}")
        print(f"  {'line':16s} {'raw peak':>9s} {'15-min':>9s} {'volume':>9s}")
        for line, d in lines.items():
            print(f"  {line:16s} {d['peak']:+9.2%} {d['peak_15min']:+9.2%} {d['volume']:+9.2%}")
    (HERE / "compare_p01.json").write_text(json.dumps(table, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
