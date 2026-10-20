from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from zipfile import ZipFile

import scripts.build_desktop_release as build_desktop_release_module
import scripts.desktop_service as desktop_service_module
from scripts import check_installer_env
import scripts.build_windows_installer as build_windows_installer_module
from scripts.build_desktop_release import build_desktop_release, build_desktop_release_zip, write_sha256_file
from scripts.desktop_service import find_available_port, logs, main, select_service_python, status, stop
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
    assert "python_command_candidates(app, &root)" in lib_rs
    assert "bundled_python_candidates(app, root)" in lib_rs
    assert 'program: "py"' in lib_rs
    assert 'args: vec!["-3.12".to_string()]' in lib_rs
    assert 'args: vec!["-3.11".to_string()]' in lib_rs
    assert 'args: vec!["-3.10".to_string()]' in lib_rs
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


def test_tauri_v060_bundle_config_and_build_script_exist():
    desktop = ROOT / "desktop"
    package = json.loads((desktop / "package.json").read_text(encoding="utf-8"))
    config = json.loads((desktop / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))

    assert package["version"] == "0.6.0-rc1"
    assert "tauri build" in package["scripts"]["tauri:build"]
    assert config["version"] == "0.6.0-rc1"
    assert config["productName"] in {"LegalFactReview Desktop", "LegalFactReview"}
    assert config["bundle"]["active"] is True
    assert "nsis" in config["bundle"]["targets"]
    assert "resources/LegalFactReview" in config["bundle"]["resources"]
    assert "resources/python" in config["bundle"]["resources"]
    assert "nsis" in config["bundle"]["windows"]
    assert (desktop / "src-tauri" / "resources" / "LegalFactReview").exists()
    assert (desktop / "src-tauri" / "resources" / "python").exists()
    assert (desktop / "src-tauri" / "icons" / "icon.ico").exists()


def test_desktop_service_prefers_bundled_python(tmp_path: Path, monkeypatch):
    root = _minimal_root(tmp_path)
    bundled = root / "python" / "python.exe"
    bundled.parent.mkdir()
    bundled.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(desktop_service_module, "_python_version", lambda path: "3.12.13")

    selected = select_service_python(root)

    assert selected.bundled is True
    assert selected.command == (str(bundled.resolve()),)
    assert selected.version == "3.12.13"


def test_desktop_service_falls_back_to_system_python(tmp_path: Path, monkeypatch):
    root = _minimal_root(tmp_path)
    monkeypatch.setattr(desktop_service_module, "find_supported_python", _fake_python)

    selected = select_service_python(root)

    assert selected.bundled is False
    assert selected.command == ("py", "-3.12")


def test_installer_scripts_exist_and_exclude_user_data():
    env_check = (ROOT / "scripts" / "check_installer_env.py").read_text(encoding="utf-8")
    embedded = (ROOT / "scripts" / "build_embedded_python.py").read_text(encoding="utf-8")
    installer = (ROOT / "scripts" / "build_windows_installer.py").read_text(encoding="utf-8")

    assert "NPM_MISSING_MESSAGE" in env_check
    assert "CARGO_MISSING_MESSAGE" in env_check
    assert "build_embedded_python" in embedded
    assert "--python-zip" in embedded
    assert "--python-dir" in embedded
    assert "desktop" in installer and "tauri:build" in installer
    assert "--no-embedded-python" in installer
    assert "0.6.0-rc1" in installer
    assert 'VERSION = "0.6.0-rc1"' in installer
    assert "windows_installer.sha256.txt" in installer
    for text in [embedded, installer]:
        assert "review_runs.sqlite" in text
        assert ".venv" in text
        assert "node_modules" in text
        assert "target" in text
        assert "tmp" in text


