from pathlib import Path

import fitz
import pytest

from app.errors import OcrDependencyError
from app.models.schemas import ReviewFinding
from app.parsers.ocr_pdf_parser import parse_pdf_with_ocr
from app.parsers.pdf_parser import is_scanned_pdf, parse_pdf
from app.reports.html_report import build_html_report
from app.review_engine import review_single_document


class FakeOcrEngine:
    def ocr(self, image, cls=True):
        return [[[[0, 0], [1, 0], [1, 1], [0, 1]], ("原告：上海星河科技有限公司，案号：（2024）沪0115民初12345号", 0.91)]]


def _blank_pdf(path: Path) -> None:
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(path)
    doc.close()


def _text_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((30, 60), "原告：上海星河科技有限公司。案号：（2024）沪0115民初12345号。")
    doc.save(path)
    doc.close()


def test_is_scanned_pdf_detects_blank_pdf(tmp_path: Path):
    path = tmp_path / "blank.pdf"
    _blank_pdf(path)
    assert is_scanned_pdf(path)


def test_is_scanned_pdf_does_not_flag_text_pdf(tmp_path: Path):
    path = tmp_path / "text.pdf"
    _text_pdf(path)
    assert not is_scanned_pdf(path)


def test_ocr_missing_dependency_returns_friendly_error(tmp_path: Path):
    path = tmp_path / "blank.pdf"
    _blank_pdf(path)
    with pytest.raises(OcrDependencyError) as exc:
        parse_pdf_with_ocr(path)
    assert "当前未安装 OCR 可选依赖" in str(exc.value)


def test_ocr_parser_marks_source_location(tmp_path: Path):
    path = tmp_path / "blank.pdf"
    _blank_pdf(path)
    chunks = parse_pdf_with_ocr(path, ocr_engine=FakeOcrEngine())
    assert chunks
    assert "OCR" in chunks[0].location


def test_ocr_parser_does_not_create_temp_images(tmp_path: Path):
    path = tmp_path / "blank.pdf"
    _blank_pdf(path)
    before = {p.name for p in tmp_path.iterdir()}
    parse_pdf_with_ocr(path, ocr_engine=FakeOcrEngine())
    after = {p.name for p in tmp_path.iterdir()}
    assert before == after


def test_existing_pdf_parser_unchanged_for_text_pdf(tmp_path: Path):
    path = tmp_path / "text.pdf"
    _text_pdf(path)
    chunks = parse_pdf(path)
    assert chunks
    assert all("OCR" not in chunk.location for chunk in chunks)


def test_single_document_mode_accepts_ocr_chunks(tmp_path: Path):
    path = tmp_path / "blank.pdf"
    _blank_pdf(path)
    chunks = parse_pdf_with_ocr(path, ocr_engine=FakeOcrEngine())
    findings = review_single_document(chunks)
    assert isinstance(findings, list)


def test_report_can_show_ocr_source_location():
    finding = ReviewFinding(
        risk_id="ocr-risk",
        risk_type="FORMAT_ERROR",
        severity="medium",
        field_name="案号",
        document_value="（202X）沪0115民初ABC号",
        reference_value=None,
        source_location="第1页 OCR 文本",
        confidence=0.8,
        reason="案号格式疑似异常，需要复核。",
        suggested_action="建议人工复核该字段格式，并与原始材料或立案信息核对。",
    )
    html = build_html_report([finding], [], [], mode_label="单文书字段抽取模式")
    assert "第1页 OCR 文本" in html
