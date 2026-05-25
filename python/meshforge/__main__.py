"""Entry point so `python -m meshforge ...` dispatches to the CLI."""

import sys

from meshforge.cli import main

sys.exit(main())
