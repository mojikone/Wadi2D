# W89 Muskingum routing

**Status (2026-11-15): built on branch `feature/muskingum`, cut from `feature/fast-products` at `243ea26`. Not
merged, not pushed. CPU only. This is the live iteration for Muskingum reach routing; `W29 conserving routing` stays
the record of the Muskingum-Cunge schemes, and nothing of it changed. Five code commits, one change each: the method
and the HMS reader (`84e3a81`), generated basins (`563bea0`), the proposal command (`74768bb`), the dock (`6ad92ef`),
the fixes the real dock found (`d6ff6b3`); then this folder. 46 of 46 through the real dock on QGIS 3.44.8;
`tests/plugin` whole 590 passed; HMS 4.12's own series to round-off on fourteen headless cases.**

His words (2026-11-15): "for HMS routing add Muskingum too ... two parameters called K and X ... Muskingum-Cunge needs
more effort to apply the section parameters, but Muskingum is faster and easier, but I have no idea how better or
worse it is."

## The answer to his question, on Block 2

**Muskingum is as good as Muskingum-Cunge only at the flood its K was taken from, and only reach by reach. It is not
the easier method on Block 2: a K worth using still comes from the section, so the effort he wants to save is spent
anyway, and the K that needs no section is two to four times too long.** [Certain for these runs; neither method has
a gauge behind it here, so "Muskingum-Cunge" below is the project's reference, not the truth.]

Block 2's HMS project, Basin 3 (71 reaches, 5 reservoirs), the depth-area analyses as HMS runs them. Every
Muskingum-Cunge reach got K, X and subreaches from the helper at its own 200-yr peak inflow
(`scripts/block2_study.py`, `results/block2_study.json`).

| What | Peak against Muskingum-Cunge | Time to peak |
|---|---|---|
| Each of the eight hill reaches alone, 200 yr (the flood K was set for) | within 0.1 % | the same 5-minute step |
| The five dams, 200 yr | Z4C +0.1 %, Faydh 01 +0.1 %, Bidah 03 0 (no reach above it), **R5A +3.5 %, R2A +4.5 %** | 0 to 20 min early |
| Junctions down the plain, 200 yr | FIZ-J1 +2.5 %, **RIJ-J2 +12.2 %, FAY-J3 +19.7 %** | 15 to 60 min early |
| The same K and X at 100 yr, dams | +0.3 to +6.8 % | 5 to 25 min early |
| The same K and X at 10,000 yr, dams | -1.0 to -8.4 % | 0 to 25 min late |
| The same K and X at 2 yr, dams | **+17 to +45 %** | **25 to 260 min early** |
| X set to 0.1, 0.2 or 0.3 on every reach, 200 yr, dams | moves the peak by 2.3 % at most | by 10 min at most |
| K 30 % shorter or longer, 200 yr, dams | **+18.7 % to -8.5 %** | 60 min early to 30 min late |
| K from Kirpich on the reach, X 0.2 (no section used), 200 yr, dams | **-21 to -34 %** | 45 min early to 275 min late |

The ranges over the dams leave out Bidah 03, which has no reach above it and reads 0 in every row.

Four things to read out of it.

1. **Reach by reach it works.** At the design flood the helper's K and X give each hill reach the Muskingum-Cunge
   peak within 0.1 % and the same lag. [Certain]
2. **Where branches meet it does not, and the cause is the method, not the numbers.** [Certain, the hydrograph table
   below.] A constant K moves the whole hydrograph at the peak's speed; Muskingum-Cunge moves the low rising limb far
   slower than the peak. Sixty minutes before its own peak, R7's outflow is 105 m3/s by Muskingum-Cunge and 317 m3/s
   by Muskingum. So a Muskingum hydrograph arrives early on its rising limb, and where it meets the peak of a shorter
   branch the sum is higher and earlier: +3.5 % at R5A, +4.5 % at R2A, +20 % after 53 km of wide channel at FAY-J3.
   No choice of X mends that (the X columns move those points by 1 to 5 %).
3. **Fixed numbers drift with the flood.** R1's peak takes 250 min through the reach at 2 yr, 85 at 200 yr and 60 at
   10,000 yr by Muskingum-Cunge; Muskingum takes 85 min at all of them. One basin model run from 2 yr to 10,000 yr,
   which is how the dam hydrology is done, is exactly what fixed K and X cannot follow. The cure is a K per return
   period, which is Muskingum-Cunge done by hand.
4. **K is the number; X hardly matters.** Chow's remark that the method is insensitive to X holds here. A 30 % error in
   K is worth up to 19 % of a dam's peak and an hour. And the K that needs no section, Kirpich on the reach, is 2 to 4
   times the travel time of the 200-yr peak (R1: 262 min against 85), so it costs a fifth to a third of the peak.

Is it faster? One route of R1's 48 h series takes about 5 ms by Muskingum-Cunge and about 0.015 ms by Muskingum
(4.6 to 6.2 ms and 12 to 17 microseconds over three runs), some 350 times less, and the whole study above runs in
2 s either way: compute time is not what Muskingum saves. One thing it does
better: its volume closes exactly (out/in 1.0000 on every reach), where the HMS-faithful Muskingum-Cunge creates 2.7 %
on R1 at 2 yr (W25, W29).

**What I would do:** keep Muskingum-Cunge for the dams and the channels, as the project has it. Use Muskingum where an
HMS model already holds it, where a travel time is known from records, or for one flood size with K from the helper
at that flood. [Likely] The reference flow matters: the EM advises midway between base flow and peak; here that
gives -1.0 to -7.1 % at the dams and -1.3 % at FAY-J3 (the sensitivity table), better down the plain and worse at
the hill dams than the peak reference he asked for. Neither is right everywhere, for the reason of point 2.

### 200 yr, K and X at each reach's 200-yr peak

HMS's own numbers are the project's results file; "Muskingum-Cunge here" is this engine's replication of it, the same
to the digit shown. J2 and J13 are not analysis points of the project, so there the two methods are compared under
the storm of the point's own drainage area, with no HMS number.

| Point | HMS's own, m3/s at h | Muskingum-Cunge here | Muskingum | Peak, % | Time to peak, min |
|---|---|---|---|---|---|
| Z4C | 2,101.1 at 15.42 | 2,101.1 at 15.42 | 2,102.5 at 15.42 | +0.07 | +0 |
| R2A | 1,735.9 at 14.17 | 1,735.9 at 14.17 | 1,814.7 at 13.83 | +4.54 | -20 |
| Faydh 01 | 1,240.1 at 13.25 | 1,240.1 at 13.25 | 1,241.1 at 13.17 | +0.08 | -5 |
| Bidah 03 | 454.6 at 12.75 | 454.6 at 12.75 | 454.6 at 12.75 | +0.00 | +0 |
| R5A | 1,143.5 at 14.67 | 1,143.5 at 14.67 | 1,183.3 at 14.33 | +3.48 | -20 |
| J2 | not an analysis point | 2,070.8 at 14.92 | 2,071.0 at 14.92 | +0.01 | +0 |
| J13 | not an analysis point | 999.7 at 14.17 | 1,009.2 at 14.00 | +0.95 | -10 |
| RIJ-J2 | 1,277.1 at 17.83 | 1,277.1 at 17.83 | 1,432.8 at 17.33 | +12.20 | -30 |
| FIZ-J1 | 2,142.2 at 17.33 | 2,142.2 at 17.33 | 2,196.0 at 17.08 | +2.51 | -15 |
| FAY-J3 | 2,217.9 at 19.33 | 2,217.9 at 19.33 | 2,655.1 at 18.33 | +19.71 | -60 |

The dams are the inflow to each reservoir (the junction of the dam's name). J2 is below R1, J13 below R7; RIJ-J2 is
below the R2A and R5A reservoirs (RIJ-R1, RIJ-R2), FIZ-J1 below the Z4C reservoir (FIZ-R1, 12 km), FAY-J3 below the
Faydh 01 reservoir and 53 km of the HAT reaches.

### The same K and X at other floods: Muskingum less Muskingum-Cunge, peak and time to peak

| Point | 2 yr MC peak, m3/s | 2 yr Muskingum | 100 yr MC peak, m3/s | 100 yr Muskingum | 200 yr MC peak, m3/s | 200 yr Muskingum | 10,000 yr MC peak, m3/s | 10,000 yr Muskingum |
|---|---|---|---|---|---|---|---|---|
| Z4C | 71.2 | +36.2 % / -260 min | 1,666.4 | +0.9 % / -10 min | 2,101.1 | +0.1 % / +0 min | 5,668.0 | -2.2 % / +25 min |
| R2A | 54.7 | +36.3 % / -150 min | 1,356.1 | +6.6 % / -25 min | 1,735.9 | +4.5 % / -20 min | 4,977.2 | -2.9 % / +0 min |
| Faydh 01 | 58.5 | +16.8 % / -25 min | 993.5 | +0.3 % / -5 min | 1,240.1 | +0.1 % / -5 min | 3,212.2 | -1.0 % / +0 min |
| Bidah 03 | 19.0 | +0.0 % / +0 min | 362.4 | +0.0 % / +0 min | 454.6 | +0.0 % / +0 min | 1,175.6 | +0.0 % / +0 min |
| R5A | 38.9 | +45.1 % / -210 min | 887.1 | +6.8 % / -25 min | 1,143.5 | +3.5 % / -20 min | 3,406.7 | -8.4 % / +15 min |
| J2 | 77.1 | +26.2 % / -170 min | 1,646.1 | +0.6 % / -10 min | 2,070.8 | +0.0 % / +0 min | 5,522.3 | -1.5 % / +15 min |
| J13 | 39.9 | +32.4 % / -135 min | 784.7 | +3.2 % / -15 min | 999.7 | +0.9 % / -10 min | 2,811.9 | -6.7 % / +10 min |
| RIJ-J2 | 11.0 | +0.0 % / +0 min | 639.6 | +13.1 % / -80 min | 1,277.1 | +12.2 % / -30 min | 7,943.8 | -4.1 % / +35 min |
| FIZ-J1 | 15.0 | +0.0 % / +0 min | 1,654.8 | +5.7 % / -25 min | 2,142.2 | +2.5 % / -15 min | 6,346.2 | -5.8 % / +55 min |
| FAY-J3 | 53.2 | +93.9 % / -455 min | 1,627.8 | +30.0 % / -105 min | 2,217.9 | +19.7 % / -60 min | 9,542.2 | -6.9 % / +90 min |

RIJ-J2 and FIZ-J1 read 0 at 2 yr because no dam above them spills: their flow is local.

### Reaches alone: each Muskingum reach on the Muskingum-Cunge run's own inflow

The eight hill reaches and five long reaches of the plain. Each cell: the reach's peak inflow at that flood, then the
Muskingum outflow peak against Muskingum-Cunge's, then the lag of the peak, Muskingum less Muskingum-Cunge. "dry": the
dam above does not spill at that flood. FAY-R1 carries nothing at 200 yr, so its K came from the index celerity of the
HMS file, 1.524 m/s (HMS's default, 5 ft/s), and at 10,000 yr it is 90 min late and 11 % low: the helper's fallback
when no flow is given is not a design number, and its words say so.

| Reach | 200-yr peak in, m3/s | K, h | X | Subreaches | Wave speed, m/s | 2 yr: peak in, m3/s: outflow peak, lag of the peak | 100 yr | 200 yr | 10,000 yr |
|---|---|---|---|---|---|---|---|---|---|
| R1 | 1,276 | 1.4085 | 0.404 | 17 | 5.13 | 63: -0.6 %, -165 min | 1,022: -0.1 %, -5 min | 1,276: -0.1 %, +0 min | 3,321: -0.0 %, +25 min |
| R2 | 2,050 | 0.4937 | 0.358 | 6 | 4.70 | 75: +1.9 %, -80 min | 1,629: -0.0 %, +0 min | 2,050: -0.0 %, +0 min | 5,473: -0.0 %, +10 min |
| R3 | 830 | 0.9693 | 0.404 | 12 | 4.17 | 41: +0.2 %, -115 min | 665: +0.0 %, -5 min | 830: -0.0 %, +0 min | 2,170: -0.0 %, +15 min |
| R4 | 431 | 0.8348 | 0.455 | 10 | 3.14 | 22: +2.3 %, -75 min | 345: -0.1 %, -5 min | 431: -0.1 %, +0 min | 1,103: -0.1 %, +15 min |
| R5 | 969 | 0.0569 | 0.267 | 1 | 3.22 | 29: +0.1 %, -10 min | 753: -0.2 %, +0 min | 969: -0.1 %, +0 min | 2,711: -0.1 %, +0 min |
| R6 | 692 | 0.26 | 0.438 | 3 | 4.55 | 39: +0.1 %, -30 min | 556: +0.0 %, +0 min | 692: +0.0 %, +0 min | 1,771: -0.0 %, +5 min |
| R7 | 610 | 1.0693 | 0.44 | 13 | 4.42 | 33: +0.2 %, -120 min | 490: -0.0 %, -5 min | 610: -0.1 %, +0 min | 1,569: -0.0 %, +20 min |
| R8 | 972 | 0.5595 | 0.394 | 7 | 3.86 | 38: +0.9 %, -60 min | 762: -0.2 %, +0 min | 972: -0.1 %, +0 min | 2,741: -0.0 %, +10 min |
| RIJ-R1 | 697 | 1.375 | 0.416 | 17 | 1.68 | dry | 344: +0.1 %, -25 min | 697: -0.0 %, +0 min | 4,641: -0.2 %, +45 min |
| FIZ-R1 | 1,980 | 1.4905 | 0.39 | 18 | 2.26 | dry | 1,544: -0.0 %, -10 min | 1,980: -0.1 %, +0 min | 5,539: -0.2 %, +30 min |
| FAY-R1 | 0 | 2.9092 | 0.443 | 35 | 1.52 | dry | dry | dry | 2,531: -11.3 %, +90 min |
| HAT-R3 | 2,122 | 1.701 | 0.416 | 20 | 2.46 | 63: +4.4 %, -120 min | 1,629: -1.3 %, -15 min | 2,122: -2.1 %, -5 min | 6,292: -1.0 %, +35 min |
| HAT-R5 | 2,292 | 1.3305 | 0.342 | 16 | 2.05 | 59: +1.8 %, -80 min | 1,703: +0.2 %, -10 min | 2,292: +0.1 %, +0 min | 8,061: -0.6 %, +30 min |

### Lag of the peak through each reach, and volume out over volume in (48 h window)

| Reach | 2 yr lag MC / M, min | 2 yr out/in MC / M | 100 yr lag MC / M, min | 100 yr out/in MC / M | 200 yr lag MC / M, min | 200 yr out/in MC / M | 10,000 yr lag MC / M, min | 10,000 yr out/in MC / M |
|---|---|---|---|---|---|---|---|---|
| R1 | 250 / 85 | 1.0274 / 1.0000 | 90 / 85 | 0.9992 / 1.0000 | 85 / 85 | 0.9992 / 1.0000 | 60 / 85 | 0.9994 / 1.0000 |
| R2 | 120 / 40 | 1.0056 / 1.0000 | 30 / 30 | 0.9996 / 1.0000 | 35 / 35 | 0.9996 / 1.0000 | 20 / 30 | 0.9997 / 1.0000 |
| R3 | 170 / 55 | 1.0097 / 1.0000 | 65 / 60 | 0.9997 / 1.0000 | 60 / 60 | 0.9997 / 1.0000 | 40 / 55 | 0.9997 / 1.0000 |
| R4 | 125 / 50 | 1.0206 / 1.0000 | 55 / 50 | 1.0003 / 1.0000 | 50 / 50 | 1.0001 / 1.0000 | 35 / 50 | 1.0000 / 1.0000 |
| R5 | 15 / 5 | 1.0008 / 1.0000 | 5 / 5 | 1.0000 / 1.0000 | 5 / 5 | 1.0000 / 1.0000 | 0 / 0 | 1.0000 / 1.0000 |
| R6 | 45 / 15 | 1.0048 / 1.0000 | 15 / 15 | 0.9999 / 1.0000 | 15 / 15 | 0.9999 / 1.0000 | 10 / 15 | 0.9999 / 1.0000 |
| R7 | 185 / 65 | 1.0211 / 1.0000 | 70 / 65 | 0.9998 / 1.0000 | 65 / 65 | 0.9998 / 1.0000 | 45 / 65 | 0.9998 / 1.0000 |
| R8 | 100 / 40 | 1.0073 / 1.0000 | 35 / 35 | 0.9997 / 1.0000 | 35 / 35 | 0.9998 / 1.0000 | 25 / 35 | 0.9998 / 1.0000 |
| RIJ-R1 | dry | dry | 110 / 85 | 1.0035 / 0.9999 | 85 / 85 | 1.0035 / 1.0000 | 40 / 85 | 1.0013 / 1.0000 |
| FIZ-R1 | dry | dry | 105 / 95 | 1.0030 / 1.0000 | 90 / 90 | 1.0043 / 1.0000 | 60 / 90 | 1.0005 / 1.0000 |
| FAY-R1 | dry | dry | dry | dry | dry | dry | 90 / 180 | 1.0184 / 1.0000 |
| HAT-R3 | 220 / 100 | 1.0131 / 1.0000 | 120 / 105 | 1.0005 / 1.0000 | 110 / 105 | 0.9996 / 1.0000 | 65 / 100 | 0.9994 / 1.0000 |
| HAT-R5 | 160 / 80 | 1.0034 / 1.0000 | 95 / 85 | 1.0000 / 1.0000 | 85 / 85 | 0.9997 / 1.0000 | 50 / 80 | 0.9995 / 1.0000 |

### 200 yr, the two outflow hydrographs of a reach round the Muskingum-Cunge peak, MC / Muskingum, m3/s

The peaks agree; the limbs do not. This is point 2 above.

| Reach | -90 min | -60 min | -30 min | -15 min | +0 min | +15 min | +30 min | +60 min | +90 min |
|---|---|---|---|---|---|---|---|---|---|
| R3 | 163 / 357 | 501 / 587 | 766 / 773 | 815 / 815 | 826 / 826 | 809 / 807 | 771 / 766 | 661 / 640 | 535 / 497 |
| R7 | 63 / 156 | 105 / 317 | 502 / 529 | 587 / 589 | 607 / 606 | 588 / 586 | 548 / 539 | 437 / 403 | 337 / 292 |
| HAT-R3 | 198 / 1,104 | 311 / 1,200 | 1,195 / 1,454 | 1,403 / 1,953 | 2,089 / 2,035 | 1,936 / 1,884 | 1,779 / 1,673 | 1,472 / 1,271 | 1,214 / 961 |

### 200 yr sensitivity: peak and time to peak against Muskingum-Cunge, % / min

X on every reach, K and subreaches as proposed. K scaled on every reach, the subreaches counted again as K over the
step, X as proposed (cut to the stable ceiling on 5 short reaches at 0.7 and 3 at 1.3). The last two columns are other
ways to the numbers: Cunge at half each reach's peak, and the helper with no section (Kirpich on the reach, X 0.2).

| Point | As proposed | X = 0.1 | X = 0.2 | X = 0.3 | K x 0.7 | K x 1.3 | K, X at half the peak | K by Kirpich, X 0.2 |
|---|---|---|---|---|---|---|---|---|
| Z4C | +0.07 % / +0 | -2.26 % / +0 | -1.49 % / +0 | -0.68 % / +0 | +2.89 % / -30 | -3.90 % / +30 | -3.08 % / +25 | -32.22 % / +275 |
| R2A | +4.54 % / -20 | +3.52 % / -20 | +3.80 % / -20 | +4.08 % / -20 | +11.89 % / -30 | -3.19 % / -5 | -1.94 % / -5 | -29.53 % / -45 |
| Faydh 01 | +0.08 % / -5 | -0.59 % / -5 | -0.40 % / -5 | -0.20 % / -5 | +1.41 % / -5 | -1.29 % / +0 | -1.05 % / +0 | -21.35 % / +35 |
| Bidah 03 | +0.00 % / +0 | +0.00 % / +0 | +0.00 % / +0 | +0.00 % / +0 | +0.00 % / +0 | +0.00 % / +0 | +0.00 % / +0 | +0.00 % / +0 |
| R5A | +3.48 % / -20 | +2.81 % / -30 | +2.91 % / -30 | +3.10 % / -25 | +18.74 % / -45 | -8.51 % / -60 | -7.05 % / -65 | -33.95 % / +20 |
| J2 | +0.01 % / +0 | -1.79 % / +0 | -1.22 % / +0 | -0.62 % / +0 | +1.83 % / -20 | -3.29 % / +25 | -2.58 % / +20 | -29.62 % / +180 |
| J13 | +0.95 % / -10 | -0.71 % / -10 | -0.28 % / -10 | +0.19 % / -10 | +10.49 % / -25 | -8.25 % / +20 | -7.10 % / +15 | -30.43 % / +125 |
| RIJ-J2 | +12.20 % / -30 | +9.69 % / -30 | +10.49 % / -30 | +11.29 % / -30 | +13.66 % / -70 | +11.12 % / +10 | +10.91 % / +5 | +2.89 % / +150 |
| FIZ-J1 | +2.51 % / -15 | -1.11 % / -15 | +0.05 % / -15 | +1.30 % / -15 | +9.72 % / -70 | -4.10 % / +45 | -3.13 % / +45 | -35.84 % / +350 |
| FAY-J3 | +19.71 % / -60 | +14.24 % / -75 | +15.82 % / -70 | +17.69 % / -65 | +47.61 % / -165 | -0.96 % / +50 | -1.30 % / +55 | -36.78 % / +320 |

### K in minutes / X / subreaches of the hill reaches, by how they were derived

| Reach | Muskingum-Cunge lag of the 200-yr peak, min | Cunge at the 200-yr peak | Cunge at half the peak | Kirpich on the reach, X default |
|---|---|---|---|---|
| R1 | 85 | 85 / 0.404 / 17 | 106 / 0.422 / 21 | 262 / 0.2 / 52 |
| R2 | 35 | 30 / 0.358 / 6 | 37 / 0.39 / 7 | 122 / 0.2 / 24 |
| R3 | 60 | 58 / 0.404 / 12 | 73 / 0.42 / 15 | 172 / 0.2 / 34 |
| R4 | 50 | 50 / 0.455 / 10 | 65 / 0.461 / 13 | 112 / 0.2 / 22 |
| R5 | 5 | 3 / 0.267 / 1 | 4 / 0.381 / 1 | 17 / 0.2 / 3 |
| R6 | 15 | 16 / 0.438 / 3 | 20 / 0.445 / 4 | 61 / 0.2 / 12 |
| R7 | 65 | 64 / 0.44 / 13 | 81 / 0.451 / 16 | 174 / 0.2 / 35 |
| R8 | 35 | 34 / 0.394 / 7 | 41 / 0.417 / 8 | 108 / 0.2 / 22 |

On all 71 reaches of Basin 3: 2 are not stable at the 5 min step (BID-R24, 237 m, and RIJ-R11, 228 m: the wave
crosses them in under half a step, and the run warns as HMS would); Cunge's X came out below zero on 6 short flat
reaches and was set to 0; X was lowered for the step on 5; BID-R1 and FAY-R1 carry no flood at 200 yr. No element's
outflow went below zero in any run.

How the reference flow of a reach was chosen: its peak inflow in the Muskingum-Cunge run of the smallest analysis
point below it, which is the flow the depth-area method gives that reach.

## [PRESERVE-CHECK]

**KEEP, numbers to the last digit:** `MuskingumCunge`, its two schemes and both kernels; the lag and no-routing
methods; every reservoir and diversion; the replication of Block 2 (`tests/hydrology` passes, the 39 depth-area
analyses included); a job without `hydrology.muskingum` keeps its hash, so an old checkpoint resumes
(`test_a_job_without_muskingum_keeps_the_hash_it_had_before_it`); `basin.json` files without a `routing` key read as
before; the dock's other rows; the solver.

**CHANGE:** a new routing method `Muskingum` in the registry; `hydrology.reach_routing` gains `muskingum`, and the job
gains `hydrology.muskingum` (K, X, subreaches by reach); the HMS reader maps `Route: Muskingum`; a reach of
`basin.json` may carry `routing: muskingum` with its own parameters; a new command `wadi2d muskingum`; the dock's Reach
routing combo gains Muskingum with a reach table and a proposal button; a run warns of a Muskingum reach outside its
stable range. One existing test was edited: `test_a_job_dates_monthly_evaporation_from_storm_rain_start` fakes the
job's hydrology with a `SimpleNamespace`, which now needs `muskingum=[]`.

**FILES:** `wadi2d/hydrology/muskingum.py` (new), `muskingum_proposal.py` (new), `constants.py`, `from_hms.py`;
`wadi2d/config/schema.py`; `wadi2d/run.py`; `wadi2d/basin/contract.py`, `loader.py`, `job.py`, `parameters.py`;
`wadi2d/engine/muskingum_proposals.py` (new), `cli.py`; `plugin/wadi2d_qgis/muskingum_rows.py` (new),
`muskingum_query.py` (new), `sections/muskingum_table.py` (new), `sections/hydrology.py`, `sections/basin_rows.py`,
`job_builder.py`, `dock.py`; tests under `tests/hydrology`, `tests/basin`, `tests/engine`, `tests/plugin`,
`tests/data/hms_muskingum`; this folder.

## What was built

### 1. The method, as HEC-HMS 4.12 computes it (`wadi2d/hydrology/muskingum.py`)

K in hours, X, and a number of subreaches. Each subreach is routed with K / n and the same X by the coefficient form
of the HMS Technical Reference Manual ("Muskingum Model", eq. 6; the same as EM 1110-2-1417, eq. 9-16 to 9-19), at the
control step, starting with outflow equal to inflow:

    O2 = C1 I2 + C2 I1 + C3 O1
    C1 = (dt - 2KX) / (2K(1-X) + dt),  C2 = (dt + 2KX) / (2K(1-X) + dt),  C3 = (2K(1-X) - dt) / (2K(1-X) + dt)

**How HMS handles the range 2KX <= dt <= 2K(1-X), measured, not read:** [Certain] the manual's page gives no
inequality at all, only that a subreach's travel time should be about the step. Run headless, HMS 4.12 neither refuses
nor corrects a reach outside the range. It prints `WARNING 41169: Muskingum routing is unstable with the given
parameters for reach "..."` and routes with the negative coefficient: under 2KX the outflow dips before it rises
(1.73 m3/s under a base flow of 2.00) and at X = 0.5 also passes the inflow's peak (401.5 m3/s from 400); on a dry
bed the reach's own outflow goes below zero on either side of the range (-2.4 and -6.2 m3/s under 2KX, -0.07 over
2K(1-X)), which the element below sets to zero (`WARNING 41201: 6 negative inflows to element "Outlet" set to
zero`). The warning fires exactly where one coefficient is negative: on 8 of the 14 cases, the 8 the inequality
names. X = 0.5 with K / n equal to the step, the edge of the range, routes without a warning.

Wadi2D does the same: the series is HMS's to round-off inside and outside the range, nothing is clipped (a clipped
ordinate would create water), and a run emits a warning per reach in HMS's words plus what HMS does not say, which
side of the range the step is on and which subreach counts are stable (`Muskingum.note`, `reach_notes`,
`stable_subreaches`). One difference stays: HMS zeroes a negative inflow at the next element and Wadi2D's network does
not, so below an unstable reach on a dry bed the two would part by that water. [Certain] It was not changed, because
zeroing at junctions would move the conserving Muskingum-Cunge of W29 by its own small dips; the warning is the
guard.

HMS's other start (a specified discharge) and a channel loss on a Muskingum reach are refused by name. X outside 0 to
0.5 is refused, as HMS's editor does.

### 2. The HMS basin file keys, proven by re-save

W59's way: a metric test project written from scratch (`scripts/musk_cases.py`, on W59's `hms_project.py`), one basin
per case with a Source, a Reach and a Sink, opened by HEC-HMS 4.12 and written back on `SaveBasinModelAs`. HMS wrote
back, in this order:

    Route: Muskingum
    Initial Variable: Combined Inflow
    Muskingum K: 1.0
    Muskingum x: 0.2
    Muskingum Steps: 12
    Channel Loss: None

