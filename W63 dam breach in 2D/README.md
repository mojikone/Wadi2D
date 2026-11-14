# W63 dam breach in 2D

**Live.** Branch `feature/dam-breach-2d` off `feature/fast-products` at `5d6ced2`; not merged, not pushed.

His to-do of 2026-11-14: "dam breach in the 2D model", much needed. A dam on the grid is a crest line (or a shaped embankment) whose faces
are closed up to the crest (`W8`), with a pool that can start at a level (`W34`). This adds a breach on a named dam line.

## The rules and where they come from

Source of record: USACE HEC, *Using HEC-RAS for Dam Break Studies*, Training Document TD-39, August 2014 (pp. 8 to 20, Table 2, the
regressions), downloaded from hec.usace.army.mil on 2026-11-14 (not kept in git). The HEC-RAS 6.x online manual page for breaching was not
reachable (404 on the Confluence URL tried), so where TD-39 is silent the source is named below.

| Item | HEC-RAS (TD-39) | Here |
|---|---|---|
| Location | centre station of the breach on the dam | `station_m` along the dam line from its first vertex; default the lowest ground under the line |
| Failure mode | overtopping or piping | same, `mode` |
| Shape | final bottom elevation, bottom width, left and right side slopes H:V | `bottom_z`, `bottom_width_m`, `left_slope` (towards the first vertex), `right_slope` |
| Time | critical breach development time | `formation_time_s` |
| Progression | linear or sine wave | `linear`, or `sine` = (1 - cos(pi x)) / 2 of the elapsed share x. [Likely] the shape of HEC-RAS's curve: slow, fast, slow (Goodell, RASModel blog 2009); HEC does not publish the formula |
| Trigger | pool elevation; pool elevation plus duration; clock time | `level`, `level_duration` (the pool must stay at or above the level; a drop resets the clock), `time` |
| Weir coefficient | 2.6 to 3.3 US for earth dams (Table 2) | `weir_coefficient` default 1.44 SI (2.6 US); it replaces the face's crest cap, `Q = C A (A/T)^0.5` on the breach section, which is C L H^1.5 on a rectangle |
| Piping | orifice, coefficient 0.5 to 0.6 | `Q = C_p A (2 g H)^0.5`, `piping_coefficient` 0.5, H the pool over the pipe's centre or over the tailwater if higher |
| Pipe growth | not stated in TD-39 | [Guessing at HEC's exact rule] a rectangle from `piping_z` growing down to the bottom and as far up, width to the final width |
| Collapse | not published by HEC | when the pool falls to the pipe's top (reported for HEC-RAS on the RAS Solution forum, Kleinschmidt), or the pipe reaches the dam top, or at `collapse_ratio` of the breach height (Flood Modeller's collapse factor, 0.6 there); then an open breach keeping the pipe's bottom and width, growing on to the same final trapezoid |
| Estimators | Froehlich 1995a and 2008, MacDonald and Langridge-Monopolis 1984, Von Thun and Gillette 1990, Xu and Zhang 2009 | `estimator.method`: `froehlich_2008`, `macdonald_langridge_monopolis`, `von_thun_gillette`, with the equations of TD-39 pp. 17 to 20; they fill only what the job leaves out |

**Not built:** Froehlich 2016 and Xu and Zhang 2009 (Xu and Zhang's categorical coefficients were not read in full from TD-39; Froehlich 2016
is not in it, and I did not use a formula I could not cite); HEC-RAS's simplified physical breach (velocity against erosion rate) and mass
wasting; a user-defined progression table.

## How it works on the grid

- The breach takes the dam's open crest faces within 0.75 cell (plus half the crest width of an embankment) of its line, and the pixels
  along each face exactly as the table builder reads them (`_face_table`, the higher of the two pixels that meet at the face).
- **Self-check at the start of every run:** the unbreached faces are rebuilt from those pixels and compared with the tables the solver holds;
  more than 1 mm of invert or 0.1 % of a table refuses the breach in words (a lined channel or a Manning raster under the dam is not handled).
- Every `update_s` (default 5 s) the trigger is read on the two cells beside the face nearest the breach centre (the higher is the pool) and
  the faces the opening has reached are rebuilt: profile = max(ground without the dam, min(crested ground, breach surface)), so the breach
  never cuts the valley sides; the ground without the dam is the DEM under a crest line, the DEM before the edits under an embankment. The
  rebuilt invert, table top and area and conveyance table are written into the backend's own arrays (numpy or CuPy, one code path), so the
  kernels are untouched and CPU and GPU take the same numbers.
