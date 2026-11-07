# W44 mesh race: a hybrid mesh with MeshKernel on the Faydh 01 gorge

Mesh only. No solver, no engine change, nothing written outside this folder. MeshKernel 8.4.0 (Deltares,
`meshkernel` Python wrapper 8.4.0) in the scratch site folder; numpy 2.5.4 and matplotlib 3.11.2 from that folder
shadow the venv's, shapely 2.1.2, rasterio 1.5.0 and scipy 1.18.0 from the venv. Date 2026-11-07.

Tags: [Certain] measured here, [Likely] a strong inference, [Guessing] filling a gap.

## The answer in one paragraph

[Certain] MeshKernel builds a 20 m lattice of exactly the 188,814 cells with their centre inside the Faydh 01
domain and an orthogonal strip along a spline (the advancing front), and it joins nothing: `mesh2d_connect_meshes`
drops a strip that does not share the hole's boundary, and its polygon triangulation changes the node count on every
real gap. A hybrid mesh came out all the same, with one step of my own (the bank snap) and shapely's constrained
Delaunay for the gap: 30 corridors along 29.3 km of W26's bank pairs, 196,930 cells against 188,814 (+4.3 %), every
breakline face on the W26 line at its ends (midpoints median 0.00, p90 0.91, max 4.03 m, against the staircase's up to
10 m), and 1.60 % of the interior edges above 0.05 on MeshKernel's orthogonality (lattice edges all exactly 0; the
strips' bank rows p90 0.08, the join triangles p90 0.11). MeshKernel's orthogonaliser confined to the join band takes
the share above 0.05 to 0.57 % in 1.7 s without moving a bank face; run on the whole mesh it reaches 0.14 % by moving
bank nodes up to 9.2 m, so the faces leave the line. **What this does not say [Certain]: nothing about the dam peak.
The staggered scheme's tolerance of 0.05 to 0.1 non-orthogonality on the bank rows is untested [Guessing], and the
snap that puts the faces on the line is what costs it: the raw MeshKernel strips sit at p90 0.025.**

## What was built, in order

### 0. Inputs (`s00_inputs.py`, `common.py`)

- Domain: `W11 validation round two/t2_faydh/domain_wadi_20m.geojson`, 75.5256 km2, 1,511 vertices, all on a 20 m
  lattice from its minimum corner (418,765.99, 2,726,180.39; EPSG:32640); 678 x 482 cells in the box. [Certain]
- Bank lines: `W26 suggested breaklines/suggested/faydh/suggested_breaklines.gpkg`, layer `breaklines`, `kind =
  'stream bank'`: 225 parts, 115.6 km, each with `side` (left/right) and `area_km2` of the reach it banks; the
  `thalwegs` layer (40) orders the parts along each reach. [Certain]
- Dam line: the `axis` result line of the W11 job (`jobs/10m_n050_em.json`). [Certain]
- The 5 m DEM (`GGC_2_MERGE_HDSM_5.tif`, EPSG:32640) was opened to read its grid and never used: a mesh needs no
  ground, and no sub-grid tables were built. [Certain]
- **Finding that set the design [Certain]:** W26's two banks of the main gorge sit 17.7 to 50.2 m apart, median 22.6 m,
  87 % of stations under 30 m: one 10 m cell clear of the thalweg each side, as W26 drew them. A 30 m strip per bank
  would overlap its partner along the whole gorge. So each bank PAIR is one corridor with both banks as interior
  grid lines, and "strip per line" in the brief is read as "corridor per pair".

Figures: `fig_00_inputs.png` (all lines by drainage area), `fig_00_inputs_zoom.png` (the gorge near the dam,
labelled `fid` + side + km2).

### 1. The lattice (`s01_lattice.py`)

`mesh2d_make_rectangular_mesh` over the box (326,796 cells, 0.34 s), then `mesh2d_delete` with the domain polygon
inverted. [Certain] `DeleteMeshOption.INSIDE_NOT_INTERSECTED` dropped 2,790 boundary cells whose centres lie inside
(186,024 left): the polygon runs along cell edges, so every boundary cell counts as intersected.
`FACES_WITH_INCLUDED_CIRCUMCENTERS` keeps exactly the 188,814 cells with their centre inside (shapely agrees), in
17.2 s. MeshKernel's orthogonality is 0.0 on all 376,220 interior edges; the centroid measure too.

