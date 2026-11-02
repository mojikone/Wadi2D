"""The engine of this branch: the dock strips PYTHONPATH, and the venv's editable install points at the main checkout."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wadi2d.engine.cli import main  # noqa: E402

sys.exit(main())
