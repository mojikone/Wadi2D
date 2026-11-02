import base64, lzma, textwrap, sys, pathlib
sc = pathlib.Path(sys.argv[1])
def blob(f):
    packed = base64.b64encode(lzma.compress(open(f, "rb").read(), preset=9)).decode()
    return "\n".join(textwrap.wrap(packed, 100))
t = (sc/"scripts/test_template.txt").read_text(encoding="utf-8")
t = t.replace("@VORTEX@", blob(sc/"work/v1/vortex.dss")).replace("@ASC@", blob(sc/"work/asc/asc.dss"))
t = t.replace("from hecdss import HecDss\nfrom hecdss.gridded_data import GriddedData\nfrom hecdss.regular_timeseries import RegularTimeSeries\n", "from hecdss import HecDss, RegularTimeSeries\nfrom hecdss.gridded_data import GriddedData\n")
pathlib.Path(r"D:\Mojtaba\Renardet\Wadi2D\tests\storm\test_rain_dss.py").write_text(t, encoding="utf-8", newline="\n")
print(len(t))
