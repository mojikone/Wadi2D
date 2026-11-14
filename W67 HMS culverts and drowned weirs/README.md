# W67 HMS culverts and drowned weirs: the third slice of reservoir structures, raced against HEC-HMS 4.12

**Status: built on branch `feature/hms-culverts` off `feature/fast-products` (`c299429`), not merged, nothing pushed.
Live iteration for HMS reservoir structures after W59 and W62 (both stay as they are; their numbers still hold).
Lumped reservoirs only, metric only.**

The uncomfortable findings first.

- [Certain] **HMS's culvert coefficients are not HDS-5's print in two places**: chart 1 scale 2 (concrete pipe, groove
  end with headwall) carries K 0.0078 where HDS-5 prints 0.0018, and chart 8 scale 1 (box, 30 to 75 degree
  wingwalls) carries Y 0.86 where HDS-5 prints 0.81. Each was fitted on HMS's own output to the last digit and each
  value is a constant in `hms.jar` (`culvert/model/routine/u.class`; 0.81 is not). Wadi2D carries HMS's numbers, so it
  agrees with HMS and differs from a hand calculation off the FHWA table there.
- [Certain] **HMS's books lose a sixtieth of each step's net inflow while the pool stands under a fixed tailwater**
  with a culvert (`culvert_box_tw_full`: 9,433 m3, storage change 59/60 of the net inflow at every such step), the
  same defect W62 found with an armed pump. Ours close, so that case is tested on HMS's own pool levels.
- [Likely] **One outlet-control regime is not identified**: a part-full barrel whose profile reaches the crown inside
  the barrel (normal depth at the crown) reads up to 1.1 cm of pool under HMS's; neither the step count of the profile,
  a switch to full flow below the crown, nor equal-length standard steps reproduce it (`scripts/probe_profile.py`,
  `probe_stations.py`). It costs 1.4e-3 of the peak culvert flow at HMS's levels, 7.8e-4 of the peak outflow routed.

## Culverts: what is built

| Piece | Where | Law, as measured on HMS's output at HMS's own pool levels |
|---|---|---|
| Hydraulics | `wadi2d/hydrology/culvert.py` | In feet and cfs inside, as HMS's routine is (`hms.jar` constants 32.174, 1.48592, 29.1673) |
| Inlet control | same | HDS-5 with velocities zero: unsubmerged to Q/(A D^0.5) = 3.5, submerged from 4.0, **between them the two forms at the same ratio blended linearly in it** (not the end values joined, which is 5e-3 off). Form 1: HW/D = Hc/D + K X^M + Ks S; form 2: K X^M; submerged c X^2 + Y + Ks S on form 1 charts and **no slope term on form 2 charts**; Ks -0.5, **+0.7 on the mitered chart 2 scale 2** |
| 16 charts and scales | same | Circular 1 (1 to 3), 2 (1 to 3), 3 (1, 2); box 8 (1 to 3), 9 (1, 2), 10 (1 to 3); every one raced, within 8e-5 of the peak culvert flow |
| Outlet control | same | Tailwater over the outlet crown: pool = TW + (ke + kx) V^2/2g + 29.1673 n^2 L / R^(4/3) V^2/2g. Otherwise a direct-step profile upstream from the higher of critical depth and the tailwater, pool = inlet invert + depth + (1 + ke) V^2/2g, the barrel full from where the profile reaches its crown |
| Automatic | same | The higher headwater of the two at a flow, so the lower flow at a pool |
| The structure | `structures.py` `Culvert` | Routed as a rating of pool against flow at the reservoir's fixed tailwater, 2,000 flows to past the pool table's top, inverted (HW rises with Q), so the kernel is unchanged (`RATING_CURVE`); series column `culvert_<n>_m3s` |
| Reader | `from_hms.py` `_culvert` | The keys below; the reservoir hands each culvert its tailwater (main outlet; none on the auxiliary) and table top, and checks them |

