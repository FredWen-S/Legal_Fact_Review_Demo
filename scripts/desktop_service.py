from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.python_selector import PythonCandidate, find_supported_python
from scripts.windows.preflight_check import (
    ensure_existing_venv_is_supported,
    ensure_supported_python_version,
    ensure_wheelhouse_matches_python,
    find_available_port,
)


DEFAULT_START_TIMEOUT_SECONDS = 45


def status(root: Path = ROOT) -> dict[str, Any]:
    pid_file = root / "logs" / "service.pid"
    port_file = root / "logs" / "current_port.txt"
    pid = _read_pid(pid_file)
    port = _read_port(port_file)
    if not pid:
        return _state("stopped", port=port, message="服务未启动")
    if not _is_pid_running(pid):
        _safe_unlink(pid_file)
        return _state("stopped", port=port, message="服务未启动")
    url = f"http://localhost:{port}" if port else None
    service_status = "running" if url and _url_ready(url) else "starting"
    message = "服务已启动" if service_status == "running" else "服务启动中"
    return _state(service_status, pid=pid, port=port, url=url, message=message)


def start(root: Path = ROOT, timeout_seconds: int = DEFAULT_START_TIMEOUT_SECONDS) -> dict[str, Any]:
    current = status(root)
    if current["status"] in {"running", "starting"}:
        current["message"] = "服务已在运行" if current["status"] == "running" else "服务正在启动"
        return current

    _ensure_runtime_dirs(root)
    main_py = root / "app" / "main.py"
    if not main_py.exists():
        return _error("当前目录缺少 app/main.py。请确认桌面发布包完整。")
    if not (root / "requirements.txt").exists():
        return _error("当前目录缺少 requirements.txt。请确认桌面发布包完整。")

    try:
        selected_python = find_supported_python()
        version_info = selected_python.major_minor
        _append_log(root, f"Using Python: {selected_python.display_command}")
        _append_log(root, f"Python version: {selected_python.version}")
        ensure_supported_python_version(version_info)
        ensure_existing_venv_is_supported(root)
        ensure_wheelhouse_matches_python(root, version_info)
        port = find_available_port()
        _ensure_venv(root, selected_python)
        _install_dependencies(root)
    except SystemExit as exc:
        message = str(exc) or "启动前检查失败。"
        _append_log(root, f"ERROR: {message}")
        return _error(message)
    except Exception as exc:
        _append_log(root, f"ERROR: {exc}")
        return _error(f"本地服务启动准备失败：{exc}")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env["PYTHONIOENCODING"] = "utf-8"
    command = [
        str(_venv_python(root)),
        "-m",
        "streamlit",
        "run",
        str(main_py),
        "--server.port",
        str(port),
        "--server.address",
        "localhost",
    ]
    with _service_log_path(root).open("a", encoding="utf-8", errors="replace") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=str(root),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=_creation_flags(),
        )
    (root / "logs" / "service.pid").write_text(str(process.pid), encoding="utf-8")
    (root / "logs" / "current_port.txt").write_text(str(port), encoding="utf-8")
    _append_log(root, f"Started Streamlit pid={process.pid} port={port}")

    url = f"http://localhost:{port}"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if process.poll() is not None:
            _safe_unlink(root / "logs" / "service.pid")
            return _error("本地服务启动失败，请查看 logs/desktop_service.log。", port=port, url=url)
        if _url_ready(url):
            return _state("running", pid=process.pid, port=port, url=url, message=f"服务已启动：{url}")
        time.sleep(0.5)
    return _state("starting", pid=process.pid, port=port, url=url, message="本地服务仍在启动，请稍后刷新状态。")


def stop(root: Path = ROOT) -> dict[str, Any]:
    pid_file = root / "logs" / "service.pid"
    pid = _read_pid(pid_file)
    if not pid:
        _safe_unlink(pid_file)
        return _state("stopped", message="服务已停止")
    if not _is_pid_running(pid):
        _safe_unlink(pid_file)
        return _state("stopped", message="服务已停止")
    if not _pid_matches_project_service(pid, root):
        _safe_unlink(pid_file)
        return _error("pid 文件指向的进程不是本项目启动的 Streamlit 服务，已清理 stale pid。")

    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
        else:
            os.kill(pid, 15)
    except Exception as exc:
        return _error(f"停止本项目服务失败：{exc}", pid=pid)

    deadline = time.time() + 10
    while time.time() < deadline:
        if not _is_pid_running(pid):
            _safe_unlink(pid_file)
            _append_log(root, f"Stopped Streamlit pid={pid}")
            return _state("stopped", message="服务已停止")
        time.sleep(0.3)
    return _error("服务停止超时，请查看日志后手动处理。", pid=pid)


