import sys, zipfile, re
pat = re.compile(rb"(get|set)?[xXyY]CoordOfGridCellZero|CoordOfGridCellZero")
for jar in sys.argv[1:]:
    try:
        z = zipfile.ZipFile(jar)
    except Exception as e:
        continue
    hits = []
    for n in z.namelist():
        if n.endswith(".class"):
            b = z.read(n)
            if pat.search(b):
                names = sorted(set(m.group().decode() for m in pat.finditer(b)))
                hits.append((n, names))
    if hits:
        print("==", jar.split("/")[-1])
        for n, names in hits: print("  ", n, names)
