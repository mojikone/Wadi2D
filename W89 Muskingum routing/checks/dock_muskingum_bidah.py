"""W89 through the real dock and the real engine on Bidah, CPU: a basin generated from the DEM, the Muskingum choice,
the reach table, Propose K and X from the reaches' own sections, a run whose reach outflows are the Muskingum route
of their inflows by hand, a reach with no K and X left out by name, a reach outside its stable range warned of."""

import csv
import json

SIM_HOURS = 3.0
THRESHOLD_KM2 = 2.0
STEP_MIN = 5.0
MUSKINGUM = "muskingum"
DRY_M3S = 0.01
FILE_FIGURES = 1.0e-5
"""The series CSV holds six figures (99.7536), so a route recomputed from the file's inflow matches the file's
outflow to about that; the engine's own arithmetic is checked to 1e-9 in tests/engine/test_handback.py."""


def done_event(h, folder):
    found = h.events(folder, "done")
    return found[-1] if found else {}


def series(folder, name):
    path = folder / "series" / f"network_{name.replace(' ', '_')}.csv"
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    head = rows[0]
    q_in, q_out = head.index("inflow_m3s"), head.index("outflow_m3s")
    return [float(r[q_in]) for r in rows[1:]], [float(r[q_out]) for r in rows[1:]]


def by_hand(inflow, k_hours, x, subreaches):
    """HEC-HMS's coefficient form, each subreach with K / n, written out here: nothing of the engine is imported."""
    k = k_hours * 60.0 / subreaches
    bottom = 2.0 * k * (1.0 - x) + STEP_MIN
    c1, c2, c3 = (STEP_MIN - 2.0 * k * x) / bottom, (STEP_MIN + 2.0 * k * x) / bottom, (2.0 * k * (1.0 - x) - STEP_MIN) / bottom
    flow = list(inflow)
    for _ in range(subreaches):
        out = [flow[0]]
        for t in range(1, len(flow)):
            out.append(c1 * flow[t] + c2 * flow[t - 1] + c3 * out[-1])
        flow = out
    return flow


def cells(box, row):
    return [box.table.item(row, c).text() for c in range(box.table.columnCount())]


