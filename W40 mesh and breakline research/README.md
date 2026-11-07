# W40 mesh and breakline research

**Status (2026-11-07): research done, recommendation delivered, no engine code written. The recommendation: fix the
faces, keep the tiles, and do not build tiles plus aligned strips now.** All three measured failures are face-rule
errors on the lattice Wadi2D already has:

- **The staircase error** (Faydh 01 at 20 m, -11.1 %) is ground read onto faces up to half a cell off a bank line. W36's
  ridge-only diagnostic already brought all four bank cases within 0.3 %.
- **The free-overfall over-carry** (2.6 to 3.8 x critical) is a missing critical section. A face carrying the full depth at
  the full head's velocity passes sqrt(2) / (2/3)^1.5 = 2.60 x critical at any cell size. A strip is built from the same
  faces, so the cap he asked for is the whole fix.
- **The bank-line loss** (W26, -9.7 to -35.5 %) is [Likely] mostly the crest law. Today's cap reads the static depth, not
  the energy head, so it binds at a face Froude number of 0.544. On a 45-degree line it binds at about 0.385, while the
  flood runs along the line. Banks a metre below ground still cost 7.8 %.

If a mesher is ever needed, **MeshKernel** (LGPL-2.1 core, MIT wrapper, 1.1 MB Windows wheel) leads Gmsh. It is the
only candidate that measures and optimises orthogonality, which a staggered scheme needs. **Triangle and JIGSAW cannot
ship under GPL-3.0**: their non-commercial and no-compensation clauses make them non-free.

His request (2026-11-07): research the mesh generator before any engine change. Speed first, so the square tiles stay;
accuracy at breaklines is critical; the leading idea is square tiles plus a strip of aligned cells along each breakline,
possibly from Gmsh; a critical-flow cap at free overfall is needed whatever the mesh. Compare every option for GPU speed
per cell, accuracy at breaklines, licence fit with GPL-3.0, Windows and Python integration, sub-grid compatibility and
effort. The result must solve the three current issues, each shown through the real dock against today's numbers. A
recommendation with the evidence goes in a W folder before any engine code.

## What is here

- `reports/Breakline mesh options for Wadi2D.md`: the recommendation. It has the seven options against his six
  criteria and the three issues, the mesher ranking with licences, the face law in tiers, the dock gates against
  today's numbers, and what is unproven and what would bring the strip back.
- `research_notes/Breakline mesh options for Wadi2D/`: the five strands it rests on, every claim tagged and linked.
  - `meshers_survey.md`: every mesher he named and the 2023 to 2026 newcomers, with the licence read from each
    licence file.
  - `production_models_breaklines.md`: HEC-RAS, TUFLOW Classic, HPC and FV, MIKE, ICM, 3Di, D-Flow FM, SFINCS, Iber,
    TELEMAC and others.
  - `gpu_speed_by_mesh.md`: published GPU speeds per mesh type, the time-step penalty of thin strips, and local time
    stepping.
  - `subgrid_porosity_cutcell.md`: staggered sub-grid on unstructured grids, porosity, cut cells and cell clones.
  - `overfall_weir_cap.md`: why a face over-carries, D-Flow FM's fixed weir, submergence, validation data, and the face
    law with tests T1 to T7.

## The recommendation in one table

| Step | What | Where in the code | Fixes | Evidence today |
|---|---|---|---|---|
| G | A face pixel lifts only where the line stands above the ground half a cell out on both sides | table builder (W36 branch) | Staircase, -11.1 % | W36 diagnostic: -0.0, +0.0, -0.0 and -0.3 % on the four cases [Certain] |
| Tier 0 | Critical flow on the energy head along the face normal, on breakline and natural-crest faces | step [6] of both face kernels | Overfall, 2.6 to 3.8 x | Arithmetic exact against the flume's 2.62 [Certain]; never run |
| Tier 1 | On drawn crest lines: cap only the flow normal to the line, on its normal energy head; share it by D-Flow FM's projection, and leave flow along the line untouched | step [6] and the crest staircase | Bank loss, -9.7 to -35.5 % | Predicted [Likely]; the split is not documented in any production code |
| Tier 2 | Structures: the user's coefficient times a drowning curve, off above r = 0.98 | step [6] | Spillways, roads | TUFLOW, HEC and D-Flow FM practice [Certain]; never run here |

