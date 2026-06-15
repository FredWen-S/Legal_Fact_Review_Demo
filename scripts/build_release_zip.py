from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
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


def normalize_version_suffix(version: str | None) -> str:
    if not version:
        return datetime.now().strftime("%Y%m%d")
    suffix = version.strip()
    if suffix.startswith("LegalFactReview_"):
        suffix = suffix.removeprefix("LegalFactReview_")
    if suffix.endswith(".zip"):
        suffix = suffix.removesuffix(".zip")
    if suffix.endswith("_windows_portable"):
        return suffix
    return f"{suffix}_windows_portable"


def build_release_zip(version: str | None = None, dist_root: str | Path = DIST_ROOT) -> Path:
    dist_root = Path(dist_root)
    package_dir = build_portable(dist_root)
    suffix = normalize_version_suffix(version)
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


def write_sha256_file(zip_path: str | Path) -> Path:
    zip_path = Path(zip_path)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path = zip_path.with_suffix(".sha256.txt")
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    print(f"SHA256 generated: {sha_path}")
    return sha_path


def _should_exclude(path: Path) -> bool:
    parts = set(path.parts)
    if parts & FORBIDDEN_PARTS:
        return True
    if path.name in FORBIDDEN_NAMES:
        return True
    return path.suffix in {".pyc", ".tmp"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Windows portable release ZIP.")
    parser.add_argument("--version", help="Release version, for example v0.4.0-rc1")
    parser.add_argument("--dist-root", default=str(DIST_ROOT), help="Output directory")
    args = parser.parse_args()
    archive = build_release_zip(version=args.version, dist_root=args.dist_root)
    write_sha256_file(archive)
