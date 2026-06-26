"""extractors.py 单元测试

覆盖：
- synthesize_pages 合成页码算法（纯函数，无外部依赖）
- extract_document 分发器路由
- extract_docx/txt/markdown 返回 dict shape 一致性
- write_extracted_output 文件产出

markitdown 调用通过 monkeypatch 模拟，测试不依赖真实 markitdown 安装。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import extractors


# ============ synthesize_pages 纯函数测试 ============

def test_synthesize_pages_empty_input():
    assert extractors.synthesize_pages("") == "[PAGE 1]\n"
    assert extractors.synthesize_pages("   \n  \n") == "[PAGE 1]\n"


def test_synthesize_pages_no_headings_short():
    """无标题短文本 → 单页"""
    md = "这是一段短文本，没有标题。"
    result = extractors.synthesize_pages(md)
    assert result.startswith("[PAGE 1]")
    assert "这是一段短文本" in result
    assert "[PAGE 2]" not in result


def test_synthesize_pages_heading_starts_new_page():
    """H1/H2 标题在累积超 min_page_chars 时触发新页"""
    # 构造：第一段超 1500 字符 + 标题 + 第二段
    long_body = "正文内容。" * 400  # ~2000 字符，超过 min_page_chars=1500
    md = f"# 第一章\n\n{long_body}\n\n# 第二章\n\n第二章内容。"
    result = extractors.synthesize_pages(md)
    assert "[PAGE 1]" in result
    assert "[PAGE 2]" in result
    # 第二章应在第二页
    parts = result.split("[PAGE 2]")
    assert "第二章" in parts[1]


def test_synthesize_pages_short_sections_merge():
    """多个短 section 应合并到同一页，直到达到 min_page_chars"""
    md = "# A\n\n短\n\n# B\n\n短\n\n# C\n\n短"
    result = extractors.synthesize_pages(md)
    # 三个短 section 应合并在 PAGE 1
    assert "[PAGE 1]" in result
    assert "[PAGE 2]" not in result
    assert "# A" in result
    assert "# B" in result
    assert "# C" in result


def test_synthesize_pages_h3_does_not_split():
    """### 不应触发新页切分（只切 # 和 ##）"""
    md = "# 标题\n\n正文 " + "x" * 1600 + "\n\n### 子标题\n\n更多内容"
    result = extractors.synthesize_pages(md)
    # ### 子标题应与父节在同一页
    assert "[PAGE 1]" in result


def test_synthesize_pages_oversized_section_splits_at_paragraph():
    """超长 section（> 4 * min_page_chars）按段落切分"""
    # 构造 8000 字符的单 section（无标题）
    para = "段落内容。" * 50  # ~250 字符/段
    md = "\n\n".join([para] * 32)  # ~8000 字符
    result = extractors.synthesize_pages(md)
    # 应切分成多页
    assert "[PAGE 1]" in result
    assert "[PAGE 2]" in result


def test_synthesize_pages_leading_content_before_first_heading():
    """标题前的引导内容应作为独立 section"""
    md = "前言内容\n\n# 第一章\n\n正文"
    result = extractors.synthesize_pages(md)
    assert "前言内容" in result
    assert "# 第一章" in result


def test_synthesize_pages_custom_min_chars():
    """可调 min_page_chars 参数"""
    md = "# A\n\n" + "x" * 100 + "\n\n# B\n\n" + "y" * 100
    # 默认 1500：两段都短，合并为 1 页
    result_default = extractors.synthesize_pages(md)
    assert "[PAGE 2]" not in result_default

    # min=50：每段超 50，各成一页
    result_small = extractors.synthesize_pages(md, min_page_chars=50)
    assert "[PAGE 2]" in result_small


def test_synthesize_pages_first_page_always_page_1():
    """首行强制 [PAGE 1]"""
    md = "# 标题\n\n正文"
    result = extractors.synthesize_pages(md)
    assert result.startswith("[PAGE 1]")


# ============ _count_pages 测试 ============

def test_count_pages_empty():
    assert extractors._count_pages("") == 0
    assert extractors._count_pages("无标记的文本") == 0


def test_count_pages_normal():
    md = "[PAGE 1]\n\n内容\n\n[PAGE 2]\n\n更多"
    assert extractors._count_pages(md) == 2


def test_count_pages_with_text_after():
    md = "intro\n[PAGE 1]\nbody\n[PAGE 2]\nend"
    assert extractors._count_pages(md) == 2


