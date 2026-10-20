from __future__ import annotations

from pathlib import Path

import fitz

from app.errors import EmptyFileError, ParseError
from app.models.schemas import TextChunk


def is_scanned_pdf(file_path: str | Path, min_chars_per_page: int = 20) -> bool:
    try:
        with fitz.open(str(file_path)) as document:
            page_count = len(document)
            if page_count == 0:
                return False
            total_chars = 0
            for page in document:
                total_chars += len((page.get_text("text") or "").strip())
            return total_chars < page_count * min_chars_per_page
    except Exception:
        return False


def parse_pdf(path: str | Path) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    try:
        with fitz.open(str(path)) as document:
            for page_index, page in enumerate(document, start=1):
                text = page.get_text("text")
                for line_index, line in enumerate(text.splitlines(), start=1):
                    clean = line.strip()
                    if clean:
                        chunks.append(
                            TextChunk(
                                text=clean,
                                location=f"PDF 第 {page_index} 页 行 {line_index}",
                            )
                        )
    except Exception as exc:
        raise ParseError("PDF 解析失败。请确认上传的是未损坏、未加密且可复制文本的 PDF。") from exc
    if not chunks:
        raise EmptyFileError("PDF 未解析到可复核文本。若文件为扫描版，请在页面勾选 OCR 识别后重试，或先转换为可复制文字的 PDF。")
    return chunks
