import os
from qgis.core import (QgsProject, QgsRasterLayer, QgsStyle, QgsColorRampShader, QgsRasterShader,
                       QgsSingleBandPseudoColorRenderer, QgsRasterBandStats)
ROOT = r"D:\Mojtaba\Renardet\Wadi2D\W100 maps the RAS Mapper way\runs"
RUNS = ["rerun2_run1_full_2d_aligned", "rerun2_run3_hybrid_aligned", "rerun2_run4_hybrid_2d_routing_aligned"]
NAME = "Highest water level, m"
project = QgsProject.instance()
done = []
for run in RUNS:
    path = os.path.join(ROOT, f"level_{run}", "pixels", "pixel_level.tif")
    if not os.path.exists(path) or not os.path.exists(path.replace("pixel_level.tif", "pixels.json")):
        done.append(f"{run}: not ready"); continue
    group = next((g for g in project.layerTreeRoot().findGroups(True)
                  if g.name().startswith("Pixel rasters") and g.parent() is not None and g.parent().name().endswith(run)), None)
    if group is None:
        done.append(f"{run}: no group"); continue
    if any(n.name() == NAME for n in group.findLayers()):
        done.append(f"{run}: already there"); continue
    layer = QgsRasterLayer(path, NAME)
    stats = layer.dataProvider().bandStatistics(1, QgsRasterBandStats.Min | QgsRasterBandStats.Max, layer.extent(), 250000)
    ramp = QgsStyle.defaultStyle().colorRamp("Spectral"); ramp.invert()
    shader = QgsColorRampShader(stats.minimumValue, stats.maximumValue, ramp)
    shader.classifyColorRamp(10)
    rs = QgsRasterShader(); rs.setRasterShaderFunction(shader)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, rs))
    project.addMapLayer(layer, False)
    node = group.addLayer(layer); node.setItemVisibilityChecked(False); node.setExpanded(False)
    done.append(f"{run}: added, {stats.minimumValue:.1f} to {stats.maximumValue:.1f} m")
print("\n".join(done))
