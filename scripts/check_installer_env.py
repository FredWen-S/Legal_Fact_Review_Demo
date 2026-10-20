from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.python_selector import PythonCandidate

PYTHON_RESOURCE = ROOT / "desktop" / "src-tauri" / "resources" / "python"

NPM_MISSING_MESSAGE = "未找到 npm。请安装 Node.js 18+ LTS，并确认 npm 在 PATH 中。"
CARGO_MISSING_MESSAGE = "未找到 cargo。请安装 Rust stable，并确认 cargo 在 PATH 中。"
NODE_MISSING_MESSAGE = "未找到 node。请安装 Node.js 18+ LTS，并确认 node 在 PATH 中。"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str


def check_installer_env(
    embedded_python: bool = False,
    check_tauri: bool = True,
    python_candidate: PythonCandidate | None = None,
) -> list[CheckResult]:
    results = [
        _check_windows(),
        _check_command("node", ["node", "--version"], NODE_MISSING_MESSAGE),
        _check_command("npm", [_npm_command_or_default(), "--version"], NPM_MISSING_MESSAGE),
        _check_command("cargo", ["cargo", "--version"], CARGO_MISSING_MESSAGE),
        _check_python_version(python_candidate),
    ]
    if check_tauri:
        results.append(_check_tauri_cli())
    if embedded_python:
        results.extend(_check_embedded_python())
    return results


def ensure_installer_env(
    embedded_python: bool = False,
    check_tauri: bool = True,
    python_candidate: PythonCandidate | None = None,
) -> None:
    results = check_installer_env(
        embedded_python=embedded_python,
        check_tauri=check_tauri,
        python_candidate=python_candidate,
    )
    for result in results:
        prefix = "[OK]" if result.ok else "[FAIL]"
        print(f"{prefix} {result.name}: {result.message}")
    failures = [result.message for result in results if not result.ok]
    if failures:
        raise SystemExit("\n".join(failures))


def _check_windows() -> CheckResult:
    if platform.system().lower() == "windows":
        return CheckResult("Windows", True, platform.platform())
    return CheckResult("Windows", False, "Windows installer 构建必须在 Windows 环境中运行。")


def _check_command(name: str, command: Sequence[str], missing_message: str) -> CheckResult:
    executable = shutil.which(command[0])
    if not executable:
        return CheckResult(name, False, missing_message)
    completed = subprocess.run(
        [executable, *command[1:]],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0:
        return CheckResult(name, False, output or f"{name} 检查失败。")
    return CheckResult(name, True, output or executable)


def _check_python_version(candidate: PythonCandidate | None = None) -> CheckResult:
    if candidate is not None:
        version = candidate.major_minor
        label = candidate.version
        source = f"Selected Python {label} ({candidate.display_command})"
    else:
        version = sys.version_info[:2]
        label = ".".join(map(str, sys.version_info[:3]))
        source = f"Python {label}"
    if (3, 10) <= version < (3, 13):
        suffix = "，推荐 Python 3.12。" if version != (3, 12) else "。"
        return CheckResult("Python", True, f"{source}{suffix}")
    return CheckResult("Python", False, f"{source} 不受支持。请使用 Python 3.10-3.12，推荐 Python 3.12。")


def _check_tauri_cli() -> CheckResult:
    diagnostics: list[str] = []

    local_tauri = _local_tauri_command()
    if local_tauri.exists():
        completed = _run_probe([str(local_tauri), "--version"], cwd=ROOT / "desktop")
        if completed.returncode == 0 and _looks_like_tauri_version(completed.stdout + completed.stderr):
            return CheckResult("Tauri CLI", True, _first_output_line(completed.stdout, completed.stderr))
        diagnostics.append(_format_probe_failure([str(local_tauri), "--version"], completed))

    npm = _npm_command()
    if npm:
        command = [npm, "run", "tauri", "--", "--version"]
        completed = _run_probe(command, cwd=ROOT / "desktop")
        if completed.returncode == 0 and _looks_like_tauri_version(completed.stdout + completed.stderr):
            return CheckResult("Tauri CLI", True, _first_output_line(completed.stdout, completed.stderr))
        diagnostics.append(_format_probe_failure(command, completed))
    else:
        diagnostics.append(NPM_MISSING_MESSAGE)

    npx = _npx_command()
    if npx:
        command = [npx, "tauri", "--version"]
        completed = _run_probe(command, cwd=ROOT / "desktop")
        if completed.returncode == 0 and _looks_like_tauri_version(completed.stdout + completed.stderr):
            return CheckResult("Tauri CLI", True, _first_output_line(completed.stdout, completed.stderr))
        diagnostics.append(_format_probe_failure(command, completed))

    detail = "\n\n".join(diagnostics).strip()
    return CheckResult("Tauri CLI", False, detail or "未检测到 Tauri CLI。请先在 desktop/ 下运行 npm install。")


def _local_tauri_command() -> Path:
    binary = "tauri.cmd" if os.name == "nt" else "tauri"
    return ROOT / "desktop" / "node_modules" / ".bin" / binary


def _run_probe(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(list(command), 127, "", str(exc))


def _looks_like_tauri_version(output: str) -> bool:
    normalized = output.lower()
    return "tauri-cli" in normalized or "tauri" in normalized or re.search(r"\b\d+\.\d+\.\d+\b", normalized) is not None


def _first_output_line(stdout: str, stderr: str) -> str:
    for text in [stdout, stderr]:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
    return "Tauri CLI 可用。"


def _format_probe_failure(command: Sequence[str], completed: subprocess.CompletedProcess[str]) -> str:
    stdout = completed.stdout.strip() if completed.stdout else ""
    stderr = completed.stderr.strip() if completed.stderr else ""
    return (
        f"command: {' '.join(command)}\n"
        f"exit code: {completed.returncode}\n"
        f"stdout:\n{stdout}\n"
        f"stderr:\n{stderr}"
    )


def _check_embedded_python() -> list[CheckResult]:
    python_exe = PYTHON_RESOURCE / "python.exe"
    pth = PYTHON_RESOURCE / "python312._pth"
    if not python_exe.exists():
        return [CheckResult("Embedded Python", False, f"内置 Python 不存在：{python_exe}")]
    results = [
        CheckResult("Embedded Python", True, str(python_exe)),
        CheckResult("Embedded python312._pth", pth.exists(), str(pth) if pth.exists() else f"缺少 {pth}"),
    ]
    completed = subprocess.run(
        [str(python_exe), "-c", "import sys; print(sys.version); import pip; print('pip ok')"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode == 0:
        results.append(CheckResult("Embedded pip", True, completed.stdout.strip()))
    else:
        results.append(
            CheckResult(
                "Embedded pip",
                False,
                (completed.stderr or completed.stdout).strip()
                or "内置 Python 无法 import pip；Python embeddable zip 需要先启用 site-packages/pip。",
            )
        )
    return results


def _npm_command_or_default() -> str:
    return _npm_command() or ("npm.cmd" if os.name == "nt" else "npm")


def _npm_command() -> str | None:
    candidates = ["npm.cmd", "npm"] if os.name == "nt" else ["npm"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _npx_command() -> str | None:
    candidates = ["npx.cmd", "npx"] if os.name == "nt" else ["npx"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Windows installer build environment.")
    parser.add_argument("--embedded-python", action="store_true", help="Also check desktop/src-tauri/resources/python")
    parser.add_argument("--skip-tauri", action="store_true", help="Skip Tauri CLI check")
    args = parser.parse_args()
    ensure_installer_env(embedded_python=args.embedded_python, check_tauri=not args.skip_tauri)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
