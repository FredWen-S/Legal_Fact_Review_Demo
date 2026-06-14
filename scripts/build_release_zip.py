from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_portable import build_portable


DIST_ROOT = ROOT / "dist"


FORBIDDEN_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache"}
FORBIDDEN_NAMES = {"review_runs.sqlite"}


def build_release_zip(version: str | None = None, dist_root: str | Path = DIST_ROOT) -> Path:
    dist_root = Path(dist_root)
    package_dir = build_portable(dist_root)
    suffix = version or datetime.now().strftime("%Y%m%d")
    zip_path = dist_root / f"LegalFactReview_{suffix}.zip"
    if zip_path.exists():
        zip_path.unlink()

    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in package_dir.rglob("*"):
            if path.is_dir() or _should_exclude(path):
                continue
            archive.write(path, path.relative_to(package_dir.parent))

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"Release ZIP generated: {zip_path} ({size_mb:.2f} MB)")
    return zip_path


def _should_exclude(path: Path) -> bool:
    parts = set(path.parts)
    if parts & FORBIDDEN_PARTS:
        return True
    if path.name in FORBIDDEN_NAMES:
        return True
    return path.suffix in {".pyc", ".tmp"}


if __name__ == "__main__":
    build_release_zip()
