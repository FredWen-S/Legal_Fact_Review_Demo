from __future__ import annotations

from pathlib import Path
import sys
from datetime import datetime
from tempfile import TemporaryDirectory
from io import BytesIO
from zipfile import ZipFile
from docx import Document
import fitz

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.parsers.docx_parser import parse_docx
from app.parsers.excel_parser import parse_base_info, parse_evidence_index
from app.extractors.external_review_fields import build_external_review_fields
from app.reports.excel_report import build_excel_report, external_fields_to_dataframe, findings_to_dataframe
from app.reports.html_report import build_html_report
from app.reports.docx_report import build_docx_report
from app.reports.package_export import build_review_package_zip
from app.manual_review import default_manual_records
from app.storage.sqlite_store import fetch_manual_review_records, save_manual_review_records
from app.review_engine import review_document, review_single_document
from app.errors import OcrDependencyError
from app.parsers.pdf_parser import is_scanned_pdf
from app.parsers.ocr_pdf_parser import parse_pdf_with_ocr
from scripts.build_portable import build_portable
from scripts.build_release_zip import build_release_zip
from scripts.windows.preflight_check import run_preflight


SAMPLE_DIR = ROOT / "app" / "sample_data"


def main() -> None:
    document = SAMPLE_DIR / "sample_document.docx"
    base_info = SAMPLE_DIR / "sample_base_info.xlsx"
    evidence = SAMPLE_DIR / "sample_evidence_index.xlsx"

    missing = [path for path in [document, base_info, evidence] if not path.exists()]
    if missing:
        raise SystemExit(f"示例数据缺失：{', '.join(str(path) for path in missing)}")

    chunks = parse_docx(document)
    external_fields = build_external_review_fields(chunks)
    findings = review_document(chunks, parse_base_info(base_info), parse_evidence_index(evidence))
    risk_types = {finding.risk_type for finding in findings}

    required_risks = {
        "PLACEHOLDER_REMAINING",
        "INTERNAL_CONFLICT",
        "SOURCE_MISMATCH",
        "EVIDENCE_REFERENCE_MISSING",
        "AMOUNT_INCONSISTENCY",
        "DATE_LOGIC_WARNING",
        "FORMAT_ERROR",
    }
    missing_risks = sorted(required_risks - risk_types)
    if missing_risks:
        raise SystemExit(f"示例复核未覆盖预期风险类型：{', '.join(missing_risks)}")
    if len(findings) < 5:
        raise SystemExit(f"示例复核发现数量过少：{len(findings)}")
    if any(not finding.source_location.strip() for finding in findings):
        raise SystemExit("存在缺少 source_location 的 finding")
    if any("建议人工复核" not in finding.suggested_action for finding in findings):
        raise SystemExit("存在未按人工复核表述输出的 suggested_action")

    manual_records = default_manual_records("acceptance-full", external_fields)
    manual_records[0] = manual_records[0].model_copy(
        update={
            "review_status": "已确认",
            "review_source": "内部客户库",
            "reviewer_note": "验收脚本生成的人工复核记录",
            "reviewed_at": datetime.now(),
        }
    )
    excel_bytes = build_excel_report(findings, external_fields, manual_records)
    html = build_html_report(findings, external_fields, manual_records, mode_label="完整复核模式")
    if excel_bytes[:2] != b"PK":
        raise SystemExit("Excel 报告生成异常")
    if "不构成法律意见" not in html:
        raise SystemExit("HTML 报告缺少免责声明")
    if "人工复核记录" not in html:
        raise SystemExit("HTML 报告缺少人工复核记录")

    df = findings_to_dataframe(findings)
    if "91310000MA1K000001" in df.to_string():
        raise SystemExit("复核表格中存在未脱敏统一社会信用代码")

    single_findings = review_single_document(chunks)
    single_risk_types = {finding.risk_type for finding in single_findings}
    if "SOURCE_MISMATCH" in single_risk_types:
        raise SystemExit("单文书模式不应生成 SOURCE_MISMATCH")
    if "EVIDENCE_REFERENCE_MISSING" in single_risk_types:
        raise SystemExit("单文书模式不应因缺少证据目录生成 EVIDENCE_REFERENCE_MISSING")
    if len(external_fields) < 5:
        raise SystemExit(f"单文书模式待外部复核字段过少：{len(external_fields)}")
    if any(not field.source_location.strip() for field in external_fields):
        raise SystemExit("存在缺少 source_location 的待外部复核字段")
    if any("建议人工复核" not in field.suggested_action for field in external_fields):
        raise SystemExit("存在未按人工复核表述输出的待外部复核字段")

    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "acceptance.sqlite"
        save_manual_review_records(manual_records, db_path)
        loaded_records = fetch_manual_review_records("acceptance-full", db_path)
        if not loaded_records:
            raise SystemExit("人工复核记录未能保存到 SQLite")
        if not any(record.review_status == "已确认" for record in loaded_records):
            raise SystemExit("人工复核记录读取结果异常")

    single_manual_records = default_manual_records("acceptance-single", external_fields)
    single_manual_records[0] = single_manual_records[0].model_copy(
        update={
            "review_status": "需修改",
            "confirmed_value": "人工确认值示例",
            "review_source": "其他",
            "reviewer_note": "验收脚本生成的单文书人工复核记录",
            "reviewed_at": datetime.now(),
        }
    )
    single_excel = build_excel_report(single_findings, external_fields, single_manual_records)
    single_html = build_html_report(single_findings, external_fields, single_manual_records, mode_label="单文书字段抽取模式")
    if single_excel[:2] != b"PK":
        raise SystemExit("单文书模式 Excel 报告生成异常")
    if "待外部复核字段清单" not in single_html:
        raise SystemExit("单文书模式 HTML 报告缺少字段清单")
    if "人工复核记录" not in single_html:
        raise SystemExit("单文书模式 HTML 报告缺少人工复核记录")
    external_df = external_fields_to_dataframe(external_fields)
    if "91310000MA1K000001" in external_df.to_string():
        raise SystemExit("待外部复核字段中存在未脱敏统一社会信用代码")

    docx_bytes = build_docx_report(findings, external_fields, manual_records, review_id="acceptance-full", mode_label="完整复核模式")
    docx_text = _extract_docx_text(docx_bytes)
    if "本报告仅基于上传文书及用户提供资料生成" not in docx_text:
        raise SystemExit("Word 复核摘要缺少免责声明")
    if "复核发现汇总" not in docx_text or "人工复核记录" not in docx_text:
        raise SystemExit("Word 复核摘要缺少关键章节")
    if "110101199001011234" in docx_text or "13800138000" in docx_text:
        raise SystemExit("Word 复核摘要存在未脱敏身份证号或手机号")

    zip_bytes = build_review_package_zip(findings, external_fields, manual_records, review_id="acceptance-full", mode_label="完整复核模式")
    with ZipFile(BytesIO(zip_bytes)) as package:
        names = set(package.namelist())
    expected = {"复核工作底稿.xlsx", "复核报告.html", "文书复核摘要.docx"}
    if not expected.issubset(names):
        raise SystemExit(f"复核包缺少文件：{', '.join(sorted(expected - names))}")

    with TemporaryDirectory() as tmpdir:
        package_dir = build_portable(Path(tmpdir))
        if not (package_dir / "start.bat").exists():
            raise SystemExit("portable 包缺少 start.bat")
        if not (package_dir / "README_快速启动.md").exists():
            raise SystemExit("portable 包缺少 README_快速启动.md")
        portable_paths = [path.relative_to(package_dir).as_posix() for path in package_dir.rglob("*")]
        if any(
            path == ".git"
            or path.startswith(".git/")
            or path == ".venv"
            or path.startswith(".venv/")
            or "__pycache__" in path
            or path.endswith("review_runs.sqlite")
            for path in portable_paths
        ):
            raise SystemExit("portable 包包含用户数据或缓存文件")

    with TemporaryDirectory() as tmpdir:
        preflight_root = Path(tmpdir) / "preflight"
        (preflight_root / "app").mkdir(parents=True)
        (preflight_root / "app" / "main.py").write_text("print('ok')", encoding="utf-8")
        (preflight_root / "requirements.txt").write_text("", encoding="utf-8")
        run_preflight(preflight_root)
        if not (preflight_root / "logs" / "current_port.txt").exists():
            raise SystemExit("preflight check 未写入 current_port.txt")

    with TemporaryDirectory() as tmpdir:
        zip_path = build_release_zip(version="acceptance", dist_root=Path(tmpdir))
        if not zip_path.exists():
            raise SystemExit("release zip 未生成")
        with ZipFile(zip_path) as release_zip:
            release_names = set(release_zip.namelist())
        required_release_files = {
            "LegalFactReview/start.bat",
            "LegalFactReview/README_快速启动.md",
        }
        if not required_release_files.issubset(release_names):
            raise SystemExit("release zip 缺少启动文件或快速说明")
        if not any(name.startswith("LegalFactReview/app/") for name in release_names):
            raise SystemExit("release zip 缺少 app 目录")
        if any(
            ".venv" in name
            or ".git/" in name
            or "__pycache__" in name
            or name.endswith("review_runs.sqlite")
            for name in release_names
        ):
            raise SystemExit("release zip 包含用户数据或缓存文件")

    with TemporaryDirectory() as tmpdir:
        blank_pdf = Path(tmpdir) / "blank_scan.pdf"
        doc = fitz.open()
        doc.new_page(width=200, height=200)
        doc.save(blank_pdf)
        doc.close()
        if not is_scanned_pdf(blank_pdf):
            raise SystemExit("PDF 扫描件检测未识别空白扫描型 PDF")
        try:
            parse_pdf_with_ocr(blank_pdf)
        except OcrDependencyError as exc:
            if "requirements-ocr.txt" not in str(exc):
                raise SystemExit("OCR 依赖缺失提示不够清晰")
        except Exception as exc:
            raise SystemExit(f"OCR 依赖缺失时未返回友好提示：{exc}") from exc

    print(
        "Acceptance check passed: "
        f"full={len(findings)} findings/{len(risk_types)} risk types; "
        f"single={len(single_findings)} findings/{len(external_fields)} external fields."
    )


def _extract_docx_text(data: bytes) -> str:
    document = Document(BytesIO(data))
    texts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            texts.extend(cell.text for cell in row.cells)
    return "\n".join(texts)


if __name__ == "__main__":
    main()
