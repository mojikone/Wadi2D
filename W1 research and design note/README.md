# W1 research and design note

**Status (2026-10-29): started. Toolchain gate run (see `toolchain_check.md`); research workflow launched; design note pending.**
Live until the design note is approved and the build starts; then it is the record of why the code is the way it is.

## What this folder holds

| Path | What it is |
|---|---|
| `toolchain_check.md` | What the RTX 5080 machine has and lacks, and the stack decision that follows |
| `data/block2_inventory.md` | Inventory of the Block 2 test data (HMS model, terrain, shapefiles, W1 peaks); the data itself stays read-only in its own folder |
| `research/raw/` | One file per research topic, written by the research agents, each with its independent verification section |
| `research/N_numerics.md`, `H_hydrology.md`, `S_software.md` | Track syntheses: the answer to each design question, evidence, rejected alternatives, numbers the code uses |
| `research/00_design_inputs.md` | The decision table that feeds the design note |
| `design_note.md` | The design note: scheme, sub-grid formulation, module map, data contracts, test plan, build order |
| `benchmarks/` | Micro-benchmarks run on the RTX 5080 (kernel throughput, compile times) with their scripts and outputs |

## How it relates to the code

The software lives at the repository root (`wadi2d/` package, `engine/` kernels, `tests/`, `plugin/`). W# folders hold the
engineering iterations: research, design, benchmarks and validation runs, never overwritten. A later iteration (W2 ...) that
revises a decision says so here and in the root `README.md`.
