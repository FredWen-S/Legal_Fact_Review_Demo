from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence

import scripts.python_selector as python_selector
from scripts.python_selector import find_supported_python, is_supported_version


def _runner(versions: dict[tuple[str, ...], str]):
    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        probe_command = tuple(command[:2]) if len(command) > 1 and command[0] == "py" else tuple(command[:1])
        version = versions.get(probe_command)
        if not version:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        payload = {"version": version, "executable": f"C:/Python{version.replace('.', '')}/python.exe"}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    return run


def test_python_selector_accepts_supported_versions_in_priority_order():
    candidate = find_supported_python(_runner({("py", "-3.12"): "3.12.13"}), include_current=False)

    assert candidate.command == ("py", "-3.12")
    assert candidate.version == "3.12.13"


def test_python_selector_falls_back_to_311_then_310():
    candidate_311 = find_supported_python(_runner({("py", "-3.11"): "3.11.9", ("py", "-3.10"): "3.10.11"}), include_current=False)
    candidate_310 = find_supported_python(_runner({("py", "-3.10"): "3.10.11"}), include_current=False)

    assert candidate_311.command == ("py", "-3.11")
    assert candidate_310.command == ("py", "-3.10")


def test_python_selector_prefers_current_312_over_py_311(monkeypatch):
    monkeypatch.setattr(python_selector.sys, "version_info", (3, 12, 13))
    monkeypatch.setattr(python_selector.sys, "executable", "C:/codex/python312/python.exe")

    candidate = find_supported_python(_runner({("py", "-3.11"): "3.11.9"}))

    assert candidate.command == ("C:/codex/python312/python.exe",)
    assert candidate.version == "3.12.13"


def test_python_selector_rejects_python_313_only():
    try:
        find_supported_python(_runner({("python",): "3.13.2"}), include_current=False)
    except SystemExit as exc:
        message = str(exc)
        assert "未找到受支持的 Python 版本" in message
        assert "3.13.2" in message
    else:
        raise AssertionError("Expected Python 3.13-only environment to fail")


def test_supported_version_matrix():
    assert is_supported_version("3.10.11")
    assert is_supported_version("3.11.9")
    assert is_supported_version("3.12.13")
    assert not is_supported_version("3.9.18")
    assert not is_supported_version("3.13.2")
