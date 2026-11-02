import subprocess, sys, pathlib, re
f = pathlib.Path(r"D:\Mojtaba\Renardet\Wadi2D\wadi2d\io\rain\dss_grid.py")
good = f.read_bytes()
muts = [
 ("no north flip", b"stored[np.newaxis, ::-1]", b"stored[np.newaxis]"),
 ("null 0 honoured", b"if record.null_value != UNSET_NULL:", b"if True:"),
 ("outside always NaN", b"stack[frame] = 0.0 if _cut_to_rain(depth) else np.nan", b"stack[frame] = np.nan"),
 ("outside always 0", b"stack[frame] = 0.0 if _cut_to_rain(depth) else np.nan", b"stack[frame] = 0.0"),
 ("cell zero ignored", b"west = first.x_cell_zero + left * first.cell_size", b"west = left * first.cell_size"),
 ("frames unsorted", b"timed = sorted(((_period(p, spec, path.name), p) for p in pathnames), key=lambda item: item[0])", b"timed = [(_period(p, spec, path.name), p) for p in pathnames]"),
 ("row placed from bottom", b"row = top - record.lower_left_y - depth.shape[0]", b"row = record.lower_left_y - bottom"),
 ("D equal E not an instant", b"if closes != opens:\n        return opens, closes", b"if pathname.e:\n        return opens, closes"),
]
try:
    for name, a, b in muts:
        src = good.replace(b"\r\n", b"\n")
        assert src.count(a) == 1, name
        f.write_bytes(src.replace(a, b))
        r = subprocess.run([sys.executable, "-m", "pytest", "tests/storm/test_rain_dss.py", "-q", "-p", "no:cacheprovider", "--no-header", "-x", "--co", "-q"], capture_output=True, text=True, encoding="utf-8", errors="replace") if False else None
        r = subprocess.run([sys.executable, "-m", "pytest", "tests/storm/test_rain_dss.py", "-q", "-p", "no:cacheprovider", "--no-header"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        failed = re.findall(r"FAILED tests/storm/test_rain_dss.py::(\S+)", r.stdout)
        tail = r.stdout.strip().splitlines()[-1][:70]
        print(f"{name:26} {tail}")
        for t in failed[:5]: print("      ", t[:90])
finally:
    f.write_bytes(good)
print("restored", f.read_bytes() == good)
