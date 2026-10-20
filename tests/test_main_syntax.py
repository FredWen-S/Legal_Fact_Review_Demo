import ast
from pathlib import Path


def test_main_py_has_valid_syntax():
    source = Path("app/main.py").read_text(encoding="utf-8")
    ast.parse(source)
