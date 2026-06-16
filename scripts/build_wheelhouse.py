from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.python_selector import find_supported_python


DEFAULT_WHEELHOUSE = ROOT / "dist" / "wheelhouse"
SUPPORTED_PYTHON_TEXT = "Python 3.10-3.12"
PREFERRED_RELEASE_PYTHON_TEXT = "Python 3.12"


def build_wheelhouse(
    requirements_path: str | Path = ROOT / "requirements.txt",
    wheelhouse_dir: str | Path = DEFAULT_WHEELHOUSE,
    dry_run: bool = False,
) -> list[str]:
    """Build a wheelhouse with a supported release Python runtime."""
    requirements_path = Path(requirements_path)
    wheelhouse_dir = Path(wheelhouse_dir)
    python = find_supported_python()
    command = [
        *python.command,
        "-m",
        "pip",
        "download",
        "-r",
        str(requirements_path),
        "-d",
        str(wheelhouse_dir),
    ]
    if dry_run:
        return command
    if not requirements_path.exists():
        raise FileNotFoundError(f"未找到 requirements.txt：{requirements_path}")
    wheelhouse_dir.mkdir(parents=True, exist_ok=True)
    print(f"目标运行环境：{SUPPORTED_PYTHON_TEXT}，推荐 {PREFERRED_RELEASE_PYTHON_TEXT}。")
    print(f"Using Python: {python.display_command}")
    print(f"Python version: {python.version}")
    print(f"正在下载离线依赖包到：{wheelhouse_dir}")
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit("离线依赖包下载失败。请检查网络连接、pip 配置或 requirements.txt 后重试。") from exc
    print(f"离线依赖包已生成：{wheelhouse_dir}")
    return command


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建离线 wheelhouse 依赖包")
    parser.add_argument("--ocr", action="store_true", help="下载 OCR 可选依赖 requirements-ocr.txt")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    req = ROOT / ("requirements-ocr.txt" if args.ocr else "requirements.txt")
    wheelhouse = ROOT / "dist" / ("wheelhouse-ocr" if args.ocr else "wheelhouse")
    build_wheelhouse(req, wheelhouse)
