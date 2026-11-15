"""Put a chunk store out of the system's file cache, to time a read as a first start after a reboot finds it.

Args: store_folder(dem_*). Windows only: a file opened without buffering and closed again has its cached pages
dropped, when nobody else holds it open. Nothing in the file changes.
"""

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

GENERIC_READ, SHARE_ALL, OPEN_EXISTING, NO_BUFFERING = 0x80000000, 0x7, 3, 0x20000000
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]  # fmt: skip
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
INVALID = wintypes.HANDLE(-1).value

t0 = time.perf_counter()
done = failed = 0
for path in Path(sys.argv[1]).glob("r*.npy"):
    handle = kernel32.CreateFileW(str(path), GENERIC_READ, SHARE_ALL, None, OPEN_EXISTING, NO_BUFFERING, None)
    if handle == INVALID or handle is None:
        failed += 1
        continue
    kernel32.CloseHandle(handle)
    done += 1
print(
    f"{done} chunk files put out of the file cache, {failed} could not be opened, {time.perf_counter() - t0:.1f} s"
)
