# W1 research and design note

**Status (2026-11-01): live. Toolchain gate, partial research, design note, prototypes and the validation of version 1 are here.** It is the record of why
the code is the way it is. Research topics N04, N06, N07, N08, N10, H05 and S01 to S05 were not run, so `research/` holds raw files only, with no track
syntheses. The design note was built on and revised by the prototypes rather than approved first, on his word to go ahead.

## What this folder holds

| Path | What it is |
|---|---|
| `toolchain_check.md` | What the RTX 5080 machine has and lacks, and the stack decision that follows |
| `data/block2_inventory.md` | Inventory of the Block 2 test data (HMS model, terrain, shapefiles, W1 peaks); the data itself stays read-only in its own folder |
| `research/raw/` | One file per research topic, written by the research agents, each with its independent verification section |
| `design_seed_architecture.md` | The architecture proposal given to the design panels (module map, config, data contracts, protocol, build order) |
| `panels/` | The design panels' proposals, kept as the record of the alternatives |
| `design_note.md` | The design note: scheme, sub-grid formulation, module map, data contracts, test plan, build order |
| `benchmarks/` | Micro-benchmarks run on the RTX 5080 (kernel throughput, compile times) with their scripts and outputs |
| `prototypes/` | The staggered-scheme prototype and its scans, kept as the evidence for decision 19 |
| `validation/hms_replication.md`, `hms_heldout.md` | Lumped hydrology against HMS on Blocks 2, 4, 6 and Majlas |
| `validation/ras_head_to_head.md` | HEC-RAS 6.6 on a fan window, scripted end to end |
| `validation/block2_first_run.md` | First real run. **Superseded by** `block2_full.md`; keep for its history |
| `validation/block2_full.md` | **Live.** Modes (b) and (c) at the five dams, speed, dams against EAV and Modified Puls, grid convergence |

## How it relates to the code

The software lives at the repository root (`wadi2d/` package with the kernels inside it, `tests/`, `plugin/`). W# folders hold the
engineering iterations: research, design, benchmarks and validation runs, never overwritten. A later iteration (W2 ...) that
revises a decision says so here and in the root `README.md`.
