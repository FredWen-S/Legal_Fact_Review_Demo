from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from zipfile import ZipFile

import scripts.build_desktop_release as build_desktop_release_module
import scripts.desktop_service as desktop_service_module
from scripts.build_desktop_release import build_desktop_release, build_desktop_release_zip, write_sha256_file
from scripts.desktop_service import find_available_port, logs, main, status, stop
from scripts.python_selector import PythonCandidate


ROOT = Path(__file__).resolve().parents[1]


def _fake_python() -> PythonCandidate:
    return PythonCandidate(("py", "-3.12"), "3.12.13", "C:/Python312/python.exe")


def _minimal_root(tmp_path: Path) -> Path:
    root = tmp_path / "LegalFactReview"
    (root / "app").mkdir(parents=True)
    (root / "logs").mkdir()
    (root / "data").mkdir()
    (root / "exports").mkdir()
    (root / "requirements.txt").write_text("", encoding="utf-8")
    (root / "app" / "main.py").write_text("print('ok')", encoding="utf-8")
    return root


def test_desktop_service_status_stopped_when_not_started(tmp_path: Path):
    root = _minimal_root(tmp_path)

    result = status(root)

    assert result["status"] == "stopped"
    assert result["ok"] is True
    assert result["pid"] is None


def test_desktop_service_cli_outputs_json_for_status(tmp_path: Path, capsys):
    root = _minimal_root(tmp_path)

    exit_code = main(["status", "--root", str(root)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["status"] == "stopped"


def test_desktop_service_cli_outputs_json_for_status_start_stop_logs(tmp_path: Path, capsys):
    root = _minimal_root(tmp_path)

    for command in ["status", "stop", "logs"]:
        exit_code = main([command, "--root", str(root)])
        payload = json.loads(capsys.readouterr().out)

        assert exit_code == 0
        assert isinstance(payload, dict)
        assert "ok" in payload
        assert "status" in payload

    broken = tmp_path / "broken-start"
    (broken / "logs").mkdir(parents=True)
    (broken / "requirements.txt").write_text("", encoding="utf-8")
    exit_code = main(["start", "--root", str(broken), "--timeout", "1"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["status"] == "error"
    assert payload["error"]


def test_stale_pid_file_is_cleaned(tmp_path: Path):
    root = _minimal_root(tmp_path)
    pid_file = root / "logs" / "service.pid"
    pid_file.write_text("999999", encoding="utf-8")

    result = status(root)

    assert result["status"] == "stopped"
    assert not pid_file.exists()


def test_stop_only_uses_recorded_pid_and_keeps_unrelated_process(tmp_path: Path):
    root = _minimal_root(tmp_path)
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        result = stop(root)
        assert result["status"] == "stopped"
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=10)


def test_start_missing_app_main_returns_friendly_error(tmp_path: Path, capsys):
    root = tmp_path / "broken"
    (root / "logs").mkdir(parents=True)
    (root / "requirements.txt").write_text("", encoding="utf-8")

    exit_code = main(["start", "--root", str(root), "--timeout", "1"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["status"] == "error"
    assert payload["error"]
    assert "app/main.py" in payload["message"]


def test_logs_without_log_file_returns_stable_json(tmp_path: Path):
    root = _minimal_root(tmp_path)
    log_path = root / "logs" / "desktop_service.log"
    log_path.unlink(missing_ok=True)

    result = logs(root)

    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["lines"] == []


def test_start_returns_clean_chinese_error_when_no_supported_python(tmp_path: Path, monkeypatch):
    root = _minimal_root(tmp_path)
    message = "未找到受支持的 Python 版本。请安装 Python 3.10-3.12，推荐 Python 3.12。"

    def fail_selector():
        raise SystemExit(message)

    monkeypatch.setattr(desktop_service_module, "find_supported_python", fail_selector)

    result = desktop_service_module.start(root, timeout_seconds=1)
    log_text = (root / "logs" / "desktop_service.log").read_text(encoding="utf-8")

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"] == message
    assert message in log_text
    assert "�" not in result["error"]
    assert not (root / ".venv").exists()


def test_find_available_port_returns_integer():
    port = find_available_port(8501, 8510)
    assert isinstance(port, int)
    assert 8501 <= port <= 8510


def test_tauri_v2_rust_library_structure_matches_cargo_config():
    src_tauri = ROOT / "desktop" / "src-tauri"
    lib_rs = src_tauri / "src" / "lib.rs"
    main_rs = src_tauri / "src" / "main.rs"
    cargo = tomllib.loads((src_tauri / "Cargo.toml").read_text(encoding="utf-8"))

    assert lib_rs.exists()
    assert main_rs.exists()
    assert cargo["lib"]["name"] == "legal_fact_review_desktop_lib"
    assert "legal_fact_review_desktop_lib::run()" in main_rs.read_text(encoding="utf-8")


def test_desktop_frontend_uses_invoke_and_binds_required_buttons():
    desktop = ROOT / "desktop"
    index_html = (desktop / "index.html").read_text(encoding="utf-8")
    main_js = (desktop / "src" / "main.js").read_text(encoding="utf-8")
    required_button_ids = [
        "btn-status",
        "btn-start",
        "btn-stop",
        "btn-open-review",
        "btn-open-data",
        "btn-open-exports",
        "btn-open-logs",
        "btn-refresh-logs",
    ]

    assert 'from "@tauri-apps/api/core"' in main_js
    assert "invoke(" in main_js
    for button_id in required_button_ids:
        assert f'id="{button_id}"' in index_html
        assert f'document.getElementById("{button_id}").addEventListener("click"' in main_js


def test_tauri_commands_are_registered_in_lib_rs():
    lib_rs = (ROOT / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
    commands = [
        "service_status",
        "service_start",
        "service_stop",
        "service_logs",
        "open_review_ui",
        "open_data_dir",
        "open_exports_dir",
        "open_logs_dir",
    ]

    for command in commands:
        assert f"fn {command}" in lib_rs
        assert command in lib_rs[lib_rs.index("tauri::generate_handler!") :]


def test_tauri_service_uses_supported_python_candidates_and_utf8():
    lib_rs = (ROOT / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")

    assert "fn python_command() -> &'static str" not in lib_rs
    assert "python_command_candidates()" in lib_rs
    assert 'program: "py"' in lib_rs
    assert 'args: &["-3.12"]' in lib_rs
    assert 'args: &["-3.11"]' in lib_rs
    assert 'args: &["-3.10"]' in lib_rs
    assert '.env("PYTHONIOENCODING", "utf-8")' in lib_rs
    assert "未找到受支持的 Python 版本。请安装 Python 3.10-3.12，推荐 Python 3.12。" in lib_rs


def test_desktop_text_files_are_clean_utf8():
    files = [
        ROOT / "desktop" / "index.html",
        ROOT / "desktop" / "src" / "main.js",
        ROOT / "desktop" / "src" / "styles.css",
        ROOT / "desktop" / "src-tauri" / "src" / "lib.rs",
        ROOT / "scripts" / "desktop_service.py",
        ROOT / "scripts" / "python_selector.py",
    ]
    mojibake_markers = ["�", "锛", "涓", "鈥", "æ", "Ã"]

    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not any(marker in text for marker in mojibake_markers), path


def test_tauri_icon_files_exist_and_match_config():
    src_tauri = ROOT / "desktop" / "src-tauri"
    config = json.loads((src_tauri / "tauri.conf.json").read_text(encoding="utf-8"))
    icon_paths = config["bundle"]["icon"]

    assert (src_tauri / "icons" / "icon.ico").exists()
    assert icon_paths
    for icon_path in icon_paths:
        assert (src_tauri / icon_path).exists(), icon_path


def test_desktop_release_package_excludes_user_sqlite(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(build_desktop_release_module, "find_supported_python", _fake_python)
    package_dir = build_desktop_release(tmp_path)
    paths = [path.relative_to(package_dir).as_posix() for path in package_dir.rglob("*")]

    assert (package_dir / "desktop" / "package.json").exists()
    assert (package_dir / "desktop" / "index.html").exists()
    assert (package_dir / "desktop" / "src" / "main.js").exists()
    assert (package_dir / "desktop" / "src-tauri" / "src" / "lib.rs").exists()
    assert (package_dir / "desktop" / "src-tauri" / "src" / "main.rs").exists()
    assert (package_dir / "desktop" / "src-tauri" / "capabilities" / "default.json").exists()
    assert (package_dir / "desktop" / "src-tauri" / "icons" / "icon.ico").exists()
    assert (package_dir / "scripts" / "desktop_service.py").exists()
    assert (package_dir / "README_桌面版启动.md").exists()
    assert (package_dir / "docs" / "桌面版说明.md").exists()
    assert not any(path.endswith("review_runs.sqlite") for path in paths)
    assert not any("__pycache__" in path or ".pytest_cache" in path or ".venv" in path for path in paths)
    assert not any("node_modules" in path or "src-tauri/target" in path for path in paths)
    assert not any("acceptance_test_cases" in path or path.startswith("tmp/") for path in paths)


def test_desktop_release_zip_and_sha256_can_be_generated(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(build_desktop_release_module, "find_supported_python", _fake_python)
    zip_path = build_desktop_release_zip(tmp_path)
    sha_path = write_sha256_file(zip_path)

    assert zip_path.exists()
    assert zip_path.name == "LegalFactReview_v0.5.0-rc1_desktop.zip"
    assert sha_path.exists()
    assert zip_path.name in sha_path.read_text(encoding="utf-8")
    with ZipFile(zip_path) as archive:
        names = archive.namelist()
        assert f"{zip_path.stem}/desktop/src-tauri/src/lib.rs" in names
        assert f"{zip_path.stem}/desktop/src-tauri/capabilities/default.json" in names
        assert f"{zip_path.stem}/desktop/src-tauri/icons/icon.ico" in names