def test_installer_env_missing_tool_messages(monkeypatch):
    monkeypatch.setattr(check_installer_env.shutil, "which", lambda name: None)

    results = check_installer_env.check_installer_env()
    messages = "\n".join(result.message for result in results)

    assert "未找到 npm。请安装 Node.js 18+ LTS，并确认 npm 在 PATH 中。" in messages
    assert "未找到 cargo。请安装 Rust stable，并确认 cargo 在 PATH 中。" in messages


def test_installer_env_can_report_selected_python_instead_of_current():
    selected = PythonCandidate(("C:/Codex/Python312/python.exe",), "3.12.13", "C:/Codex/Python312/python.exe")

    result = check_installer_env._check_python_version(selected)

    assert result.ok is True
    assert "Selected Python 3.12.13" in result.message
    assert "C:/Codex/Python312/python.exe" in result.message


def test_installer_env_prefers_local_tauri_cmd(monkeypatch, tmp_path: Path):
    local_tauri = tmp_path / "desktop" / "node_modules" / ".bin" / "tauri.cmd"
    local_tauri.parent.mkdir(parents=True)
    local_tauri.write_text("", encoding="utf-8")
    commands: list[list[str]] = []

    monkeypatch.setattr(check_installer_env, "ROOT", tmp_path)
    monkeypatch.setattr(check_installer_env.os, "name", "nt")
    monkeypatch.setattr(check_installer_env, "_npm_command", lambda: "npm.cmd")

    def fake_run(command, cwd):
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, "tauri-cli 2.11.2\n", "")

    monkeypatch.setattr(check_installer_env, "_run_probe", fake_run)

    result = check_installer_env._check_tauri_cli()

    assert result.ok is True
    assert result.message == "tauri-cli 2.11.2"
    assert commands == [[str(local_tauri), "--version"]]


def test_installer_env_falls_back_to_npm_then_npx(monkeypatch, tmp_path: Path):
    commands: list[list[str]] = []
    monkeypatch.setattr(check_installer_env, "ROOT", tmp_path)
    monkeypatch.setattr(check_installer_env.os, "name", "nt")
    monkeypatch.setattr(check_installer_env, "_npm_command", lambda: "npm.cmd")
    monkeypatch.setattr(check_installer_env, "_npx_command", lambda: "npx.cmd")

    def fake_run(command, cwd):
        commands.append(list(command))
        if command[0] == "npm.cmd":
            return subprocess.CompletedProcess(command, 1, "npm banner", "script failed")
        return subprocess.CompletedProcess(command, 0, "tauri-cli 2.11.2", "")

    monkeypatch.setattr(check_installer_env, "_run_probe", fake_run)

    result = check_installer_env._check_tauri_cli()

    assert result.ok is True
    assert result.message == "tauri-cli 2.11.2"
    assert commands == [["npm.cmd", "run", "tauri", "--", "--version"], ["npx.cmd", "tauri", "--version"]]