def scenario(h):
    ground = h.Bidah()
    dam = json.loads((h.VALIDATION / "jobs" / "dam_Bidah03_100yr_20.json").read_text(encoding="utf-8"))
    crests = [o for o in dam["terrain"]["objects"] if o["kind"] == "crest_line"]
    spillway = next(o for o in dam["terrain"]["objects"] if o["kind"] == "spillway")
    longest = max(crests, key=lambda o: len(o["coordinates"]))
    crest = h.add_vector(
        h.geojson("crest", [h.line(o["coordinates"], z=o["z_constant"], name="Bidah 03" if o is longest else f"saddle {n}")
                            for n, o in enumerate(crests, 1)]),
        "crest", ground.crs,
    )  # fmt: skip
    spill = h.add_vector(
        h.geojson("spill", [h.line(spillway["coordinates"], z=spillway["z_constant"], c=2.1, l=spillway["length"])]),
        "spill", ground.crs,
    )  # fmt: skip
    cn = h.add_raster(h.BLOCK / "HEC_HMS_Block_02" / "Hydrology Data" / "CN_Include_Hill_Area.tif", "cn")
    dock = yield from h.open_dock()
    hy, basin, s, box = dock.hydrology, dock.hydrology.basin, dock.structures, dock.hydrology.muskingum
    routing = hy.routing

    h.set_rain_job(dock, ground, "cunge", dx=20.0, rain=60.0, hours=1.0, sim_hours=SIM_HOURS, pixels=False)
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    h.check("the engine choice is CPU only", dock.panel.backend.currentData() == "cpu")
    hy.cn.raster.setLayer(cn)
    s.layers["crest_line"].setLayer(crest)
    s.fields["crest_line"]["crest_z"].setField("z")
    s.layers["spillway"].setLayer(spill)
    s.fields["spillway"]["crest_z"].setField("z")
    s.fields["spillway"]["coefficient"].setField("c")
    s.fields["spillway"]["length"].setField("l")

    h.log("=== 1 the choice, and the basin")
    schemes = [routing.itemData(i) for i in range(routing.count())]
    h.check("the choices are the engine's three, HMS-faithful first", schemes == dock.schema.enum("hydrology.reach_routing") == ["hms", "conserving", MUSKINGUM], schemes)
    h.check("Muskingum has words of its own", "K and X per reach" in routing.itemText(routing.findData(MUSKINGUM)), routing.itemText(routing.findData(MUSKINGUM)))
    h.check("the tooltip says what fixed K and X cost", "drifting from" in routing.toolTip() and "hydrology.muskingum" in routing.toolTip(), routing.toolTip()[-200:])
    h.check("no reach table under the default", box.isHidden())
    basin.setChecked(True)
    basin.threshold.setValue(THRESHOLD_KM2)
    basin.generate_button.click()
    yield lambda: basin.generate_button.isEnabled()
    model = basin.model
    h.check("a basin was generated", model is not None, basin.summary.text())
    reaches = [e["name"] for e in model["elements"] if e["kind"] == "reach"]
    h.check("with reaches to route", len(reaches) >= 2, reaches)

    h.log("=== 2 the reference run: Muskingum-Cunge on the sections")
    first = h.RUNS / "cunge"
    yield from h.run(dock)
    h.check("the Muskingum-Cunge run finished", done_event(h, first).get("code") == 0, dock.panel.message.text()[:300])
    reference = {name: series(first, name) for name in reaches}
    peaks = {name: max(reference[name][0]) for name in reaches}
    h.log(f"reach inflow peaks, m3/s: { {k: round(v, 1) for k, v in peaks.items()} }")

    h.log("=== 3 Muskingum: the reach table and the proposal")
    routing.setCurrentIndex(routing.findData(MUSKINGUM))
    h.check("the reach table shows", not box.isHidden())
    h.check("with the generated reaches", [row.name for row in box.rows] == reaches, [row.name for row in box.rows])
    h.check("nothing proposed by itself", all(row.empty() for row in box.rows) and dock._collect()[MUSKINGUM] == [])
    h.check("the note says what a run would do", f"0 of {len(reaches)} reaches have K and X" in box.note.text() and "left out" in box.note.text(), box.note.text())
    at = {name: n for n, name in enumerate(reaches)}
    carrying = [name for name in reaches if peaks[name] > DRY_M3S]
    dry = [name for name in reaches if name not in carrying]
    main = max(carrying, key=peaks.get)
    h.log(f"reaches that carry the flood: {carrying}; below a dam that does not spill: {dry}; the largest: {main}")
    h.check("at least two reaches carry the flood", len(carrying) >= 2, carrying)
    for name in carrying:
        box.table.item(at[name], 1).setText(f"{peaks[name]:.1f}")
    for name in dry:  # what a user might type for a reach that stayed dry: a flow of nothing
        box.table.item(at[name], 1).setText("0")
    h.check("each reach's peak of the reference run typed as its reference flow", all(box.rows[at[n]].flow == round(peaks[n], 1) for n in carrying))
    h.check("a flow of zero is named and not used", all(box.rows[at[n]].flow is None and "so none is used" in box.table.item(at[n], 5).text() for n in dry), [cells(box, at[n]) for n in dry])
    box.button.click()
    h.check("the button is busy while the engine answers", not box.button.isEnabled())
    yield lambda: box.button.isEnabled()
    h.log(f"note: {box.note.text()}")
    for n in range(len(reaches)):
        h.log(f"row {cells(box, n)}")
    rows = {row.name: row for row in box.rows}
    h.check("every reach got K, X and subreaches", all(row.complete() and row.proposed and row.subreaches >= 1 for row in box.rows), [cells(box, n)[:5] for n in range(len(reaches))])
    h.check("the reaches with a flow by Cunge at that flow, on their sections", all(f"Cunge (1969) at {round(peaks[n], 1):.4g} m3/s" in rows[n].words and "K = L / c" in rows[n].words and "index celerity" not in rows[n].words for n in carrying), rows[main].words[:200])
    h.check("the dry reaches at the flow of their index celerity, and told to give a flow", all("index celerity" in rows[n].words and "give a reference flow" in rows[n].words for n in dry), [rows[n].words[:120] for n in dry])
    h.check("proposals in italics, the derivation in the last column", box.table.item(at[main], 2).font().italic() and box.table.item(at[main], 5).text() == rows[main].words)
    h.check("the note counts them and calls them a start", f"{len(reaches)} proposed for a 5 min step" in box.note.text() and "A proposal is a start" in box.note.text(), box.note.text())
    h.check("every row in 0 to 0.5 and K above zero", all(0.0 <= row.x <= 0.5 and row.k_hours > 0.0 for row in box.rows))
    flagged = sorted(name for name, row in rows.items() if "NOT stable" in row.words)
    h.log(f"proposals the helper calls not stable at the step: {flagged}")
    h.check("the note counts the reaches no K and X route at this step", (f"{len(flagged)} not stable at this step" in box.note.text()) == bool(flagged), box.note.text())
    h.widget_shot("hydrology_muskingum", hy)
    other = next(name for name in carrying if name != main)
    typed = round(0.5 * rows[other].x, 3)
    box.table.item(at[other], 3).setText(str(typed))
    h.check("an edit makes the row the user's", not rows[other].proposed and rows[other].x == typed and not box.table.item(at[other], 2).font().italic(), cells(box, at[other]))
    wanted = [{"reach": r.name, "k_hours": r.k_hours, "x": r.x, "subreaches": r.subreaches} for r in box.rows]

    h.log("=== 4 the Muskingum run")
    second = h.RUNS / "muskingum"
    dock.panel.folder.setFilePath(str(second))
    yield from h.run(dock)
    done = done_event(h, second)
    h.check("the Muskingum run finished", done.get("code") == 0, dock.panel.message.text()[:300])
    job = json.loads((second / "job.json").read_text(encoding="utf-8"))["hydrology"]
    h.check("job.json holds the choice and the table's rows, the dry reaches' too", job.get("reach_routing") == MUSKINGUM and job.get(MUSKINGUM) == wanted, job.get(MUSKINGUM))
    resolved = json.loads((second / "config.resolved.json").read_text(encoding="utf-8"))["hydrology"]
    h.check("and so does the job as it ran", resolved["reach_routing"] == MUSKINGUM and resolved[MUSKINGUM] == wanted)
    h.check("mass closes", abs(done.get("balance", {}).get("relative_error", 1.0)) < 1e-6, done.get("balance", {}).get("relative_error"))
    notes = [e["message"] for e in h.events(second, "warn")]
    h.check("no reach is left out", not [n for n in notes if "lacks" in n], notes)
    warned = sorted(n.split(":")[0].removeprefix("reach ") for n in notes if "Muskingum routing is unstable" in n)
    h.check("the run warns of exactly the reaches the helper called not stable", warned == flagged, (warned, flagged))
    record = {}
    for row in wanted:
        name = row["reach"]
        inflow, outflow = series(second, name)
        hand = by_hand(inflow, row["k_hours"], row["x"], row["subreaches"])
        worst = max(abs(a - b) for a, b in zip(hand, outflow, strict=True))
        cunge_in, cunge_out = reference[name]
        record[name] = {
            **row, "peak_in": round(max(inflow), 2), "muskingum_peak": round(max(outflow), 2),
            "cunge_peak_in": round(max(cunge_in), 2), "cunge_peak": round(max(cunge_out), 2),
            "lowest_out": round(min(outflow), 4), "by_hand_worst": worst,
        }
        h.check(f"{name}: the outflow is the Muskingum route of its inflow by hand, to the series file's six figures", worst < FILE_FIGURES * max(1.0, max(inflow)), (worst, max(inflow)))
    h.log(f"reaches: {json.dumps(record)}")
    ratio = record[main]["muskingum_peak"] / record[main]["cunge_peak"]
    h.check(f"{main}, proposed at its own peak: the outflow peak within 5 % of Muskingum-Cunge's", abs(ratio - 1.0) < 0.05, ratio)
    (h.P / "bidah_muskingum_reaches.json").write_text(json.dumps(record, indent=1), encoding="utf-8")

    h.log("=== 5 a reach with no K and X is left out, by name")
    for column in (2, 3, 4):
        box.table.item(at[main], column).setText("")
    h.check("the row is empty and the note names it", rows[main].empty() and main in box.note.text() and "left out" in box.note.text(), box.note.text())
    third = h.RUNS / "left_out"
    dock.panel.folder.setFilePath(str(third))
    yield from h.run(dock)
    h.check("the run finished", done_event(h, third).get("code") == 0, dock.panel.message.text()[:300])
    notes = [e["message"] for e in h.events(third, "warn")]
    h.check("the run says which reach lacks K and X and where its water goes", any(f"reach {main} lacks muskingum_k_hours, muskingum_x" in n and "enters the 2D grid" in n for n in notes), notes)
    h.check("the reach has no series: it did not run", not (third / "series" / f"network_{main}.csv").is_file())
    h.check("mass closes", abs(done_event(h, third).get("balance", {}).get("relative_error", 1.0)) < 1e-6)

    h.log("=== 6 a second proposal fills the empty row and leaves the typed one; a count outside the range is warned of")
    box.button.click()
    yield lambda: box.button.isEnabled()
    h.check("the empty row is proposed again, the typed row kept", rows[main].proposed and rows[main].complete() and rows[other].x == typed and "1 kept as typed" in box.note.text(), box.note.text())
    box.table.item(at[main], 4).setText("400")
    fourth = h.RUNS / "unstable"
    dock.panel.folder.setFilePath(str(fourth))
    yield from h.run(dock)
    h.check("the run finished", done_event(h, fourth).get("code") == 0, dock.panel.message.text()[:300])
    notes = [e["message"] for e in h.events(fourth, "warn")]
    h.check("the run warns as HMS does, and names the stable counts", any(n.startswith(f"reach {main}: Muskingum routing is unstable") and "41169" in n and "stable at this step" in n for n in notes), notes)

    h.log("=== 7 back to the default")
    routing.setCurrentIndex(routing.findData("hms"))
    h.check("the table hides and the rows stay out of the job", box.isHidden() and MUSKINGUM not in dock._collect())
    h.widget_shot("hydrology_final", hy)