def logs(root: Path = ROOT, lines: int = 80) -> dict[str, Any]:
    log_path = _service_log_path(root)
    if not log_path.exists():
        return _state("ok", lines=[], message="暂无日志")
    text_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    recent_lines = text_lines[-max(lines, 0) :] if lines else []
    return _state("ok", lines=recent_lines, message="日志已刷新" if recent_lines else "暂无日志")


def main(argv: list[str] | None = None) -> int:
    root_for_log = ROOT
    try:
        parser = argparse.ArgumentParser(description="Manage LegalFactReview desktop local service.")
        parser.add_argument("command", choices=["start", "stop", "status", "logs"])
        parser.add_argument("--root", default=str(ROOT))
        parser.add_argument("--timeout", type=int, default=DEFAULT_START_TIMEOUT_SECONDS)
        parser.add_argument("--lines", type=int, default=80)
        args = parser.parse_args(argv)
        root = Path(args.root).resolve()
        root_for_log = root

        if args.command == "start":
            result = start(root, timeout_seconds=args.timeout)
        elif args.command == "stop":
            result = stop(root)
        elif args.command == "logs":
            result = logs(root, lines=args.lines)
        else:
            result = status(root)
    except Exception as exc:
        _append_log(root_for_log, f"UNHANDLED ERROR: {exc}\n{traceback.format_exc()}")
        result = _error(f"桌面服务命令执行失败：{exc}")
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result.get("ok") else 1


def _ensure_runtime_dirs(root: Path) -> None:
    for directory in [root / "data", root / "exports", root / "logs"]:
        directory.mkdir(parents=True, exist_ok=True)


def _ensure_venv(root: Path, selected_python: PythonCandidate) -> None:
    python = _venv_python(root)
    if python.exists():
        return
    _append_log(root, f"Creating virtual environment with {selected_python.display_command}")
    subprocess.run([*selected_python.command, "-m", "venv", str(root / ".venv")], cwd=str(root), check=True)


def _install_dependencies(root: Path) -> None:
    python = _venv_python(root)
    wheelhouse = root / "wheelhouse"
    base_command = [str(python), "-m", "pip", "install"]
    if wheelhouse.exists():
        command = base_command + ["--no-index", f"--find-links={wheelhouse}", "-r", "requirements.txt"]
        _append_log(root, "Installing dependencies from wheelhouse")
        result = subprocess.run(command, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        _append_log(root, result.stdout)
        if result.returncode == 0:
            return
        _append_log(root, "Wheelhouse install failed, trying online install")
    command = base_command + ["-r", "requirements.txt"]
    result = subprocess.run(command, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    _append_log(root, result.stdout)
    if result.returncode != 0:
        raise RuntimeError("依赖安装失败，请查看 logs/desktop_service.log。")


def _venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _service_log_path(root: Path) -> Path:
    return root / "logs" / "desktop_service.log"


def _append_log(root: Path, text: str) -> None:
    _ensure_runtime_dirs(root)
    with _service_log_path(root).open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")


def _read_pid(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def _read_port(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True, encoding="utf-8", errors="replace")
            return str(pid) in result.stdout
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _pid_matches_project_service(pid: int, root: Path) -> bool:
    if os.name != "nt":
        return True
    try:
        result = subprocess.run(
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/value"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
    except Exception:
        return False
    command_line = result.stdout.replace("\\\\", "\\")
    return "streamlit" in command_line and "app\\main.py" in command_line and str(root) in command_line


def _url_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=0.5) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _state(status_value: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": status_value != "error",
        "status": status_value,
        "pid": None,
        "port": None,
        "url": None,
        "message": None,
        "error": None,
        "lines": [],
    }
    payload.update(extra)
    return payload


def _error(message: str, **extra: Any) -> dict[str, Any]:
    return _state("error", message=message, error=message, **extra)


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


if __name__ == "__main__":
    raise SystemExit(main())
