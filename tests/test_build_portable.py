from pathlib import Path

from scripts.build_portable import build_portable


def test_build_portable_creates_expected_structure(tmp_path: Path):
    package_dir = build_portable(tmp_path)

    assert package_dir.exists()
    assert (package_dir / "start.bat").exists()
    assert (package_dir / "stop.bat").exists()
    assert (package_dir / "README_快速启动.md").exists()
    assert (package_dir / "app").is_dir()
    assert (package_dir / "sample_data").is_dir()
    assert (package_dir / "data").is_dir()
    assert (package_dir / "exports").is_dir()
    assert (package_dir / "logs").is_dir()


def test_build_portable_excludes_user_and_cache_data(tmp_path: Path):
    package_dir = build_portable(tmp_path)
    all_paths = [path.relative_to(package_dir).as_posix() for path in package_dir.rglob("*")]

    assert not any(".venv" in path for path in all_paths)
    assert not any(".git/" in path or path == ".git" for path in all_paths)
    assert not any("__pycache__" in path for path in all_paths)
    assert not any(path.endswith("review_runs.sqlite") for path in all_paths)
