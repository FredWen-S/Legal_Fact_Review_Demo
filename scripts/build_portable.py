from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.python_selector import find_supported_python


DEFAULT_DIST_ROOT = ROOT / "dist"
PACKAGE_NAME = "LegalFactReview"

EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "data",
    "exports",
    "logs",
    "dist",
}

EXCLUDED_FILE_NAMES = {
    "review_runs.sqlite",
}


def build_portable(dist_root: str | Path = DEFAULT_DIST_ROOT) -> Path:
    python = find_supported_python()
    print(f"Using Python: {python.display_command}")
    print(f"Python version: {python.version}")
    dist_root = Path(dist_root)
    package_dir = dist_root / PACKAGE_NAME
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    _copy_tree(ROOT / "app", package_dir / "app")
    _copy_tree(ROOT / "scripts", package_dir / "scripts")
    _copy_tree(ROOT / "docs", package_dir / "docs")
    _copy_tree(ROOT / ".streamlit", package_dir / ".streamlit")
    _copy_tree(ROOT / "app" / "sample_data", package_dir / "sample_data")
    wheelhouse = ROOT / "dist" / "wheelhouse"
    if wheelhouse.exists():
        _copy_tree(wheelhouse, package_dir / "wheelhouse")

    for filename in ["requirements.txt", "requirements-ocr.txt", "README.md", "README_快速启动.md", "Dockerfile", "docker-compose.yml"]:
        source = ROOT / filename
        if source.exists():
            shutil.copy2(source, package_dir / filename)

    shutil.copy2(ROOT / "scripts" / "windows" / "start.bat", package_dir / "start.bat")
    shutil.copy2(ROOT / "scripts" / "windows" / "stop.bat", package_dir / "stop.bat")

    for dirname in ["data", "exports", "logs"]:
        (package_dir / dirname).mkdir(exist_ok=True)
        (package_dir / dirname / ".gitkeep").write_text("", encoding="utf-8")

    print(f"Portable package generated: {package_dir}")
    return package_dir


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
        if path.is_file() and (name.endswith(".pyc") or name.endswith(".tmp")):
            ignored.add(name)
    return ignored


if __name__ == "__main__":
    build_portable()
