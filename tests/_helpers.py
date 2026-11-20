"""Shared helpers for the smoke test suite."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Top-level names of third-party packages that may be absent in CI/dev envs.
EXTERNAL_PACKAGES = ("telegram", "google", "googleapiclient")

_MISSING_RE = re.compile(r"ModuleNotFoundError: No module named '([\w.]+)'")


def missing_external(text: str) -> str | None:
    """Return the missing external module name if *text* reports one, else None."""
    for name in _MISSING_RE.findall(text or ""):
        if name.split(".")[0] in EXTERNAL_PACKAGES:
            return name
    return None