# ============ extract_document 分发器测试 ============

def test_dispatch_unsupported_format_returns_error(tmp_path):
    fake = tmp_path / "test.zip"
    fake.write_bytes(b"fake")
    result = extractors.extract_document(str(fake))
    assert result["status"] == "error"
    assert "不支持" in result["message"]


def test_dispatch_nonexistent_file_returns_error(tmp_path):
    result = extractors.extract_document(str(tmp_path / "nonexistent.docx"))
    assert result["status"] == "error"
    assert "不存在" in result["message"]


def test_dispatch_docx_routes_to_extract_docx(tmp_path, monkeypatch):
    """扩展名 .docx 应路由到 extract_docx"""
    fake = tmp_path / "test.docx"
    fake.write_bytes(b"fake docx")

    called = {}

    def fake_extract(path, output_dir, strip_images=False):
        called["path"] = path
        called["output_dir"] = output_dir
        called["strip_images"] = strip_images
        return {"status": "success", "stem": path.stem}

    monkeypatch.setitem(extractors.EXTRACTORS, ".docx", fake_extract)
    result = extractors.extract_document(str(fake))
    assert result["status"] == "success"
    assert called["path"] == fake


def test_dispatch_txt_routes_to_extract_txt(tmp_path, monkeypatch):
    fake = tmp_path / "test.txt"
    fake.write_text("hello", encoding="utf-8")

    called = {}

    def fake_extract(path, output_dir, strip_images=False):
        called["ext"] = path.suffix
        return {"status": "success"}

    monkeypatch.setitem(extractors.EXTRACTORS, ".txt", fake_extract)
    extractors.extract_document(str(fake))
    assert called["ext"] == ".txt"


def test_dispatch_md_and_markdown_both_route_to_same(tmp_path, monkeypatch):
    """`.md` 和 `.markdown` 都应路由到 markdown 提取器"""
    md_file = tmp_path / "test.md"
    md_file.write_text("hello", encoding="utf-8")
    markdown_file = tmp_path / "test.markdown"
    markdown_file.write_text("hello", encoding="utf-8")

    called = []

    def fake_extract(path, output_dir, strip_images=False):
        called.append(path.suffix)
        return {"status": "success"}

    monkeypatch.setitem(extractors.EXTRACTORS, ".md", fake_extract)
    monkeypatch.setitem(extractors.EXTRACTORS, ".markdown", fake_extract)
    extractors.extract_document(str(md_file))
    extractors.extract_document(str(markdown_file))
    assert ".md" in called
    assert ".markdown" in called


def test_dispatch_uses_default_output_dir(tmp_path, monkeypatch):
    """未传 output_dir 时，默认创建 Review - <stem>/ 目录"""
    fake = tmp_path / "test.docx"
    fake.write_bytes(b"fake")

    def fake_extract(path, output_dir, strip_images=False):
        return {"status": "success", "output_dir": str(output_dir)}

    monkeypatch.setitem(extractors.EXTRACTORS, ".docx", fake_extract)
    result = extractors.extract_document(str(fake))
    assert "Review - test" in result["output_dir"]


def test_dispatch_passes_strip_images(tmp_path, monkeypatch):
    """strip_images=True 应透传到 extractor"""
    fake = tmp_path / "test.docx"
    fake.write_bytes(b"fake")

    called = {}

    def fake_extract(path, output_dir, strip_images=False):
        called["strip_images"] = strip_images
        return {"status": "success"}

    monkeypatch.setitem(extractors.EXTRACTORS, ".docx", fake_extract)
    extractors.extract_document(str(fake), strip_images=True)
    assert called["strip_images"] is True


def test_strip_base64_images_removes_truncated_placeholders():
    """MarkItDown 截断占位符 ![](data:image/jpeg;base64...) 应替换为 <!-- image -->"""
    md = "前面文字\n\n![](data:image/jpeg;base64...)\n\n后面文字"
    from pathlib import Path
    result, count = extractors._strip_base64_images(md, Path("/tmp/test_imgs"))
    assert count == 0  # 截断占位符不算真实图片
    assert "<!-- image -->" in result
    assert "data:image" not in result


def test_strip_base64_images_saves_real_base64(tmp_path):
    """完整 base64 图片应存为独立文件"""
    import base64
    # 1x1 像素 PNG 的 base64
    tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    md = f"![](data:image/png;base64,{tiny_png_b64})"
    result, count = extractors._strip_base64_images(md, tmp_path / "images")
    assert count == 1
    assert "images/img_001.png" in result
    assert (tmp_path / "images" / "img_001.png").exists()