- Known events (the trigger time, the end of a held level, the end of formation) shorten the source window so a step lands on them exactly.
- A pipe is a pair of equal and opposite sources on the two cells, held to half the pool cell's water per update; the faces stay closed until
  the roof falls.
- Output: `series/breach_<dam>.csv` (t, formed share, bottom, bottom width, pipe top, pool level, tail level, pipe flow) and `breach` events
  (`start`, `collapse`, `formed`, `estimated`) in the progress stream.
- Refused in words: the quadtree mesh, corridors (strips), local time stepping, a resumed run, an unknown dam name, a bottom or pipe above the
  dam top, a station past the line's end.
- **Job only, no dock row:** a breach has 15 to 20 fields and two modes; a row in the Structures table would not be small. The dock is next if
  he wants it.

## Tests (`tests/engine/test_breach.py`, 10 tests, CPU) and the cases (`run_cases.py`)

Synthetic V valley of W34 (8 m cells on a 2 m DEM, falling 1 % east, sides 0.2 m/m), a crest line at 103 m across it, the pool started at
102.5 m (12,570 m3 on the grid), a free boundary at the east edge. Breach on the valley axis, bottom 98 m (the valley floor at the dam), 16 m
wide, side slopes 1:1, formed in 300 s.

| Check | Result |
|---|---|
| Unbreached faces rebuilt against the built tables | within 1 mm and 0.1 % (the run refuses otherwise; every case passed) |
| Final faces against the trapezoid | opened area under the crest within 3 % of the trapezoid cut between the ground and 103 m, sampled every 1 cm; the deepest face invert on the valley floor to one pixel's rise; faces outside the trapezoid unchanged bit for bit |
| Time trigger at 60 s | starts at 60.000000 s, formed at 360.000000 s |
| Level held 90 s (pool above 102 m from the start) | starts at 90.000000 s |
| A trigger never reached | storage and the line series below the dam equal to the run with no breach, to the digit |
| Mass balance, overtopping | 12,570.0 m3 at the start, 12.3 left, 12,557.7 out at the boundary; relative error 1.9e-9 CPU, -2.4e-9 GPU |
| Peak below the dam, linear / sine | 71.02 m3/s at 308 s / 81.22 m3/s at 278 s |
| GPU against CPU, overtopping | 71.02 m3/s at 308.399 s on both, the same storage to 0.1 m3 (one GPU run, the machine free of other Wadi2D jobs) |
| Piping from 100 m, trigger at 102 m, 600 s | pipe flow up to 46.8 m3/s, never above the orifice law; roof falls at 353 s with the pool at the pipe's top; then an open breach; peak below 51.3 m3/s; balance -1.1e-10 |
| Froehlich (2008) by hand, Von Thun and Gillette, MacDonald | equal to the equations of TD-39 |
| Refusals | unknown dam name and local time stepping refused in words |

Indicative only: Froehlich's (1995b) regression for the peak, Q = 0.607 V^0.295 h^1.24 with V 12,570 m3 and h 4.5 m, gives 64 m3/s against 71
here with a 300 s formation time chosen, not regressed. The pool is tiny (a test of mechanics, not of a dam).

Old jobs: `test_dam_levels.py`, `test_terrain.py`, `test_earthworks_solver.py`, `test_physics.py`, `test_dam_rows.py` and the plugin contract
pass (146 with the breach tests; the frozen schema sample regenerated for the new `breaches` section, insertions only). A job without
`breaches` keeps its hash. The full suite was not run (his rule: at merge).

## Not done

- No dock row; the time slider and Make map show the breach through the water only, the geometry is in the CSV.
- Not run on real ground (Bidah's or a Block 2 dam), nor on an embankment object (the code path is there; its "ground without the dam" is the
  raw DEM, so a channel cut beside the dam is undone under the breach).
- Cells beside a breached face keep their storage tables: a dam body standing in the DEM itself (not drawn as a line) keeps its volume in
  the cells; only the face opens.
- Trigger by level is checked every `update_s`, not every step (HEC-RAS: every step); a time trigger and a held level are exact.
- The breach weir coefficient is a cap on the 2D face flow, not HEC-RAS's weir equation with submergence; drowned flow is the 2D momentum
  equation's own.
