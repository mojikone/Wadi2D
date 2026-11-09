# Acceptance tolerances for 2D flood models in guidance and benchmark programmes (vendor-independent)

Scope note for the report writer. The three kinds of tolerance are kept apart throughout: **(C) model against observed data** (calibration and verification), **(M) model against model** (benchmarks, comparisons between packages or meshes, model tie-ins, software-version changes) and **(I) internal checks** (mass balance, time step, iteration convergence, grid convergence). Each document's edition is given. "Second-hand" marks a figure taken from a document that cites another document, not from the original. Sources were read as full text (PDF extracted locally) unless marked "search snippet".

## 1. UK Environment Agency 2D benchmarking (Néelz and Pender, SC080035/SR2 2010; SC120002/R 2013): pass/fail tolerances or package-to-package comparison only?

### Takeaway
Neither report sets a pass/fail tolerance. Both compare packages with each other and, in a few tests, with an analytical or laboratory reference, and describe the spread in words. Their numbers describe how far apart packages landed: SWE packages within "a few per cent" on a simple propagation test, about 0.4 m (about 10 % of depth) on peak levels and about 20 % on travel times in valley/dam-break tests, and up to 100 % on velocity in shallow urban flow at 2 m cells. They set no grid-convergence criterion. They tolerated reported volume errors up to about 1.5 % as having no visible effect.

