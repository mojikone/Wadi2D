### Test 3, regional envelope: **cannot say at 21 km2; the record leans to 17, and near Block 2 it sits under both**

**The find first: Block 2 does have gauges.** Two ministry stations lie below Block 2 catchments, and the project holds decades of neighbouring annual peaks, gauged event hydrographs and a national flood-frequency report. Decision 20's "no gauges" holds only in the narrow sense: no event with rain and flow together inside Block 2. Gauge basins from project 2331 laid over the HMS subbasins (`t3_envelope\gauge_basin_overlap.json`) [Certain]:

| Gauge | Basin km2 | Holds of Block 2 | Peaks on record | Largest, year, return period | Q100, report |
|---|---|---|---|---|---|
| **DC417300AD Fizh near Sabakh** | 262 | **S1, S2, S3, S4: all 210.7 km2 of Z4C** | 28 | 475, 1981, 39 yr | 770 |
| **DC434816AD Hatta near Shinas** | 653 | **S11, S12: all 74.2 km2 of Faydh 01** | 27 | 638, 1988, 55 yr | 837 |
| DC237976AD Hatta near Ajib | 478 | 0.9 km2; the mountain station beside Faydh | 26, plus 5 event hydrographs, no rain | 1,200, 1976, 44 yr | 1,710 |

`Francou-Rodier.xlsx` gives other areas (121 km2 for Hatta near Shinas); the polygons are used here. Hatta near Ajib reads 1,710 and Shinas downstream reads 837: the peak halves across the plain, the warning that goes with every plain gauge below.

**What is on W: and where** [Certain, opened]:

