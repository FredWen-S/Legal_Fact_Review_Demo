from __future__ import annotations

import subprocess
import sys
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.python_selector import find_supported_python


@dataclass(frozen=True)
class Stage:
    name: str
    command: list[str]


def main() -> int:
    python = find_supported_python()
    print(f"Using Python: {python.display_command}")
    print(f"Python version: {python.version}")
    print(f"Python executable: {python.executable}")

    tmp_root = ROOT / "tmp"
    tmp_root.mkdir(exist_ok=True)
    pytest_temp = tmp_root / "pytest-verify"
    if pytest_temp.exists():
        shutil.rmtree(pytest_temp)
    stages = [
        Stage("pytest", [*python.command, "-m", "pytest", "tests", "-q", "--basetemp", str(pytest_temp), "-p", "no:cacheprovider"]),
        Stage("acceptance_check", [*python.command, str(ROOT / "scripts" / "acceptance_check.py")]),
        Stage("build_desktop_release", [*python.command, str(ROOT / "scripts" / "build_desktop_release.py")]),
    ]

    for stage in stages:
        print(f"[RUN] {stage.name}: {' '.join(stage.command)}")
        completed = subprocess.run(stage.command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            print(f"[FAIL] {stage.name}: exit code {completed.returncode}")
            return completed.returncode
        print(f"[OK] {stage.name}")

    print("Release verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
