from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import argparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WHEELHOUSE = ROOT / "dist" / "wheelhouse"
SUPPORTED_PYTHON_TEXT = "Python 3.10-3.12"


def build_wheelhouse(
    requirements_path: str | Path = ROOT / "requirements.txt",
    wheelhouse_dir: str | Path = DEFAULT_WHEELHOUSE,
    dry_run: bool = False,
) -> list[str]:
    """Build a wheelhouse for the current Python runtime.

    The generated wheelhouse must match the target Python major/minor version
    used by Windows portable users, for example cp311 wheels for Python 3.11.
    """
    requirements_path = Path(requirements_path)
    wheelhouse_dir = Path(wheelhouse_dir)
    command = [
        sys.executable,
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
    print(f"目标运行环境：{SUPPORTED_PYTHON_TEXT}。wheelhouse 必须与目标 Python 版本匹配。")
    print(f"当前用于下载依赖的 Python：{sys.version.split()[0]}")
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