Each step gets its own branch, W folder and gate. The gates (G0 baseline, I1 to I3 for his three issues, T1 to T9) are in
section 5 of the report. The first gate, G0, builds the missing dock scenarios on today's `main`: Faydh 01 at 20 m and
Bidah 03, with banks sent as Breaklines and as Crest lines. That is needed because W36's -11.1 % and W26's losses came
from frozen engine jobs, not from the dock.

## What he must decide

1. **The recommendation:** smarter faces on the lattice in the order G, tier 0, tier 1, tier 2, each behind its dock
   gate, or the strip anyway?
2. **Tier 0's scope:** breakline and natural-crest faces only, behind a named setting, with old jobs held to the last
   digit while it is off (the report's advice), or every face? On every face it moves every rain-on-grid hill cell.
3. **Bank lines in the plugin:** stop offering them as barriers and route them to refinement only, as W26 and W36
   both point to.
4. **Downloads:** the UK EA benchmark data (Test 7, the levee case, and Tests 1 and 3) and the Iber weir flume set on
   Zenodo (194 runs on 9 weirs, oblique ones included). Both need his yes.

## His answers (2026-11-07)

1. **He rejects the recommendation until an aligned mesh is tested.** In his words: "you are still using the Square mesh
   that do not align the breakline... i am sure the breaklines are worth it, and you can not agreen until use a proper
   mesh generator"; and "the cells may sit on both sides of a breakline and the high ground do not match the face".
   [Certain] He is right on the geometry. A staircase face lies up to half a cell off the line. A cell that a ridge cuts
   through holds both sides at one water level, so its storage sits on the wrong side for up to half a cell along the
   line. The ridge rule (G) fixes only the crest height on the face. None of the three measured errors tested that,
   and this report never raced an aligned mesh on his cases. **Next: a prototype race.** MeshKernel (or Gmsh) strips
   along the breaklines, joined to the square tiles, against squares plus rule G. The cases: Faydh 01 at 20 m, the
   overfall flume, the W26 banks, a diagonal road through cells (his shared-level case) and EA Test 7. Both accuracy
   and run time are measured, including the strip's two risks: the false sideways drive at the join and the time step
   of thin cells. The strip goes into the engine if it wins.
2. **The cap: TUFLOW HPC's way, on breakline faces.** The upstream energy head, critical flow in free fall, a drowned
   curve. He agrees to test it on the EA benchmarks and the flume data. The line-normal split of tier 1 is not
   documented in any production code, so it is dropped in favour of the documented form.
3. **Breaklines are never barriers** (his rule): a breakline aligns faces so that a face on high ground reflects it.
   The dock's Suggest message now sends bank lines to refinement only (merged, 6 of 6 through the dock).
4. **Downloads: yes.** Both datasets are in `W42 benchmark data`.

## Not done, and why

- **Nothing has gone through the dock.** No engine code exists for the face law yet, and his rule puts the research
  before any engine change. Each gate in the report ends in a dock scenario against today's numbers.
- **Sources read only in part:** several primary texts refused the fetch or could not be read in full. These include
  Stelling and Duinmeijer 2003, Kramer and Stelling 2008, Sehili 2014, Casulli 2019, Kindsvater 1964, the numeric
  FHWA roadway curves and the PDFs of Vacondio 2017 and Dazzi 2018. The notes mark each claim that rests on a summary.
- **T8 needs a reading first:** the two notes take different control levels from the EA 2010 report for Test 7
  (12.13 m against about 12.5 m), so the pass mark must be read from the report before it is fixed.
