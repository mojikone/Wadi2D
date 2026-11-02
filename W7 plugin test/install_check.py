"""Inside a separate QGIS: load the plugin the way QGIS does, from the plugins folder, on a fresh profile."""
import time
import traceback
from pathlib import Path

import qgis.utils as qu
from qgis.core import QgsProject
from qgis.PyQt.QtCore import QTimer
from qgis.utils import iface

P = Path(r"C:\Users\mojtaba\AppData\Local\Temp\claude\D--Mojtaba-Renardet-Wadi2D\563cf3f8-070b-42eb-82ea-489205b14695\scratchpad\plug")
LOG = P / "install_log.txt"
LOG.write_text("", encoding="utf-8")
state = {"t": time.monotonic(), "stage": 0}


def log(text):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(text + "\n")


def done():
    log("DONE")
    QgsProject.instance().setDirty(False)
    QTimer.singleShot(400, iface.actionExit().trigger)


def tick():
    try:
        if state["stage"] == 0:
            log(f"available {qu.available_plugins}")
            log(f"loaded {qu.loadPlugin('wadi2d_qgis')}")
            log(f"started {qu.startPlugin('wadi2d_qgis')}")
            plugin = qu.plugins["wadi2d_qgis"]
            log(f"menu action {plugin.toggle_action is not None}")
            plugin.toggle_action.setChecked(True)
            state["plugin"] = plugin
            state["stage"] = 1
        elif state["stage"] == 1:
            dock = state["plugin"].dock
            label = dock.engine_label.text()
            if "Looking" not in label or time.monotonic() - state["t"] > 40:
                log(f"engine label on a fresh profile: {label}")
                from wadi2d_qgis import settings

                log(f"default engine text: {settings.engine_text()}")
                settings.set_engine_text(rf'"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe" -m wadi2d.engine.cli')
                dock.load_engine()
                state["stage"] = 2
        elif state["stage"] == 2:
            dock = state["plugin"].dock
            if dock.schema is not None or time.monotonic() - state["t"] > 60:
                log(f"after setting the engine: {dock.engine_label.text()}, run enabled {dock.panel.run_button.isEnabled()}")
                log(f"unload {qu.unloadPlugin('wadi2d_qgis')}")
                done()
                return
    except Exception:
        log(traceback.format_exc())
        done()
        return
    QTimer.singleShot(300, tick)


QTimer.singleShot(4000, tick)
