from java.lang import System, Class
System.loadLibrary("gdalalljni")
for name in ["hec.heclib.grid.Asc2DssGrid", "hec.heclib.grid.Dss2AscGrid", "mil.army.usace.hec.vortex.geo.WktFactory", "mil.army.usace.hec.vortex.io.BatchExporter", "mil.army.usace.hec.vortex.io.BatchExporter$BatchExporterBuilder", "mil.army.usace.hec.vortex.geo.WktFactory"]:
    try:
        c = Class.forName(name)
        print("==", name)
        for m in sorted(set(str(x) for x in c.getDeclaredMethods() if x.getModifiers() & 1)): print("  ", m[:170])
        for m in c.getConstructors(): print("  ctor", m)
    except Exception as e:
        print("!!", name, e)