# ============ extract_docx/txt/markdown 测试（mock 底层转换）============

def _mock_markitdown_return(monkeypatch, text: str):
    """让 _markitdown_convert 返回固定文本（用于 DOCX 测试）"""
    monkeypatch.setattr(
        extractors, "_markitdown_convert", lambda path: text
    )


def _mock_decode_text_file(monkeypatch, text: str, encoding: str = "utf-8"):
    """让 _decode_text_file 返回固定文本（用于 TXT/MD 测试）"""
    monkeypatch.setattr(
        extractors, "_decode_text_file", lambda path: (text, encoding)
    )


def test_extract_docx_returns_correct_shape(tmp_path, monkeypatch):
    _mock_markitdown_return(monkeypatch, "# 标题\n\n正文内容")
    fake = tmp_path / "test.docx"
    fake.write_bytes(b"fake")

    result = extractors.extract_docx(fake, tmp_path / "out")

    assert result["status"] == "success"
    assert result["stem"] == "test"
    assert result["source_path"] == str(fake)
    assert "markdown_path" in result
    assert "json_path" in result
    assert "pages" in result
    assert result["extractor"] == "markitdown"
    assert result["format"] == "docx"


def test_extract_docx_writes_markdown_with_page_markers(tmp_path, monkeypatch):
    _mock_markitdown_return(monkeypatch, "# 标题\n\n正文内容")
    fake = tmp_path / "test.docx"
    fake.write_bytes(b"fake")

    result = extractors.extract_docx(fake, tmp_path / "out")
    md = Path(result["markdown_path"]).read_text(encoding="utf-8")
    assert "[PAGE 1]" in md


def test_extract_docx_writes_json_sidecar(tmp_path, monkeypatch):
    _mock_markitdown_return(monkeypatch, "# 标题\n\n正文")
    fake = tmp_path / "test.docx"
    fake.write_bytes(b"fake")

    result = extractors.extract_docx(fake, tmp_path / "out")
    data = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert data["schema_name"] == "MultiFormatDocument"
    assert data["name"] == "test"
    assert data["extractor"] == "markitdown"
    assert "pages" in data


def test_extract_docx_handles_markitdown_failure(tmp_path, monkeypatch):
    def boom(path):
        raise RuntimeError("DOCX 损坏")

    monkeypatch.setattr(extractors, "_markitdown_convert", boom)
    fake = tmp_path / "bad.docx"
    fake.write_bytes(b"bad")

    result = extractors.extract_docx(fake, tmp_path / "out")
    assert result["status"] == "error"
    assert "DOCX 提取失败" in result["message"]


def test_extract_txt_returns_correct_shape(tmp_path, monkeypatch):
    _mock_decode_text_file(monkeypatch, "纯文本内容", "utf-8")
    fake = tmp_path / "test.txt"
    fake.write_text("fake", encoding="utf-8")

    result = extractors.extract_txt(fake, tmp_path / "out")
    assert result["status"] == "success"
    assert result["format"] == "txt"
    assert result["stem"] == "test"
    assert result["extractor"] == "charset-normalizer"
    assert result["encoding"] == "utf-8"


def test_extract_markdown_returns_correct_shape(tmp_path, monkeypatch):
    _mock_decode_text_file(monkeypatch, "# MD 标题\n\n内容", "utf-8")
    fake = tmp_path / "test.md"
    fake.write_text("fake", encoding="utf-8")

    result = extractors.extract_markdown(fake, tmp_path / "out")
    assert result["status"] == "success"
    assert result["format"] == "markdown"
    assert result["stem"] == "test"
    assert result["extractor"] == "charset-normalizer"


def test_extract_markdown_preserves_headings(tmp_path, monkeypatch):
    """markdown 输入的标题应在输出中保留"""
    _mock_decode_text_file(monkeypatch, "# H1\n\n正文\n\n## H2\n\n更多", "utf-8")
    fake = tmp_path / "test.md"
    fake.write_text("fake", encoding="utf-8")

    result = extractors.extract_markdown(fake, tmp_path / "out")
    md = Path(result["markdown_path"]).read_text(encoding="utf-8")
    assert "# H1" in md
    assert "## H2" in md


