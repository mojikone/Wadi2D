# W97 domain from outline

**Status (2026-11-15): engine and command line built on `feature/domain-outline` (off `main` at v0.4.0, with
`feature/fast-products` at `193a506` merged in for W92's store read); not merged, nothing pushed; no dock yet.** Live.

His requirements (`W94 dock redesign/README.md`, Domain): the user draws the downstream part exactly (to the sea) and a
rough outline towards the mountains; every catchment draining into it is delineated and dissolved in, so the mountain
edge follows catchment boundaries exactly and a hybrid model has no rain-on-grid rim (W79's finding); and where the user
has catchments of his own, the domain's edge is aligned to them.

## What was built

`wadi2d domain JOB --out DIR [--outline LAYER] [--keep LINES] [--align LAYER|job] [--threshold-km2 T] [--pixel P]
[--tolerance-m M] [--cell-m C] [--settings FILE]` writes `domain.geojson` (what `grid.domain` reads), `domain.gpkg`
(layers `domain` and `changes`, with the CRS, for QGIS) and `domain_report.json`. Settings: `DomainSettings` in
`wadi2d/config/schema.py` (not part of a job, so no job hash and no plugin schema moved): `keep_m` 50, `margin_m` 5000,
`align_tolerance_m` 100, `join_m` 1. The delineation's pixel and stream threshold are the job's `basin` settings.

**Completion** (`wadi2d/domain/outline.py`, walks in `walks.py`), on the basin generator's own D8 lines (its read, its
WhiteboxTools breach, its walls and burns):

- **Kept edges** are the parts of the outline drawn exactly: within `keep_m` of a kept line (the job's boundary lines and
  `--keep` lines) and within 30 degrees of its direction. Everything else of the outline is rough.
- A pixel whose way down passes through the outline is in the domain when its water last leaves the outline across a
  kept edge (a D8 step whose middle lies within 0.75 pixel of a kept edge and nearer to it than to a rough one), or
  where the ground ends within `keep_m` of a kept line (the sea). So the outline is **extended** by every catchment
  entering across a rough edge and **cut back** where its rough edge reaches ground draining elsewhere.
- A pixel outside whose water arrives across a kept edge stays outside: the drawn edge stays and the report names the
  inflow it needs.
- With no kept line at all, nothing is cut back (everything draining in is added).
- The edge follows the analysis pixels where it moved and the drawn outline where it did not (a band of 1.5 pixels).
  The window grows from `margin_m` by doubling while a catchment reaches its edge; a catchment reaching the DEM's edge
  is named. Each change is grouped by where its water crosses the outline: a crossing draining at least the stream
  threshold is listed as a catchment with its point, the rest as slivers.

**Alignment** (`wadi2d/domain/align.py`), vector only, given any polygons (`--align FILE`, or `--align job` for the
job's HMS sqlite, generated basin or polygon file): the parts of the outline outside every catchment narrower than twice
the tolerance and within it of the catchments are removed (the rim), the parts of catchments outside the outline as
narrow are added (the gap), thin read by an opening on a band four tolerances round the edge, so a wide piece outside
the catchments (the coast strip) stays with the band that joins it to them. Kept lines stay as drawn.

**The read** (coordinator's order, mid-task): the analysis raster comes from the job's chunk store as GDAL's own block
means (`wadi2d/demstore/coarse.py`, W92) when the job has a cache folder, through GDAL otherwise; the basin generator's
`read_surface` reads the same way now (`wadi2d/basin/delineate.py`). The domain's window is kept inside the raster so
the store can serve it.

## Tests (one file at a time under the 10 GB cap)

`tests/domain/test_outline.py` (5) on two V valleys to a sea with every divide known: a rough outline 10 columns short
of valley A's west divide, 5 over its east divide into valley B and cut at row 150 becomes valley A's catchment exactly
(symmetric difference 0 m2, corners included); without kept lines nothing is cut; a kept north edge keeps the valley
above outside and names the inflow; a 100 m margin widens until whole; the command writes all three files.
`tests/domain/test_align.py` (5): W79's rim and coast strip on two polygons with a hairline gap (no cell outside every
catchment away from the strip, over 1,000 before; exact but for the opening's two rounded junctions at the strip); a
70 m gap added; nothing moves beyond the tolerance; a kept edge stays; the command on a layer. Also passed after the
read change: `tests/basin/` test_model 36, test_barriers 10, test_points 17, test_job 16, test_network 19,
test_diversion_points 11, test_tc 5, test_block2 3; `tests/demstore/test_coarse.py` 7; `tests/plugin/test_contract.py`
97; `tests/engine/test_cli_environment.py` 3. The full suite was not run.

## Block 2 (CPU, 10 m analysis pixel, W79 rerun2 job's DEM and Basin 3; `scripts/s01` to `s03`, results in the JSON files here)

Rough outline (`s01`): Basin 3's 104 polygons joined, the edge moved in and out in turn by 1 to 3 km (offset from Basin
3's edge: median 1,742 m, 5 to 95 % 339 to 2,780 m), the move fading to nothing within 3 km of W79's coast strip; the
coast strip and sea edge exactly W79's; 1,434.1 km2, 157.9 km2 outside Basin 3, 124.4 km2 of Basin 3 left out,
394,956 cells of 20 m outside every polygon. Counts are W79's (`s16`): 20 m cells inside, outside every polygon, more
than 66 m from the coast strip.

| Domain | km2 | Basin 3 left out, km2 | Against W79's hand-made domain, symmetric difference km2 | Cells outside every polygon |
|---|---|---|---|---|
| W79 polygons + 40 m (the rim) | 1,406.06 | 0 | | 17,420 |
| W79 by hand (`domain_no_rim`) | 1,398.90 | | 0 | 13 |
| **W79's rim domain aligned (100 m)** | 1,399.13 | 0 | 0.31 | **13** |
| Rough outline | 1,434.11 | 124.36 | | 394,956 |
| **Completed, sea kept** | 1,401.36 | 3.81 | 10.47 | 12,130 |
| Completed, sea kept, aligned 100 / 200 / 300 m | 1,400.8 / 1,400.1 / 1,400.1 | 3.55 / 3.41 / 3.02 | 9.6 / 9.9 / 9.1 | 10,288 / 9,832 / 8,875 |
| Completed, all four W79 lines kept | 1,405.37 | 0.84 | 8.59 | 14,762 |
| Completed, all four kept, aligned 100 m | 1,404.36 | 0.62 | 7.35 | 11,948 |

- [Certain] **The alignment meets W79's test: W79's rim domain aligned to Basin 3 leaves 13 cells outside every polygon
  away from the coast strip, the hand-made domain's own count, against 17,420**, 0.31 km2 from the hand-made outline.
- [Certain] **The completion turns a rough outline 1 to 3 km off into Basin 3's area within 0.2 %** (1,401.4 against
  W79's 1,398.9 km2; 3.8 km2 of Basin 3 left out with the sea alone kept, 0.8 km2 with W79's three side outflow lines
  kept too): 125 km2 added (one catchment over 10 km2, 12.7 km2 at 411,517 / 2,724,375, the rest hillslope), 61 km2 cut
  back.
- [Certain] **It does not reach W79's 13 cells against Basin 3's polygons: 12,130 remain, 8,875 even after a 300 m
  alignment.** The D8 lines and HMS's delineation are two delineations. In the mountains they part by a pixel or two
  (2,767 slivers 6 to 24 m wide, about 0.7 km2 in all). On the plain they part on two pieces: 5.10 km2 at
  444,654 / 2,738,075 and 0.63 km2 at 437,286 / 2,740,541 on the north edge, which the D8 lines send to the sea through
  the outline while Basin 3's edge runs south of them, and 2.98 km2 at 452,647 / 2,715,129 on the south edge, which the
  D8 lines send out across the rough south edge (the 16.1 km2 cut back with its exit at 451,007 / 2,710,875). The north
  pieces join the coast strip, so the opening reads them as wide ground and keeps them, as it must keep the strip.
  [Likely] On real work the user takes one delineation for both: a basin generated on the completed domain tiles it to
  the pixel, and HMS polygons are aligned with `--align`; mixing a D8 domain with HMS polygons leaves these plain
  differences, and they are rain-on-grid cells in a hybrid run.
- **Time.** Completion 37 s (sea kept) and 39 s (all four), of which the read 14.7 s from the store against 286.4 s
  through GDAL on the same 5,701 x 6,173 window, identical to the bit (`read_times_10m.json`); the first check, before the
  store read was merged, took about 300 s to its D8 lines. Alignment 66 s for W79's domain, 87 to 158 s for the
  completed one (Basin 3's polygons hold 2.3 M vertices; the first version, on whole polygons, took 220 s).

## Not done

- The dock (its button and the drawing of the kept edge); the full suite; a basin generated on the completed domain
  and run (the claim that it tiles the domain is [Likely], from the generator reading the same D8 lines).
- 5 m analysis pixel on Block 2 (10 m run; 5 m is about 141 M pixels, within `max_pixels`, untried).
- The store read writes chunks into the job's cache folder: here W79's `runs/cache` in the main checkout, which other
  runs share (it is a cache, made on first read).

## Scripts

`s01_block2_check.py [pixel] [sea|all]` the rough outline, the completion, its alignment and W79's rim domain aligned;
`s02_read_times.py [pixel]` the analysis raster both ways, timed and compared; `s03_wider_alignment.py` the completed
domain aligned at 100, 200 and 300 m through the command line. Outputs in `runs/` (out of git).
