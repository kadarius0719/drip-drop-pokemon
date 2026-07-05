#!/usr/bin/env python3
"""Convenience entrypoint so you can run the tool without installing it.

    python run.py init
    python run.py status
    python run.py check
    python run.py watch
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from pokedrop.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
