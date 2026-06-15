from pathlib import Path
from zipfile import ZipFile

from scripts.build_release_zip import build_release_zip


ROOT = Path(__file__).resolve().parents[1]
START_BAT = ROOT / "scripts" / "windows" / "start.bat"
STOP_BAT = ROOT / "scripts" / "windows" / "stop.bat"


def test_start_bat_is_cmd_safe_ascii_without_bom():
    data = START_BAT.read_bytes()

    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\x00" not in data
    assert b'"""' not in data
    data.decode("ascii")


def test_windows_bat_files_use_crlf_line_endings():
    for path in [START_BAT, STOP_BAT]:
        data = path.read_bytes()
        assert b"\r\n" in data
        assert b"\n" not in data.replace(b"\r\n", b"")


def test_release_zip_start_bat_matches_source(tmp_path: Path):
    zip_path = build_release_zip(version="bat-test", dist_root=tmp_path)

    with ZipFile(zip_path) as archive:
        packaged_start = archive.read("LegalFactReview/start.bat")

    assert packaged_start == START_BAT.read_bytes()


def test_start_bat_sets_pythonpath_and_uses_module_streamlit():
    text = START_BAT.read_text(encoding="ascii")

    assert 'set "PYTHONPATH=%CD%"' in text
    assert '"%VENV_PY%" -m streamlit run "app\\main.py"' in text
    assert "streamlit.exe run" not in text
