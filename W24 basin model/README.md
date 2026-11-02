# W24 basin model (D6a)

[PRESERVE-CHECK]

KEEP, not touched:
- `wadi2d/forcing.py`, `wadi2d/run.py`, everything under `plugin/`: D5 is changing them on another branch.
- `RunConfig` and its JSON Schema: no new field, so `tests/plugin/schema_sample.json` stays as it is and an old job
  is byte-identical in its resolved config, its grid key and its checkpoint hash.
- `wadi2d/mesh/streams.py`, the mesher, the lumped engine and the reservoir classes: reused, unchanged.

CHANGE:
- New package `wadi2d/basin/`: delineation on the job's DEM and domain, the network, terrain parameters, reservoirs, the
  `basin.json` contract, `basin.gpkg`, the loader into `wadi2d/hydrology/model.py`, the junction routes.
- `wadi2d/engine/cli.py`: one new subcommand, `wadi2d basin JOB --out FOLDER`. Nothing else in the file moves.
- `wadi2d/config/schema.py`: one new class, `BasinSettings`. It is not a field of `RunConfig`; it holds the defaults of the
  command, so each is set once.
- Nothing is removed; nothing existing changes behaviour.

FILES: `wadi2d/basin/*` (new), `wadi2d/engine/cli.py` (`_basin`, one subparser), `wadi2d/config/schema.py` (`BasinSettings`),
`tests/basin/*` (new), `W24 basin model/*` (new).
