"""His rule of 2026-11-07 through the real dock: Suggest breaklines tells the user that bank lines are refinement lines,
never barriers, and that only road, dam and dyke crests go under Structures as Crest lines."""


def scenario(h):
    from pathlib import Path

    h.VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")  # a worktree has no venv of its own
    ground = h.Bidah()
    dock = yield from h.open_dock()
    from wadi2d_qgis import suggest_lines

    m = dock.mesh
    h.set_rain_job(dock, ground, "banks", dx=20.0, sim_hours=0.5)
    m.setCollapsed(False)
    m.suggest_button.click()
    yield lambda: dock.panel.message.text() != suggest_lines.WORKING
    text = dock.panel.message.text()
    h.log(f"message: {text}")
    h.check("suggested", text.startswith("Suggested"), text)
    h.check("banks go to the Mesh section's Refinement lines", "bank lines as Refinement lines in the Mesh section" in text, text)
    h.check("banks are never loaded as Crest lines", "never load them as Crest lines" in text, text)
    h.check("only road, dam and dyke crests go to Structures", "road, dam and dyke crests as Crest lines" in text, text)
    h.widget_shot("suggest_message", dock.panel)
