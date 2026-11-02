### Test 4, extent F 0.40: **main cause named: the comparison counted ground his model never covered**

**Rule 4 verdict.** His layer stops at his model's perimeter, 1,083 km2, and is blank across the rest of its 2,068 km2 rectangle (the 1,730 km2 in `W2 full extent run/README.md` is wrong). Wadi2D had 119 km2 over 0.3 m in that blank ground, each of it counted as a miss. Restricting both to his perimeter takes F from **0.407 to 0.598, +0.19**, and removes 54 % of the misses. Both tests of the rule pass. **The run was not as far from his map as 0.40 said.**

**How his layer was made** [Certain for the plans read; Likely for the 200-yr plan, whose files were not found]. It is plan `Block2_FM_200Yr(F)` of the model at `W:\2512-1 Liwa- Fizah Road\06-WORKING\03-Hydrology\07. HECRAS\Block02.p06\`, an October 2025 refinement of the Workshop model `2224...\10 Workshops with stakeholders\Hydraulic Models\Block2\Block02`. The rasmap names the plan, and the raster grid sits on the same pixel corners. The plans, geometry and rain table of the sibling plans were read; `Block02.p10` itself and its results are not on W:.

| Input | His layer | W2 | Tested here |
|---|---|---|---|
| Domain | 1,083 km2 perimeter, Sea line the only outlet, S 0.0065 | 15,398 km2, coast S 0.003 | Yes |
| Rain | FM pattern, 10 min steps, uniform, table of the 50-yr plan 153.0 mm = 168.1 x 0.91, so **228 mm** at 200 yr [Likely] | 251 x ARF at 300 km2 = **209 mm** | Yes |
| Losses | SCS CN layer on the cells | Project CN grid | Not separately |
| Terrain | `HDSM_DTM_NSA`, 3 m raster on the GGC pixel corners | NSA 5 m + Copernicus | Yes, GGC 5 m stands in |
| n | 0.06 uniform [Likely, base value, `LCMann Table=0`] | 0.05 | Yes |
| Cells | 476,943 unstructured, about 23 m mean, 4,714 breaklines, 60 m base, 25 m along breaklines | 30 m uniform | 15 m only; breaklines cannot be tested here |
| Equations | SWE-ELM, Courant 0.85, 10 s, 24 h | Full SWE, 36 h | No |
| Roads, channels, dams | In the DTM as surveyed; **no 2D connections, so no culverts**; `g02` has no channels and no dams | Same natural ground, no structures | |

**Layers on one metric.** Depth over 30 m with dry as dry, 0.3 m, the metric of the 0.40; `t4_extent\s05_decompose.py`, `s08_score.py`. Changes from A, one at a time:

| Change | F | Move | Rule |
|---|---|---|---|
| A. As reported: W2 cell mean, his rectangle | 0.407 | | |
| **B. Inside his perimeter** | **0.598** | **+0.191** | **Main cause** |
| C. Pixel depth averaged to 30 m, not cell mean | 0.413 | +0.006 | Excluded |
| E. 5 m pixels, inside his perimeter, against B | 0.612 | +0.014 | Excluded |
| Whole-map shift, best of +/-40 m in 10 m steps, plain | 0.659 at 0, 0 | 0 | Excluded |
| Shift tile by tile, 2 km, 199 tiles, +/-60 m | median best shift 0 m, 1 % over 30 m | 0 | Excluded: no channel sits elsewhere |

**Runs on his perimeter, one input moved, against the base `c_t0`.** All with the gated outlet of the section above: 172 of 189 Mm3 leaves, 9 % on land at 30 h.

| Run | Rain Mm3 | F | Move | Rule |
|---|---|---|---|---|
| `c_t0` base, W2 inputs | 189 | 0.598 | | |
| `c_t1` rain 228 mm | 209 | 0.606 | +0.008 | Excluded |
| `c_t2` n 0.06 | 189 | 0.606 | +0.008 | Excluded |
| `c_t4` cell 15 m | 189 | 0.611 | +0.013 | Excluded |
| `c_t3` GGC 5 m terrain | 189 | 0.631 | +0.033 | **Partial** |
| `c_t5` all four | 209 | 0.662 | +0.064 | Below the 0.10 of a main cause |

**The rest, F 0.60 to 0.66, is not explained and is not noise.** Yardstick: his own 100- and 200-yr layers score 0.90 on the same metric.

| 5 m pixels, 0.3 m, inside his perimeter | Both | His only | W2 only | F |
|---|---|---|---|---|
| Hills, 599 km2 | 28.8 | 26.9 | 4.6 | 0.48 |
| Plain, 484 km2 | 112.7 | 31.3 | 27.1 | 0.66 |

- **The misses are thin.** 54 of his-only's 58 km2 sit in patches under 60 m wide, so they are gully edges, not a different flood path. The same network lights up in both (`t4_extent\fig_extent_w2.png`).
- **Water depth agrees better than edges.** Median Wadi2D less his -0.11 m where both exceed 0.5 m, as W2 reported.
- **Candidates left, not testable on this grid:** his 25 m breakline cells along the gullies, SWE-ELM, Mapper's depth rendering against a mean depth [Guessing which].

**The hybrid (W7) is a separate case.** F 0.14 inside his perimeter, because its 2D area is only 226 km2: hills lumped, plain cut at 443,500 E. Inside its own 2D area F is 0.53, against 0.61 for W2 on the same ground. That job also ran n 0.04, and the map used 15 min frames.

**What this does not settle.** Neither map is observed. Both carry 200-yr rain through CN losses that test 3 found high by a wide margin, so agreement between them says nothing about a real 200-yr flood.
