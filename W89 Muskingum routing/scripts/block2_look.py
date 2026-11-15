"""What Block 2's HMS project holds for the W89 comparison: the depth-area analyses on Basin 3, their points with
drainage areas, and the reaches. Reads the project; writes nothing.

Usage (repo root on PYTHONPATH): ``python block2_look.py``.
"""

from __future__ import annotations

from pathlib import Path

from wadi2d.hms import load_basin, load_nals, load_project
from wadi2d.hms.methods import MuskingumCungeRoute
from wadi2d.hydrology.replication import _Project

PROJECT = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")


def main() -> None:
    source = next(PROJECT.glob("*.hms"))
    print(source.name)
    project = load_project(source)
    print("basins:", list(project.basins))
    for analysis in load_nals(source.with_suffix(".nals")).analyses:
        if analysis.basin_model_name and analysis.basin_model_name.endswith("3"):
            print(f"{analysis.name!r}: met {analysis.met_model_name!r}, {analysis.time_interval} min, "
                  f"{analysis.start} to {analysis.end}, points {analysis.points}")
    held = _Project(source)
    _hms_basin, engine = held.model("Basin 3")
    basin = engine.basin
    kinds: dict[str, list[str]] = {}
    for name, element in basin.elements.items():
        kinds.setdefault(type(element).__name__, []).append(name)
    for kind, names in kinds.items():
        print(kind, len(names), names)
    for name in kinds.get("Reservoir", []) + kinds.get("Junction", []):
        print(f"  {name}: {basin.drainage_area(name):.2f} km2, drains to {basin.elements[name].downstream}")
    for name, element in load_basin(project.path_of(project.basins["Basin 3"])).reaches.items():
        route = element.route
        if isinstance(route, MuskingumCungeRoute):
            print(f"  {name}: L {route.length} m, S {route.energy_slope}, n {route.mannings_n}, b {route.bottom_width}, "
                  f"z {route.side_slope}, index c {route.index_celerity}, to {element.downstream}")
        else:
            print(f"  {name}: {element.route_method}, to {element.downstream}")


if __name__ == "__main__":
    main()
