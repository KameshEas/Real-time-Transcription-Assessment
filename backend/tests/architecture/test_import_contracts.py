"""Fails the build when a Clean Architecture layer rule is broken."""

import shutil
import subprocess
from pathlib import Path


def test_import_linter_contracts_hold():
    exe = shutil.which("lint-imports")
    assert exe, "import-linter not installed"
    result = subprocess.run([exe], cwd=Path(__file__).parents[2], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
