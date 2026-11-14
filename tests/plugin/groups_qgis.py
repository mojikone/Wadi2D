# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""On QGIS's own Python: the layer tree's pattern, one group per model (W68).

Started by ``test_groups_qgis.py``. Argument: a scratch folder. Memory layers stand in for a run's; prints
``GROUPS PASSED`` as its last line.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "plugin"))
WORK = Path(sys.argv[1])

from qgis.core import QgsApplication, QgsProject, QgsVectorLayer  # noqa: E402

app = QgsApplication([], False)
app.initQgis()

from wadi2d_qgis import layer_groups as g  # noqa: E402

project = QgsProject.instance()
root = project.layerTreeRoot()


def memory(name: str) -> QgsVectorLayer:
    return QgsVectorLayer("Point?crs=EPSG:32640", name, "memory")


def names(group) -> list[str]:
    return [child.name() for child in group.children()]


# the model of a run folder
for sub in ("bidah", "bidah_2", "bidah_arf", "solo_7"):
    (WORK / sub).mkdir(parents=True, exist_ok=True)
assert g.model_of_run(WORK / "bidah") == "bidah"
assert g.model_of_run(WORK / "bidah_2") == "bidah"
assert g.model_of_run(WORK / "bidah_arf") == "bidah"
assert g.model_of_run(WORK / "solo_7") == "solo_7", "no solo beside it: the number is part of the name"
assert g.model_name("") == g.NO_MODEL and g.model_name(WORK / "bidah") == "bidah"

# the pattern, made whole the first time; a user's layer at the root stays out of it
user = memory("my own layer")
project.addMapLayer(user)
top = g.model_group("bidah")
assert top.name() == g.model_title("bidah") and top.parent() is root
inputs = top.children()[-1]
assert inputs.name() == g.INPUTS and names(inputs) == list(g.INPUT_GROUPS), names(inputs)
assert g.input_group("bidah", g.MESH).name() == g.MESH
assert root.findLayer(user.id()).parent() is root

# results on top of the inputs, newest first
first = g.run_results(WORK / "bidah")
g.add_layer(g.subgroup(first, g.SETUP), memory("domain"))
second = g.run_results(WORK / "bidah_2")
assert names(top) == [g.results_title("bidah_2"), g.results_title("bidah"), g.INPUTS], names(top)

# a rerun replaces its own results group, at its place; the user's layer put inside it survives, moved up
mine = memory("my note in the results")
project.addMapLayer(mine, False)
first.addLayer(mine)
moved = memory("moved out by the user")
g.add_layer(first, moved)
node = root.findLayer(moved.id())
root.insertChildNode(0, node.clone())
node.parent().removeChildNode(node)
old_domain = [n.layerId() for n in first.findLayers() if n.layer().name() == "domain"]
mine_id, moved_id = mine.id(), moved.id()
again = g.run_results(WORK / "bidah", fresh=True)
assert names(top)[:2] == [g.results_title("bidah_2"), g.results_title("bidah")], names(top)
assert again.children() == [], "the fresh group starts empty"
assert project.mapLayer(old_domain[0]) is None, "the plugin's old layer left the project"
assert project.mapLayer(mine_id) is not None and root.findLayer(mine_id).parent() is top, "the user's layer kept"
assert project.mapLayer(moved_id) is not None and root.findLayer(moved_id).parent() is root, "a moved layer stays"
assert g.find_run_results(WORK / "bidah") is again and g.find_run_results(WORK / "bidah_2") is second

# an input slot replaces only its own layers inside the model; one moved out stays
old_mesh = memory("mesh preview")
g.add_layer(g.input_group("bidah", g.MESH), old_mesh, g.SLOT_MESH)
kept = memory("suggested breaklines")
g.add_layer(g.input_group("bidah", g.MESH), kept, g.SLOT_SUGGEST)
mesh_id, kept_id = old_mesh.id(), kept.id()
g.clear_slot("bidah", g.SLOT_MESH)
assert project.mapLayer(mesh_id) is None and project.mapLayer(kept_id) is not None

# the user moves the model's group into a group of their own: the next run finds it there
own = root.insertGroup(0, "my project")
own.insertChildNode(0, top.clone())
root.removeChildNode(top)
assert g.find_model("bidah").parent() is own
g.run_results(WORK / "bidah_2")
assert len([grp for grp in g._groups(root) if grp.customProperty(g.ROLE) == "model"]) == 1, "no second model group"

# a second model is a second group
g.run_results(WORK / "solo_7")
assert root.findGroup(g.model_title("solo_7")) is not None

print("GROUPS PASSED", flush=True)
sys.stdout.flush()
os._exit(0)
