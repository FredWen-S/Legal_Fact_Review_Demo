from pathlib import Path

import pytest
from openpyxl import Workbook

from app.errors import ExcelSchemaError
from app.parsers.excel_parser import parse_base_info, parse_evidence_index


def test_base_info_requires_columns(tmp_path: Path):
    path = tmp_path / "bad_base.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["字段名", "标准值"])
    ws.append(["法定代表人", "张三"])
    wb.save(path)

    with pytest.raises(ExcelSchemaError) as exc:
        parse_base_info(path)
    assert "缺少必要列" in str(exc.value)


def test_evidence_index_requires_columns(tmp_path: Path):
    path = tmp_path / "bad_evidence.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["证据编号"])
    ws.append(["1"])
    wb.save(path)

    with pytest.raises(ExcelSchemaError) as exc:
        parse_evidence_index(path)
    assert "证据目录" in str(exc.value)