### Cited Findings
**Status and editions**
- SC120002/R (Néelz and Pender, August 2013) supersedes SC080035/SR2 (2010), which "has been withdrawn". The 2013 report has 19 packages: 15 new or refreshed results plus four carried over from 2010. — [EA 2013 summary SC120002/S](https://assets.publishing.service.gov.uk/media/6033a91ce90e076601e9f4e2/_SC120002_Benchmarking_2D_hydraulic_models_Summary.pdf); [EA 2013 report, Executive summary](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf)
- **Purpose: evidence and a data set, not an acceptance test.** The stated objectives are an evidence base that packages "are capable of adequately predicting the variables on which decisions are based" and "a data set against which such packages can be evaluated by their developers". The summary adds that the results "may also help other users ... make their own decisions about whether any software is fit for their purposes". — [EA 2013 report, Section 1](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf); [EA 2013 summary](https://assets.publishing.service.gov.uk/media/6033a91ce90e076601e9f4e2/_SC120002_Benchmarking_2D_hydraulic_models_Summary.pdf)
- **Benchmarking approaches.** Section 2 lists the possible approaches as comparison "with analytical solutions, field data, physical model data and other model predictions". Most tests are model against model. Test 6A was the only test against real measured data, from a laboratory dam-break at UCL Belgium; the report recommended removing it because the measurement points did not separate the packages. For Test 3 the report states that "no exact solution exists". It expects any full-SWE model to show a level rise at point 2, a qualitative test. — [EA 2013 report, Sections 2, 4.4.1 (p. 36), 5.1.6 (p. 118)](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf)
- **The 2013 tests (Table 2.1):**
  - 1: disconnected water body
  - 2: filling of floodplain depressions
  - 3: momentum over a 0.25 m obstruction
  - 4: speed of flood propagation
  - 5: valley flooding
  - 6A/6B: dam break
  - 7: 1D–2D river–floodplain linking
  - 8A/8B: urban rainfall and sewer surcharge at 2 m

  Recommendations: remove Tests 1 and 6A; keep Test 7 and reject results that do not follow the instructions; replace 8A/8B with a single Test 8. — [EA 2013 report, Table 2.1; Section 5](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf)
- **Conclusions are qualitative.** SWE packages are "appropriate to support decision making across the full range" of EA activities, with two exceptions:
  - very large areas (>1000 km2) or many-run probabilistic work, because of run time;
  - supercritical-to-subcritical transitions near a breach, where shock-capturing schemes perform better.
  
  — [EA 2013 report, Executive summary](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf)

**Agreement figures (M, model against model, descriptive)**
- **2013, Test 4 (flood propagation).** Full SWE models predicted depths and velocities "within a few per cent of each other during the entire duration of the event". Arrival times were within about 5 min of each other at the furthest points, against a travel time of about 1 h. — [EA 2013 report, Section 4.5.2, p. 48](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf)
- **2013, Test 5 (valley flood from a dam failure).**
  - Arrival times were consistent within a maximum range of about 30 min at the valley bottom, against a travel time of almost 3 h.
  - Peak levels were consistent within about 0.4 m at most points, which "at most represented ~10% of the predicted peak depth in the deeper areas". Spreads were larger at the shallow valley edges.
  
  — [EA 2013 report, Section 4.6.2, p. 63](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf)
- **2013, Test 7 (1D–2D linking).** A final elevation of about 11.5 m was "predicted by all models within ~0.05m". However, the different 1D–2D linking methods gave "significantly different predictions of the volume of water exchanged". — [EA 2013 report, Section 4.8.5, p. 96; Executive summary](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf)
- **2013, Test 8A (urban, 2 m cells).**
  - At point 1, with depths over 0.5 m, all SWE models agreed within about 5 % of depth.
  - At points 2, 4 and 7, with depths of about 0.35 m or less, the full models agreed on peak levels within about 0.04 m.
  - Velocity differences reached 100 %, "This suggests that a 2m grid may be too coarse". Yet the report adds: "it is not currently clear that grid resolutions finer that 2m will improve the quality of velocity predictions". Its reasons are that DTM and boundary uncertainty act "to at least the same order as the grid resolution", and that run-time cost limits multi-run uncertainty work.
  
  — [EA 2013 report, Sections 4.9.2 (p. 105), 4.9.5 (p. 108); Executive summary](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf)
- **2010, Test 5.** Full models were similar on travel times "(within ~20%)" and peak water levels "(within 0.4m)". The report judged these differences "unlikely to be larger than the required accuracy" for that problem type and scale. — [EA 2010 report SC080035/SR2 (withdrawn), Section 4.5.4, p. 50](https://assets.publishing.service.gov.uk/media/5a75765c40f0b6360e4744dd/scho0510bsno-e-e.pdf)
- **2010, Test 6B (field-scale dam break).**
  - Peak depths downstream of the gate were within 15–20 % of each other, a 30–40 cm wide range.
  - Peak velocities agreed within about 10 %.
  - Three packages "consistently predicted levels ~10% higher" than four others at four gauges, which the report calls "unexplained".
  
  — [EA 2010 report, Section 4.6.2.2, p. 60](https://assets.publishing.service.gov.uk/media/5a75765c40f0b6360e4744dd/scho0510bsno-e-e.pdf)
- **2010, Test 2.** Final-level differences between full models were "within the level of acceptable accuracy for practical application". Simplified models differed by more than about 0.05 m at several locations and "may also be considered acceptable depending on the level of accuracy required". No number is given for "acceptable". — [EA 2010 report, Section 4.2.3, p. 24](https://assets.publishing.service.gov.uk/media/5a75765c40f0b6360e4744dd/scho0510bsno-e-e.pdf)
- **2010, Test 8A.** Ground elevations differed between packages by "typically within a 0.05-0.1m range, although up to ~0.2m" because each package coarsens a 0.5 m DEM to the 2 m grid differently. The report calls the choice of grid resolution "(finer than 2m in a case similar to the present one) ... crucial". — [EA 2010 report, Section 4.7.x, pp. 81–82](https://assets.publishing.service.gov.uk/media/5a75765c40f0b6360e4744dd/scho0510bsno-e-e.pdf)

**Volume conservation (I)**
- **2013:** "The largest volume change reported is a 1.46% volume loss" in one package, which "did not have any identifiable consequence in the results". The effect of model choice "was clearly more significant". — [EA 2013 report, Section 4.3.3, p. 33](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf)
- **2010:** the same wording for a 1.4 % loss by one package. — [EA 2010 report, Test 2, p. 23](https://assets.publishing.service.gov.uk/media/5a75765c40f0b6360e4744dd/scho0510bsno-e-e.pdf)
- **Vendor self-reports in Appendix B of the 2013 report** (vendor statements, not EA criteria):
  - one package needed double precision in 2010 "to keep mass error below 1%";
  - another reports a final mass balance error "never greater than 0.03%";
  - a third accepted a 1.3 % mass error with default iterations.
  
  — [EA 2013 report, Section 4 tables and Appendix B](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf)

### Inferences
- [Likely] There is no EA benchmark pass mark to borrow. The defensible reading of "agreement" in the EA programme is a level spread of a few centimetres in shallow flow, about 0.4 m or about 10 % of depth in deep transient flow, and travel-time spreads of 10–20 % among mature SWE codes. A 3 % peak-flow difference between two meshes of the same code is tighter than any spread the EA reported as normal between packages.
- [Likely] The EA's own 2 m result applies here. Differences in how terrain is sampled to the grid produced 0.05–0.2 m ground differences and up to 100 % velocity differences. This is the class of effect Wadi2D's square-against-aligned race measures: the same equations, different terrain sampling.

### Gaps
- The 2013 Appendix A test specifications were not read line by line for numbers. It is unverified whether any test states an expected answer with a tolerance; the body text read did not.
- The 2009 desktop review (SC080035/SR) was not read for recommended evaluation metrics.
- Whether an EA benchmark round after 2013 exists was not found. The 2013 report recommended a further round.

## 2. Australian Rainfall and Runoff (ARR 2019, Books 6 and 7) and ARR Project 15 (Babister and Barton, 2012 draft)

### Takeaway
ARR 2019 explicitly declines to set calibration acceptance criteria and recommends that specifications "should not be prescriptive". It gives two numbers:
- mass balance errors "greater than 1% to 2%" should be investigated;
- 6 to 8 cells are needed to resolve flow separation round a structure.

The 2012 Project 15 draft gives the denser rules of thumb:
- at least 5 cells across a channel;
- direct-rainfall volume error of 0–5 % of outlet volume "considered acceptable";
- mass balance over 1–2 % investigated;
- sensitivity to ±20 % roughness and +20 % inflow;
- a finer-resolution check that results "do not demonstrably change";
- a time-step-halving check.

Its calibration examples are 0.2 m and 300 mm. Neither document has numeric benchmark tolerances.

### Cited Findings
**ARR 2019** (Ball et al. eds, © Commonwealth of Australia (Geoscience Australia) 2019, CC-BY 4.0; the file read is dated 14 May 2019)
- **Book 7, Ch. 5, Section 5.6 "Acceptance of Calibration"** (pp. 36–39):
  - "it is difficult to define an acceptance criterion for model calibration";
  - "Unrealistic calibration criteria do not lead to an improvement in model design applications";
  - "It is recommended that specifications for flood studies should not be prescriptive in defining calibration criteria, but should aim for realistic and applicable criteria."
  
  It warns of "overfitting" when unrealistic acceptance criteria force extreme parameter sets. — [ARR 2019 full PDF](https://arr-software.org/pdfs/ARR_190514.pdf)
- **Book 7, Section 5.6 worked example.** A council set peak levels "within 300mm of recorded" at more than 400 debris marks. Calibration "was accepted with 50% of points meeting this criterion" because the debris-mark levels were uncertain. — [ARR 2019](https://arr-software.org/pdfs/ARR_190514.pdf)
- **Book 7, Section 5.6.1 "Matching Timing and Magnitude".** Calibration should show the model reproduces timing and hydrograph shape, not peak marks alone. Flows at gauges are "not 'recorded' but 'derived'" from rating curves. No numeric timing or flow tolerance is given. — [ARR 2019](https://arr-software.org/pdfs/ARR_190514.pdf)
- **Book 7, Ch. 10, Section 10.4 "Interpretation of Modelling Results"** (results checklist): "Mass Balance – errors greater than 1% to 2% should generally be investigated, and the cause of the errors identified and rectified where possible". It also lists continuity checks of hydrographs along flow paths and stability checks for oscillations and excessive time-step reductions. — [ARR 2019](https://arr-software.org/pdfs/ARR_190514.pdf)
- **Book 6, Ch. 4 "Numerical Models", Section 4.7 (2D unsteady models), p. 170:**
  - a structured grid "should, where possible, be aligned with the main flow direction";
  - flexible meshes can be aligned to flow paths;
  - "the smallest feature that can be resolved will be one grid or mesh cell wide";
  - flow separation and eddies behind abutments need "a minimum of 6 to 8 grid or mesh cells";
  - run time scales roughly with the cube of the cell size, so halving the cell costs about 8 times.
  
  — [ARR 2019](https://arr-software.org/pdfs/ARR_190514.pdf)
- **Book 6, Ch. 4, p. 163 (ADI schemes):** the Courant number should be "less than the minimum number of grid cells used to describe the width of a channel", in practice of order 1 in narrow channels. — [ARR 2019](https://arr-software.org/pdfs/ARR_190514.pdf)
- **Book 7, Section 4.11 "Model Resolution".** Resolution sometimes has to be compromised; the example is a 30 m levee with 20 m or 40 m cells, decided by "Engineering judgement". There is no convergence criterion. — [ARR 2019](https://arr-software.org/pdfs/ARR_190514.pdf)

**ARR Project 15, Stage 1 & 2 Report P15/S1/009, draft of 18 November 2012** (Babister, ed.; released for industry comment)
- **Section 6.2.1.1 "Rectilinear Grids"** (p. 6-88/89): "Generally a minimum of five (5) grid cells across the width of a channel is required to produce an adequate representation of channel flow". A meandering channel through a fixed grid may need more cells than one aligned with the grid. — [ARR P15 draft 2012](https://arr.ga.gov.au/__data/assets/pdf_file/0019/40573/ARR_Project15_TwoDimensional_Modelling_DraftReport.pdf)
- **Section 7.3.1 "Defining an Acceptable Calibration"** (p. 7-105/106). Criteria should be agreed with stakeholders before calibrating. The example is "modelled peak water levels are to be within 0.2m of the peak flood marks", with timing "consistent" with observations. The same 300 mm / 50 % council example as ARR 2019 appears here. — [ARR P15 draft 2012](https://arr.ga.gov.au/__data/assets/pdf_file/0019/40573/ARR_Project15_TwoDimensional_Modelling_DraftReport.pdf)
- **Section 7.4 "Sensitivity Testing"** suggests:
  - roughness up and down by 20 %;
  - inflows +20 %;
  - downstream boundary, blockage and weir-coefficient variations;
  - "Making the model's resolution finer to check that results do not demonstrably change" (no numeric threshold);
  - varying the time step.
  
  — [ARR P15 draft 2012](https://arr.ga.gov.au/__data/assets/pdf_file/0019/40573/ARR_Project15_TwoDimensional_Modelling_DraftReport.pdf)
- **Section 8.3 "Checking of Results"** (p. 8-125/126): "Mass balance – errors greater than 1% to 2% should generally be investigated". This is the same wording later carried into ARR 2019 Book 7 Section 10.4. — [ARR P15 draft 2012](https://arr.ga.gov.au/__data/assets/pdf_file/0019/40573/ARR_Project15_TwoDimensional_Modelling_DraftReport.pdf)
- **Section 10.5.3 "Timestep"** (p. 10-159/160), rules of thumb: an initial time step of half the grid size in seconds per metre, and "Halve the present timestep and check if there are any differences in the results"; if there are no significant changes, the larger step is appropriate. — [ARR P15 draft 2012](https://arr.ga.gov.au/__data/assets/pdf_file/0019/40573/ARR_Project15_TwoDimensional_Modelling_DraftReport.pdf)
- **Section 11.4.3 "Volume Checks"** (direct rainfall, p. 11-196): "Generally, errors within the range 0% to 5% of Vo would be considered acceptable". Vo is the volume at the outlet, with the error term from a full volume balance. Acceptability "is dependent upon several factors including modelling application and standard of results required". — [ARR P15 draft 2012](https://arr.ga.gov.au/__data/assets/pdf_file/0019/40573/ARR_Project15_TwoDimensional_Modelling_DraftReport.pdf)
- **Section 5.1 (p. 5-53) and Section 5.3.1.5 (p. 5-67) on data accuracy:** if the aim is modelled levels with "a vertical accuracy of +/-0.2m", input data must be at least that accurate. Photogrammetry accuracy for flood studies ranges "+/- 0.1 m to +/- 0.3 m". — [ARR P15 draft 2012](https://arr.ga.gov.au/__data/assets/pdf_file/0019/40573/ARR_Project15_TwoDimensional_Modelling_DraftReport.pdf)
- **Benchmarking (M).** P15 has no benchmark-test chapter. Section 12 defers "test catchments" that "will allow the benchmarking between models" to a later phase of the ARR revision. — [ARR P15 draft 2012, Section 12, p. 12-204](https://arr.ga.gov.au/__data/assets/pdf_file/0019/40573/ARR_Project15_TwoDimensional_Modelling_DraftReport.pdf)
- **Second-hand, via the EA "pathway" standard:** ARR P15 found that "model resolutions of up to 10m were adequate for representing peak flood levels", while "resolutions of 2m or less were needed to represent complex flow paths around buildings". — [EA, Represent river channels, floodplains and pipe networks (pathway)](https://www.gov.uk/government/publications/river-modelling-technical-standards-and-assessment/represent-river-channels-floodplains-and-pipe-networks-pathway)
- A UNSW WRL laboratory urban-floodplain benchmarking dataset (Smith, Rahman, Wasko; Issue 3, 2 July 2016) is associated with the P15 programme. — [BL catalogue record](https://eld.bl.uk/catalog/100035128028_0x000001) (search snippet; contents not read)

### Inferences
- [Likely] The Australian position is the clearest statement of the profession's stance: calibration criteria are project-specific and non-prescriptive. The 0.2 m and 0.3 m figures are examples, not standards.
- [Likely] The only numeric internal checks are 1–2 % mass balance as an investigation trigger and 0–5 % of outlet volume for direct-rainfall models. A volume-error criterion therefore has better standing than any peak-flow criterion between meshes.
- [Likely] The cells-across rules apply directly to the W48 finding that the bank rule leaves exactly two aligned cells across the wadi at every cell size:
  - P15: at least 5 cells across a channel;
  - SEPA: 3–4 cells per major flow path (Section 3);
  - ARR 2019: 6–8 cells to resolve flow separation.
  
  By every one of these rules of thumb, two cells across a bending gorge is below what guidance calls adequate representation of channel flow.

### Gaps
- Whether a final version of P15 superseding the 2012 draft was published (the task brief cites "2012/2016") was not established. The 2016 item found is the WRL dataset, not a final guideline.
- ARR 2019 later revisions (v4.2, 2024 [Likely]) were not checked for changed wording. The text read is the 14 May 2019 file.
- The tolerances of the 2016 WRL laboratory benchmark dataset were not read.

## 3. UK guidance: EA modelling standards, SEPA, CIWEM (calibration tolerances, mass balance)

### Takeaway
Current EA best practice (England) gives one calibration number: recorded peaks matched "typically to within ±0.15 metres", over at least 3 events. It gives no flow, timing or mass balance number, and a Courant number below 1 for explicit models. SEPA's guidance for responsible authorities gives "usually within ±1% cumulative" mass balance and 3–4 cells per major flow path. It leaves calibration tolerances as blanks ("+/- X mm", "within X hours") to be set in each brief. The CIWEM UDG 2017 code is the one UK document with full numeric verification targets, written for sewer and coupled 1D–2D models against observed data:
- depth ±0.1 m or ±10 %;
- surcharged depth +0.5/−0.1 m;
- peak flow +25 %/−15 %;
- volume +20 %/−10 %;
- timing ±0.5 h;
- Nash–Sutcliffe >0.5.

### Cited Findings
**Environment Agency, "River modelling: technical standards and assessment"** (collection first published 13 August 2021, last updated 2 November 2026; the Fluvial Modelling Standards are being revised, completion expected by end of 2027) — [EA collection page](https://www.gov.uk/government/publications/river-modelling-technical-standards-and-assessment)
- **"Hydraulic modelling: best practice (model approach)"**:
  - **Calibration (C):** recorded peaks should match "typically to within ±0.15 metres"; "You should use at least 3 flood events during calibration where possible"; flows and timing need "a good representation of hydrograph timing and shape" with no numeric tolerance.
  - **Validation (C):** where calibration data are lacking, compare gauge median annual flood levels against modelled 50 % AEP events, with no tolerance.
  - **Mass balance (I):** mass balance errors that indicate volume is being artificially gained or lost should be checked, with no numeric limit.
  - **Time step (I):** for explicit models the Courant number should be below 1. For TUFLOW Classic (implicit) the 2D time step "should be between a half and a fifth of the grid resolution".
  - **Sensitivity:** "Testing usually sees a 20% change adjustment to inflows, hydraulic roughness" and to boundary and structure coefficients.
  - **Convergence (I):** default solver tolerances should not be increased because this can mask instability, with no number.
  
  — [EA, Hydraulic modelling: best practice (model approach)](https://gov.uk/government/publications/river-modelling-technical-standards-and-assessment/hydraulic-modelling-best-practice-model-approach)
- **"Represent river channels, floodplains and pipe networks (pathway)"**:
  - cites SEPA (2016): "a major flow path can only be well represented with at least 3 or 4 grid cells";
  - gives an estuarine resolution table: for levels and inundation timing, 2 m very good, 10 m good, 25 m satisfactory, >25 m poor; for velocity, 1 m, 2 m, 5 m and >5 m;
  - cites FRMRC (2008) tests at 2, 10 and 50 m, where "predicted peak levels were comparable across each tested resolution", with the caveat that "the results of the study cannot be generalised";
  - 2D roughness "should generally increase with model grid size";
  - gives no grid-convergence criterion and no mass balance limit.
  
  — [EA pathway standard](https://www.gov.uk/government/publications/river-modelling-technical-standards-and-assessment/represent-river-channels-floodplains-and-pipe-networks-pathway)

**SEPA, "Flood Modelling Guidance for Responsible Authorities", Version 1.1** (undated in the extracted text; cites SEPA 2015 and Néelz and Pender 2013, so 2016 or later [Likely])
- **Section 7.3 (2D models), grid:** "A rule of thumb is that 3-4 grid cells are required to resolve major flow paths". For example, a 5 m wide channel needs about 1.5 m cells, while for a 30 m river "a 10 m resolution may be adequate". — [SEPA FMG v1.1](https://www.sepa.org.uk/media/219653/flood_model_guidance_v2.pdf)
- **Section 7.3, mass balance (I):** "The mass balance files should be checked to ensure the mass balance is within acceptable limits, usually within ±1% cumulative error". — [SEPA FMG v1.1, p. 76–77](https://www.sepa.org.uk/media/219653/flood_model_guidance_v2.pdf)
- **Section 7.4, 1D–2D (I):** check the mass balance for the 1D component, the 2D component and the combined model, "usually within 1% cumulative error". Models "should not be accepted without evidence of mass balance checks"; the mass balance should be reported. — [SEPA FMG v1.1, p. 78](https://www.sepa.org.uk/media/219653/flood_model_guidance_v2.pdf)
- **Section 8.2, calibration (C):**
  - "A minimum of 3 calibration events and one validation event is recommended";
  - target criteria are to be defined in the Scope of Requirements (SoR);
  - criteria should cover peak level, hydrograph shape and timing of peak;
  - the template leaves the numbers open: tolerances "of both peak water level (e.g. +/- X mm) ... and in the timing of peak level (e.g. within X hours or less)".
  
  A case study reports "discrepancies of less than 0.2 m ... for the majority of locations". — [SEPA FMG v1.1, pp. 81–85](https://www.sepa.org.uk/media/219653/flood_model_guidance_v2.pdf)

**CIWEM Urban Drainage Group, "Code of Practice for the Hydraulic Modelling of Urban Drainage Systems", 2017, Version 01** (successor to the WaPUG code)
- **Section 5, Table 5-1 "Storm Verification Targets" (C).** Targets are to be met for at least two of three storm events.

  | Parameter | General | Critical locations |
  |---|---|---|
  | Shape | "Good match (NSEC if used >0.5)" | Same |
  | Time of peaks and troughs | ±0.5 hour | ±0.5 hour |
  | Peak depth, unsurcharged | ±0.1 m or ±10 %, whichever is greater | ±0.1 m |
  | Peak depth, surcharged | +0.5 m to −0.1 m | ±0.1 m |
  | Peak flow | +25 % to −15 % | ±10 % [the PDF layout makes the column assignment Likely, not Certain] |
  | Flow volume | +20 % to −10 % | ±10 % [same caveat] |

  The table states: "Where coupled 1D-2D models are used the 'critical locations' criteria should apply". — [CIWEM UDG CoP 2017, Table 5-1, pp. 73–74](https://www.ciwem.org/assets/pdf/Special%20Interest%20Groups/Urban%20Drainage%20Group/Code%20of%20Practice%20for%20the%20Hydraulic%20Modelling%20of%20Ur.pdf)
- **Appendix G:** the NSEC (Nash–Sutcliffe efficiency coefficient) is applied to depth and flow separately. Second-hand: "Research by Moriasi et al. (2007) states that a NSEC score of 0.5 is a 'satisfactory' replication". NSEC criteria "should be set by Commissioning Bodies". For depth, NSEC applies only where depth exceeds 10 % of pipe height or 100 mm. — [CIWEM UDG CoP 2017, Appendix G, p. 132](https://www.ciwem.org/assets/pdf/Special%20Interest%20Groups/Urban%20Drainage%20Group/Code%20of%20Practice%20for%20the%20Hydraulic%20Modelling%20of%20Ur.pdf)
- **Status:** the code "is issued for guidance in good faith"; CIWEM "cannot accept responsibility for consequences arising from its application". — [CIWEM UDG CoP 2017, front matter](https://www.ciwem.org/assets/pdf/Special%20Interest%20Groups/Urban%20Drainage%20Group/Code%20of%20Practice%20for%20the%20Hydraulic%20Modelling%20of%20Ur.pdf)

### Inferences
- [Likely] Across UK documents, the numeric consensus for internal volume error is about ±1 % cumulative (SEPA). The EA programme read 1.4–1.5 % volume loss as inconsequential.
- [Likely] The only UK peak-flow tolerance is CIWEM's +25 %/−15 % (±10 % at critical locations) against observed sewer-survey flows. It is a calibration tolerance against data and is not transferable to a mesh-against-mesh comparison.
- [Likely] ±0.15 m (EA) and 0.5 ft = 0.152 m (FEMA, Section 4) are the same number on both sides of the Atlantic for peak levels against observed marks.

### Gaps
- SEPA "Technical Flood Risk Guidance for Stakeholders" (latest about 2022) could not be downloaded: the server refused the request. Its hydraulic modelling section was not checked for numbers.
- EA "Using modelling for flood risk assessments" (December 2023, linked from the best-practice page) was not read directly.
- EA LIT56326, a PDF version of the standards available by email, was not seen.
- The CIRIA documents named in the brief were not found with numeric 2D criteria. No CIRIA source was read.

## 4. US: FEMA flood risk analysis guidance, FEMA model acceptance, USACE

### Takeaway
FEMA's numbers are all in water-surface elevation:
- calibration "should match known high-water marks ... within 0.5 feet" (C);
- different models along a stream "must tie-in within 0.5-feet" (M); 44 CFR 65.6(a)(2) requires revised and unrevised base flood elevations to match "within one-half foot" at transitions;
- a modified 2D model must report results out to where elevations tie in within 0.5 ft.

FEMA sets no mass balance, cell-size or convergence number. Model acceptance under 44 CFR 65.6(a)(6) requires review, documentation and availability. The testing needed is "adequately reproduce the measured data or provide results comparable to other models", with no numeric threshold. USACE EM 1110-2-1416 (1993) says rigorous calibration-error guidance "cannot be given" and mentions a ±1 ft rule of thumb.

### Cited Findings
- **FEMA Guidance Document 52, "General Hydraulics Considerations", November 2022 (C):**
  - Section 4.5: "Models should match known high-water marks reflective of the studied recurrence interval within 0.5 feet";
  - calibrate "where practicable" using high-water marks, measured profiles or gauge stages;
  - Section 4: "As with all models, calibration is highly recommended for two-dimensional models".
  
  — [FEMA GD 52 (Nov 2022)](https://www.fema.gov/sites/default/files/documents/fema_general-hydraulics-guidance_112022.pdf)
- **FEMA GD 52, Section 3.4 (M).** "Along a stream, various hydraulic modeling methods and/or models may be used ... The water surface elevations for all recurrence intervals from the different models must tie-in within 0.5-feet". All models "must adhere to 44 CFR 65.6 a (6)". The floodway surcharge limit is "typically between zero and 1.0 ft". — [FEMA GD 52](https://www.fema.gov/sites/default/files/documents/fema_general-hydraulics-guidance_112022.pdf)
- **FEMA Guidance Document 81, "Hydraulics: Two-Dimensional Analysis", November 2023:**
  - Section 2.1 (M): when an effective model is rerun in a new version or type of software, variations due to model code should be tested and documented. Significant BFE (base flood elevation) or SFHA (special flood hazard area) changes are discussed with the regional project officer. **No numeric threshold is given.**
  - Section 2.2: when a 2D model is modified, results must be provided "for the extent where resulting grid and/or cross section elevations tie in within 0.5 foot".
  - Section 3: model settings and tolerances should be documented "to ensure that rerunning the model will reproduce previous results".
  - Section 3.1, cell size: qualitative only. Avoid cells too large ("flat water-surface elevations over a large area") or too small. Refine so linear features "are not lost", and maintain "gradual changes in elevation from one cell to adjacent cells to avoid numerical instability".
  - Section 4: calibration refers back to GD 52, Section 4.5.
  - No mass balance or convergence criterion appears.
  
  — [FEMA GD 81 (Nov 2023), mirrored by Kentucky Transportation Cabinet](https://transportation.ky.gov/Highway-Design/Drainage%20Manual/FEMA%20-%20Hydraulics%20Two-Dimensional%20Analyses%20Guidance%20-%20Nov%202023.pdf)
- **44 CFR 65.6(a)(6), model acceptance.** A program must be:
  - (i) "reviewed and accepted by a governmental agency responsible for the implementation of programs for flood control and/or the regulation of flood plain lands"; for non-Federal agencies, certification that it "has been reviewed, tested, and accepted";
  - (ii) "well-documented including source codes and user's manuals";
  - (iii) available to FEMA and all affected parties.
  
  65.6(a)(2): revised and unrevised base flood elevations "must match within one-half foot where such transitions occur". — [44 CFR 65.6 (Cornell LII)](https://www.law.cornell.edu/cfr/text/44/65.6)
- **FEMA Guidance Document 98, "Accepting Numerical Models for Use in the NFIP", February 2018** (marked "Superseded. For Reference Only"):
  - "FEMA does not provide technical review or testing of models".
  - The certifying agency must review the model as "scientifically correct and technically sound". It must "test the model with measured data or compare the model to other similar models on FEMA's list ... to determine whether the model can adequately reproduce the measured data or provide results comparable to other models accepted by FEMA". **No numeric comparability threshold is given.**
  - Section 5: a revised model must match the effective profile "within 0.5 foot" at the ends of the revised reach.
  
  — [FEMA GD 98 (2018, superseded)](https://www.fema.gov/sites/default/files/documents/fema_accepting-numerical-models-guidance_022018.pdf)
- FEMA's current numerical-models page says listed models "have met the requirements of Subparagraph 65.6(a)(6)". The policy itself now sits in the FEMA Policy for Flood Risk Analysis and Mapping. — [FEMA numerical models page](https://www.fema.gov/flood-maps/products-tools/numerical-models)
- **USACE EM 1110-2-1416, "River Hydraulics", 15 October 1993 (C):**
  - Ch. 3, pp. 3-11/12: "Rigorous guidance on acceptable calibration errors cannot be given. The judgment and experience of the responsible hydraulic engineer and reviewers is foremost. Rules of thumb of ± 1 foot are often used, but this criterion may not be acceptable for all situations, particularly for steep streams". Manning's n estimates by experienced engineers "commonly differing by ±20 percent", which justifies adjustments of that size.
  - A case study notes "calibration tolerance should be relaxed from 0.5 foot to 1 foot" because of superelevation.
  - Section 7-8: for mobile-bed studies, "± 0.5 foot is usually satisfactory".
  - Ch. 6, standard-step iteration convergence (I): "agree to within .01 feet".
  
  — [EM 1110-2-1416 (third-party mirror; verify against the official USACE copy)](https://chet-aero.com/wp-content/uploads/2016/11/em-1110-2-1416.pdf)

### Inferences
- [Likely] FEMA's 0.5 ft tie-in is the only regulatory model-against-model tolerance found. It is on water level at a junction between two models, not on discharge. The same 0.5 ft is used for calibration against high-water marks.
- [Likely] Under FEMA, a new solver or mesh type is accepted by an agency's judgement that it "adequately" reproduces data or is "comparable" to listed models, not by a percentage.

### Gaps
- The current FEMA "Policy for Flood Risk Analysis and Mapping" text on numerical model acceptance was not read. The 2018 guidance is superseded, so newer wording may differ.
- The USGS FDST 2D guidance for FEMA Base Level Engineering (April 2022) was found but not read. It is HEC-RAS-specific per its own description. — [USGS FDST 2D guidance](https://webapps.usgs.gov/infrm/pubs/FDST_2D_Guidance_vApr2022.pdf) (search snippet)
- No USACE engineering manual with 2D-specific numeric criteria was found. The HEC-RAS 2D user's manual is the developer's own document, so it was excluded as vendor guidance.

## 5. Other national or state guidance with numbers (New Zealand, Queensland, NSW, Netherlands)

### Takeaway
No primary New Zealand, Queensland, NSW or Dutch document with numeric 2D acceptance criteria could be read in this pass. Search results show council practice using about 0.3 m on peak levels and ±25 % on rainfall-runoff accuracy, but not the governing specifications.

### Cited Findings
- Queensland (Cardwell inundation study, 2008, a council report) reports calibration of peak levels "within 0.3m" at several points. This shows 0.3 m in local practice, not a state standard. — [Cassowary Coast, Cardwell inundation study 2008 part 2](https://cassowarycoast.qld.gov.au/downloads/file/1747/cardwell-inundation-study-2008-final-part-2) (search snippet)
- The QRA template project brief for flood studies (July 2023) requires hydrologic and hydraulic models "calibrated and verified, where possible, against historic flood events". No numeric tolerance was visible in the excerpt. — [QRA template project brief](https://www.qra.qld.gov.au/sites/default/files/2023-07/template_project_brief_for_flood_study.docx) (search snippet; the file download was blocked)
- Moreton Bay Regional Council flood studies report mass balance errors of −1.78 % to +0.78 % for selected runs. These are values achieved, not a criterion. — [Moreton Bay Sideling Creek appendices](https://www.moretonbay.qld.gov.au/files/assets/public/services/publications/flood-reports/regional-floodplain-database-catchment-sideling-creek-appendix-d-to-f.pdf) (search snippet)
- Auckland: a Pakuranga Creek report states that the TP108 rainfall-runoff model "is expected to be within ± 25% at a confidence level of 90 percent". A Meola Creek report refers to "Auckland Council model specification criteria" for peak flow and runoff volume without the numbers in the snippet. — [Knowledge Auckland TP108 page](https://knowledgeauckland.org.nz/publications/guidelines-for-stormwater-runoff-modelling-in-the-auckland-region/) (search snippet)

### Inferences
- [Guessing] Australian state and council briefs most likely carry project-specific calibration targets in the 0.2–0.3 m range, consistent with the ARR and P15 examples. This was not verified from a primary state document.

### Gaps
- The Auckland Council Stormwater Flood Modelling Specifications, Wellington Water hydraulic modelling specification, NSW Flood Risk Management Manual 2023 and toolkit, the QRA flood study guideline, and Melbourne Water flood mapping specifications were not obtained.
- Dutch guidance (Rijkswaterstaat or STOWA 2D modelling guidance) was not searched.
- No peer-reviewed paper was found in this pass that tabulates guidance tolerances across countries.

## 6. Separating the three kinds of tolerance (synthesis for the writer)

### Takeaway
- **Model against observed (C):** guidance sets numbers for peak level against observed marks:
  - ±0.15 m (EA);
  - 0.5 ft (FEMA);
  - 0.2–0.3 m as examples (ARR and P15, which explicitly refuse to make them prescriptive);
  - ±1 ft as a USACE rule of thumb;
  - SEPA leaves "X" to the brief.
  
  Only the sewer-modelling code (CIWEM) sets flow, volume and timing numbers.
- **Model against model (M):** the only numeric tolerance found is FEMA's 0.5 ft water-level tie-in between models or reaches. The benchmark programmes publish spreads, not pass marks.
- **Internal checks (I):**
  - mass balance about ±1 % cumulative (SEPA);
  - >1–2 % to be investigated (ARR, P15);
  - 0–5 % of outlet volume for direct rainfall (P15);
  - Courant <1 for explicit schemes (EA);
  - a halved time step and a finer grid that do "not demonstrably change" results, with no number (P15).
  
  **No document read sets a numeric grid- or mesh-convergence criterion.**

### Cited Findings
- **C (levels):**
  - EA ±0.15 m typical, at least 3 events — [EA best practice](https://gov.uk/government/publications/river-modelling-technical-standards-and-assessment/hydraulic-modelling-best-practice-model-approach)
  - FEMA 0.5 ft — [FEMA GD 52, Section 4.5](https://www.fema.gov/sites/default/files/documents/fema_general-hydraulics-guidance_112022.pdf)
  - ARR non-prescriptive, with 300 mm / 50 % example — [ARR 2019 Book 7, Section 5.6](https://arr-software.org/pdfs/ARR_190514.pdf)
  - P15 0.2 m example — [ARR P15, Section 7.3.1](https://arr.ga.gov.au/__data/assets/pdf_file/0019/40573/ARR_Project15_TwoDimensional_Modelling_DraftReport.pdf)
  - USACE ±1 ft rule of thumb — [EM 1110-2-1416](https://chet-aero.com/wp-content/uploads/2016/11/em-1110-2-1416.pdf)
  - SEPA "+/- X mm" — [SEPA FMG v1.1, Section 8.2](https://www.sepa.org.uk/media/219653/flood_model_guidance_v2.pdf)
- **C (flows):** CIWEM peak flow +25 %/−15 % general, ±10 % critical; volume +20 %/−10 %; NSEC >0.5 — [CIWEM UDG CoP 2017, Table 5-1](https://www.ciwem.org/assets/pdf/Special%20Interest%20Groups/Urban%20Drainage%20Group/Code%20of%20Practice%20for%20the%20Hydraulic%20Modelling%20of%20Ur.pdf). EA, FEMA, ARR and SEPA give no peak-flow percentage — [EA best practice](https://gov.uk/government/publications/river-modelling-technical-standards-and-assessment/hydraulic-modelling-best-practice-model-approach); [ARR 2019](https://arr-software.org/pdfs/ARR_190514.pdf).
- **M:**
  - FEMA 0.5 ft tie-in — [FEMA GD 52, Section 3.4](https://www.fema.gov/sites/default/files/documents/fema_general-hydraulics-guidance_112022.pdf); [44 CFR 65.6(a)(2)](https://www.law.cornell.edu/cfr/text/44/65.6)
  - software-version change: document, no number — [FEMA GD 81, Section 2.1](https://transportation.ky.gov/Highway-Design/Drainage%20Manual/FEMA%20-%20Hydraulics%20Two-Dimensional%20Analyses%20Guidance%20-%20Nov%202023.pdf)
  - model acceptance: "comparable to other models", no number — [FEMA GD 98](https://www.fema.gov/sites/default/files/documents/fema_accepting-numerical-models-guidance_022018.pdf)
  - EA benchmark spreads: few %, about 0.05 m, about 0.4 m or about 10 % of depth, 20 % timing, 100 % velocity in shallow urban flow — [EA 2013](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf); [EA 2010](https://assets.publishing.service.gov.uk/media/5a75765c40f0b6360e4744dd/scho0510bsno-e-e.pdf)
- **I:**
  - ±1 % cumulative — [SEPA FMG v1.1, Sections 7.3, 7.4](https://www.sepa.org.uk/media/219653/flood_model_guidance_v2.pdf)
  - 1–2 % investigate — [ARR 2019 Book 7, Section 10.4](https://arr-software.org/pdfs/ARR_190514.pdf)
  - 0–5 % of Vo for direct rainfall — [ARR P15, Section 11.4.3](https://arr.ga.gov.au/__data/assets/pdf_file/0019/40573/ARR_Project15_TwoDimensional_Modelling_DraftReport.pdf)
  - 1.46 % "no identifiable consequence" — [EA 2013, Section 4.3.3](https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf)
  - finer resolution and halved time step, no number — [ARR P15, Sections 7.4, 10.5.3](https://arr.ga.gov.au/__data/assets/pdf_file/0019/40573/ARR_Project15_TwoDimensional_Modelling_DraftReport.pdf)
- **Cell-count rules (build checks):**
  - ≥5 cells across a channel — [ARR P15, Section 6.2.1.1](https://arr.ga.gov.au/__data/assets/pdf_file/0019/40573/ARR_Project15_TwoDimensional_Modelling_DraftReport.pdf)
  - 3–4 cells per major flow path — [SEPA FMG v1.1, Section 7.3](https://www.sepa.org.uk/media/219653/flood_model_guidance_v2.pdf)
  - 6–8 cells for flow separation — [ARR 2019 Book 6, Ch. 4, p. 170](https://arr-software.org/pdfs/ARR_190514.pdf)

### Inferences
- [Likely] "Peak flow within 3 % of the square-cell run" has no counterpart in any guidance read. The profession's model-against-model numbers are on water level, not discharge. The only fixed one is FEMA's 0.5 ft tie-in; the EA spreads between packages are an order looser than 3 %.
- [Likely] A self-set 3 % is therefore neither required nor contradicted. Its weakness is the reference, not the number: the square-cell run is itself a discretisation of uncertain accuracy. A convergence statement against a finer run is closer to what ARR P15 asks ("finer resolution ... results do not demonstrably change") than a comparison with another coarse mesh.
- [Likely] If an external anchor is wanted for design work, the defensible set is:
  - water level within about 0.15 m against observed marks (EA, FEMA);
  - cumulative volume error within about ±1 % (SEPA), investigated above 1–2 % (ARR);
  - at least 3–5 cells across the main flow path (SEPA, P15);
  - a documented time-step and grid refinement check.
- [Guessing] The guidance's silence on grid-convergence numbers likely reflects that, with terrain and boundary uncertainty "at least the same order" as grid effects (EA 2013), regulators treat convergence as engineering judgement. That leaves a solver developer free to adopt a formal procedure such as Richardson extrapolation or a grid convergence index. None of the flood guidance read cites one.

### Gaps
- No vendor-independent flood document was found with a numeric grid-convergence criterion or a peak-discharge tolerance between models. If one exists, it was not in EA, ARR, P15, SEPA, CIWEM, FEMA or USACE material. Dutch, NZ and US state guidance remain unchecked.
- Moriasi et al. (2007) is known here only second-hand through CIWEM ("NSEC ... 0.5 ... satisfactory"). Its thresholds and the later ASABE/Moriasi 2015 guidance were not read.
