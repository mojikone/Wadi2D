"""W87: compile ``poly.cu`` with NVRTC on the host, no device context and nothing on the GPU, to prove the CUDA twin
of the speed of record is valid source while the card is busy with another job. It proves syntax and types, not numbers.

    .venv\\Scripts\\python "W87 strip max speed\\compile_poly.py"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cupy.cuda import compiler

from wadi2d.solver.gpu.backend import KERNELS, header

if __name__ == "__main__":
    source = (
        header()
        + (KERNELS / "common.cuh").read_text(encoding="utf-8")
        + "\n"
        + (KERNELS / "poly.cu").read_text(encoding="utf-8")
    )
    ptx = compiler.compile_using_nvrtc(source, options=("-std=c++17", "--use_fast_math"))
    text = ptx[0] if isinstance(ptx, tuple) else ptx
    text = text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text)
    wanted = ("poly_cell_maxima", "poly_cell_speed", "poly_faces", "poly_sums", "poly_edges")
    print(
        "compiled:",
        len(text),
        "characters of PTX;",
        {name: (f".entry {name}" in text or name in text) for name in wanted},
    )
