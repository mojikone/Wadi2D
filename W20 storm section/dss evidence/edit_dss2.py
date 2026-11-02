from pathlib import Path
p = Path(r"D:\Mojtaba\Renardet\Wadi2D\wadi2d\hms\dss.py")
t = p.read_bytes().decode("utf-8")
a = 'import shutil\nimport tempfile\nfrom dataclasses import dataclass\nfrom pathlib import Path\n'
b = 'import shutil\nimport tempfile\nfrom dataclasses import dataclass\nfrom functools import partial\nfrom pathlib import Path\n'
assert t.count(a) == 1; t = t.replace(a, b)
a = 'NATIVE_DEBUG_LEVEL = 1\n'
b = 'NATIVE_DEBUG_LEVEL = 1\nGRID_SRS_CHARACTERS = 8192\n"""``hecdss`` asks for 600 unless told, and PSD93 / UTM zone 40N takes 616."""\n'
assert t.count(a) == 1; t = t.replace(a, b)
a = '''        grid = self._native.get(str(pathname))
        if grid is None:
            raise DssLookupError(f"no gridded record at {pathname}")
'''
b = '''        layer = self._native._native
        layer.hec_dss_gridRetrieve = partial(layer.hec_dss_gridRetrieve, srsDefinitionLength=GRID_SRS_CHARACTERS)
        try:
            grid = self._native.get(str(pathname))
        finally:
            del layer.hec_dss_gridRetrieve
        if grid is None:
            raise DssLookupError(f"no gridded record at {pathname}")
'''
assert t.count(a) == 1; t = t.replace(a, b)
p.write_bytes(t.encode("utf-8")); print("ok")
