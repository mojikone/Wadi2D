"""Make the Faydh copies of the ras_rain_on_grid scripts. W1 stays as it is; every change is an assert-checked replace."""
from pathlib import Path

W1 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\ras_rain_on_grid")
HERE = Path(__file__).resolve().parent


def cp(name, pairs):
    s = (W1 / name).read_text(encoding="utf-8")
    for a, b in pairs:
        assert a in s, (name, a)
        s = s.replace(a, b)
    (HERE / name).write_text(s, encoding="utf-8")


cp("s01_domain.py", [
    ('    s13 = max(polygons()[case.SUBBASIN].geoms, key=lambda g: g.area)\n    box = geometry.box(case.BOX_WEST, case.BOX_SOUTH, case.BOX_EAST, case.Y0)\n',
     '    p = polygons()\n    s13 = shapely.union_all([p[n].buffer(1.0) for n in case.SUBBASINS]).buffer(-1.0)\n    box = geometry.box(case.BOX_WEST, case.BOX_SOUTH, case.BOX_EAST, case.BOX_NORTH)\n'),
    ('from shapely import geometry\n', 'import shapely\nfrom shapely import geometry\n'),
    ('    strip[0, i_west:nx] = True  # north of the north outlet\n    strip[1:j_south, nx] = True  # east of the east outlet\n',
     '    j_north = 1 + round((case.Y0 - case.BOX_NORTH) / dx)\n    strip[j_north:j_south, nx] = True  # east of the east outlet\n'),
    ('        "east_outlet": [[case.BOX_EAST - d, case.BOX_SOUTH + d], [case.BOX_EAST - d, case.Y0 - d]],\n        "north_outlet": [[case.BOX_EAST - d, case.Y0 - d], [case.BOX_WEST + d, case.Y0 - d]],\n',
     '        "east_outlet": [[case.BOX_EAST - d, case.BOX_SOUTH + d], [case.BOX_EAST - d, case.BOX_NORTH - d]],\n'),
    ('"properties": {"name": "bidah"}', '"properties": {"name": "faydh"}'),
    ('        prj = case.HERE.parent / "ras_head_to_head" / "ras_common" / "Projection UTM40.prj"\n',
     '        prj = case.W1.parent / "ras_head_to_head" / "ras_common" / "Projection UTM40.prj"\n'),
])

cp("build_case.py", [
    ('import case\nimport ras_text\n', 'import case\nimport sys\nsys.path.insert(0, str(case.W1))\nimport ras_text\n'),
    ('name="Bidah", title=f"Bidah rain on grid {name}"', 'name="Faydh", title=f"Faydh rain on grid {name}"'),
    ('map_interval: str, ', 'map_interval: str, ') if False else ('cores=cores, step="10SEC", map_interval=map_interval,\n        bc_lines={"OutEast": np.array(per["east_outlet"]), "OutNorth": np.array(per["north_outlet"])},',
     'cores=cores, step="10SEC", map_interval=map_interval,\n        bc_lines={"OutEast": np.array(per["east_outlet"])},'),
    ('            {"kind": "normal", "slope": case.SLOPE_OUT,\n             "coordinates": [[case.BOX_WEST + h, case.Y0 + h], [case.BOX_EAST - h, case.Y0 + h]]},\n', ''),
    ('             "coordinates": [[case.BOX_EAST + h, case.BOX_SOUTH + h], [case.BOX_EAST + h, case.Y0 - h]]},\n',
     '             "coordinates": [[case.BOX_EAST + h, case.BOX_SOUTH + h], [case.BOX_EAST + h, case.BOX_NORTH - h]]},\n'),
    ('"Rain-on-grid head-to-head, same case as the RAS project"', '"Faydh rain-on-grid head-to-head, same case as the RAS project"'),
    ('    ap.add_argument("--map", default="1MIN")\n', '    ap.add_argument("--map", default="2MIN")\n'),
    ('        cfg = case.WADI_VARIANTS[a.name]\n', '        cfg = case.CONFIGS[a.name]\n'),
    ('    wadi_job(a.name, cfg)\n    else:', '    wadi_job(a.name, cfg)\n    else:') if False else ('from __future__ import annotations\n', 'from __future__ import annotations\n'),
])

cp("compare.py", [
    ('SUM2D = BASE + "/Summary Output/2D Flow Areas/Bidah"', 'SUM2D = BASE + "/Summary Output/2D Flow Areas/Faydh"'),
    ('"Bidah.p01.hdf"', '"Faydh.p01.hdf"'),
    ('f["Geometry/2D Flow Areas/Bidah"]', 'f["Geometry/2D Flow Areas/Faydh"]'),
    ('ts["2D Flow Areas/Bidah"]', 'ts["2D Flow Areas/Faydh"]'),
    ('f[TS]["2D Flow Areas/Bidah"]', 'f[TS]["2D Flow Areas/Faydh"]'),
    ('for k in ("OutEast", "OutNorth"):', 'for k in ("OutEast",):'),
    ('    i_w = round((case.BOX_WEST - case.X0) / dx)\n    j_s = round((case.Y0 - case.BOX_SOUTH) / dx)\n    outlet[0, i_w:] = True\n    outlet[:j_s, -1] = True\n',
     '    j_n = round((case.Y0 - case.BOX_NORTH) / dx)\n    j_s = round((case.Y0 - case.BOX_SOUTH) / dx)\n    outlet[j_n:j_s, -1] = True\n'),
    ('label="HMS-equivalent, S13"', 'label="HMS, Faydh 01"'),
])