Refused by name: shapes other than Box and Circular (arch, Con-Span, elliptical, the arch profiles, pipe arch,
semi-circular need HMS's own size tables, `H.class`'s 551 constants, not transcribed); a chart and scale not in the
table above, or one of the other shape; a barrel with no fall; outlet control governing on a steep barrel (normal
under critical depth: HMS's rule there not measured); any key not listed.

## The basin-file keys

As W59: written into a test basin, **re-saved by HEC-HMS 4.12** (`SaveBasinModelAs`), every key written back; the box
block is also HMS's own `river_bend` sample's.

| Block | Keys |
|---|---|
| `Conduit: Culvert` | `Conduit Outlet`, `Culvert Shape` (`Box`, `Circular`), `Chart Number`, `Scale Number`, `Solution Control` (`Inlet Control`, `Outlet Control`, `Automatic`), `Rise` and `Span` (box) or `Diameter` (circular), `Number Barrels`, `Culvert Length`, `Entrance Loss Coefficient`, `Exit Loss Coefficient`, `Top Manning's n`, `Inlet Invert Elevation`, `Outlet Invert Elevation` |

## The race against HEC-HMS 4.12

W59's project and method unchanged (`scripts/w67_cases.py` adds the cases): a 400 m3/s flood into a 100 to 125 m pool
from 103 m, 48 h at 5 min, Adaptive Control On, HMS headless (W62's `run_hms.ps1`), the rating spillway of W59 as
relief beside each culvert, 2 barrels, inverts 100.5 (or 100.3) and 100 m. `scripts/export_cases.py` writes the oracle
into `tests/data/hms_structures/`. The pool sweeps each inlet from unsubmerged through the transition to submerged.

| Case | Barrel | HMS peak outflow, m3/s | routed: max outflow difference, of peak | pool, m | at HMS's levels: culvert, of its peak |
|---|---|---|---|---|---|
| `culvert_box_ic` | box 3 x 3 m, 40 m, chart 8/1, inlet control | 185.64 | 2.7e-5 | 1.1e-4 | 3.9e-5 |
| `culvert_box_form2` | the same, chart 10/2 (form 2) | 189.05 | 5.2e-5 | 1.2e-4 | 7.2e-5 |
| `culvert_pipe_ic` | pipe 2.5 m, 40 m, chart 1/1 | 158.77 | 1.8e-5 | 6.3e-5 | 4.4e-5 |
| `culvert_box_auto` | box, 300 m, n 0.02, Automatic | 165.87 | 7.2e-4 | 3.1e-3 | 1.4e-3 |
| `culvert_box_oc` | the same, outlet control | 165.87 | 7.2e-4 | 3.1e-3 | 1.4e-3 |
| `culvert_box_tw_part` | the same, tailwater 101.5 m (half the rise) | 165.88 | 7.8e-4 | 3.1e-3 | 1.4e-3 |
| `culvert_pipe_auto` | pipe, 250 m, n 0.024, chart 2/3, tailwater 101.5 m | 151.83 | 2.6e-4 | 1.2e-3 | 8.4e-4 |
| `culvert_box_tw_full` | box, tailwater 104 m (over the crown) | 169.81 | HMS's books (above) | | 2.1e-4 |
| `culvert_chart_<c>_<s>`, 12 cases | the other charts, inlet control | (culvert peaks 70 to 152) | | | 3.6e-5 to 7.9e-5 |

The tolerances in `tests/hydrology/test_hms_culverts.py`: inlet control routes within W59's 3e-4 of the peak and
2e-4 m; outlet control within 1e-3 and 4 mm (the crown-reaching barrel); at HMS's levels 1e-4 (inlet) and 1.5e-3.
A culvert's rating costs 0.4 to 3 s once per reservoir run (Python, the profile per flow), HMS's warning that culverts
compute slowly holds here only at packing.

## Not done

- Culvert shapes other than box and circular; steep barrels in outlet control; the crown-reaching part-full barrel's
  last centimetre.
- A culvert with a tailwater other than none or Fixed Stage (as every structure).
- The dock: no change; the HMS route reads culverts from the file as it is. Not run through the real dock.

## Files

- `scripts/w67_cases.py` (the cases, on W59's `hms_project.py` and W62's Jython runner), `export_cases.py`.
- Probes: `submergence_breaks.py`, `fit_inlet.py`, `probe_inlet.py`, `probe_transition.py`, `probe_culvert.py`,
  `probe_outlet.py`, `probe_profile.py`, `probe_stations.py`; `class_constants.py` and `find_culvert_jar.py` read
  `hms.jar` in place. `_work/` holds the HMS projects and is not committed.
- Tests: `tests/hydrology/test_hms_culverts.py`.
