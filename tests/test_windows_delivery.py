from pathlib import Path
from zipfile import ZipFile

from scripts.build_portable import build_portable
from scripts.build_release_zip import build_release_zip
from scripts.build_wheelhouse import build_wheelhouse
from scripts.windows.preflight_check import find_available_port, run_preflight


def test_preflight_creates_required_directories(tmp_path: Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("", encoding="utf-8")

    port = run_preflight(tmp_path)

    assert port >= 8501
    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "exports").is_dir()
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "logs" / "current_port.txt").exists()


def test_port_detection_returns_available_port():
    port = find_available_port(8501, 8510)
    assert 8501 <= port <= 8510


def test_build_wheelhouse_dry_run():
    command = build_wheelhouse(dry_run=True)
    assert "pip" in command
    assert "download" in command
    assert "requirements.txt" in " ".join(command)


def test_build_portable_copies_wheelhouse_when_present(tmp_path: Path):
    root_dist_wheelhouse = Path("dist") / "wheelhouse"
    root_dist_wheelhouse.mkdir(parents=True, exist_ok=True)
    marker = root_dist_wheelhouse / "offline-marker.txt"
    marker.write_text("offline", encoding="utf-8")
    try:
        package_dir = build_portable(tmp_path)
        assert (package_dir / "wheelhouse" / "offline-marker.txt").exists()
    finally:
        marker.unlink(missing_ok=True)
        try:
            root_dist_wheelhouse.rmdir()
        except OSError:
            pass


def test_build_release_zip_creates_clean_zip(tmp_path: Path):
    zip_path = build_release_zip(version="test", dist_root=tmp_path)
    assert zip_path.exists()
    with ZipFile(zip_path) as archive:
        names = set(archive.namelist())

    assert "LegalFactReview/start.bat" in names
    assert "LegalFactReview/README_快速启动.md" in names
    assert any(name.startswith("LegalFactReview/app/") for name in names)
    assert not any(".venv" in name for name in names)
    assert not any(".git/" in name or name.endswith("/.git") for name in names)
    assert not any("__pycache__" in name for name in names)
    assert not any(name.endswith("review_runs.sqlite") for name in names)