Files: `lattice.npz`, `lattice.json`, `fig_01_lattice.png`.

### 2. The corridors (`s02_strips.py`; probes `probe_splines.py`, `probe_front.py`, `probe_rows.py`)

What MeshKernel offers for a strip along a line, as found by the probes [Certain unless marked]:

| Call | Finding |
|---|---|
| `curvilinear_compute_orthogonal_from_splines` with the line alone | refused: `Not enough splines to create a curvilinear grid` |
| the same with the line plus cross splines | works; the centre spline is sampled every `average_width` (19.9 m here, uniform; `curvature_adapted_grid_spacing` 0 or 1 made no difference on this line), layers of `aspect_ratio x average_width` grow on both sides |
| cross-spline length | sets the grid height on that side; a one-sided cross spline (0 to +30 m) grows one side only; an asymmetric one (-10 to +30) gives 1 and 3 layers |
| layer heights | the first `maximum_num_faces_in_uniform_part` layers are fixed at aspect x width; beyond them the layers taper (grow factor) and the outermost is squeezed to the cross-spline height (+-25 m: 10, 8.2, 6.8); a layer never stretches to a longer cross spline, so the front cannot follow a bank whose offset varies |
| intermediate cross splines | with cross splines every 100 m, all of the same +-30 m, the front tapered the outer layers to 8.1, 6.6, 5.3 m and made 8 rows instead of 6; with the two end cross splines alone every row is 10.0 to 10.1 m. Not understood, recorded as a quirk; the corridors use end cross splines only |
| a cross spline 0.5 m longer than 3 layers | a fourth, 0.35 m layer on each side |
| the spline through a polyline | a spline through a 60 m / +-30 degree zigzag misses it by median 0.95, p90 2.5, max 4.1 m (`probe_front_zigzag.png`) |
| tight bends | the front folds: 4 corridors rejected for 1 to 3 cells of zero or negative area; one corridor (pair 15) came out with 80 rows, the front running away |
| `curvilinear_compute_transfinite_from_splines` | not tried on the gorge: it needs four bounding splines and its cross edges are blends of the two end lines, not normals, so it is not orthogonal on a bend by construction [Likely] |
| `mesh2d_refine_based_on_gridded_samples` | not used: refining the lattice near a line adds hanging-node levels, not alignment [Likely] |

The corridor, per bank pair:

1. The parts of one reach (`area_km2`) and side are chained along the reach's thalweg (gaps under 30 m join);
   the mid-line between a left and a right chain is the midpoints of 10 m stations, smoothed over 5 stations (50 m),
   resampled every 20 m. Pairs with a facing stretch under 300 m are dropped. 21 reaches, 39 pairs, 74 unpaired
   chains (single banks and parts that face nothing). [Certain]
2. MeshKernel grows 3 layers of 10 m each side of the mid-line spline (aspect 0.5 x 20 m, uniform 3, grow 1.0, end
   cross splines +-30 m, `check_front_collisions`, `remove_skinny_triangles`): 6 rows, cells 19.9 x 10 m. The +-10 m
   grid lines fall near the banks: on the main corridor they miss the W26 lines by p90 6.2 / 7.4 m, max 14.5 m. [Certain]
3. **The snap, my step, not MeshKernel's:** each +-10 m node moves along its own cross line to where that line meets
   the bank polyline (the nearest crossing within 25 m, else the nearest point, 1 node of 366 on the main corridor),
   and the two outer nodes on that side move with it, so the outer rows stay 10 m. Main corridor moves: median 1.4 /
   1.6 m, p90 6.1 / 6.5, max 13.8 / 14.6 m. [Certain]
4. Gates: a corridor is rejected when the raw +-10 m line misses a bank by over 15 m (a mis-pairing: 3 corridors,
   19 to 135 m), when a bank face is still over 5 m off after the snap (none), when the raw or snapped grid has a
   folded cell (4), when the grid has not 6 rows (1), or when it overlaps an accepted corridor (1). Later corridors are
   cut 25 m clear of accepted ones and 35 m inside the domain. [Certain]

