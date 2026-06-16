from __future__ import annotations

import shutil
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist"
PACKAGE_NAME = "LegalFactReview_v0.5.0-rc1_desktop"
EXCLUDED_DIR_NAMES = {".git", ".venv", "__pycache__", ".pytest_cache", "data", "exports", "logs", "dist", "node_modules", "target"}
EXCLUDED_FILE_NAMES = {"review_runs.sqlite"}


def build_desktop_release(dist_root: str | Path = DIST_ROOT) -> Path:
    dist_root = Path(dist_root)
    package_dir = dist_root / PACKAGE_NAME
    staging_dir = dist_root / f".{PACKAGE_NAME}_staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    for dirname in ["app", "scripts", "docs", "desktop"]:
        _copy_tree(ROOT / dirname, staging_dir / dirname)
    _copy_tree(ROOT / ".streamlit", staging_dir / ".streamlit")
    for filename in [
        "requirements.txt",
        "requirements-ocr.txt",
        "README.md",
        "README_快速启动.md",
        "Dockerfile",
        "docker-compose.yml",
    ]:
        source = ROOT / filename
        if source.exists():
            shutil.copy2(source, staging_dir / filename)

    readme = ROOT / "docs" / "桌面版说明.md"
    if readme.exists():
        shutil.copy2(readme, staging_dir / "README_桌面版启动.md")

    wheelhouse = ROOT / "dist" / "wheelhouse"
    if wheelhouse.exists():
        _copy_tree(wheelhouse, staging_dir / "wheelhouse")

    bundle_dir = ROOT / "desktop" / "src-tauri" / "target" / "release" / "bundle"
    if bundle_dir.exists():
        _copy_tree(bundle_dir, staging_dir / "tauri-bundle")

    for dirname in ["data", "exports", "logs"]:
        (staging_dir / dirname).mkdir(exist_ok=True)
        (staging_dir / dirname / ".gitkeep").write_text("", encoding="utf-8")

    if package_dir.exists():
        try:
            shutil.rmtree(package_dir)
        except PermissionError:
            _merge_tree(staging_dir, package_dir)
            print(
                f"Warning: existing desktop release is locked and was not replaced: {package_dir}. "
                f"Updated files in place where possible and using staging package for ZIP: {staging_dir}"
            )
            print(f"Desktop release package generated: {staging_dir}")
            return staging_dir
    staging_dir.replace(package_dir)

    print(f"Desktop release package generated: {package_dir}")
    return package_dir


def build_desktop_release_zip(dist_root: str | Path = DIST_ROOT) -> Path:
    dist_root = Path(dist_root)
    package_dir = build_desktop_release(dist_root)
    zip_path = dist_root / f"{PACKAGE_NAME}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in package_dir.rglob("*"):
            relative_path = path.relative_to(package_dir)
            if path.is_dir() or _should_exclude_file(relative_path):
                continue
            archive.write(path, Path(PACKAGE_NAME) / relative_path)
    print(f"Desktop release ZIP generated: {zip_path}")
    return zip_path


def write_sha256_file(path: str | Path) -> Path:
    release_path = Path(path)
    digest = hashlib.sha256(release_path.read_bytes()).hexdigest()
    sha_path = release_path.with_suffix(".sha256.txt")
    sha_path.write_text(f"{digest}  {release_path.name}\n", encoding="utf-8")
    print(f"SHA256 generated: {sha_path}")
    return sha_path


def _copy_tree(source: Path, target: Path) -> None:
    if source.exists():
        shutil.copytree(source, target, ignore=_ignore)


def _merge_tree(source: Path, target: Path) -> None:
    if not source.exists() or not target.exists():
        return
    for source_path in source.rglob("*"):
        relative_path = source_path.relative_to(source)
        target_path = target / relative_path
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source_path, target_path)
        except PermissionError:
            print(f"Warning: locked file was not updated: {target_path}")


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


def _should_exclude_file(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDED_DIR_NAMES:
        return True
    if path.name in EXCLUDED_FILE_NAMES:
        return True
    return path.suffix in {".pyc", ".tmp", ".log"}


if __name__ == "__main__":
    zip_path = build_desktop_release_zip()
    write_sha256_file(zip_path)
