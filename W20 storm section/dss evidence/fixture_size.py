import sys, zlib, lzma, base64
for f in sys.argv[1:]:
    b = open(f, "rb").read()
    z = zlib.compress(b, 9); x = lzma.compress(b, preset=9)
    print(f[-14:], len(b), "zlib", len(z), "b64", len(base64.b85encode(z)), "lzma", len(x), "b64", len(base64.b64encode(x)))