Result [Certain]: **30 corridors, 29.3 km, 1,484 cells along, 8,904 cells, 2,968 breakline faces** (one per bank per
cell along). The main gorge: 3,620 m, 182 cells along, 1,092 cells, the dam axis crosses it. Strip cell size
sqrt(area) median 14.2 m (p10 13.2, p90 15.7, min 5.9, max 22.9); edge lengths median 16.6 m, min 0.36 m, max 40.8 m,
the extremes at tight bends [Likely]. Run time: 1.18 s of MeshKernel for all 39 growths, 0.11 s for the snap.

Sensitivity [Certain]: a 110 m smoothing window (`--smooth 11`, outputs `*_s11.*`) accepts 20 corridors instead of 30
(the main corridor fails the 15 m gate at 17.0 m) and the snapped strips read p90 0.112 instead of 0.071, so the 50 m
window stays.

Files: `strips.npz`, `strips_raw.npz` (MeshKernel's unsnapped corridors), `strips.json` (every corridor's numbers
and every rejection), `strips_polygons.pkl`; `fig_02_strips_all.png`, `fig_02_main_raw.png`,
`fig_02_main_snapped.png` (300 m windows at the dam axis and a third of the way along), `fig_02_strips_orthogonality.png`.

### 3. The join (`s03_join.py`; probe `probe_join.py`)

What MeshKernel offers [Certain]:

