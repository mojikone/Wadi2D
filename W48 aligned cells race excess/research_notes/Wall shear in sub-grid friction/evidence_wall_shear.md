# Wall shear in narrow, deep, confined channels: what the measurements say about 2D bed-shear-only models against 1D Manning

Researcher's notes, 2026-11-08. The direct measured evidence is thin. I found no field or benchmark study that isolates wall shear in a depth-averaged 2D model against surveyed stage in a gorge. The laboratory evidence that does isolate it is one 1998 technical note, which I read in abstract only. The rest is shear-distribution flume data, practitioner guidance, and the way the commercial sub-grid codes compute face friction. That evidence all points one way: a model that gives the walls no shear sits at the low end of the stage range. How far below the truth it sits depends on a wall-shear share that I could not pin to better than about 26 to 45 % at B/h around 2.5.

Reading status legend: **[full]** = text read in full (or the relevant chapters, extracted locally); **[page]** = a web page read through the fetch tool's summary, with key sentences checked verbatim where stated; **[abstract]** = abstract or catalogue record only; **[snippet]** = search-result snippet only, document not opened.

## Q1. Laboratory channels (rectangular or trapezoidal) in 2D depth-averaged models: stage or velocity errors attributed to side-wall friction, and the B/h where it matters

### Takeaway
One lab comparison, a straight rectangular channel backwater against Lansford and Mitchell's data, says a 2D depth-averaged model with bed friction only and free-slip walls does not reproduce the measured profile unless the friction slope is modified to include the side walls. Its error magnitude and B/h are behind a paywall. Smooth-flume shear measurements show that walls carry a substantial share of boundary shear when B/h < 5. No lab study I found reports a stage error number for a trapezoidal or narrow channel attributed to missing wall friction in a 2D model.

