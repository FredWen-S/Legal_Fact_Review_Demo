from __future__ import annotations

import socket
import sys
from collections.abc import Sequence
from pathlib import Path


REQUIRED_DIRS = ["data", "exports", "logs"]
DEFAULT_PORT_RANGE = range(8501, 8511)
MIN_PYTHON = (3, 10)
MAX_PYTHON = (3, 13)


def find_available_port(start: int = 8501, end: int = 8510) -> int:
    for port in range(start, end + 1):
        if is_port_available(port):
            return port
    raise RuntimeError(f"未找到可用端口：{start}-{end}")


def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def is_supported_python_version(version_info: Sequence[int] = sys.version_info) -> bool:
    major_minor = (version_info[0], version_info[1])
    return MIN_PYTHON <= major_minor < MAX_PYTHON


def ensure_supported_python_version(version_info: Sequence[int] = sys.version_info) -> None:
    major_minor = (version_info[0], version_info[1])
    if major_minor >= MAX_PYTHON:
        raise SystemExit(
            "当前检测到 Python 3.13。该交付包推荐 Python 3.10-3.12。请安装 Python 3.11 或 3.12 后重试。"
        )
    if major_minor < MIN_PYTHON:
        raise SystemExit("Python 版本过低。请安装 Python 3.10-3.12，推荐 Python 3.11 或 3.12。")


def _read_venv_version(root_path: Path) -> tuple[int, int] | None:
    pyvenv_cfg = root_path / ".venv" / "pyvenv.cfg"
    if not pyvenv_cfg.exists():
        return None
    for line in pyvenv_cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip().lower() == "version":
            parts = value.strip().split(".")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
    return None


def ensure_existing_venv_is_supported(root_path: Path) -> None:
    venv_version = _read_venv_version(root_path)
    if venv_version and not is_supported_python_version(venv_version):
        version = f"{venv_version[0]}.{venv_version[1]}"
        raise SystemExit(
            f"当前 .venv 由 Python {version} 创建，不适用于该交付包。请删除 .venv 后重试，脚本会使用 Python 3.10-3.12 重新创建。"
        )


def detect_wheelhouse_python_tags(wheelhouse_dir: str | Path) -> set[tuple[int, int]]:
    wheelhouse = Path(wheelhouse_dir)
    if not wheelhouse.exists():
        return set()
    tags: set[tuple[int, int]] = set()
    for wheel in wheelhouse.glob("*.whl"):
        parts = wheel.name.split("-")
        for part in parts:
            if part.startswith("cp") and len(part) >= 5 and part[2:5].isdigit():
                tags.add((int(part[2]), int(part[3:5])))
    return tags


def ensure_wheelhouse_matches_python(root_path: Path, version_info: Sequence[int] = sys.version_info) -> None:
    tags = detect_wheelhouse_python_tags(root_path / "wheelhouse")
    if not tags:
        return
    current = (version_info[0], version_info[1])
    if current not in tags:
        tag_text = ", ".join(f"cp{major}{minor}" for major, minor in sorted(tags))
        current_text = f"cp{current[0]}{current[1]}"
        raise SystemExit(
            f"wheelhouse 依赖包与当前 Python 版本不匹配。检测到 wheelhouse 标签：{tag_text}，当前 Python 标签：{current_text}。请使用匹配的 Python 版本，推荐 release 统一使用 Python 3.12，或重新生成对应版本 wheelhouse。"
        )


def run_preflight(root: str | Path | None = None) -> int:
    root_path = Path(root or Path.cwd()).resolve()
    print("正在执行启动前环境检查……")

    ensure_supported_python_version()
    print(f"Python 版本：{sys.version.split()[0]}")
    ensure_existing_venv_is_supported(root_path)
    ensure_wheelhouse_matches_python(root_path)

    if not (root_path / "app" / "main.py").exists():
        raise SystemExit("当前目录缺少 app/main.py。请在 LegalFactReview 根目录运行 start.bat。")
    if not (root_path / "requirements.txt").exists():
        raise SystemExit("当前目录缺少 requirements.txt。请确认交付包完整。")

    for dirname in REQUIRED_DIRS:
        (root_path / dirname).mkdir(parents=True, exist_ok=True)
    logs_dir = root_path / "logs"

    port = find_available_port()
    if port != 8501:
        print(f"检测到 8501 端口被占用，已改用 http://localhost:{port}")
    else:
        print("8501 端口可用。")
    (logs_dir / "current_port.txt").write_text(str(port), encoding="utf-8")
    print(f"浏览器地址：http://localhost:{port}")
    return port


if __name__ == "__main__":
    run_preflight()