| Call | Finding |
|---|---|
| `mesh2d_connect_meshes(strip, connect=True)` | on a lattice with a hole and a rotated strip inside it: the strip's 84 nodes are added, none of its 60 faces or 143 edges; faces 538 before and after. It connects meshes that share a boundary; `search_fraction` over 0.4 is refused (`Valid range: 0 < value <= 0.4`) |
| `mesh2d_make_triangular_mesh_from_polygon` on the gap | on the toy annulus 110 triangles on the 110 ring nodes; on every real gap polygon (25 of 25) it changed the node count (+5 to +37 nodes, e.g. 455 against the ring's 418), so its triangles would not share the lattice's and the strip's edges |
| `mesh2d_delete(..., INSIDE_AND_INTERSECTED)` on the corridor polygon | removes the lattice cells under and touching a corridor, as wanted; done in shapely here for the counts |

The join as built: the lattice cells within 10 m of a corridor are removed (`--gap-buffer 10`; 8,302 cells, 25 gap
polygons with 30 holes, 3,678 cells of area); the gap's rings are densified with every mesh node lying on them and
triangulated on those nodes only with `shapely.constrained_delaunay_triangles` (no new node, so nothing hangs). The
cell shapes at the join [Certain]: **7,514 triangles, nothing else** (no pentagons, no hanging nodes); minimum angle
median 44.5 degrees, p10 30.2, smallest 2.9; 2 triangles under 10 degrees, 1 under 5; 35 obtuse over 120 degrees;
area median 200 m2, min 0.14 m2 (one sliver at a corridor end), max 568 m2. Without the 10 m buffer (`join.json`,
`fig_03_join_zoom.png`) the gap is thinner than a cell in places: 7,416 triangles, 577 under 10 degrees, 941
obtuse, and 2.60 % of edges above 0.05 instead of 1.60 %. A greedy merge of triangle pairs into convex quads
(`joined_quad_gap10.npz`: 2,753 quads, 2,008 triangles left) reads worse, 3.05 % above 0.05, and is not used.

Files: `joined_tri_gap10.npz` (the mesh), `joined_quad_gap10.npz`, `join_gap10.json`; `fig_03_join_zoom_gap10.png`
(dam axis and a corridor end; grey lattice, blue strip, orange triangles, green merged quads),
`fig_03_join_orthogonality_map_gap10.png`, `fig_03_join_orthogonality_hist_gap10.png`; the same without suffix for
the 0 m gap.

### 4. Measurements (`s05_measure_export.py`, `s04_orthogonalize.py`)

MeshKernel's orthogonality is |cos| of the angle between an edge and the segment joining the two faces'
circumcentres (0 orthogonal; D-Flow FM wants under 0.01, accepts 0.02). The centroid measure is Wadi2D's sense: the
same with the face centroids. Boundary edges excluded. All of it in `measure_gap10.json`, `join_gap10.json`,
`strips.json`, `lattice.json`, `orthogonalize_gap10.json`.

**Orthogonality, MeshKernel's measure, interior edges [Certain]**

| Mesh | edges | median | p90 | p99 | max | > 0.01 | > 0.02 | > 0.05 |
|---|---|---|---|---|---|---|---|---|
| lattice alone | 376,220 | 0 | 0 | 0 | 0 | 0 % | 0 % | 0 % |
| strips alone, MeshKernel raw (before the snap) | 16,144 | 0.0072 | 0.0251 | 0.0575 | 0.141 | 38.9 % | 15.9 % | 1.7 % |
| strips alone, snapped to the banks | 16,144 | 0.0223 | 0.0711 | 0.161 | 0.930 | 73.0 % | 53.7 % | 19.3 % |
| joined (10 m gap, triangles) | 388,685 | 0 | 0 | 0.0730 | 1.0 | 4.36 % | 3.39 % | 1.60 % |
| joined, by edge kind: lattice-lattice | 357,530 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| lattice-triangle | 4,174 | 0 | 0 | 0.127 | 0.284 | 6.5 % | 5.9 % | 3.9 % |
| strip-strip | 16,144 | 0.0253 | 0.0815 | 0.185 | 0.931 | 75.5 % | 57.9 % | 23.8 % |
| strip-triangle | 3,328 | 0.0198 | 0.135 | 0.312 | 1.0 | 70.5 % | 49.8 % | 24.9 % |
| triangle-triangle | 7,509 | 0 | 0.109 | 0.370 | 0.795 | 28.2 % | 25.3 % | 18.7 % |

The centroid measure on the joined mesh: 6.7 % above 0.01, 5.8 % above 0.02, 4.2 % above 0.05, p99 0.237; on the
snapped strips p90 0.075, 20.3 % above 0.05. [Certain] The strip-strip edges in the joined mesh read 0.0253 median
against 0.0223 alone because the strips' outer boundary edges, open alone, have a triangle on the other side.

**Distance of every breakline face from its W26 bank line, 2,968 faces [Certain]**

| | midpoint median | midpoint p90 | midpoint max | ends max |
|---|---|---|---|---|
| MeshKernel raw +-10 m line | 1.02 m | 4.16 m | 14.50 m | 14.85 m |
| snapped | 0.00 m | 0.91 m | 4.03 m | 2e-10 m |
| the 20 m staircase, for scale | | | 10 m (half a cell) | |

The snapped midpoints are off only where the W26 polyline bends between two of our 20 m nodes (its own vertices
are about 60 m apart); the nodes are on it. `fig_05_bank_distance.png`.

**Cell sizes, joined mesh [Certain]** (`fig_05_cell_size_gap10.png`): lattice 180,512 cells of 20.0 m; strips 8,904
cells, sqrt(area) median 14.2 m, p10 13.2, p90 15.7, min 5.9, max 22.9; triangles 7,514, median 14.1 m, p10 10.8,
p90 16.7, min 0.38, max 23.8.

**Cell count against the plain lattice [Certain]**: 196,930 against 188,814, x 1.043 (180,512 kept + 8,904 strip +
7,514 triangles); the 0 m gap gives 198,475, x 1.051.

**`mesh2d_compute_orthogonalization` on the joined mesh [Certain]** (`orthogonalize_gap10.json`,
`fig_04_ortho_gap10_*.png`; no land boundary, `DO_NOT_PROJECT_TO_LANDBOUNDARY`):

| Trial | s | > 0.01 | > 0.02 | > 0.05 | p99 | bank nodes moved p90 / max | bank face distance median / p90 / max |
|---|---|---|---|---|---|---|---|
| before | | 4.36 % | 3.39 % | 1.60 % | 0.073 | | 0.00 / 0.91 / 4.03 m |
| whole mesh, defaults (2 outer iterations) | 1.9 | 1.16 % | 0.54 % | 0.14 % | 0.011 | 2.95 / 9.22 m | 1.00 / 3.19 / 8.62 m |
| whole mesh, 5 outer iterations | 4.6 | 0.48 % | 0.13 % | 0.04 % | 0.007 | 5.50 / 13.07 m | 1.97 / 5.50 / 12.62 m |
| join band only, lattice hole-boundary nodes free (`band_out`) | 1.7 | 3.70 % | 2.17 % | 0.57 % | 0.037 | 0.00 / 3.52 m | 0.00 / 0.92 / 4.03 m |
| join band only, lattice nodes fixed (`band_in`) | 1.7 | 3.79 % | 2.52 % | 0.81 % | 0.044 | 0.00 / 3.53 m | 0.00 / 0.92 / 4.03 m |

So: on the whole mesh it does not keep the strip faces on the line (152,097 nodes move, the bank nodes a median
1.2 m and up to 9.2 m, 3,028 of them); with a selecting polygon over the join band (the removed lattice cells less
the corridor shrunk by 12 m) only 8,727 nodes move, the bank rows stay (the 3.5 m maximum is a handful of bank
nodes at corridor ends inside the band), the triangles improve (above 0.05 from 18.7 % to 7.0 %) and the lattice
cells next to the hole lose their exact zero (under 0.05, visible in `fig_04_ortho_gap10_band_out.png`). The
strip-strip edges stay at 9 to 12 % above 0.05 because the bank rows are pinned: that non-orthogonality is the
snap's, and only a smoother snap (following the bank within a metre rather than exactly) would remove it [Likely].
One cell of 0.14 m2 (the sliver triangle) is counted as "folded" in every trial; it is the same cell. The 0 m gap
whole-mesh trial (`orthogonalize_gap0.json`) reads alike: 0.80 % above 0.05, bank faces up to 11.2 m off.

### 5. The export (`mesh_faydh01_hybrid_20m.npz`)

The joined 10 m gap mesh before any orthogonalisation (`joined_tri_gap10.npz` under a plain name). Arrays, all
0-based, EPSG:32640 metres:

| array | shape | meaning |
|---|---|---|
| `node_x`, `node_y` | (194,582,) float64 | node coordinates |
| `face_nodes` | (196,930, 4) int64 | node indices of each face counter-clockwise, -1 padding after `nodes_per_face` |
| `nodes_per_face` | (196,930,) int64 | 4 or 3 |
| `face_kind` | (196,930,) int8 | 0 lattice, 1 strip, 2 join triangle |
| `face_corridor` | (196,930,) int64 | corridor id (the pair index in `strips.json`) for strip cells, -1 otherwise |
| `face_row` | (196,930,) int64 | strip row -3..2 across the corridor (-1 and 0 are the channel halves, the banks on the lines between -2/-1 and 0/1), 99 otherwise |
| `face_area`, `face_cx`, `face_cy` | (196,930,) float64 | area and centroid |
| `edge_nodes` | (391,511, 2) int64 | the two nodes of each edge, lower first |
| `edge_faces` | (391,511, 2) int64 | the faces either side, -1 for a boundary edge |
| `face_edges` | (196,930, 4) int64 | edges of each face, -1 padded |
| `edge_boundary` | (391,511,) bool | one face only |
| `edge_on_breakline` | (391,511,) bool | the 2,968 faces lying on a W26 bank line |
| `edge_breakline_side`, `edge_breakline_corridor` | (391,511,) int8 / int64 | 0 left, 1 right; the corridor id; -1 elsewhere |
| `edge_orthogonality_mk` | (391,511,) float64 | MeshKernel's value, NaN on boundary edges |
| `crs`, `dx` | | "EPSG:32640", 20.0 |

The edge-face tables are built from the face table in `mkutil.topology` and not taken from MeshKernel: the Python
wrapper's `Mesh2d.edge_faces` from `mesh2d_get` holds one entry per edge (379,036 for 379,036 edges), not two.
[Certain] The orthogonalised variants are `joined_tri_gap10_ortho_<trial>.npz` (nodes, faces, `node_move_m`).

## Run times [Certain]

Operations, measured inside the scripts (AMD Ryzen 9 9950X3D, one process): lattice make 0.34 s, delete outside
17.2 s, orthogonality 0.5 s; all 39 corridor growths 1.18 s, the snap 0.11 s; cell removal 0.1 s, gap polygons
0.2 s, triangulation 1.0 s, MeshKernel orthogonality on the joined mesh 1.1 s; orthogonalisation 1.7 to 4.6 s.
Wall clock per script including the figures (`run_times.txt`, 2026-11-07): `s00` 0.7 s, `s01` 21.1 s, `s02` 6.5 s,
`s03` 7.4 s, `s04` 22.6 s (four trials and four figures), `s05` 1.6 s; the whole chain 60 s.

## What MeshKernel could not do, in one list [Certain]

1. Grow a grid from a line alone; it needs cross splines, and their lengths set the height.
2. Follow a bank whose offset from the centre line varies: layers are a fixed aspect x width, squeezed but never
   stretched. The bank snap is outside MeshKernel.
3. Keep uniform layers with intermediate cross splines of equal length (the taper quirk).
4. Survive the tightest bends of five of the 39 pairs.
5. Join a strip into a lattice hole whose boundary it does not share (`mesh2d_connect_meshes`).
6. Triangulate a gap on its ring nodes alone (it adds nodes on every real gap).
7. Orthogonalise while holding interior lines: no frozen lines exist for `Mesh2d` (they do for curvilinear grids),
   so the bank rows are held by excluding them from the selecting polygon.
8. Delete cells outside a staircase polygon with the obvious option (`INSIDE_NOT_INTERSECTED` loses the boundary
   cells; the circumcentre option is exact).

## Rerun

Git Bash, from `D:\Mojtaba\Renardet\Wadi2D\W44 mesh race\meshkernel`, in this order (each reads the previous
one's files):

```
export PYTHONPATH="C:/Users/mojtaba/AppData/Local/Temp/claude/0411bb1eda7ca588/563cf3f8-070b-42eb-82ea-489205b14695/scratchpad/mk_site"
PY=../../.venv/Scripts/python
$PY s00_inputs.py
$PY s01_lattice.py
$PY s02_strips.py                              # options: --smooth N (default 5), --no-snap, --max-pairs N, --suffix S
$PY s03_join.py --gap-buffer 10 --suffix _gap10   # without options: the 0 m gap into the unsuffixed files
$PY s04_orthogonalize.py --in _gap10           # trials: whole whole_x5 band_out band_in
$PY s05_measure_export.py --in _gap10
```

Probes, standalone: `probe_splines.py`, `probe_front.py`, `probe_rows.py`, `probe_join.py`. The `PYTHONPATH` site
folder is the session's scratch install of MeshKernel and goes with the session; a rerun later needs `pip install
meshkernel==8.4.0` somewhere on the path (it was not installed into the venv, by the brief).

## Figures

| file | shows |
|---|---|
| `fig_00_inputs.png`, `fig_00_inputs_zoom.png` | W26 bank lines by drainage area, thalwegs, the dam axis |
| `fig_01_lattice.png` | the lattice boundary and a 600 m window at the dam axis |
| `fig_02_strips_all.png` | the 30 corridors over the domain with the W26 lines |
| `fig_02_main_raw.png`, `fig_02_main_snapped.png` | the main corridor before and after the snap, at the dam axis and a third of the way along |
| `fig_02_strips_orthogonality.png` | strips alone: raw, snapped, centroid measure |
| `fig_03_join_zoom_gap10.png` | the join at the dam axis and at a corridor end, cells by kind (and the merged-quad variant) |
| `fig_03_join_orthogonality_map_gap10.png`, `fig_03_join_orthogonality_hist_gap10.png` | the joined mesh's orthogonality on the map and as a histogram |
| `fig_04_ortho_gap10_<trial>.png` | before and after each orthogonalisation trial at the dam axis |
| `fig_05_orthogonality_gap10.png`, `fig_05_bank_distance.png`, `fig_05_cell_size_gap10.png` | the step-4 measures side by side |
| `probe_*.png` | the MeshKernel probes |

Files without `_gap10` from `s03` and `s04` (and `fig_04_ortho_gap0_whole.png`, `orthogonalize_gap0.json`,
`joined_tri_gap0_ortho_whole.npz`) are the 0 m gap variant; `*_s11.*` the 110 m smoothing sensitivity.
