import re, sys
pat = re.compile(sys.argv[2], re.I) if len(sys.argv) > 2 else None
data = open(sys.argv[1], "rb").read()
for m in re.finditer(rb"[\x20-\x7e]{4,}", data):
    s = m.group().decode()
    if pat is None or pat.search(s):
        print(s)