### Cited Findings
- Molls, Zhao and Molls (1998), "Friction Slope in Depth-Averaged Flow", J. Hydraul. Eng. 124(1):81-85, technical note. Because of how the friction slope is calculated, "many two-dimensional (2D) depth-averaged models include only bottom friction", and models "that assume vertical channel sidewalls and utilize free-slip boundary conditions do not account for the friction due to the channel sidewalls". In a straight rectangular channel backwater test against Lansford and Mitchell's experiments, "the 2D numerical solution does not coincide with the experimental data unless the 2D friction slope equation is modified to account for sidewall friction". The note proposes a modified friction slope. **[abstract]**: the stage error, the B/h of the experiment and the form of the correction were not readable (ASCE returned 403). A discussion and closure followed in J. Hydraul. Eng. 125(5), 1999 (Afzalimehr and Lévesque, with the authors). — [ASCE abstract](https://ascelibrary.org/doi/10.1061/%28ASCE%290733-9429%281998%29124%3A1%2881%29); [discussion record](https://ascelibrary.com/doi/10.1061/%28ASCE%290733-9429%281999%29125%3A5%28549%29)
- Knight, Demetriou and Hamed (1984), "Boundary Shear in Smooth Rectangular Channels", J. Hydraul. Eng. 110(4):405-422. It gives an empirical equation for the percentage of total boundary shear force carried by the walls (%SFw) as a function of breadth/depth, plus ancillary equations for mean wall, bed and centre-line bed shear. **[abstract]** — [ASCE](https://ascelibrary.com/doi/10.1061/%28ASCE%290733-9429%281984%29110%3A4%28405%29)
- A 2020 PLOS ONE paper restates a Knight-and-Patel relation as %SFw = 103.23 (1 + 2b/3h)^-1.4128, with aspect ratio b/h (b the channel width, h the flow depth). Its Table 1 compiles experimental data spanning b/h 0.31 to 50. **[page]**: the equation was extracted from HTML, so the exponent's sign is my reconstruction (a positive exponent would give over 100 %). The paper cites Knight and Patel, whose 1985 paper is on closed ducts, so its use for open channels is not verified. — [PMC7145149](https://pmc.ncbi.nlm.nih.gov/articles/PMC7145149/); [Knight-1984 search record](https://ascelibrary.com/doi/10.1061/%28ASCE%290733-9429%281994%29120%3A7%28787%29)
- Tavakkol and Zarrati (2018, Scientia Iranica 25(6)) show that secondary currents govern how shear divides between wall and bed in rectangular channels, and that zero-shear division lines give poor results. Their subsection method matches experimental wall and bed shear forces within 5 % mean relative error. **[abstract]** — [Scientia Iranica](https://scientiairanica.sharif.edu/article_4222.html)
- A 2023 study (Int. Rev. Model. Simul. 16(2):51-61) of supercritical flow in a straight-wall contraction ran a 2D depth-averaged SWE model with Manning, Chézy, Prandtl and a "Manning for vertical channel sidewalls" friction model, against experiments. Wall friction and no-slip conditions did not alter the wave structure or amplitude, but they noticeably changed the mean downstream depth. **[abstract]**, no numbers seen. — [catalogue record](https://searchworks.jioinstitute.edu.in/articles/edb__170766414); [ResearchGate](https://www.researchgate.net/publication/372842098_Friction_Effect_on_Supercritical_Shallow-Water_Flows_in_Straight-Wall_Open-Channel_Contraction)
- Shafiai and Kamaruzaman (2013, Scientific Research Journal 10(1):83-93) added a sidewall-friction force term to a lattice-Boltzmann SWE model (LABSWE). They report that bed and wall Manning coefficients change the simulated flow pattern in a channel with a side cavity, validated on velocity vectors. **[abstract]**, no depth numbers. — [UiTM](https://journal.uitm.edu.my/index.php/SRJ/article/view/3316)
- USACE ERDC's STREMR 2D depth-averaged model, tested on three trapezoidal bends and one straight trapezoidal channel, performed poorly in bends without a secondary-current correction. With the correction it matched on the bed and lower side slope but over-predicted velocity on the upper side slope. That error is in velocity distribution, not stage, and is not attributed to wall shear. **[snippet]** — [ERDC library](https://erdc-library.erdc.dren.mil/jspui/handle/11681/13145)
- Kansas DOT report KS-17-02 (2017): in a walled bridge flume (prototype n 0.0233, scaled from a measured 0.0141), HEC-RAS 2D and SRH-2D **over**-estimated headwater by up to 11.0 % and 13.1 % at the highest discharge. HEC-RAS 2D was "virtually" insensitive to n there, and SRH-2D at n = 0.0010 still exceeded the lab depth of 17.77 ft by 0.16 ft. Local bridge losses dominate this case, so it does not test wall shear. It shows that 2D error near structures can run opposite to the wall-shear bias. **[full, chapters 3, 4 and 6.5 extracted]** — [KS-17-02](https://rosap.ntl.bts.gov/view/dot/32362/dot_32362_DS1.pdf)
- Same report, a synthetic test. In a curved 68-ft-wide circular-bottom channel (n 0.045, 3001 cfs, S 0.002, Manning normal depth 16.27 ft), HEC-RAS 2D full momentum stayed "near 17 ft" for most of the reach (entering at 17.82 and 17.42 ft for 8-ft and 10-ft meshes). SRH-2D and the diffusion wave gave an M1 profile. This is not wall-isolating: the channel has bends and B/h ≈ 4. **[full]** — [KS-17-02](https://rosap.ntl.bts.gov/view/dot/32362/dot_32362_DS1.pdf)

### Inferences
- [Certain, arithmetic, assuming 1D Manning on R is the reference] For a rectangular channel at the same depth, a bed-only model (R = h) needs n_2D/n_1D = (1 + 2h/B)^(2/3) to match 1D Manning. At the same Q, its depth comes out at about (1 + 2h/B)^(-0.4) of the 1D depth. That gives the B/h where it matters:

  | B/h | n_2D/n_1D | depth ratio |
  |---|---|---|
  | 2.5 | 1.48 | 0.79 |
  | 5 | 1.25 | 0.87 |
  | 10 | 1.13 | 0.93 |
  | 20 | 1.07 | 0.96 |
  | 50 | 1.03 | 0.98 |

  So the bias exceeds 5 % in depth below B/h ≈ 15 and 10 % below B/h ≈ 6.
- [Certain, arithmetic] The synthetic gorge sits at B/h ≈ 2.2 to 2.7. Its bed-only depth of 4.40 m is 0.82 of the 1D 5.39 m. To reproduce 5.39 m, the bed-only face sum needs n ≈ 0.071 instead of 0.05 (+42 %); to reproduce HEC-RAS's coarse-cell 5.28 m it needs n ≈ 0.069. (My arithmetic on the exact section: plan-width conveyance 0.1 × h^(5/3) × (12 + 0.75 × wedge width) / n.)
- [Likely in form; the input value is uncertain] Take the measured wall share f_w from flume data, keep a local Manning law on the bed, and approximate the section as rectangular. Uniform flow then gives h ≈ h_bed-only × (1 − f_w)^-0.3:
  - With f_w ≈ 0.26 (the reconstructed Knight–Patel relation read as an open-channel law at b/h ≈ 2.5): h ≈ 4.8 m.
  - With f_w ≈ 0.45 (the same relation read as a duct law, or the plain perimeter share 2h/(B+2h) at this B/h): h ≈ 5.25 m.

  Either way, the measured shear data place the physical answer above the bed-only 4.40 m, between about 4.8 and 5.4 m. The bed-only value is the one result the flume shear measurements exclude, since walls measurably carry shear at B/h < 5.
- [Likely] Velocity-distribution and secondary-flow errors (STREMR) and local-loss errors (KS-17-02) are of the same order as the wall-shear effect, and they can have the opposite sign. A single stage comparison in a real gorge cannot attribute an error to wall shear without separating those effects.

### Gaps
- I could not read the Molls et al. (1998) full text, so the size of the backwater error without sidewall friction and the experiment's B/h are unknown. Lansford and Mitchell's original data (an Illinois Engineering Experiment Station bulletin, as cited) were not located.
- The exact Knight et al. (1984) %SFw equation for open channels and its roughness correction (C_sf for walls rougher or smoother than the bed) are unverified. This is the input that turns the 4.8 to 5.25 m bracket into one number. A record titled "Law of boundary shear in open rectangular channels with uniform roughness" exists ([zhenzhi](https://data.zhenzhi.com/details/1/863989627)) but was not read.
- No lab study found that runs a 2D depth-averaged model in a narrow trapezoidal or near-vertical-walled channel at B/h < 5 and reports stage error with and without a wall term. Shape-effect literature on Manning or Darcy resistance in narrow rectangular channels (resistance at the same R varying with B/h) was not retrieved in this pass.

## Q2. Field cases (canyons, gorges, bedrock or incised wadis, mountain rivers) in 2D against flood marks or gauges; whether calibrated 2D n comes out higher than 1D n, and by how much

### Takeaway
I found no field study in a gorge or bedrock canyon that compares 2D and 1D calibrated n for the same reach. The published 1D-against-2D n comparisons come from floodplain rivers, and they run the other way: 1D needs n 23 to 34 % higher than 2D, because 1D lumps losses that 2D resolves. Calibrated 2D cases in deep, bendy rivers (Brisbane River 2011, up to 30 m deep) match flood marks within ±0.2 m with standard n. In that case the sub-grid face wetted perimeter, not an n uplift, carries the walls and banks.

### Cited Findings
- Huxley, Syme, Ryan and Collecutt (2022, HWRS, BMT). Brisbane River 2011, a 10 km reach "up to 30 metres deep and 4 m/s with numerous 90-to-180-degree river bends", from a model calibrated to thousands of flood marks and a dozen gauges. Cell sizes 20, 30, 40, 50 and 60 m were each run with first-order, second-order and second-order SGS schemes, with ±0.2 m against surveyed 2011 peak marks counted as good calibration:
  - First-order: poor at every cell size.
  - Second-order: good at cells of 30 m or less.
  - Second-order SGS: good at cells of 50 m or less.

  Throsby Creek (1990 event, 70 surveyed marks, cells of 3, 6, 9 and 12 m) has gauges in concrete trapezoidal channels 20 m wide (Jellicoe) and about 12 m wide (Litchfield):
  - Traditional sampling: agreement at Jellicoe only below 6 m cells, and at Litchfield it "do[es] not match well … or converge".
  - SGS: good below 12 m cells at Jellicoe and below 9 m at Litchfield.

  The authors credit SGS with "an improved definition of the wetted perimeter and hydraulic radius at each cell face". They also say that first-order numerical diffusion "presents similar to a solution that exhibits hydraulic losses greater than reality". **[full]** — [Huxley et al. 2022](https://www.tuflow.com/media/7555/2022-hydraulic-modelling-2d-cell-size-result-convergence-huxley-et-al-hwrs.pdf)
- TUFLOW wiki, FMA Challenge 2. Verbatim: "Generally Manning's n values are very similar for 1D and 2D schemes". 1D needs user-specified losses or "artificially increasing Manning's n" at structures, sharp bends and embankment openings, so 1D may use higher n. Also verbatim, in the same paragraph: "Conversely, 2D schemes typically apply no side wall friction, so if there is significant wall friction a 2D scheme may require a slightly **lower** Manning's n than a 1D scheme" (wording checked twice). **[page]** The direction as published contradicts the physics: missing wall shear would need a higher 2D n. It reads like a slip in the wiki, and I would not quote it as evidence either way. — [TUFLOW wiki](https://wiki.tuflow.com/index.php?title=FMA_Challenge_2)
- Napa River, St Helena (CSU Sacramento thesis, HEC-RAS 5.0.3): the 1D model needed n 25 to 34 % higher than 2D for the same calibration, and its water surfaces were in places more than 2 ft lower than 2D. This is a floodplain reach, not a confined channel. **[snippet/abstract]** — [CSUS record](https://csu-csus.esploro.exlibrisgroup.com/esploro/outputs/graduate/A-comparison-of-1D-and-2D/99257831153901671)
- A Nile River calibration study (J. Hydrol.: Regional Studies, 2024) found the 1D optimum n about 23 % higher than TELEMAC-2D's, and quotes the 25 to 34 % above. **[snippet]** (the article returned 403). — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S221458182400257X)
- Krzyk, Klasinc and Četina (2012, Strojniški vestnik 58(4)) modelled a dam-break wave in a narrow, steep stream (Kolarjev vrh) in 2D depth-averaged PCFLOW2D-ORTHOCURVE against a 1:200 physical model. They replaced Manning with a Rickenmann-type law whose roughness varies with cell slope, because Manning "fails to give good results for streams with steep bed slopes". Maximum depths differed by up to 27 % at one gauge and about 7 % on average at four others. Wall friction is not discussed. **[abstract]** — [SV-JME](https://www.sv-jme.eu/?p=2983)
- Lumbroso and Gaume (2012, J. Hydrol.) found, with the HYDRATE project, that Manning formulae with tabulated n used without verification can over-estimate flash-flood peak discharges reconstructed from flood marks. In steep, confined channels the true resistance exceeds the tabulated n. **[abstract]** — [HR Wallingford eprint](https://eprints.hrwallingford.com/876/)
- Hocini, Gaume et al. (EGU 2020): on French flash floods, simulated water levels differed from high-water marks by less than 50 cm in most cases. **[abstract via snippet]** — [EGU2020-16441](https://meetingorganizer.copernicus.org/EGU2020/EGU2020-16441.html)
- Bohorquez and Darby (2008) reconstructed an outburst flood through a bedrock gorge in 2D. The retrodicted discharge depended on roughness and boundary-condition choices even with well-constrained field evidence. **[snippet]** — [EPFL PDF](https://infoscience.epfl.ch/record/130122/files/BOHORQUEZ_DARBY2008.pdf)
- HEC (Brunner, in a 1D-vs-2D presentation): "Steep streams that are highly gravity driven and have small overbank areas, such that the flow is confined to the channel" are listed as where "1D modeling can produce similar results to 2D modeling, with less effort". **[full, extracted locally]** — [HEC slides](https://www.hec.usace.army.mil/confluence/prospect/files/179605245/179605314/2/1714402023387/2.9+1D+vs+2D+Modeling.pdf)

### Inferences
- [Likely] The practitioner rule "2D n ≤ 1D n" comes from floodplain rivers, where 1D must absorb bend, expansion and exchange losses. It does not carry over to a narrow, straight, deep gorge, where the only loss the 2D model lacks is the walls. There the bias runs the other way: the bed-only 2D n must rise, by +42 % on the W48 gorge by the arithmetic in Q1.
- [Likely] The Brisbane and Throsby successes were achieved with face-wetted-perimeter sub-grid codes (TUFLOW HPC SGS). They do not show that a plan-width, bed-only face sum would match the same marks. Litchfield, a 12 m trapezoidal concrete channel matched at cells under 9 m, is the closest field analogue to the gorge's width, but its B/h is far larger than 2.5.
- [Guessing] Bedrock-gorge paleoflood practice relies on 1D step-backwater with Manning on R (USGS), so slack-water-calibrated n values in canyons already include the walls. A bed-only 2D model using those n would read stage low.

### Gaps
- No field case found: a gorge, canyon or incised wadi run in 2D and 1D against the same flood marks with calibrated n reported for both. Carling et al. (2010, Altai paleofloods, 1D and 2D) was cited in a secondary source but not read.
- I could not get the Brisbane per-cell-size water-level table values (they are in table graphics). I did not check whether the BRCFS calibrated n differs between grid sizes.
- The NASEM/NCHRP 2024 report "Selection and Application of Manning's Roughness Values in Two-Dimensional Hydraulic Models" (DOI 10.17226/27730), chapter 4, "Flow Resistance Factors, Required Conditions for Resolving a Feature, and Effect of Model Choice" (pp. 44-116), is the most likely source of tested 1D-against-2D n numbers. The OpenBook pages did not render its text. Only the front matter was read. — [NASEM](https://www.nationalacademies.org/read/27730)

## Q3. Benchmarks with confined channels (EA 2D benchmark, Malpasset, Toce, IAHR/ASCE, Brisbane 2011, Costabile on rain-on-grid): does any isolate the effect?

### Takeaway
None that I found isolates wall shear. The cell-size studies (Brisbane 2011, TUFLOW convergence tests, ARR guidance) measure total convergence against marks. Their recommended minimum cells across a channel (≥ 5 per ARR, 6 to 8 without SGS, 3 to 4 with SGS) are about conveyance resolution, not wall friction. The one steep-terrain benchmark-type advance (Costabile and Maranzoni 2026) addresses bed-slope steepness, not lateral walls.

### Cited Findings
- ARR (as quoted by TUFLOW): "at least 5 grid/mesh elements laterally across the channel" to resolve in-channel flow. In an EA Test 5 dam-break convergence test (single n 0.04), results converged for 10 to 100 m cells and not for 150 to 250 m. At 100 m the flow is "approximately (4) four cells laterally across the valley". No water-level differences are given in the text. **[page]** — [TUFLOW wiki, cell size](https://wiki.tuflow.com/TUFLOW_2D_Cell_Size_Selection)
- TUFLOW manual 2026.0 §3.2, Table 3.1, minimum cells across flow paths: 4 to 6 (Classic), 6 to 8 (HPC without SGS), 3 to 4 (HPC with SGS), the last assuming a DEM at least twice as fine as the grid. SGS "generates a non-linear relationship between water surface elevation and cell face area and width (i.e. wetted perimeter)". In the U-bend flume (De Vriend 1978), "with SGS off the upstream water level is over predicted"; with SGS on, the head drop round the bend "is correctly modelled". Smagorinsky viscosity "can allow the model results to diverge with decreasing cell size once the cell face width becomes less than the depth". **[page]** — [TUFLOW manual 2026.0](https://docs.tuflow.com/classic-hpc/manual/2026.0/ModelResolutionDiscretisation-2.html)
- TUFLOW webinar Q&A: ARR guidance means about 6 cells across a waterway without SGS. SGS preserves total conveyance with fewer cells, at some cost to the velocity distribution near the edges. **[snippet]** — [AWS Q&A](https://awschool.com.au/content/uploads/Webinar_QA-Flood-Modelling-101.TUFLOW-Replies.pdf)
- Collecutt and Syme (2017, HIWE) benchmarked mesh-size and time-step convergence of first- and second-order TUFLOW HPC against experimental data, in transient supercritical flow with moving shocks. **[abstract]**, numbers not seen. — [IAHR](https://iahr.org/library/info?pid=3066); [TUFLOW PDF](https://downloads.tuflow.com/_archive/Publications/07-31-1369.pdf)
- Costabile and Maranzoni (2026), Water Resources Research 62(5), DOI 10.1029/2025WR041653, extend the 2D steep-slope SWE to overland flow. Conventional small-angle SWE predict lower equilibrium depths and response times and higher velocities, with discrepancies "substantial for slopes steeper than 20°". They propose an analytically derived, slope-dependent and, in 2D, anisotropic correction to Manning's n, so that existing solvers can be kept. **[abstract]** — [UNICAL record](https://iris.unical.it/handle/20.500.11770/406897)

### Inferences
- [Likely] The ARR and TUFLOW cells-across rules are calibrated on codes that either carry face wetted perimeter (SGS, HEC-RAS) or resolve banks with many cells. With a bed-only plan-width face sum, more cells do not add the wall shear; Wadi2D's own runs show 4.38 to 4.41 m from 2 to 20 m cells. Refinement converges to the bed-only answer, not to the physical one, so "finer cells" is not a correction for this bias.
- [Guessing] Costabile and Maranzoni's correction is derived for bed slope along the flow. A 78° wall in a sub-grid pixel is a lateral slope whose wetted surface exceeds its plan area by about 1/cos 78° ≈ 4.8. An anisotropic, slope-dependent n is the published framework closest to a "slope-corrected bed shear" on wall pixels, but I have not seen it applied or validated for lateral walls.

### Gaps
- Not retrieved in this pass: the Néelz and Pender EA benchmark reports (2010, 2013), Malpasset, Toce, the IAHR/ASCE benchmarks, and Costabile et al.'s earlier rain-on-grid papers. From what is known of their set-ups, none has a narrow, deep confined channel with measured stage at B/h < 5, but I did not verify that.

## Q4. HEC guidance or papers on 1D against 2D HEC-RAS stage differences in confined reaches, with numbers

### Takeaway
HEC's general position is that 1D and 2D agree in steep, confined channels. In sub-grid 2D codes, each face's friction uses that face's own hydraulic radius, area over wetted perimeter from the face's terrain profile. That is why HEC-RAS 2D carries most of the wall effect at coarse cells and loses it as cells refine. A 1D worked example at B/h = 2.7 puts a number on the wall perimeter: dropping it lowers normal depth by 20 %, the same size as the W48 gap.

### Cited Findings
- HEC-RAS 2D faces act as "virtual cross sections": flow area, wetted perimeter, hydraulic radius and conveyance come from the sub-grid terrain on each face. Practitioner sources report face R = wetted area / face wetted perimeter, with the friction slope taken between the adjacent cell centres and a centre-to-centre length used for friction. **[snippets, secondary]**; the official technical reference page returned 404. — [CivilGEO](https://knowledge.civilgeo.com/hec-ras-2d-grid-subgrid-computations); [RAS Solution forum](https://therassolution.kleinschmidtgroup.com/the-ras-solution-forum/topic/shear-stress-in-2d-ras); [Kleinschmidt subgrid post](https://therassolution.kleinschmidtgroup.com/ras-post/hec-ras-subgrid-bathymetry-theory-and-application)
- Kleinschmidt, "Vertical Walls – What are the Implications?" (1D HEC-RAS): a flume with Q 12 m³/s, n 0.014, B 4 m and S 0.001 has normal depth **1.48 m** with the full wetted perimeter. The old 0.01 m-offset wall trick turns the walls into zero-conveyance overbanks, R = D, and gives **1.19 m**. "You'll get the wrong answer", because the side walls' perimeter, that is their roughness, is removed. **[full]** — [Kleinschmidt](https://therassolution.kleinschmidtgroup.com/ras-post/vertical-walls-what-are-the-implications/)
- HEC (Brunner): steep, gravity-driven streams confined to the channel are where "1D modeling can produce similar results to 2D". **[full]** — [HEC slides](https://www.hec.usace.army.mil/confluence/prospect/files/179605245/179605314/2/1714402023387/2.9+1D+vs+2D+Modeling.pdf)
- KS-17-02: HEC-RAS 2D full momentum ran 0.7 to 1.5 ft above the Manning normal depth of 16.27 ft in a curved channel (B/h ≈ 4). In a constricted near-vertical-walled test channel (walls 0 to 70 ft over 0.5 ft horizontal, 1-ft cells), upstream depth rose 85.3 % between the lowest and highest n in HEC-RAS 2D and 64.9 % in SRH-2D. **[full]** — [KS-17-02](https://rosap.ntl.bts.gov/view/dot/32362/dot_32362_DS1.pdf)

### Inferences
- [Certain, arithmetic] The Kleinschmidt example has B/h = 2.7 and a depth ratio of 0.80 without walls. The W48 gorge's bed-only 4.40 m against 5.39 m is 0.82. These are the same effect at the same aspect ratio, so the W48 face sum is numerically the HEC-RAS "no wall perimeter" error.
- [Likely; the coordinator's own emulation agrees] HEC-RAS 2D's 5.28 m at 20 m cells and 4.70 m at 5 m cells are not two measurements of wall shear. The wall perimeter is applied over the whole width of a face that spans bed and wall, and that weighting fades as faces resolve the section. HEC-RAS's fine-cell limit is the bed-only answer plus the walls' inclined length, not 1D Manning. Its cell-size spread is a numerical artefact that happens to straddle the physical range; it is not evidence for either end.
- [Likely] TUFLOW HPC SGS describes the same face wetted-perimeter construction, so the same cell-size dependence probably applies there. Huxley et al. report SGS's good convergence on channels with B/h well above 5, which says nothing about B/h ≈ 2.5.

### Gaps
- I found no HEC document that reports a 1D against 2D stage difference for a narrow, deep, straight confined reach. The HEC-RAS 2D technical reference text on the face friction term was not retrieved (404).

## Q5. Studies adding a wall-shear or slope-corrected bed-shear term to a 2D model and testing it against measurements

### Takeaway
Explicit wall terms exist, and in each case found they are justified by lab data or are switchable code features. None I found reports a stage improvement in a natural gorge or incised wadi:
- the modified friction slope of Molls et al. 1998
- the vertical-sidewall Manning variant of the 2023 contraction study
- TELEMAC-2D lateral-boundary roughness
- the LABSWE sidewall force term
- slope-dependent roughness (Krzyk 2012 for steep beds, Costabile and Maranzoni 2026 anisotropic n)

Where tested in wide geometries (TELEMAC on shallow lab reservoirs), sidewall friction made no difference. That is consistent with the effect vanishing at large B/h.

### Cited Findings
- Molls et al. (1998): a modified 2D friction slope that includes sidewall friction reproduces Lansford and Mitchell's rectangular-channel backwater data; the unmodified one does not. **[abstract]** — [ASCE](https://ascelibrary.org/doi/10.1061/%28ASCE%290733-9429%281998%29124%3A1%2881%29)
- Int. Rev. Model. Simul. (2023): a "Manning for vertical channel sidewalls" friction option in a 2D SWE model changed the mean downstream depth against experiment, but not the shock structure. **[abstract]** — [record](https://searchworks.jioinstitute.edu.in/articles/edb__170766414)
- TELEMAC-2D: in a study of shallow rectangular laboratory reservoirs, the effect of sidewall friction "was tested and no influence on the numerical results was noted". **[snippet]**: the document was not opened, and of the two core.ac.uk PDFs returned I could not tell which holds the passage. The Flanders Hydraulics Lower Sea Scheldt model varied the "roughness coefficient of boundaries" as a wall-friction sensitivity test. **[snippet]** — [core.ac.uk 482118713](https://core.ac.uk/download/482118713.pdf); [VLIZ / Flanders Hydraulics](https://www.vliz.be/imisdocs/publications/400508.pdf)
- Shafiai and Kamaruzaman (2013): a LABSWE sidewall force term, validated on velocity vectors in a cavity channel. **[abstract]** — [UiTM](https://journal.uitm.edu.my/index.php/SRJ/article/view/3316)
- Krzyk et al. (2012): a slope-varying Rickenmann-type roughness in 2D on a narrow, steep stream, against a 1:200 model, with depth error ≈ 7 % mean and 27 % at one gauge. **[abstract]** — [SV-JME](https://www.sv-jme.eu/?p=2983)
- Costabile and Maranzoni (2026): a slope-dependent, anisotropic Manning correction for steep-slope SWE, with discrepancies substantial above 20°. **[abstract]** — [UNICAL](https://iris.unical.it/handle/20.500.11770/406897)
- Fenton, "The long wave equations for arbitrary slopes", gives generalised Chézy–Weisbach and Gauckler–Manning formulae for finite slopes in steady uniform flow. **[snippet]** — [Fenton PDF](https://www.johndfenton.com/Papers/05-The-long-wave-equations-for-arbitrary-slopes.pdf)
- A granular-flow multilayer model (not water) adds a side-wall friction term. It notes that walls dominate "when the characteristic width of the channel is small in comparison with its characteristic height". **[snippet]** — [arXiv 1707.01256](https://arxiv.org/pdf/1707.01256)

### Inferences
- [Likely] The measured basis for a wall term in a depth-averaged model is the flume literature: Molls 1998 for stage, and Knight's shear distribution for the share. It is not field data. A wall term calibrated to put the walls' measured share of shear on them gives the gorge depth as roughly 4.8 to 5.25 m (Q1 inference, f_w 0.26 to 0.45). The 1D Manning answer, 5.39 m, is the upper end, where shear is spread uniformly over the perimeter.
- [Likely] Practitioner corrections, ranked by what the evidence supports for B/h < 5:
  1. An explicit wall or face wetted-perimeter term. It has lab support, and the sub-grid codes HEC-RAS 2D and TUFLOW SGS do this implicitly, though resolution-dependently.
  2. A higher n on the channel cells. It is a fix that works, on the order of +25 to +48 % at B/h 5 to 2.5, but no published calibrated numbers exist for gorges.
  3. Finer cells. This does nothing for a bed-only face sum and is not a correction.
- [Guessing] On the W48 race, a bed-only aligned mesh on 20 m cells reading high, while 20 m squares read low against converged squares, implies the race excess is not a wall-shear effect. Every bed-only Wadi2D mesh shares the same 4.40 m section answer. The wall-shear question bears on absolute stage in narrow gorges against HEC-RAS and 1D, not on the aligned-against-square difference.

### Gaps
- No study found that adds a wall-shear or wall-pixel slope-corrected bed shear to a sub-grid 2D model and tests it against measured stage in a natural confined channel.
- Delft3D's partial-slip wall option, and Iber's wall treatment, were not verified in this pass; Iber's Manning use was found for the bed only.
- Read in full in this pass: Huxley et al. 2022; the HEC 1D-vs-2D slides; KS-17-02 chapters 3, 4 and 6.5; Kleinschmidt "Vertical Walls"; TUFLOW wiki pages and manual §3.2 (via summary, two sentences verbatim). Everything else above is abstract, catalogue or snippet only, as tagged.
