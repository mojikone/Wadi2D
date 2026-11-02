# W23 mesh controls

```
[PRESERVE-CHECK] D3, mesh controls. Written before any edit, on 4ec2ac2.

KEEP (not touched, same numbers)
- The uniform path: grid, tables, cache key, solver, every output.
- A mesh job with no lines: same levels, same grid, same numbers, same job.json from the dock (no `lines` key).
- Stream rules, slope breaks, zones, refine_lines, lines_on_coarse_tiles, balance, QuadGrid, the refusals of mesh_grid.
- The mesh stays off by default. Section 2 keeps every widget it has, the preview, local time stepping.
- mesh_text for a preview with no lines, mesh.json's existing keys, the `mesh` event.

CHANGE
- schema.py: new RefineLine (name, coordinates, near_dx, rows, far_dx); new Mesh.lines, default []. Adds; removes nothing.
  The frozen tests/plugin/schema_sample.json is regenerated to match.
- refine.py: new rung() (a size to the ladder, down), new band_levels(). zone_levels calls rung() in place of its own
  identical expression: no change of behaviour, one rule for "a size on the ladder".
- build.py: lattice_levels also takes band_levels; new line_sizes() (asked and actual, per line); MeshReport gains `lines`;
  report() takes them; build_grid refuses a line that reaches no active cell.
- cli.py: `wadi2d mesh` passes the line sizes to the report.
- run.py: a run with rounded line sizes warns once per line.
- plugin job_builder.py: new notes, problems and job keys for lines, `mesh_lines.geojson` in inputs/.
- plugin protocol.py: mesh_text adds the lines when there are any.
- plugin sections/mesh.py: a line layer, a table of near, rows, far with actual near and far beside them, a note.
- plugin dock.py: passes the finest cell to the section, which never reads another section.
- New: plugin mesh_rows.py (rows, no Qt), plugin sections/mesh_lines.py (the table), tests, this folder.

FILES
wadi2d/config/schema.py, wadi2d/mesh/refine.py, wadi2d/mesh/build.py, wadi2d/engine/cli.py, wadi2d/run.py,
plugin/wadi2d_qgis/{job_builder,protocol,dock,mesh_rows,README}, plugin/wadi2d_qgis/sections/{mesh,mesh_lines},
tests/engine/test_mesh_lines.py, tests/plugin/{test_mesh_rows,test_job_builder,test_contract,test_protocol}.py,
tests/plugin/schema_sample.json.
```
