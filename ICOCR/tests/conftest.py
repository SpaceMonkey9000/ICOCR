"""Shared test setup.

Makes the application modules importable when tests run from tests/, and
points rule loading at the bundled factory rules before any application module
is imported. Several tests used to set ICOCR_RULES_DIR themselves; when the
files ran in one session, whichever imported the rule modules first decided
which rules everyone got.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('ICOCR_RULES_DIR', str(ROOT / 'factory' / 'rules'))
