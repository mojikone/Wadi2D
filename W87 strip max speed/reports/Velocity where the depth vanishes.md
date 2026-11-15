# Velocity where the depth vanishes: published practice and what the squares already do

Research in brief, before bounding the strip's two unbounded velocities (W87, his rule of 2026-11-08: published
practice before a numerical fix). Read on 2026-11-15. Confidence tags are mine.

## The question

Two places in the aligned-mesh step divide a discharge by a volume that can vanish:

1. the **Perot cell vector** `U = sum (xf - c) q / (h area)`, the volume floored at 1e-9 m3;
2. the **velocity on the join** written into the squares' closed face, `q / (max(h, 1e-6) dx)`.

How do published schemes and the two reference programs keep such a quotient from blowing up, and what do the square
tiles of this engine already do?

## Published practice

**Kurganov and Petrova 2007** (Commun. Math. Sci. 5 (1), 133 to 160, section 2.2) [Certain, read in the paper]. Their
scheme stores depth and discharge, and needs `u = (hu) / h` at cell interfaces where the reconstructed depth can be
tiny or zero, so the plain quotient cannot be trusted there. They replace it by

    u = sqrt(2) h (hu) / sqrt(h^4 + max(h^4, eps))          (2.17)

`eps` is a small positive number fixed beforehand, `(dx)^4` in all their experiments. The formula is exact for
`h >= eps^(1/4)` and drives `u` to zero as `h` goes to zero. They name a simpler alternative, `u = h (hu) / (h^2 +
eps)` (2.18), and prefer (2.17) because it changes less at small but not tiny depths. They then recompute the
discharge as `h u` from the corrected velocity, so that depth, velocity and discharge stay consistent.

Two things matter for us. The fix is applied **where the quotient is formed**, not downstream. And `eps` is a depth
scale: the method assumes one depth per cell, so "small `h`" means "little water and a thin film".

**TUFLOW Classic and HPC** (manual 2026.0, section 7.1 and Appendix A) [Certain for what is quoted, the manual is
silent on the rest]. HPC keeps depth at cell centres and velocity at cell faces, the same staggering as this engine.
A cell is wet above `Cell Wet/Dry Depth`, default 0.002 m to wet and 0.0019 m to dry since 2026; faces are switched
off with their dry cell. The first-order face depth is the upstream cell's depth, bounded at zero and by the upstream
level over the face's bed. The manual gives no formula for a velocity cap. It does state the symptom and guards the
**record** against it: `Maximum Velocity Cutoff Depth`, default 0.1 m, tracks the maximum velocity only above that
depth, "because high velocities can occur at very shallow depths during wetting and drying". That is this engine's
`outputs.speed_depth` (0.05 m), the same rule for the same reason.

**HEC-RAS 2D** [Guessing beyond this: the search found no documented rule]. Flow is controlled at faces from the
sub-grid face tables and a cell is wet once water enters it; users report no adjustable wet/dry depth tolerance. The
Hydraulic Reference Manual's treatment of momentum at a face that has just wetted was not found, so nothing is
claimed about it.

## What the square tiles already do

From the code (`wadi2d/solver/cpu/kernels.py`, `faces.cu`) and decision 18 c [Certain]:

- The lattice never forms a cell velocity from a cell volume. Its velocity unknown lives on the **face**: momentum over
  the mean wet section of the two cells, `abar = (h_l + h_r) dx / 2`.
- **A floor on the divisor**: where `abar <= 1e-6 dx` the momentum is not divided at all; the face keeps its last
  velocity and takes the pressure term.
- **Implicit friction**, which grows without bound as the section thins, so a thin face is pulled to rest.
- **A cap**: `|u| <= numerics.u_max` (25 m/s), applied to every face velocity, every step.
- **A dry face carries exactly zero**, and with `mirror` on the advection stencil does not read a zero as a velocity
  (`gated`).
- **The step search** leaves out faces whose upwind level is under `numerics.h_cfl` (0.01 m).
- **The record** leaves out cells under `outputs.speed_depth` (0.05 m).

Decision 18 c names "velocity desingularised in thin cells (Kurganov-Petrova type)". What was built is the floor, the
friction and the cap above; `design_note.md` gives the step rule over cells with `d > h_cfl` and no formula of the
Kurganov and Petrova kind. So on the lattice the bounded form is: **a quotient that is not taken below a floor, and
a velocity held to `u_max`.**

## What follows for the strip

- The strip's faces already have all of the above: they are stepped by the same six statements.
- The two quotients of the question have the floor (1e-9 m3, 1e-6 m) and **lack the cap**. They are the only
  velocities in the model that the cap does not reach.
- **Kurganov and Petrova's formula does not transfer as it stands** [Likely]. Its `eps` is a depth below which there
  is no water worth a velocity. A sub-grid cell breaks that reading: on Block 2 the aligned cells that spiked hold a
  mean depth of 0.02 m while the level stands 1.5 m over the lowest pixel, a notch carrying real flow. A depth
  threshold on the mean depth would damp real flow in every such cell, and it would be a new tunable. On a level
  threshold it would not act where the fault is, because the volume vanishes with the level high.
- **So the strip takes the lattice's form**: hold the cell vector and the join velocity to `numerics.u_max`, at the
  place each is formed, on the CPU and in `poly.cu` alike. No new setting. Below the cap nothing changes, so every
  validated steady result stands to the digit until a velocity passes 25 m/s.
- **Not taken: the strip's own face velocity on the join.** It is bounded by construction and is the unknown a lattice
  face carries, so it looked the better form. Tested: the patch of squares carried by a strip of the same squares
  then reads 1.0026 of normal depth against the all-tiles 1.0004, outside that test's 0.002. [Likely] the strip's
  interface faces carry no depth-carry term on the ghost side (W47), so their velocity is not the lattice's on an
  inflow join. The cap keeps the form that test validated.

## What the cap does not do

It bounds; it does not make the quotient right. A join face of a nearly dry ghost still reads up to 25 m/s for a
step, and a square on the join can record half of that. In the test job the squares beside the join read up to 9.7 m/s
where squares alone read 3.4 m/s (before: 33,971 m/s). A form that is right there needs the ghost-side depth carry
first; that is a study of its own.

## Sources

- A. Kurganov and G. Petrova, A second-order well-balanced positivity preserving central-upwind scheme for the
  Saint-Venant system, Commun. Math. Sci. 5 (1), 2007:
  https://www.math.umd.edu/~tadmor/centpack/publications/files/KT%20positive%20SW%20CMS2007-centpack.pdf ,
  https://projecteuclid.org/euclid.cms/1175797625
- TUFLOW Classic/HPC User Manual 2026.0, section 7.1 Solvers: https://docs.tuflow.com/classic-hpc/manual/2026.0/Solvers-2.html
- TUFLOW Classic/HPC User Manual 2026.0, Appendix A TCF Commands (`Maximum Velocity Cutoff Depth`, `Cell Wet/Dry
  Depth`): https://docs.tuflow.com/classic-hpc/manual/2026.0/TCFCommands-1.html
- TUFLOW Classic/HPC User Manual 2026.3, Default Changes (wetting 0.002 m, drying 0.0019 m):
  https://docs.tuflow.com/classic-hpc/manual/2026.3/16-Features-and-Changes.html
- HEC-RAS, secondary only: https://therassolution.kleinschmidtgroup.com/the-ras-solution-forum/topic/wetting-and-drying-tolerance/ ,
  https://knowledge.civilgeo.com/hec-ras-2d-grid-subgrid-computations
