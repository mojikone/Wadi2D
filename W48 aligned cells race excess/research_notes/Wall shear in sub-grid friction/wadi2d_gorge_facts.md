# Wadi2D's own measurements on the synthetic gorge (W48, 2026-11-08)

Source: runs of Wadi2D (GPU, the option A kernels) and HEC-RAS 6.6 SWE-EM made by the coordinating session; every
number below is a run or an arithmetic check of this session, none from outside sources.

## The case

A straight channel on a 0.5 m DEM, 8.4 km long: a 12 m flat bed, walls rising 7 m over 1.5 m each side (about 78
degrees), a 10 m ledge at 5 %, hills at 50 %; bed slope 1 %, Manning n 0.05 everywhere, a steady 300 m3/s. The same
section on a sine wave of 150 m amplitude and 1,200 m wavelength (radius 243 m at the bends) is the "tight sine".
Depth read on the axis (3 m either side of it), 1 to 8 km.

## Measured depths, m

| Mesh | HEC-RAS straight | HEC-RAS tight sine | Wadi2D straight | Wadi2D tight sine |
|---|---|---|---|---|
| Squares 2 m | | | 4.407 | 4.806 |
| Squares 5 m | 4.698 | 5.319 | 4.382 | 4.843 |
| Squares 20 m | 5.276 | 4.974 | 4.383 | 7.082 |
| Aligned 20 m | 5.273 | 5.287 | 4.407 | 4.569 |
| Aligned 10 m | | 5.347 | 4.408 | 4.532 |

(a HEC-RAS 2.5 m run of the straight gorge was running when this note was written)

## Normal depths of the straight section, by formula (arithmetic on the exact section)

- The face sum Wadi2D uses (Lotter / divided channel, plan width, no wall shear): **4.398 m**; Wadi2D's runs reproduce
  it at every cell size.
- Manning on the whole section's hydraulic radius, the walls in the wetted perimeter: **5.392 m**.
- An emulation of HEC-RAS's rule, each face's own hydraulic radius from its own profile, walls in that face's
  perimeter, the section cut into faces of width w and their conveyances summed (normal depth, faces centred / shifted
  half a face): w = 40 m 5.42 / 5.43; 20 m 5.42 / 5.43; 10 m 5.42 / 4.74; 5 m 4.73 / 5.11; 2 m 4.46 / 4.69;
  1 m 4.41 / 4.50. **It reproduces HEC-RAS's 5.28 m at 20 m and 4.70 m at 5 m, and falls toward the face sum as the
  faces shrink**: the extra depth comes from applying one face's wall perimeter to the whole face's width, which
  fades as faces resolve the section, leaving only the walls' own strips with their inclined length.

## What it suggests (the session's reading, to be weighed against the literature)

- HEC-RAS 2D's extra depth in a narrow deep channel at coarse cells is a property of its per-face hydraulic radius on a
  face spanning bed and walls, not a wall shear it keeps at fine resolution; at fine resolution it should approach the
  face sum plus the walls' inclined-length effect, which on this section is small (the 1 to 2 m faces give 4.41 to
  4.69 m).
- The physical question that remains: whether a narrow deep channel's walls should carry more shear than a depth-
  averaged model gives them (a section-wide hydraulic radius as 1D Manning has it, 5.39 m, or the side-wall
  corrections of flume work), which is what the n values were calibrated with.
