from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz

from app.errors import EmptyFileError, OcrDependencyError, ParseError
from app.models.schemas import TextChunk


def parse_pdf_with_ocr(path: str | Path, ocr_engine: Any | None = None, zoom: float = 2.0) -> list[TextChunk]:
    engine = ocr_engine or _load_ocr_engine()
    chunks: list[TextChunk] = []
    try:
        with fitz.open(str(path)) as document:
            for page_index, page in enumerate(document, start=1):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                image = _pixmap_to_numpy(pixmap)
                raw_result = engine.ocr(image, cls=True)
                lines = _extract_ocr_lines(raw_result)
                page_text = "\n".join(text for text, _confidence in lines).strip()
                if page_text:
                    avg_confidence = sum(conf for _text, conf in lines) / len(lines) if lines else 0
                    chunks.append(
                        TextChunk(
                            text=page_text,
                            location=f"第{page_index}页 OCR 文本（平均置信度 {avg_confidence:.2f}）",
                        )
                    )
    except OcrDependencyError:
        raise
    except Exception as exc:
        raise ParseError("OCR 解析失败。请确认 PDF 未损坏，或先将扫描件转换为清晰 PDF 后重试。") from exc
    if not chunks:
        raise EmptyFileError("OCR 未识别到可复核文本。请确认扫描件清晰，或尝试提高扫描质量后重试。")
    return chunks


def _load_ocr_engine() -> Any:
    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise OcrDependencyError("当前未安装 OCR 可选依赖。请运行 pip install -r requirements-ocr.txt 后重试。") from exc
    return PaddleOCR(use_angle_cls=True, lang="ch")


def _pixmap_to_numpy(pixmap: fitz.Pixmap) -> Any:
    try:
        from PIL import Image
        import numpy as np
    except Exception as exc:
        raise OcrDependencyError("当前未安装 OCR 图像处理依赖。请运行 pip install -r requirements-ocr.txt 后重试。") from exc
    image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
    return np.array(image)


def _extract_ocr_lines(raw_result: Any) -> list[tuple[str, float]]:
    lines: list[tuple[str, float]] = []
    if not raw_result:
        return lines
    candidates = raw_result
    if len(candidates) == 1 and isinstance(candidates[0], list) and not _looks_like_ocr_line(candidates[0]):
        candidates = candidates[0]
    for item in candidates:
        try:
            text = str(item[1][0]).strip()
            confidence = float(item[1][1])
        except Exception:
            continue
        if text:
            lines.append((text, confidence))
    return lines


def _looks_like_ocr_line(value: Any) -> bool:
    try:
        return len(value) >= 2 and isinstance(value[1], (tuple, list)) and len(value[1]) >= 2 and isinstance(value[1][0], str)
    except Exception:
        return False
