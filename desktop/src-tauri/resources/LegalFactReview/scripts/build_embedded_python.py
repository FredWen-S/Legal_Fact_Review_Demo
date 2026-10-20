from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCES_ROOT = ROOT / "desktop" / "src-tauri" / "resources"
PYTHON_RESOURCE = RESOURCES_ROOT / "python"
APP_RESOURCE = RESOURCES_ROOT / "LegalFactReview"

EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "data",
    "exports",
    "logs",
    "dist",
    "tmp",
    "node_modules",
    "target",
}
EXCLUDED_FILE_NAMES = {"review_runs.sqlite"}


def build_embedded_python(
    python_zip: str | Path | None = None,
    python_dir: str | Path | None = None,
    install_deps: bool = True,
) -> Path:
    RESOURCES_ROOT.mkdir(parents=True, exist_ok=True)
    if PYTHON_RESOURCE.exists():
        shutil.rmtree(PYTHON_RESOURCE)
    PYTHON_RESOURCE.mkdir(parents=True, exist_ok=True)

    if python_zip:
        _extract_python_zip(Path(python_zip), PYTHON_RESOURCE)
    elif python_dir:
        _copy_tree(Path(python_dir), PYTHON_RESOURCE)
    else:
        raise SystemExit(
            "未提供 Python runtime。请使用 --python-zip 指向 python-3.12-embed-amd64.zip，"
            "或使用 --python-dir 指向已准备好的 Python 3.12 运行目录。"
        )

    python_exe = PYTHON_RESOURCE / "python.exe"
    if not python_exe.exists():
        raise SystemExit(f"内置 Python runtime 缺少 python.exe：{python_exe}")
    version = _python_version(python_exe)
    if not version.startswith("3.12."):
        raise SystemExit(f"内置 Python 必须是 3.12.x，当前为 {version}")

    if install_deps:
        _install_requirements(python_exe)
    build_app_resource()
    print(f"Embedded Python prepared: {PYTHON_RESOURCE}")
    print(f"Python version: {version}")
    print(f"App resource prepared: {APP_RESOURCE}")
    return PYTHON_RESOURCE


def build_app_resource() -> Path:
    PYTHON_RESOURCE.mkdir(parents=True, exist_ok=True)
    (PYTHON_RESOURCE / ".gitkeep").write_text("", encoding="utf-8")
    if APP_RESOURCE.exists():
        shutil.rmtree(APP_RESOURCE)
    APP_RESOURCE.mkdir(parents=True, exist_ok=True)
    for dirname in ["app", "scripts", ".streamlit"]:
        _copy_tree(ROOT / dirname, APP_RESOURCE / dirname)
    for filename in ["requirements.txt", "requirements-ocr.txt", "README.md", "README_快速启动.md"]:
        source = ROOT / filename
        if source.exists():
            shutil.copy2(source, APP_RESOURCE / filename)
    for dirname in ["data", "exports", "logs"]:
        (APP_RESOURCE / dirname).mkdir(exist_ok=True)
        (APP_RESOURCE / dirname / ".gitkeep").write_text("", encoding="utf-8")
    return APP_RESOURCE


def _extract_python_zip(source: Path, target: Path) -> None:
    if not source.exists():
        raise SystemExit(f"Python embed zip 不存在：{source}")
    with zipfile.ZipFile(source) as archive:
        archive.extractall(target)


def _copy_tree(source: Path, target: Path) -> None:
    if not source.exists():
        return
    shutil.copytree(source, target, ignore=_ignore)


def _ignore(directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        path = Path(directory) / name
        if name in EXCLUDED_DIR_NAMES or name in EXCLUDED_FILE_NAMES:
            ignored.add(name)
            continue
        if path.is_file() and (name.endswith(".pyc") or name.endswith(".tmp") or name.endswith(".log")):
            ignored.add(name)
    return ignored


def _python_version(python_exe: Path) -> str:
    result = subprocess.run(
        [str(python_exe), "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or f"无法运行 {python_exe}")
    return result.stdout.strip().splitlines()[-1]


def _install_requirements(python_exe: Path) -> None:
    requirements = ROOT / "requirements.txt"
    if not requirements.exists():
        raise SystemExit("缺少 requirements.txt")
    result = subprocess.run(
        [str(python_exe), "-m", "pip", "install", "-r", str(requirements)],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit("内置 Python 依赖安装失败。")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare embedded Python resources for Tauri installer.")
    parser.add_argument("--python-zip", help="Path to python-3.12.x-embed-amd64.zip")
    parser.add_argument("--python-dir", help="Path to a prepared Python 3.12 runtime directory")
    parser.add_argument("--no-install-deps", action="store_true", help="Only copy runtime and app resources")
    parser.add_argument("--app-only", action="store_true", help="Only refresh LegalFactReview app resources")
    args = parser.parse_args()

    if args.app_only:
        build_app_resource()
        print(f"App resource prepared: {APP_RESOURCE}")
        return 0
    build_embedded_python(args.python_zip, args.python_dir, install_deps=not args.no_install_deps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
