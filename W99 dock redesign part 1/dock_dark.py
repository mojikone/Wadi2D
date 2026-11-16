"""W99 step 3 on a dark QGIS theme: the dock's own frame takes the palette's dark counterpart, and still reads.

Night Mapping is set in the throwaway profile before the dock is made. The proof that it reads is the screenshots, kept
in ``shots/``; the checks hold what a screenshot cannot: which palette was taken, and that the words are all there.
"""

from qgis.core import QgsApplication
from qgis.PyQt.QtWidgets import QApplication

THEME = "Night Mapping"


def big_shot(h, dock, name, size=(440, 900)):
    frame = dock.widget()
    held = frame.size()
    frame.resize(*size)
    QApplication.processEvents()
    frame.grab().save(str(h.P / f"widget_{name}.png"))
    frame.resize(held)
    QApplication.processEvents()


def scenario(h):
    h.check("QGIS has the theme", THEME in QgsApplication.uiThemes(), list(QgsApplication.uiThemes()))
    QgsApplication.setUITheme(THEME)
    yield lambda: True
    ground = h.Bidah()
    dock = yield from h.open_dock(all_sections=False)
    from wadi2d_qgis import look
    from wadi2d_qgis.section_status import MISSING

    h.check("the theme's window is dark", look.is_dark(dock.palette()), dock.palette().window().color().name())
    sheet = dock.widget().styleSheet()
    h.check("the dock took the dark palette", look.DARK.card in sheet and look.LIGHT.card not in sheet)
    big_shot(h, dock, "dark_start_page")
    dock.start_page.cards["hybrid_lumped"].click()
    yield lambda: True
    h.set_rain_job(dock, ground, "dark", dx=30.0, rain=40.0, hours=0.5, sim_hours=0.75, pixels=False)
    statuses = dock.status_links.refresh()
    h.check("a missing section says so in words on the dark card too", statuses["hydrology"].state == MISSING and dock.cards["hydrology"].pill.text() == "Missing" and dock.cards["hydrology"].closed_words.text() == statuses["hydrology"].words, statuses["hydrology"])
    h.check("the footer names it", dock.footer.needs.text() == "1 section needs you before running: Hydrology", dock.footer.needs.text())
    dock.terrain.setCollapsed(False)
    dock.hydrology.setCollapsed(True)
    big_shot(h, dock, "dark_model_page")
    yield lambda: True
