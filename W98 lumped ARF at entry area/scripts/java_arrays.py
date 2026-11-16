"""Read the double arrays a Java class builds in its methods: the constant pool and a small bytecode walk (W98).

Used on HEC-HMS 4.12's ``hms.jar`` to read the NRCS 24-hour distributions its SCS Storm uses; nothing is run, the
class file is only read. ``main(jar, member)`` prints each array of more than 20 doubles."""
import struct
import sys
import zipfile


def pool(b):
    n = struct.unpack(">H", b[8:10])[0]
    cp = [None] * n
    i, k = 10, 1
    while k < n:
        tag = b[i]
        if tag == 1:
            ln = struct.unpack(">H", b[i + 1:i + 3])[0]
            cp[k] = ("utf8", b[i + 3:i + 3 + ln].decode("utf-8", "replace"))
            i += 3 + ln
        elif tag in (3, 4):
            cp[k] = ("int" if tag == 3 else "float", struct.unpack(">i" if tag == 3 else ">f", b[i + 1:i + 5])[0])
            i += 5
        elif tag in (5, 6):
            cp[k] = ("long" if tag == 5 else "double", struct.unpack(">q" if tag == 5 else ">d", b[i + 1:i + 9])[0])
            i += 9
            k += 1
        elif tag in (7, 8, 16, 19, 20):
            cp[k] = ("ref", tag, struct.unpack(">H", b[i + 1:i + 3])[0])
            i += 3
        elif tag in (9, 10, 11, 12, 17, 18):
            cp[k] = ("pair", tag, *struct.unpack(">HH", b[i + 1:i + 5]))
            i += 5
        elif tag == 15:
            cp[k] = ("mh",)
            i += 4
        else:
            raise ValueError(f"tag {tag} at {i}")
        k += 1
    return cp, i


def name_of(cp, idx):
    e = cp[idx]
    if e[0] == "utf8":
        return e[1]
    if e[0] == "ref":
        return name_of(cp, e[2])
    if e[0] == "pair":
        if e[1] == 12:
            return name_of(cp, e[2])
        return name_of(cp, e[2]) + "." + name_of(cp, e[3])
    return str(e)


def methods(b, cp, i):
    i += 6  # access, this, super
    ni = struct.unpack(">H", b[i:i + 2])[0]
    i += 2 + 2 * ni

    def members(i):
        n = struct.unpack(">H", b[i:i + 2])[0]
        i += 2
        out = []
        for _ in range(n):
            _acc, nm, _desc, na = struct.unpack(">HHHH", b[i:i + 8])
            i += 8
            attrs = []
            for _ in range(na):
                an, ln = struct.unpack(">HI", b[i:i + 6])
                attrs.append((cp[an][1], b[i + 6:i + 6 + ln]))
                i += 6 + ln
            out.append((cp[nm][1], attrs))
        return out, i

    _fields, i = members(i)
    ms, i = members(i)
    return ms


def arrays(code, cp):
    """Walk the bytecode; each `newarray double` collects the dastore constants that follow until the array is
    stored (putstatic / putfield / aastore / astore)."""
    ln = struct.unpack(">I", code[4:8])[0]
    bc = code[8:8 + ln]
    i = 0
    stack = []
    found = []
    current = None
    last_int = None
    while i < len(bc):
        op = bc[i]
        if op in range(0x02, 0x09):  # iconst
            last_int = op - 3
            stack.append(last_int)
            i += 1
        elif op == 0x10:
            last_int = struct.unpack(">b", bc[i + 1:i + 2])[0]
            stack.append(last_int)
            i += 2
        elif op == 0x11:
            last_int = struct.unpack(">h", bc[i + 1:i + 3])[0]
            stack.append(last_int)
            i += 3
        elif op in (0x0E, 0x0F):  # dconst
            stack.append(float(op - 0x0E))
            i += 1
        elif op == 0x14:  # ldc2_w
            idx = struct.unpack(">H", bc[i + 1:i + 3])[0]
            stack.append(cp[idx][1])
            i += 3
        elif op in (0x12,):
            i += 2
        elif op == 0x13:
            i += 3
        elif op == 0xBC:  # newarray
            if bc[i + 1] == 7:
                current = {"size": last_int, "values": {}}
                found.append(current)
            i += 2
        elif op == 0x52:  # dastore
            if current is not None and len(stack) >= 2:
                value, index = stack[-1], stack[-2]
                current["values"][index] = value
            stack.clear()
            i += 1
        elif op in (0xB3, 0xB5):  # putstatic / putfield
            idx = struct.unpack(">H", bc[i + 1:i + 3])[0]
            if current is not None and "field" not in current:
                current["field"] = name_of(cp, idx)
            current = None
            i += 3
        elif op == 0x59:  # dup
            i += 1
        elif op in (0xB2, 0xB4, 0xB6, 0xB7, 0xB8, 0xBB, 0xBD, 0xC0, 0xC1):
            i += 3
        elif op == 0xB9 or op == 0xBA:
            i += 5
        elif op in (0x15, 0x16, 0x17, 0x18, 0x19, 0x36, 0x37, 0x38, 0x39, 0x3A, 0xA9):
            i += 2
        elif op == 0x84 or 0x99 <= op <= 0xA8 or op in (0xC6, 0xC7):
            i += 3
        elif op in (0xC8, 0xC9):
            i += 5
        elif op == 0xC4:
            raise ValueError("wide")
        elif op in (0xAA, 0xAB):
            j = i + 1 + ((4 - (i + 1) % 4) % 4)
            if op == 0xAA:
                low, high = struct.unpack(">ii", bc[j + 4:j + 12])
                i = j + 12 + 4 * (high - low + 1)
            else:
                npairs = struct.unpack(">i", bc[j + 4:j + 8])[0]
                i = j + 8 + 8 * npairs
        else:
            i += 1
    return found


def main(jar, member):
    b = zipfile.ZipFile(jar).read(member)
    cp, i = pool(b)
    for name, attrs in methods(b, cp, i):
        for an, data in attrs:
            if an != "Code":
                continue
            for a in arrays(data, cp):
                vals = [a["values"].get(k, 0.0) for k in range(a["size"] or 0)]
                if a["size"] and a["size"] > 20:
                    print(name, a.get("field"), a["size"], " ".join(f"{v:.4g}" for v in vals[:8]), "...", " ".join(f"{v:.4g}" for v in vals[-4:]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
