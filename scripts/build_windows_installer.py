from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_embedded_python import build_app_resource, build_embedded_python
from scripts.check_installer_env import ensure_installer_env
from scripts.python_selector import PythonCandidate, find_supported_python, is_supported_version


VERSION = "0.6.0-rc1"
DIST_DIR = ROOT / "dist" / "LegalFactReview_v0.6.0-rc1_windows_installer"
FORBIDDEN_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", "target", "tmp", "dist"}
FORBIDDEN_NAMES = {"review_runs.sqlite"}


def build_windows_installer(
    python_zip: str | Path | None = None,
    python_dir: str | Path | None = None,
    skip_tests: bool = False,
    skip_npm_install: bool = False,
    no_embedded_python: bool = False,
) -> Path:
    test_python = select_test_python()
    print(f"Using test Python: {test_python.display_command}")
    print(f"Test Python version: {test_python.version}")
    ensure_installer_env(embedded_python=False, check_tauri=False, python_candidate=test_python)
    if skip_tests:
        print("WARNING: 已跳过自动测试，请确保已手动运行 pytest/acceptance_check/verify_release。")
    else:
        _run_tests(test_python)

    if no_embedded_python:
        build_app_resource()
        print("Embedded Python disabled; installer will require system Python 3.10-3.12.")
    else:
        _validate_runtime_source(python_zip=python_zip, python_dir=python_dir)
        build_embedded_python(python_zip=python_zip, python_dir=python_dir)
        print("Embedded Python enabled.")

    _clean_old_bundle_outputs()
    if not skip_npm_install:
        _run([_npm_command(), "install"], cwd=ROOT / "desktop")
    ensure_installer_env(embedded_python=False, check_tauri=True, python_candidate=test_python)
    _run([_npm_command(), "run", "tauri:build"], cwd=ROOT / "desktop")

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    copied = _collect_installers(DIST_DIR)
    if not copied:
        raise SystemExit("未找到 Tauri installer 产物。")
    _write_sha256(DIST_DIR, copied)
    _audit_resources()
    print(f"Installer package generated: {DIST_DIR}")
    return DIST_DIR


def select_test_python(
    fallback_selector: Callable[[], PythonCandidate] | None = None,
) -> PythonCandidate:
    """Prefer the current interpreter for build-time tests when it is supported.

    Runtime Python discovery is still handled by desktop_service.py/python_selector.py.
    The installer test stage should use the interpreter that launched this script
    when it is Python 3.10-3.12, because that environment is the one most likely
    to have the project's test dependencies installed.
    """
    version = tuple(sys.version_info[:3])
    if is_supported_version(version):
        return PythonCandidate((sys.executable,), ".".join(map(str, version)), sys.executable)
    selector = fallback_selector or find_supported_python
    return selector()


def _run_tests(python: PythonCandidate) -> None:
    _ensure_pytest_available(python)
    _run([*python.command, "-m", "pytest", "tests", "-q", "--ignore=tmp"])


def _ensure_pytest_available(python: PythonCandidate) -> None:
    completed = subprocess.run(
        [*python.command, "-m", "pytest", "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode == 0:
        return
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    details = []
    if stdout:
        details.append(f"stdout:\n{stdout}")
    if stderr:
        details.append(f"stderr:\n{stderr}")
    suffix = "\n" + "\n".join(details) if details else ""
    raise SystemExit(
        f"当前 Python 缺少 pytest。请先运行：{python.display_command} -m pip install -r requirements.txt 或使用 --skip-tests。"
        f"{suffix}"
    )


def _run(command: list[str], cwd: Path = ROOT) -> None:
    print(f"[RUN] {' '.join(command)}")
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"命令失败：{' '.join(command)}")


def _npm_command() -> str:
    candidates = ["npm.cmd", "npm"] if os.name == "nt" else ["npm"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise SystemExit("未找到 npm。请先安装 Node.js 18+ LTS，并确认 npm 在 PATH 中。")


def _validate_runtime_source(python_zip: str | Path | None, python_dir: str | Path | None) -> None:
    if python_zip and not Path(python_zip).exists():
        raise SystemExit(f"Python embed zip 不存在：{python_zip}")
    if python_dir and not Path(python_dir).exists():
        raise SystemExit(f"Python runtime 目录不存在：{python_dir}")
    if not python_zip and not python_dir:
        raise SystemExit(
            "未提供 Python runtime。请使用 --python-zip/--python-dir，或使用 --no-embedded-python 构建不内置 Python 的 installer。"
        )


def _clean_old_bundle_outputs() -> None:
    bundle_root = ROOT / "desktop" / "src-tauri" / "target" / "release" / "bundle"
    for dirname in ["nsis", "msi"]:
        target = bundle_root / dirname
        if target.exists():
            shutil.rmtree(target)


def _collect_installers(dist_dir: Path) -> list[Path]:
    bundle_root = ROOT / "desktop" / "src-tauri" / "target" / "release" / "bundle"
    copied: list[Path] = []
    for pattern in ["nsis/*.exe", "msi/*.msi"]:
        for source in bundle_root.glob(pattern):
            suffix = source.suffix.lower()
            if suffix in {".exe", ".msi"}:
                target = dist_dir / _installer_filename(suffix)
            else:
                target = dist_dir / source.name
            shutil.copy2(source, target)
            copied.append(target)
    return copied


def _installer_filename(suffix: str) -> str:
    mode = "embedded_python" if (ROOT / "desktop" / "src-tauri" / "resources" / "python" / "python.exe").exists() else "no_python"
    return f"LegalFactReview_v{VERSION}_windows_installer_{mode}{suffix}"


def _write_sha256(dist_dir: Path, files: list[Path]) -> Path:
    sha_path = dist_dir / f"LegalFactReview_v{VERSION}_windows_installer.sha256.txt"
    lines = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    sha_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"SHA256 generated: {sha_path}")
    return sha_path


def _audit_resources() -> None:
    resources = ROOT / "desktop" / "src-tauri" / "resources"
    bad: list[Path] = []
    if not resources.exists():
        return
    for path in resources.rglob("*"):
        relative = path.relative_to(resources)
        parts = set(relative.parts)
        if parts & FORBIDDEN_PARTS or path.name in FORBIDDEN_NAMES:
            bad.append(relative)
    if bad:
        joined = ", ".join(path.as_posix() for path in bad[:20])
        raise SystemExit(f"installer resources 包含禁止文件：{joined}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Windows installer for LegalFactReview Desktop.")
    parser.add_argument("--python-zip", help="Path to python-3.12.x-embed-amd64.zip")
    parser.add_argument("--python-dir", help="Path to a prepared Python 3.12 runtime directory")
    parser.add_argument("--no-embedded-python", action="store_true", help="Build installer without bundled Python")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-npm-install", action="store_true")
    args = parser.parse_args()
    build_windows_installer(
        python_zip=args.python_zip,
        python_dir=args.python_dir,
        skip_tests=args.skip_tests,
        skip_npm_install=args.skip_npm_install,
        no_embedded_python=args.no_embedded_python,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
