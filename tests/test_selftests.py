"""Run every *_selftest.py from the project root as a subprocess; expect exit 0."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tests._helpers import ROOT, missing_external

SELFTESTS = sorted(p.name for p in ROOT.glob("*_selftest.py"))

# Several selftests (crm_plus, final_freeze, messenger_ux, minute_model, ux_final)
# write database.DB_NAME = <root>/tutor.db directly; remove it afterwards if it
# did not exist before the run, so results stay order-independent.
_ROOT_DB_FILES = [ROOT / n for n in ("tutor.db", "tutor.db-wal", "tutor.db-shm", "tutor.db-journal")]


@pytest.fixture(autouse=True)
def _cleanup_root_db():
    existed = {p for p in _ROOT_DB_FILES if p.exists()}
    yield
    for p in _ROOT_DB_FILES:
        if p not in existed and p.exists():
            p.unlink()


@pytest.mark.parametrize("script", SELFTESTS)
def test_selftest(script, tmp_path):
    env = os.environ.copy()
    # Keep test-DB writes inside pytest's tmp dir instead of ../tutorbot_data.
    env["TUTORBOT_TEST_DATA_DIR"] = str(tmp_path / "testdata")
    env["TUTORBOT_TEST_DB"] = str(tmp_path / "testdata" / "tutor_test.db")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, script],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"{script}: timeout after 120s")
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        missing = missing_external(output)
        if missing:
            pytest.skip(f"external package not installed: {missing}")
    assert proc.returncode == 0, f"{script} exited {proc.returncode}\n{output[-3000:]}"
