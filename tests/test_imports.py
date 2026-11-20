"""Smoke-import project modules (packages + root .py)."""
from __future__ import annotations

import importlib
import sys

import pytest

from tests._helpers import ROOT, missing_external

PACKAGES = (
    "core", "final_features", "crm_plus", "handlers", "repositories",
    "learning", "ux_final", "ai_assistant", "automation", "vk_adapter",
)

ROOT_EXCLUDE_SUFFIXES = ("_selftest", "_probe", "_test")
ROOT_EXCLUDE_NAMES = {"launch_readiness_check", "preflight_check", "bot"}

# Modules with side effects at import time -- not imported here.
SIDE_EFFECT_MODULES = {
    # calls initialize() at import: database.connect() creates/migrates tutor.db in project root
    "homework_attachments",
    # a script: ensure_test_db() writes the test DB to ../tutorbot_data, then prints
    "stage3_testdb_upgrade",
}


def _collect():
    mods = []
    for pkg in PACKAGES:
        base = ROOT / pkg
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(ROOT).with_suffix("")
            parts = list(rel.parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            mods.append(".".join(parts))
    for path in sorted(ROOT.glob("*.py")):
        name = path.stem
        if name in ROOT_EXCLUDE_NAMES or name.endswith(ROOT_EXCLUDE_SUFFIXES):
            continue
        mods.append(name)
    return sorted(set(mods))


ALL_MODULES = _collect()
MODULES = [m for m in ALL_MODULES if m not in SIDE_EFFECT_MODULES]


def test_side_effect_exclusions_exist():
    """Excluded modules must still exist, otherwise the list is stale."""
    stale = SIDE_EFFECT_MODULES - set(ALL_MODULES)
    assert not stale, f"stale exclusions: {sorted(stale)}"


@pytest.mark.parametrize("module", MODULES)
def test_import(module):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        importlib.import_module(module)
    except ModuleNotFoundError as exc:
        missing = missing_external(f"ModuleNotFoundError: No module named '{exc.name}'")
        if missing:
            pytest.skip(f"external package not installed: {missing}")
        raise