# ============ write_extracted_output 测试 ============

def test_write_extracted_output_creates_files(tmp_path):
    out = tmp_path / "out"
    src = tmp_path / "src.txt"

    result = extractors.write_extracted_output(
        output_dir=out,
        stem="src",
        markdown="[PAGE 1]\n\nbody",
        source_path=src,
        pages=1,
        extra_meta={"extractor": "markitdown", "format": "txt"},
    )

    assert (out / "extracted_content.md").exists()
    assert (out / "extracted_content.json").exists()
    assert result["status"] == "success"
    assert result["pages"] == 1
    assert result["stem"] == "src"


def test_write_extracted_output_json_has_pages_dict(tmp_path):
    out = tmp_path / "out"
    src = tmp_path / "src.txt"

    extractors.write_extracted_output(
        output_dir=out,
        stem="src",
        markdown="[PAGE 1]\n\nbody",
        source_path=src,
        pages=3,
    )

    data = json.loads((out / "extracted_content.json").read_text(encoding="utf-8"))
    assert data["page_count"] == 3
    assert "1" in data["pages"]
    assert "2" in data["pages"]
    assert "3" in data["pages"]


# ============ 契约一致性：返回 dict 与 extract_pdf 对齐 ============

REQUIRED_KEYS = {"status", "source_path", "output_dir", "markdown_path",
                 "json_path", "pages", "stem"}


def test_extract_docx_dict_shape_matches_contract(tmp_path, monkeypatch):
    """extract_docx 返回 dict 必须包含下游所需的所有字段"""
    _mock_markitdown_return(monkeypatch, "# 标题\n\n正文")
    fake = tmp_path / "test.docx"
    fake.write_bytes(b"fake")

    result = extractors.extract_docx(fake, tmp_path / "out")
    assert result["status"] == "success"
    assert REQUIRED_KEYS.issubset(result.keys())


def test_extract_txt_dict_shape_matches_contract(tmp_path, monkeypatch):
    _mock_markitdown_return(monkeypatch, "纯文本")
    fake = tmp_path / "test.txt"
    fake.write_text("fake", encoding="utf-8")

    result = extractors.extract_txt(fake, tmp_path / "out")
    assert result["status"] == "success"
    assert REQUIRED_KEYS.issubset(result.keys())


def test_extract_markdown_dict_shape_matches_contract(tmp_path, monkeypatch):
    _mock_markitdown_return(monkeypatch, "# 标题\n\n正文")
    fake = tmp_path / "test.md"
    fake.write_text("fake", encoding="utf-8")

    result = extractors.extract_markdown(fake, tmp_path / "out")
    assert result["status"] == "success"
    assert REQUIRED_KEYS.issubset(result.keys())


# ============ GBK 编码场景模拟 ============

def test_extract_txt_handles_gbk_encoding(tmp_path, monkeypatch):
    """模拟 GBK 编码 TXT：charset-normalizer 返回正确解码的中文"""
    chinese_text = "# 第一章 函数\n\n这是中文内容。"
    _mock_decode_text_file(monkeypatch, chinese_text, "gb18030")

    # 写一个真实的 GBK 文件（虽然 _decode_text_file 被 mock，但文件要存在）
    gbk_file = tmp_path / "chinese.txt"
    gbk_file.write_bytes("中文内容".encode("gbk"))

    result = extractors.extract_txt(gbk_file, tmp_path / "out")
    assert result["status"] == "success"
    assert result["encoding"] == "gb18030"
    md = Path(result["markdown_path"]).read_text(encoding="utf-8")
    assert "中文内容" in md or "第一章" in md
    assert "[PAGE 1]" in md


def test_extract_txt_real_gbk_file_end_to_end(tmp_path):
    """真实 GBK 文件端到端测试：charset-normalizer 实际检测"""
    chinese_text = "# 第一章 函数\n\n这是中文内容，用于测试 GBK 编码检测。"
    gbk_file = tmp_path / "chinese.txt"
    gbk_file.write_bytes(chinese_text.encode("gbk"))

    result = extractors.extract_txt(gbk_file, tmp_path / "out")
    assert result["status"] == "success"
    assert result["encoding"] in ("gbk", "gb2312", "gb18030")  # charset-normalizer 可能返回任一
    md = Path(result["markdown_path"]).read_text(encoding="utf-8")
    assert "第一章" in md
    assert "中文内容" in md
    assert "[PAGE 1]" in md
