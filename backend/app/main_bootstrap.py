"""Project path and optional venv re-exec when running this file as __main__."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_early_setup(entry_file: Path, *, is_main: bool) -> None:
    """Ensure repo root on sys.path; optionally re-exec under .venv when launched as a script."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    if not is_main:
        return
    target = _venv_python()
    if not target.exists():
        return
    current = Path(sys.executable).resolve()
    if current != target.resolve():
        env = os.environ.copy()
        env["PYTHONNOUSERSITE"] = "1"
        result = subprocess.run(
            [str(target), str(entry_file.resolve())],
            cwd=str(PROJECT_ROOT),
            env=env,
            check=False,
        )
        if result.returncode == 0:
            raise SystemExit(0)
        print(
            (
                f"[main] Warning: failed to switch to venv interpreter '{target}' "
                f"(exit code {result.returncode}). Continuing with '{current}'. "
                "Rebuild .venv if needed."
            ),
            file=sys.stderr,
        )


def _venv_python() -> Path:
    if os.name == "nt":
        return PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    return PROJECT_ROOT / ".venv" / "bin" / "python"
