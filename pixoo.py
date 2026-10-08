#!/usr/bin/env python3
"""Standalone entry point for pixoo-cli — run it without ``pip install``-ing
the package.

Run it directly (``./pixoo.py text "Hi"``) or symlink it onto your PATH
(``ln -s "$PWD/pixoo.py" ~/.local/bin/pixoo``). Only the dependencies in
``requirements.txt`` need to be installed for the Python that runs it.
"""

import os
import sys

# Resolve symlinks so the pixoo_cli package next to the real file is found.
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

try:
    from pixoo_cli.cli import main
except ImportError as exc:
    sys.exit(
        f"pixoo: missing dependency ({exc.name}).\n"
        f"Install them with: {sys.executable} -m pip install -r "
        f"{os.path.join(os.path.dirname(os.path.realpath(__file__)), 'requirements.txt')}"
    )

if __name__ == "__main__":
    main()