| Holds | Where |
|---|---|
| Annual instantaneous peaks 1971 to 2022, 36 stations; frequency fits; Francou-Rodier K | `2224...\06-WORKING\03-Hydrology\WadiGaugeDataAnalyses_MT\` |
| Ministry raw files, 10 stations, Fizh near Sabakh and Hatta near Shinas among them | `2224...\09-RECEIVED\13 SharePoint Data 06.06.2023\General\02_Data\00_Received\01_MAFWWR\27122022_MAFWWR\Wadi Data\` |
| **Shaheen 2021: 6-min flow at Lihban, 1-min rain, the project's HMS calibration** | `2224...\06-WORKING\03-Hydrology\calibration\` |
| **Rain and flow together, 4 events at Lihban; hydrographs at 4 more stations** | `2331...\0.13 REPORTS\Hydrology Final Report- Flood Data Analysis\Data for model calibration- hydrograph\` |
| **National report: Q by return period at 103 stations, K maps, Tc from hydrographs, return period of each largest flood** | same folder, `Report\Final Report\` |

**Readings at 21 km2, 100 yr, m3/s/km2.** HMS 17, 2D 30; the rule's bands are 12 to 23 and 24 or more.

| Source | Reading | Note |
|---|---|---|
| Report's K map for 100 yr at Block 2, K 4.5 to 4.9 [read off its Figure 49 by eye] | 10 to 19 | The method the report prescribes for a location in northern Oman |
| Six nearest gauges, K 4.06 to 4.80 | 5 to 16 | Mostly plain or fan head, low by construction |
| MRMEWR synthetic method, Qmaf = 2.1 A^0.76 S^0.16 NM^-0.142, x 5.9 [JICA] | 7 to 11 | Mountain form; S 15 to 50 m/km, NM 1 to 5 |
| Five northern gauges of 38 to 59 km2, each at its own K | 10, 20, 24, 30, 30 | Kid, Lansab, Misfah, Jifar, Saal; all about 190 to 240 km away |
| All 72 northern stations, u = 220 A^-0.70 | 26 | Scatter x/÷ 1.8 |
| The 37 northern stations of 300 km2 or less, u = 191 A^-0.68 | 24 | Scatter x/÷ 1.6 |
| Musandam regional table, 20 km2 [report Table 69] | 26 | Another governorate |

**Verdict by the rule: cannot say.** Readings fall in both bands and the rule names no winner. It leans to 17: the location-specific methods read 5 to 19; the readings of 24 or more pool all of northern Oman, and the report itself says one table cannot serve there. [Likely] 30 is not ruled out at 21 km2.

**Envelopes rule out nothing.** Saudi regional maximum Q = 251 A^0.45 gives 47 at 21 km2 (Ewea et al. 2018, K 5.5, recurrence 1,000 to 100,000 yr). Shaheen at Lihban, K 5.44, read down to 21 km2 gives 43. Both lie above 17 and 30, so by the rule they support neither. No published Creager or Francou-Rodier set for Oman surfaced on the web beyond project 2331. Wadi Dayqah in Gonu, about 10,000 m3/s estimated on about 1,700 km2, is an estimate at 80 x Bidah's area and is not used.

**At Block 2's own scale no extrapolation is needed, and the record reads lower than the question asked.** K at 100 yr; the same formula, Q0 1e6, A0 1e8:

| | km2 | HMS | 2D, mode c, 20 m |
|---|---|---|---|
| Bidah | 21 | 4.85 | 5.20 |
| Faydh 01 | 74 | 5.10 | 5.52 |
| R5A | 117 | 4.85 | 5.35 |
| R2A | 176 | 5.02 | 5.57 |
| Z4C | 211 | 5.10 | 5.36 |

The six gauges within 30 km read 4.06 to 4.80. Northern Oman, 72 stations: median 4.72, p90 5.29. 2D sits above p90 at four of five dams; HMS above the median at all five.

**A run at a real gauge** (extra; no rule set, reported as a measurement). `t3_envelope\s14_fizh_job.py`: rain-on-grid over the Fizh basin, 100-yr storm at 262 km2, project CN, n 0.05, 20 m.

| At or above the gauge | m3/s |
|---|---|
| Gauge, largest of 28 years | 475 |
| Gauge, Q100 of the report | 770 |
| HMS at Z4C, 7 km upstream, 211 km2 | 1,666 |
| Wadi2D at Z4C | 2,380 |
| **Wadi2D at the gauge** | **2,582, 3.4 x Q100** |

In the model 96 % of the flow passes in two adjoining threads beside the gauge, so the many-channels excuse for plain gauges does not apply here. No transmission loss is in the model. [Likely] A plain gauge reads low, the rating above bank is an extrapolation, and 28 years is short. None of these obviously closes a factor of 3.4, or 2.2 for HMS. **Either the 100-yr storm with these losses is too large for this ground, or 28 years have missed what it describes.**

**Sources.** Project 2331, *Hydrology Final Report - Flood Data Analysis*, 2025 (internal, read on W:). JICA Oman road study, chapter 11, [11784287_04.pdf](https://openjicareport.jica.go.jp/pdf/11784287_04.pdf), quoting the MRMEWR method and growth factors. Ewea, Al-Amri, Dawoud, Elfeki, Natural Hazards 94(2), 2018, [doi 10.1007/s11069-018-3421-x](https://ideas.repec.org/a/spr/nathaz/v94y2018i2d10.1007_s11069-018-3421-x.html). Dayqah: [Water Power Magazine](https://www.waterpowermagazine.com/analysis/the-day-wadi-dayqah-roared/). Al-Rawas and Valeo 2010, 12 Omani basins of 64 to 1,730 km2: [listing](https://squ.elsevierpure.com/ar/publications/relationship-between-wadi-drainage-characteristics-and-peak-flood), not read in full. Searches found no public peak discharge for Shaheen in Al Batinah; the project's gauge is the source.

### Extra: Shaheen at Lihban, an observed flood: **2D response consistent with the flood, in one of two loss forms**

Rule above, fixed before the run. Bani Umar near Lihban, 197.5 km2, 2,540 m3/s, 29.8 Mm3 (an older project table says 35.45; the 5-min record integrates to 29.76 and the 2331 sheet says 29.72), 459 mm at one gauge near the outlet; the two upstream gauges did not record. The sheet's Time column runs on from the start of the record and its Day column flips between 656 and 658, so minute 657 is midnight: main rain 00:00 to 05:40 on the 4th, as the project's HMS run has it [Likely]. Uncalibrated: n 0.05, nothing tuned. Figure: `t3_envelope\fig_lihban.png`.

| At the gauge | Peak, m3/s | / observed | First crest, h | Second flood, h | NSE |
|---|---|---|---|---|---|
| Observed | 2,540 at 4.0 h | 1 | 3.1 (2,160) | 6.0 | |
| **Wadi2D, phi loss** | **2,428** | **0.96** | 3.1 | 6.5 | 0.75 |
| Wadi2D, constant fraction | 1,486 | 0.59 | 3.1 | 6.6 | 0.70 |
| SCS lag 140 min (project HMS), same volume | 1,559 phi, 1,125 fraction | 0.61, 0.44 | | | |
| Project calibration, CN 92, lag 140 | 2,557 | 1.01, with **1.95 x the volume** | | | |

- **Rise and first crest match to about 15 min with nothing tuned.** The model has one broad crest where the gauge has two, so its highest point falls 54 min before the gauge's. The rule reads the first crest.
- **The first set-up run was invalid and is not a result:** the box below the gauge touched the basin at a pinch and 1 % of the water left. The box was widened; nothing else changed.
- **Best-fit SCS lag at Lihban, gauged rain, volume held** (`s11_lag_fit.py`, `s15_lag_events.py`): Shaheen 44 to 86 min; 2013, 72; 2019, 86; 2007, 114 at NSE 0.39. Centroid to centroid 81 to 147 min. Project lag 140. [Likely] The real lag is 0.3 to 0.8 of the project's on this basin, overlapping 2D's 0.3 to 0.6 of HMS. One basin, rain from at most three gauges.
- **The national report points the same way, and warns:** Tc from index hydrographs is a median 0.45 of Kirpich on 33 stations, but it says rising limbs may be under-recorded and the implied velocities look high.
- **Runoff was 33 % of the gauge's rain, against 81 to 85 % at CN 88 in the design storm.** 151 of 459 mm. Implied CN 34 at the gauge's rain, 51 at 330 mm, 69 at 250 mm over the basin; the basin mean is not known. Earlier events 14 to 27 %.

**What the two extras say together** [Likely]: HMS at Block 2 carries two errors of opposite sign, a lag too slow and an excess too large; that is why the calibration needed 1.95 x the volume to reach the peak. 2D corrects the first and keeps the second, so it stands furthest from the gauges. 17 may lie nearer the record than 30 for the wrong reason.
