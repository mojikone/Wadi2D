### Test 1, crest line against a 2D Connection: **agree, with RAS given Wadi2D's own weir coefficient**

**Rule 1 verdict on `a94_10`:** peak overtopping Q 536.6 against 534.0 m3/s, **1.005**, limit 10 %; stage at `pool150` 94.616 against 94.614 m, **+0.002 m**, limit 0.15 m. **Agree.** RAS closed its volume to 0.017 %.

| Bidah axis, crest level, 2D Connection overflow by | Peak RAS | Peak Wadi2D | Ratio | Time, W - R, min | Volume ratio | Stage, W - R, m | RAS volume error, % |
|---|---|---|---|---|---|---|---|
| **94 m, 10 m, weir equation, aligned, the judged run** | **534.0** | **536.6** | **1.005** | +0.5 | 1.013 | **+0.002** | 0.017 |
| 94 m, 20 m, weir equation, aligned | 522.4 | 506.5 | 0.969 | +2.5 | 1.004 | -0.019 | 0.004 |
| 96 m, 20 m, weir equation, aligned, the pool attenuates | 184.8 | 190.3 | 1.030 | +3.5 | 1.049 | +0.001 | 0.027 |
| 94 m, 20 m, **2D equations**, aligned, no coefficient | **627.3** | 506.5 | **0.807** | +9.5 | 1.004 | **+0.337** | 0.008 |
| 94 m, 20 m, weir equation, **lattice** | 548.2 | 506.5 | 0.924 | +4.5 | 0.930 | +0.049 | **28.1** |
| 94 m, 10 m, weir equation, lattice, the primary as first fixed | unstable at 3.15 h | | | | | | 2.4e8 |

Wadi2D at `pool400` and at a tail point 100 m below the crest stands within 0.003 m of RAS at 10 m. RAS's weir submergence stayed about 0.001. Over 800 m of pool upstream, deep cells differ by -3.9 cm mean, 39 cm rms at 10 m, mostly on the steep margin, because the RAS mesh there is not the lattice [Likely].

**Read the agreement for what it is.**

- **The coefficient was shared.** RAS's weir equation was given 1.7046, Wadi2D's critical-flow value, so this pair cannot fail on the coefficient. It tests the pool, the staircase's length factor, timing and mass, and those pass. Back-calculated from the peaks on 651 m of crest, RAS reads C 1.71 and Wadi2D 1.71 at 10 m.
- **A real embankment's coefficient is a separate question.** Broad crest over a rough road is often taken lower than 1.7 [Guessing without a source here]. The result scales with it in both models.
- **The one test with no coefficient does not pass, and RAS is the one that looks wrong.** With overflow by the 2D equations RAS passes 627 m3/s with the pool only 0.25 m over the crest. That is C 7.8, 4.6 x critical flow for a free overfall on the crest [Certain, arithmetic], and it equals the natural peak of 628 as if the crest were not there. A pool level cannot pass 4.6 x critical flow over a crest, so I read this as RAS's face equations carrying no critical control across a thin raised face [Likely]. **It is outside the rule, it does not change the verdict, and it needs saying: on the only coefficient-free pair the two models differ by 19 % and 0.34 m.** Wadi2D sits on critical flow, 0.996 of it in the analytic test. `a94_10_2d` is running as the same check at 10 m.
- **Not tested:** submerged overtopping (submergence 0.001 here), a crest profile that varies, the shaped embankments of `W8 terrain tools`, a spillway beside a crest. This is a constant thin line on one site.

**RAS's connection on a lattice is a trap, for anyone copying this pipeline.** With the mesh not aligned to the connection, the weir equation made water from the first rain: 12 m3/s steady on the 20 m run, a 28 % volume error, and instability at 10 m. Nothing in RAS flagged the 20 m run, which reported `Unsteady Finished Successfully`. Aligned seeds cured it with no other change. The 20 m peak of 548 was 5 % off the clean 522 and looked plausible. The volume error is what gave it away.
