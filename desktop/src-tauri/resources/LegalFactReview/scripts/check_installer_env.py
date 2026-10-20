from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
PYTHON_RESOURCE = ROOT / "desktop" / "src-tauri" / "resources" / "python"

NPM_MISSING_MESSAGE = "未找到 npm。请安装 Node.js 18+ LTS，并确认 npm 在 PATH 中。"
CARGO_MISSING_MESSAGE = "未找到 cargo。请安装 Rust stable，并确认 cargo 在 PATH 中。"
NODE_MISSING_MESSAGE = "未找到 node。请安装 Node.js 18+ LTS，并确认 node 在 PATH 中。"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str


def check_installer_env(embedded_python: bool = False) -> list[CheckResult]:
    results = [
        _check_windows(),
        _check_command("node", ["node", "--version"], NODE_MISSING_MESSAGE),
        _check_command("npm", [_npm_command_or_default(), "--version"], NPM_MISSING_MESSAGE),
        _check_command("cargo", ["cargo", "--version"], CARGO_MISSING_MESSAGE),
        _check_python_version(),
        _check_tauri_cli(),
    ]
    if embedded_python:
        results.extend(_check_embedded_python())
    return results


def ensure_installer_env(embedded_python: bool = False) -> None:
    results = check_installer_env(embedded_python=embedded_python)
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


def _check_python_version() -> CheckResult:
    version = sys.version_info[:3]
    label = ".".join(map(str, version))
    if (3, 10) <= version[:2] < (3, 13):
        suffix = "，推荐 Python 3.12。" if version[:2] != (3, 12) else "。"
        return CheckResult("Python", True, f"Python {label}{suffix}")
    return CheckResult("Python", False, f"当前 Python {label} 不受支持。请使用 Python 3.10-3.12，推荐 Python 3.12。")


def _check_tauri_cli() -> CheckResult:
    npm = _npm_command()
    if not npm:
        return CheckResult("Tauri CLI", False, NPM_MISSING_MESSAGE)
    completed = subprocess.run(
        [npm, "run", "tauri", "--", "--version"],
        cwd=ROOT / "desktop",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = (completed.stdout or completed.stderr).strip()
    if completed.returncode == 0:
        return CheckResult("Tauri CLI", True, output)
    package_json = ROOT / "desktop" / "node_modules" / "@tauri-apps" / "cli" / "package.json"
    if package_json.exists():
        return CheckResult("Tauri CLI", True, "检测到 @tauri-apps/cli。")
    return CheckResult("Tauri CLI", False, output or "未检测到 Tauri CLI。请先在 desktop/ 下运行 npm install。")


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Windows installer build environment.")
    parser.add_argument("--embedded-python", action="store_true", help="Also check desktop/src-tauri/resources/python")
    args = parser.parse_args()
    ensure_installer_env(embedded_python=args.embedded_python)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