so `Muskingum K` (hours), `Muskingum x` (a small x) and `Muskingum Steps` are the keys HMS reads; the control key that
HMS does not read was dropped, as in W59. The re-saved files are the test data (`tests/data/hms_muskingum`).

### 3. The race against HEC-HMS 4.12

HMS ran headless (W59's `run_hms.ps1`), W59's inflow (400 m3/s at 6 h over a base of 2 m3/s) and a second gage for a
flood on a dry bed (0 to 400 m3/s and back to 0), 5 min step, 48 h. `scripts/export_cases.py` wrote HMS's series and
messages to the oracle; `scripts/probe_form.py` is the probe.

| Case | K, h | X | Subreaches | Step against 2KX to 2K(1-X) of a subreach, min | HMS peak, m3/s | HMS lowest, m3/s | max abs difference, m3/s | HMS warns |
|---|---|---|---|---|---|---|---|---|
| musk_in_range | 1.0 | 0.2 | 12 | 2 <= 5 <= 8 | 396.355 | 2.000 | 4.0e-13 | no |
| musk_long | 3.0 | 0.3 | 36 | 3 <= 5 <= 7 | 393.565 | 2.000 | 0 | no |
| musk_x0 | 1.5 | 0.0 | 6 | 0 <= 5 <= 30 | 382.486 | 2.000 | 0 | no |
| musk_x05 | 1.0 | 0.5 | 12 | 5 <= 5 <= 5 | 400.000 | 2.000 | 0 | no |
| musk_one | 0.1 | 0.25 | 1 | 3 <= 5 <= 9 | 399.591 | 2.000 | 0 | no |
| musk_low | 1.0 | 0.2 | 1 | 5 under 24 | 377.772 | 1.730 | 3.4e-13 | 41169 |
| musk_low_mild | 0.5 | 0.1 | 1 | 5 under 6 | 391.215 | 1.997 | 3.4e-13 | 41169 |
| musk_high | 0.05 | 0.2 | 1 | 5 over 4.8 | 399.891 | 2.000 | 5.7e-14 | 41169 |
| musk_high_n | 1.0 | 0.2 | 40 | 5 over 2.4 | 398.282 | 2.000 | 9.1e-13 | 41169 |
| musk_x05_low | 1.0 | 0.5 | 4 | 5 under 15 | 401.464 | 1.305 | 5.1e-13 | 41169 |
| musk_dry_in | 1.0 | 0.2 | 12 | 2 <= 5 <= 8 | 387.730 | 0.000 | 4.0e-13 | no |
| musk_dry_low | 1.0 | 0.2 | 1 | 5 under 24 | 334.886 | -2.364 | 3.4e-13 | 41169, 41201 |
| musk_dry_high | 0.05 | 0.2 | 1 | 5 over 4.8 | 399.014 | -0.068 | 5.7e-14 | 41169, 41201 |
| musk_dry_x05_low | 1.0 | 0.5 | 4 | 5 under 15 | 392.198 | -6.201 | 5.7e-13 | 41169, 41201 |

The worst difference on fourteen cases is 9e-13 m3/s on a 400 m3/s peak, 2e-15 of it. W59's tolerance for its solved
structures is 3e-4 of peak; the test here asks 1e-12, since the method is a closed form
(`tests/hydrology/test_muskingum.py`, the 14 cases three ways: the file read whole, the series, and a note exactly
where HMS warns).

### 4. The textbook check

Chow, Maidment and Mays (1988), Applied Hydrology, Example 8.4.1 (Table 8.4.1): K = 2.3 h, X = 0.15, a 1 h step.
The test gets the book's C1 = 0.0631, C2 = 0.3442, C3 = 0.5927 to the four decimals printed and its outflow column
(85, 91, 114, 159, ... peak 642 cfs at the eleventh hour) to the unit the book rounds to. [Likely] The table was
typed from memory of the book, not from the book on the desk; its first four lines were recomputed by hand from the
coefficients before the test was written (91.0, 114.2, 159.5), and the whole column follows from the coefficients
within the book's rounding, which is what the test asserts. The book starts the outflow at 85 under an inflow of 93;
a reach here starts at its inflow, and the routing is linear, so the two differ by 8 cfs decaying as C3 to the step,
which the test removes.

### 5. The job, and generated basins

- `hydrology.reach_routing: muskingum` with `hydrology.muskingum: [{reach, k_hours, x, subreaches}]`. On an HMS
  basin every Muskingum-Cunge reach then needs an entry, and a run stops naming every reach without one; nothing is
  invented. Entries with another `reach_routing` are refused ("or the numbers would be ignored"). A reach the HMS
  file routes by Muskingum keeps its own numbers under any choice; a lag reach keeps its lag.
- On a generated basin (`basin.json`), a reach may carry `"routing": "muskingum"` with parameters
  `muskingum_k_hours`, `muskingum_x` and `muskingum_subreaches` (1 when absent); its section is then not needed, and
  `missing` asks for K and X. Under the job's `muskingum` every reach is such a reach, with the job's numbers
  (source `job`) or the file's own. One with neither is incomplete by the existing rule of W27: left out and named
  ("reach R1 lacks muskingum_k_hours, muskingum_x: the water of ... enters the 2D grid there"), its water on the grid.
- Through the hand-back (W25's closed box): the reach's outflow is the coefficient form of the line's inflow by hand
  to 1e-9, the books close, `routing_defect` under 1e-6 of the water, from the file's own reach and from the job's
  numbers alike (`tests/engine/test_handback.py`).

### 6. The helper: K, X and subreaches proposed, shown, never applied (`muskingum_proposal.py`, `wadi2d muskingum`)

`wadi2d muskingum <file.basin or basin.json> [--flow REACH=M3S ...] [--velocity M_S] [--dt MIN | --control FILE]
[--out FILE]` prints one line of numbers and the derivation per reach, or writes JSON. It changes nothing; the job
takes numbers only from `hydrology.muskingum`. Per reach, the best basis its data allow:

1. **A section and a reference flow:** Cunge (1969). K = L / c with c by Seddon's law on the trapezoid's rating,
   c = (1 / B) dQ / dy (EM 1110-2-1417 eq. 9-20, 9-21; HMS manual eq. 7, 8); X = 1/2 (1 - Q0 / (B S0 c dx)) with dx the
   subreach's length (EM eq. 9-22). Subreaches: K over the step (EM 9-3c(3); HMS manual), or the nearest count at
   which X is not negative and a subreach is stable.
2. **A section, no flow:** the same at the flow whose wave speed is the reach's index celerity, with a sentence telling
   the user to give a flow if that one is far from the flood. On Block 2 it is far: 1.524 m/s is HMS's default, and
   the hill reaches carry their 200-yr peaks at 3.1 to 5.1 m/s.
3. **No section, a mean velocity from the user:** K = L / (1.5 v); 1.5 is the EM's ratio of wave speed to mean
   velocity for natural channels (9-3c(2)(b): 1.67 wide rectangular, 1.44 wide parabolic, 1.33 triangular). X = 0.2,
   said to be a default.
4. **No section, a length and a slope:** K from Kirpich's expression on the reach, L^0.77 / (52 S^0.385) minutes,
   which the words call a rough start; on Block 2 it is 2 to 4 times too long (table above). X = 0.2.
5. **None of these:** no proposal, in words.

Where the step makes Cunge's X unusable the helper says what it did: a negative X becomes 0 on one subreach ("the
reach attenuates more than Muskingum can show"); an X no count keeps stable is lowered to the highest stable value;
a reach the wave crosses in under half a step is called not routable at this step. K is rounded to 4 decimals and X
to 3 before the stability check, so the numbers shown are the numbers checked.

**Sources, each read on 2026-11-15:** EM 1110-2-1417, Flood-Runoff Analysis (USACE, 31 August 1994), chapter 9,
paragraph 9-3c: the Muskingum equation and coefficients (9-15 to 9-19), K as travel time and Seddon's law (9-20,
9-21), the wave-speed ratios, X ("0.0" and "0.5" the limits; mild slopes with overbank flow nearer 0.0, steep well
defined channels nearer 0.5), Cunge's X (9-22) with the note that a reference flow midway between base flow and peak
suits best and a peak reference speeds the wave up (Ponce 1983), and 2KX < dt <= K with subreaches = K / dt (9-23).
HEC-HMS Technical Reference Manual, "Muskingum Model": eq. 6, X between 0.0 and 0.5, the subreach guidance, Seddon's
law. **Not read today, cited from memory:** Cunge (1969), J. Hydraulic Research 7(2), through the EM's eq. 9-22;
Chow, Maidment and Mays (1988) for X "between 0 and 0.3 with a mean value near 0.2" in natural streams and for the
method's insensitivity to X, which is why the default is 0.2. [Likely]

### 7. The dock

The Reach routing combo of section 3 gains "Muskingum: K and X per reach, as HEC-HMS routes them". Under it a table
shows every reach of the HMS basin file or of the generated basin: Reach, Ref. flow, K, X, Subreaches, How it was
derived. `Propose K and X` asks the engine (`wadi2d muskingum`, at the HMS control file's step for an HMS project) and
fills the rows the user has not typed, in italics, with the derivation in the last column; an edit makes a row the
user's, and a later proposal leaves it alone. A velocity box serves the reaches with no section. The note under the
table says how many reaches have K and X and what a run does with the rest. The job takes what the cells hold.
A number HMS would not take (X over 0.5, K of zero, half a subreach) is named in the row and stays out of the job.

## Through the real dock (`checks/dock_muskingum_bidah.py`, `log_dock_muskingum_bidah.txt`, `hydrology_muskingum.png`)

QGIS 3.44.8, a throwaway profile, the engine of this checkout on the CPU, Bidah's ground at 20 m, 60 mm in an hour,
3 h simulated. A basin generated from the DEM (8 subbasins, 4 reaches, the Bidah 03 dam), a reference run on
Muskingum-Cunge, then the Muskingum choice, each reach's peak of that run typed as its reference flow, Propose K and
X, and three more runs. **46 of 46 on the third attempt.** Checked: the combo holds the engine's three choices; the
table lists the generated reaches and proposes nothing by itself; the proposals fill the cells in italics with their
derivation; an edit makes a row the user's and a second proposal leaves it; `job.json` and the job as it ran hold the
table's rows; each reach's outflow in the run is the Muskingum route of its own inflow recomputed by hand in the check
(to the six figures the series file holds); a reach with its K and X cleared is left out by name, its water entering
the grid at J2, and has no series; 400 subreaches on R2 run with the warning in HMS's words and the stable counts;
mass closes in every run; back on the default the table hides and the rows leave the job.

| Reach | K, h / X / subreaches in the job | Peak in, m3/s | Muskingum peak out | Muskingum-Cunge peak out (reference run) |
|---|---|---|---|---|
| R1 (below the dam, which does not spill) | 0.0948 / 0.439 / 1 | 0 | 0 | 0 |
| R2 | 0.2036 / 0.409 / 2 | 142.27 | 140.25 | 141.30 |
| R3 (X halved by hand in the check) | 0.1086 / 0.192 / 1 | 70.92 | 69.19 | 70.27 |
| R4 | 0.0517 / 0.194 / 1 | 48.22 | 47.69 | 47.76 |

**What the real dock found that the unit tests had not** (first attempt 22 of 28, second 44 of 46):

1. A reference flow of 0 typed for R1, the reach below the dry dam, was named a problem of the row and kept the row's
   K and X out of the job, so the run left R1 out. Fixed: a reference flow is only a question to the helper; one that
   means nothing is named, not used, and never holds the row back (`test_a_reference_flow_that_means_nothing...`).
2. On a generated basin the index celerity is taken at the full depth of the fitted section (5.6 to 5.8 m here), so
   with no reference flow the helper stood in flows of 6,700 to 12,900 m3/s for a 20 km2 basin and K of 1 to 6 min,
   two of them not routable at the step. The words said so each time ("Cunge (1969) at 12,940 m3/s", "give a
   reference flow"), which is the helper working as built, but it means: **on a generated basin, type reference
   flows; the fallback is not a starting value there.** Not changed; a cure would be the peaks of a previous run
   offered as reference flows, which is not built.
3. A flow of 12,940 m3/s was printed as 1.294e+04. Fixed (`flow_words`).
4. The two failures of the second attempt were the check's own: it compared a route recomputed from the series file,
   which holds six figures, to 1e-6 of the peak (3e-6 found), and it looked for an unrounded flow in the words. The
   engine's own arithmetic is held to 1e-9 in `tests/engine/test_handback.py`. `log_dock_muskingum_bidah_second_attempt.txt`
   is kept; the first attempt's log was overwritten by the second.
5. With these short steep reaches (500 to 1,800 m, 2.5 to 2.7 m/s) Cunge's X came out at 0.48 and no count of
   subreaches was stable with it at 5 min, so every X was lowered to its stable ceiling (0.19 to 0.41), and said so.
   R2's peak is then 0.7 % under Muskingum-Cunge's.

One line of the log is older than the code: the run's warning for a step over 2K(1-X) said "the outflow
overshoots"; HMS's dry-bed case shows it swinging about the inflow and below zero as the flood ends, and the warning
now says that. The dock check does not read those words.

## Tests

- `tests/hydrology/test_muskingum.py` (71): the textbook, the 14 HMS cases three ways, the books, the range rules,
  the HMS reader under each `reach_routing`, the job's refusals.
- `tests/hydrology/test_muskingum_proposal.py` (20): the section and Cunge by hand, Seddon's law against a difference
  of the rating, a proposal at the flood routing within 2 % of Muskingum-Cunge, each fallback, the rounding, the
  command, the control file's step.
- `tests/basin/test_job.py` (5 new), `tests/engine/test_handback.py` (5 new, two of them the hand-back run from the
  file and from the job), `tests/plugin/test_muskingum_rows.py` (8), the headless QGIS smoke test with the fake
  engine (the table, the button through the process wrapper, the job).
- Run on the branch with the project venv, one folder or file at a time, the GPU hidden from the engine
  (`CUDA_VISIBLE_DEVICES=-1`): `tests/hydrology` 485 passed, 9 skipped (the skips are W59's cases without evaporation);
  `tests/basin` 117 passed; `tests/engine/test_handback.py` 32 passed, 1 skipped (its GPU case); `tests/engine/test_basin_run.py`
  10 passed; `test_network_series.py`, `test_design_lines.py`, `test_rain_preview.py` 12 passed; `tests/hms` 111 passed,
  1 skipped (as before); **`tests/plugin` whole, 590 passed, 0 failed**, both QGIS smoke tests among them. One earlier
  run of `tests/plugin` in this session was made before the GPU was hidden, so its real-engine smoke test ran with
  the engine choice automatic for a few seconds.
- Old jobs: the replication of Block 2 inside `tests/hydrology` passes unchanged; a job without the new key hashes
  as it did; `git restore "W1 research and design note/validation/hms_replication.md"` after the run, as in W29.

## Not done, and what is weak

- **No gauge.** Every number above is one model against another. Whether a wadi flood's rising limb behaves as
  Muskingum-Cunge has it or as Muskingum has it was not tested against a record.
- **Negative ordinates below an unstable reach** are passed on, where HMS zeroes them at the next element (above).
- **An 8-point section or a non-trapezoid HMS reach** gets no Cunge proposal: the helper reads the trapezoid only.
- **A specified initial discharge and channel loss** on an HMS Muskingum reach are refused, not built.
- **The depth-area study and the workbook** were not run with Muskingum reaches; nothing in them is method-specific,
  but it is untested. A resume with a Muskingum reach in a hand-back network: not run.
- **The dock table does not show the file's own K and X of an HMS Muskingum reach until Propose is pressed.**
- **On a generated basin the helper's fallback with no reference flow is useless** (the dock finding above); the
  table has no way yet to take the peaks of a previous run.
- **Preview rain under Muskingum before any K and X is given** builds the same network as a run, so on an HMS
  project it stops with the run's message ("no K and X for ..."). True, and unhelpful in a preview.
- **The real dock was driven on a generated basin only.** The HMS route through the dock is covered by the headless
  smoke test with the fake engine and by the engine tests, not by a real-engine dock run on an HMS project.
- **The full suite was not run** (his rule: at the merge). The folders touched were: see Tests. **No GPU run.**
- **The Chow table** is from memory (above).
- **No human hand** has typed into the table.

## How to rerun

- HMS cases: `python "W89 Muskingum routing/scripts/musk_cases.py" hms every`, then `powershell -File "W59 HMS
  reservoir structures\scripts\run_hms.ps1" "<repo>\W89 Muskingum routing\_work\hms\w89_run.py" <log>`, then
  `python "W89 Muskingum routing/scripts/export_cases.py" hms` and `scripts/probe_form.py`. `_work` is not committed.
- Block 2: with the repo root on `PYTHONPATH`, `python "W89 Muskingum routing/scripts/block2_study.py"` (2 s), then
  `scripts/block2_tables.py`; `results/block2_study.json` and `.md`. `scripts/block2_look.py` lists the project.
- Dock: `powershell -File tests\dock\run_check.ps1 "<repo>\W89 Muskingum routing\checks\dock_muskingum_bidah.py"
  <throwaway folder> -Copy "<repo>\W89 Muskingum routing"`; QGIS 3.44.8, a throwaway profile, the engine on the CPU.
  The harness looks for `.venv` in the checkout; in a worktree, link the main checkout's and remove the link after.
