from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


SUPPORTED_MIN = (3, 10)
SUPPORTED_MAX = (3, 13)
PREFERRED_VERSIONS = ("3.12", "3.11", "3.10")
NO_SUPPORTED_PYTHON_MESSAGE = "未找到受支持的 Python 版本。请安装 Python 3.10-3.12，推荐 Python 3.12。"


@dataclass(frozen=True)
class PythonCandidate:
    command: tuple[str, ...]
    version: str
    executable: str

    @property
    def display_command(self) -> str:
        return " ".join(self.command)

    @property
    def major_minor(self) -> tuple[int, int]:
        parts = self.version.split(".")
        return int(parts[0]), int(parts[1])


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def is_supported_version(version: str | Sequence[int]) -> bool:
    major_minor = _major_minor(version)
    return SUPPORTED_MIN <= major_minor < SUPPORTED_MAX


def find_supported_python(runner: Runner | None = None, include_current: bool = True) -> PythonCandidate:
    runner = runner or _run_probe
    errors: list[str] = []
    current = PythonCandidate((sys.executable,), ".".join(map(str, sys.version_info[:3])), sys.executable)
    commands: list[tuple[str, ...]] = []
    for version in PREFERRED_VERSIONS:
        commands.append(("py", f"-{version}"))
        if include_current and current.version.startswith(f"{version}."):
            commands.append(current.command)
    commands.append(("python",))

    seen: set[tuple[str, ...]] = set()
    for command in commands:
        if command in seen:
            continue
        seen.add(command)
        candidate = current if include_current and command == current.command else probe_python(command, runner)
        if candidate is None:
            errors.append(f"{' '.join(command)} 不可用")
            continue
        if is_supported_version(candidate.version):
            return candidate
        errors.append(f"{candidate.display_command} 是 Python {candidate.version}，不受支持")

    detail = "；".join(errors)
    if detail:
        raise SystemExit(f"{NO_SUPPORTED_PYTHON_MESSAGE}\n检测结果：{detail}")
    raise SystemExit(NO_SUPPORTED_PYTHON_MESSAGE)


def ensure_running_on_supported_python() -> None:
    if not is_supported_version(sys.version_info):
        raise SystemExit(
            f"当前解释器是 Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}，不受支持。\n"
            f"{NO_SUPPORTED_PYTHON_MESSAGE}"
        )


def reexec_with_supported_python_if_needed(script_path: str | Path, argv: Sequence[str]) -> None:
    if is_supported_version(sys.version_info):
        return
    candidate = find_supported_python()
    current = Path(sys.executable).resolve()
    selected = Path(candidate.executable).resolve()
    if current == selected:
        return
    completed = subprocess.run([*candidate.command, str(script_path), *argv], check=False)
    raise SystemExit(completed.returncode)


def probe_python(command: Sequence[str], runner: Runner | None = None) -> PythonCandidate | None:
    runner = runner or _run_probe
    probe_code = (
        "import json, sys; "
        "print(json.dumps({'version': '.'.join(map(str, sys.version_info[:3])), 'executable': sys.executable}))"
    )
    try:
        completed = runner([*command, "-c", probe_code])
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError, KeyError):
        return None
    return PythonCandidate(tuple(command), str(payload["version"]), str(payload.get("executable") or ""))


def _run_probe(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    env = None
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, env=env)


def _major_minor(version: str | Sequence[int]) -> tuple[int, int]:
    if isinstance(version, str):
        parts = version.split(".")
        return int(parts[0]), int(parts[1])
    return int(version[0]), int(version[1])


def main() -> int:
    candidate = find_supported_python()
    print(f"Using Python: {candidate.display_command}")
    print(f"Python version: {candidate.version}")
    print(f"Python executable: {candidate.executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
