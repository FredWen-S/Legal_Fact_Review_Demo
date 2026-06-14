from app.extractors.field_extractor import extract_fields
from app.models.schemas import TextChunk


def test_regex_extractor_extracts_core_fields():
    chunks = [
        TextChunk(
            text="原告：上海星河科技有限公司，统一社会信用代码：91310000MA1K000001，合同编号：HT-2024-001，证据7。",
            location="测试段落 1",
        )
    ]
    items = extract_fields(chunks)
    pairs = {(item.field_name, item.value) for item in items}
    assert ("当事人名称", "上海星河科技有限公司") in pairs
    assert ("统一社会信用代码", "91310000MA1K000001") in pairs
    assert ("合同编号", "HT-2024-001") in pairs
    assert ("证据编号", "7") in pairs


def test_placeholder_extraction():
    chunks = [TextChunk(text="其他事项：待补充，金额为XXXX元。", location="测试段落 2")]
    items = extract_fields(chunks)
    assert any(item.field_name == "文书中的占位符" for item in items)