def test_installer_env_tauri_failure_includes_diagnostics(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(check_installer_env, "ROOT", tmp_path)
    monkeypatch.setattr(check_installer_env, "_npm_command", lambda: "npm")
    monkeypatch.setattr(check_installer_env, "_npx_command", lambda: None)

    def fake_run(command, cwd):
        return subprocess.CompletedProcess(command, 7, "npm script banner", "real tauri error")

    monkeypatch.setattr(check_installer_env, "_run_probe", fake_run)

    result = check_installer_env._check_tauri_cli()

    assert result.ok is False
    assert "command: npm run tauri -- --version" in result.message
    assert "exit code: 7" in result.message
    assert "stdout:\nnpm script banner" in result.message
    assert "stderr:\nreal tauri error" in result.message


def test_build_windows_installer_missing_runtime_source_fails(tmp_path: Path):
    missing_zip = tmp_path / "missing-python.zip"

    try:
        build_windows_installer_module._validate_runtime_source(missing_zip, None)
    except SystemExit as exc:
        assert "Python embed zip 不存在" in str(exc)
    else:
        raise AssertionError("Expected missing python zip to fail")


def test_build_windows_installer_test_python_prefers_current_supported_interpreter(monkeypatch):
    monkeypatch.setattr(build_windows_installer_module.sys, "version_info", (3, 12, 13, "final", 0))
    monkeypatch.setattr(build_windows_installer_module.sys, "executable", "C:/Codex/Python312/python.exe")

    selected = build_windows_installer_module.select_test_python(
        fallback_selector=lambda: PythonCandidate(("py", "-3.12"), "3.12.10", "C:/Python312/python.exe")
    )

    assert selected.command == ("C:/Codex/Python312/python.exe",)
    assert selected.version == "3.12.13"


def test_build_windows_installer_test_python_falls_back_when_current_unsupported(monkeypatch):
    fallback = PythonCandidate(("py", "-3.12"), "3.12.10", "C:/Python312/python.exe")
    monkeypatch.setattr(build_windows_installer_module.sys, "version_info", (3, 13, 0, "final", 0))
    monkeypatch.setattr(build_windows_installer_module.sys, "executable", "C:/Python313/python.exe")

    selected = build_windows_installer_module.select_test_python(fallback_selector=lambda: fallback)

    assert selected == fallback


def test_build_windows_installer_rejects_python_313_when_no_fallback(monkeypatch):
    monkeypatch.setattr(build_windows_installer_module.sys, "version_info", (3, 13, 0, "final", 0))
    monkeypatch.setattr(build_windows_installer_module.sys, "executable", "C:/Python313/python.exe")

    try:
        build_windows_installer_module.select_test_python(
            fallback_selector=lambda: (_ for _ in ()).throw(SystemExit("未找到受支持的 Python 版本"))
        )
    except SystemExit as exc:
        assert "未找到受支持的 Python 版本" in str(exc)
    else:
        raise AssertionError("Expected unsupported Python 3.13 to fail without fallback")


def test_build_windows_installer_missing_pytest_has_friendly_error(monkeypatch):
    candidate = PythonCandidate(("C:/Codex/Python312/python.exe",), "3.12.13", "C:/Codex/Python312/python.exe")

    def fake_run(command, cwd, capture_output, text, encoding, errors, check):
        return subprocess.CompletedProcess(command, 1, "", "No module named pytest")

    monkeypatch.setattr(build_windows_installer_module.subprocess, "run", fake_run)

    try:
        build_windows_installer_module._ensure_pytest_available(candidate)
    except SystemExit as exc:
        message = str(exc)
        assert "当前 Python 缺少 pytest" in message
        assert "C:/Codex/Python312/python.exe -m pip install -r requirements.txt" in message
        assert "--skip-tests" in message
        assert "No module named pytest" in message
    else:
        raise AssertionError("Expected missing pytest to fail")


def test_build_windows_installer_skip_tests_prints_warning(tmp_path: Path, monkeypatch, capsys):
    dist_dir = tmp_path / "installer"

    monkeypatch.setattr(build_windows_installer_module, "DIST_DIR", dist_dir)
    monkeypatch.setattr(build_windows_installer_module, "select_test_python", _fake_python)
    monkeypatch.setattr(build_windows_installer_module, "_run_tests", lambda python: (_ for _ in ()).throw(AssertionError("tests should be skipped")))
    monkeypatch.setattr(
        build_windows_installer_module,
        "ensure_installer_env",
        lambda embedded_python=False, check_tauri=True, python_candidate=None: None,
    )
    monkeypatch.setattr(build_windows_installer_module, "build_app_resource", lambda: None)
    monkeypatch.setattr(build_windows_installer_module, "_clean_old_bundle_outputs", lambda: None)
    monkeypatch.setattr(build_windows_installer_module, "_run", lambda command, cwd=build_windows_installer_module.ROOT: None)
    monkeypatch.setattr(build_windows_installer_module, "_audit_resources", lambda: None)

    def fake_collect(target_dir: Path) -> list[Path]:
        installer = target_dir / "LegalFactReview_v0.6.0-rc1_windows_installer_no_python.exe"
        installer.write_bytes(b"fake")
        return [installer]

    monkeypatch.setattr(build_windows_installer_module, "_collect_installers", fake_collect)

    build_windows_installer_module.build_windows_installer(
        skip_tests=True,
        skip_npm_install=True,
        no_embedded_python=True,
    )
    output = capsys.readouterr().out

    assert "已跳过自动测试，请确保已手动运行 pytest/acceptance_check/verify_release。" in output


def test_installer_resources_are_clean():
    resources = ROOT / "desktop" / "src-tauri" / "resources"
    forbidden_parts = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", "target", "tmp", "dist"}
    forbidden_names = {"review_runs.sqlite"}
    bad = []
    for path in resources.rglob("*"):
        relative = path.relative_to(resources)
        if set(relative.parts) & forbidden_parts or path.name in forbidden_names:
            bad.append(relative.as_posix())

    assert bad == []


def test_desktop_release_package_excludes_user_sqlite(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(build_desktop_release_module, "find_supported_python", _fake_python)
    package_dir = build_desktop_release(tmp_path)
    paths = [path.relative_to(package_dir).as_posix() for path in package_dir.rglob("*")]

    assert package_dir.name == "LegalFactReview_v0.5.0_desktop"
    assert (package_dir / "desktop" / "package.json").exists()
    assert (package_dir / "desktop" / "index.html").exists()
    assert (package_dir / "desktop" / "src" / "main.js").exists()
    assert (package_dir / "desktop" / "src-tauri" / "src" / "lib.rs").exists()
    assert (package_dir / "desktop" / "src-tauri" / "src" / "main.rs").exists()
    assert (package_dir / "desktop" / "src-tauri" / "capabilities" / "default.json").exists()
    assert (package_dir / "desktop" / "src-tauri" / "icons" / "icon.ico").exists()
    assert (package_dir / "scripts" / "desktop_service.py").exists()
    assert (package_dir / "app").is_dir()
    assert (package_dir / "requirements.txt").exists()
    assert (package_dir / "README.md").exists()
    assert (package_dir / "README_快速启动.md").exists()
    assert (package_dir / "docs").is_dir()
    assert (package_dir / ".streamlit" / "config.toml").exists()
    assert (package_dir / "README_桌面版启动.md").exists()
    assert (package_dir / "docs" / "桌面版说明.md").exists()
    assert not any(path.endswith("review_runs.sqlite") for path in paths)
    assert not any("__pycache__" in path or ".pytest_cache" in path or ".venv" in path for path in paths)
    assert not any("node_modules" in path or "src-tauri/target" in path for path in paths)
    assert not any(path == "dist" or path.startswith("dist/") for path in paths)
    assert not any("acceptance_test_cases" in path or path.startswith("tmp/") for path in paths)


def test_desktop_release_zip_and_sha256_can_be_generated(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(build_desktop_release_module, "find_supported_python", _fake_python)
    zip_path = build_desktop_release_zip(tmp_path)
    sha_path = write_sha256_file(zip_path)

    assert zip_path.exists()
    assert zip_path.name == "LegalFactReview_v0.5.0_desktop.zip"
    assert sha_path.exists()
    assert zip_path.name in sha_path.read_text(encoding="utf-8")
    with ZipFile(zip_path) as archive:
        names = archive.namelist()
        assert "LegalFactReview_v0.5.0_desktop/desktop/src-tauri/src/lib.rs" in names
        assert "LegalFactReview_v0.5.0_desktop/desktop/src-tauri/capabilities/default.json" in names
        assert "LegalFactReview_v0.5.0_desktop/desktop/src-tauri/icons/icon.ico" in names
        assert not any("node_modules" in name or "src-tauri/target" in name for name in names)
        assert not any(".venv" in name or name.endswith("review_runs.sqlite") for name in names)
