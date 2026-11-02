"""Query the running Everything through its IPC window; prints full paths, one per line."""
import ctypes as C, ctypes.wintypes as W, struct, sys
u = C.windll.user32; k = C.windll.kernel32
u.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]; u.DefWindowProcW.restype = C.c_ssize_t
u.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]; u.SendMessageW.restype = C.c_ssize_t
k.GetModuleHandleW.restype = W.HMODULE
class CDS(C.Structure):
    _fields_ = [("dwData", C.c_size_t), ("cbData", W.DWORD), ("lpData", C.c_void_p)]
WNDPROC = C.WINFUNCTYPE(C.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
out = []
done = [False]
def proc(h, m, w, l):
    if m == 0x004A:
        cds = C.cast(l, C.POINTER(CDS)).contents
        raw = C.string_at(cds.lpData, cds.cbData)
        hdr = struct.unpack("<7I", raw[:28])
        n = hdr[5]
        for i in range(n):
            flags, fo, po = struct.unpack("<3I", raw[28 + i*12: 40 + i*12])
            def s(o):
                e = o
                while raw[e:e+2] != b"\0\0": e += 2
                return raw[o:e].decode("utf-16le")
            out.append(s(po) + "\\" + s(fo))
        done[0] = True
        return 1
    return u.DefWindowProcW(h, m, w, l)
cb = WNDPROC(proc)
class WC(C.Structure):
    _fields_ = [("style", W.UINT), ("proc", WNDPROC), ("ce", C.c_int), ("we", C.c_int), ("inst", W.HINSTANCE), ("icon", W.HICON), ("cur", W.HANDLE), ("bg", W.HBRUSH), ("menu", W.LPCWSTR), ("name", W.LPCWSTR)]
wc = WC(); wc.proc = cb; wc.inst = k.GetModuleHandleW(None); wc.name = "wadi2d_ev_reply"
u.RegisterClassW(C.byref(wc))
u.CreateWindowExW.restype = W.HWND
u.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
hw = u.CreateWindowExW(0, "wadi2d_ev_reply", "r", 0, 0, 0, 0, 0, None, None, wc.inst, None)
u.FindWindowW.restype = W.HWND
ev = u.FindWindowW("EVERYTHING_TASKBAR_NOTIFICATION", None)
print("everything window", bool(ev), file=sys.stderr)
q = sys.argv[1].encode("utf-16le") + b"\0\0"
body = struct.pack("<5I", int(hw), 0x004A + 0x400, 0, 0, 0xFFFFFFFF) + q
# reply_copydata_message is the dwData of the reply, not the window message
buf = C.create_string_buffer(body)
cds = CDS(2, len(body), C.cast(buf, C.c_void_p))
u.SendMessageW(ev, 0x004A, hw, C.addressof(cds))
msg = W.MSG()
for _ in range(2000):
    while u.PeekMessageW(C.byref(msg), None, 0, 0, 1):
        u.TranslateMessage(C.byref(msg)); u.DispatchMessageW(C.byref(msg))
    if done[0]: break
    k.Sleep(5)
print("\n".join(out))
