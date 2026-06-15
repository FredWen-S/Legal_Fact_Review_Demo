from pathlib import Path
from zipfile import ZipFile

from scripts.build_portable import build_portable
from scripts.build_release_zip import build_release_zip, normalize_version_suffix, write_sha256_file
from scripts.build_wheelhouse import build_wheelhouse
from scripts.windows.preflight_check import detect_wheelhouse_python_tags, ensure_wheelhouse_matches_python, find_available_port, is_supported_python_version, run_preflight


ROOT = Path(__file__).resolve().parents[1]


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


def test_python_version_check_accepts_supported_versions():
    assert is_supported_python_version((3, 10))
    assert is_supported_python_version((3, 11))
    assert is_supported_python_version((3, 12))


def test_python_version_check_rejects_unsupported_versions():
    assert not is_supported_python_version((3, 9))
    assert not is_supported_python_version((3, 13))


def test_start_bat_does_not_use_bare_py3_default():
    start_bat = (ROOT / "scripts" / "windows" / "start.bat").read_text(encoding="ascii")
    assert "set \"PY_CMD=py -3\"" not in start_bat
    assert "py -3.12 --version" in start_bat
    assert "py -3.11 --version" in start_bat
    assert "py -3.10 --version" in start_bat


def test_readme_documents_supported_python_range():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quickstart = (ROOT / "README_快速启动.md").read_text(encoding="utf-8")
    assert "Python 3.10-3.12" in readme
    assert "Python 3.10-3.12" in quickstart


def test_app_package_marker_exists():
    assert (ROOT / "app" / "__init__.py").exists()


def test_preflight_detects_wheelhouse_python_tag_mismatch(tmp_path: Path):
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    (wheelhouse / "demo-1.0.0-cp312-cp312-win_amd64.whl").write_text("", encoding="utf-8")

    assert detect_wheelhouse_python_tags(wheelhouse) == {(3, 12)}
    try:
        ensure_wheelhouse_matches_python(tmp_path, (3, 11))
    except SystemExit as exc:
        assert "wheelhouse" in str(exc)
        assert "cp312" in str(exc)
        assert "cp311" in str(exc)
    else:
        raise AssertionError("Expected wheelhouse/Python mismatch to fail")


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
    sha_path = write_sha256_file(zip_path)
    assert sha_path.exists()
    with ZipFile(zip_path) as archive:
        names = set(archive.namelist())

    assert "LegalFactReview/start.bat" in names
    assert "LegalFactReview/README_快速启动.md" in names
    assert "LegalFactReview/app/config/review_rules.yml" in names
    assert "LegalFactReview/docs/规则配置说明.md" in names
    assert "LegalFactReview/docs/用户使用说明书.md" in names
    assert "LegalFactReview/docs/releases/v0.2.0-rc1.md" in names
    assert any(name.startswith("LegalFactReview/app/sample_data/test_cases/") for name in names)
    assert any(name.startswith("LegalFactReview/app/") for name in names)
    assert not any(".venv" in name for name in names)
    assert not any(".git/" in name or name.endswith("/.git") for name in names)
    assert not any("__pycache__" in name for name in names)
    assert not any(name.endswith("review_runs.sqlite") for name in names)
    assert not any(name.startswith("LegalFactReview/exports/") and not name.endswith(".gitkeep") for name in names)


def test_release_version_suffix_normalization():
    assert normalize_version_suffix("v0.4.0-rc1") == "v0.4.0-rc1_windows_portable"
    assert normalize_version_suffix("v0.4.0-rc1_windows_portable") == "v0.4.0-rc1_windows_portable"
