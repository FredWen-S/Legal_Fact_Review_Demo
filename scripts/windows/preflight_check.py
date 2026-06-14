from __future__ import annotations

import socket
import sys
from pathlib import Path


REQUIRED_DIRS = ["data", "exports", "logs"]
DEFAULT_PORT_RANGE = range(8501, 8511)


def find_available_port(start: int = 8501, end: int = 8510) -> int:
    for port in range(start, end + 1):
        if is_port_available(port):
            return port
    raise RuntimeError(f"未找到可用端口：{start}-{end}")


def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def run_preflight(root: str | Path | None = None) -> int:
    root_path = Path(root or Path.cwd()).resolve()
    print("正在执行启动前环境检查……")

    if sys.version_info < (3, 10):
        raise SystemExit("Python 版本过低。请安装 Python 3.10 或更高版本。")
    print(f"Python 版本：{sys.version.split()[0]}")

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
