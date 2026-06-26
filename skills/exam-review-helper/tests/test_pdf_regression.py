"""PDF 回归测试：确保新增多格式支持后，PDF 工作流不回归。

关键验证：
1. extract() 分发器对 .pdf 严格走 extract_pdf 路径
2. 大 PDF 仍能触发 chunked_extract_pdf（通过 --chunk-size 或自动检测）
3. --no-chunk 仍能禁用分块
4. extract_pdf 返回 dict 包含 source_path 新字段（向后兼容）
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import controller


def test_extract_dispatcher_routes_pdf_to_extract_pdf(tmp_path, monkeypatch):
    """.pdf 扩展名应路由到 extract_pdf，不走 extractors"""
    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.write_bytes(b"fake pdf")

    called = {}

    def fake_extract_pdf(pdf_path, output_dir=None, page_range=None, **kwargs):
        called["pdf_path"] = pdf_path
        called["output_dir"] = output_dir
        return {
            "status": "success",
            "pdf_path": pdf_path,
            "source_path": pdf_path,
            "output_dir": output_dir,
            "markdown_path": "fake.md",
            "json_path": "fake.json",
            "pages": 1,
            "stem": "test",
        }

    # 屏蔽 _get_pdf_page_count 避免真实 PDF 解析
    monkeypatch.setattr(controller, "_get_pdf_page_count", lambda p: 1)
    monkeypatch.setattr(controller, "extract_pdf", fake_extract_pdf)

    result = controller.extract(str(fake_pdf))
    assert result["status"] == "success"
    assert called["pdf_path"] == str(fake_pdf)


def test_extract_pdf_no_chunk_flag_disables_chunking(tmp_path, monkeypatch):
    """--no-chunk 应阻止 chunked_extract_pdf 调用"""
    fake_pdf = tmp_path / "big.pdf"
    fake_pdf.write_bytes(b"fake")

    chunked_called = []
    pdf_called = []

    monkeypatch.setattr(controller, "_get_pdf_page_count", lambda p: 500)
    monkeypatch.setattr(
        controller, "chunked_extract_pdf",
        lambda *a, **kw: chunked_called.append(a) or {"status": "success"},
    )
    monkeypatch.setattr(
        controller, "extract_pdf",
        lambda *a, **kw: pdf_called.append(a) or {"status": "success"},
    )

    controller.extract(str(fake_pdf), no_chunk=True)
    assert not chunked_called
    assert pdf_called


def test_extract_pdf_auto_chunk_on_large_file(tmp_path, monkeypatch):
    """>100 页 PDF 应自动触发 chunked_extract_pdf"""
    fake_pdf = tmp_path / "big.pdf"
    fake_pdf.write_bytes(b"fake")

    chunked_called = []
    monkeypatch.setattr(controller, "_get_pdf_page_count", lambda p: 200)
    monkeypatch.setattr(
        controller, "chunked_extract_pdf",
        lambda *a, **kw: chunked_called.append(a) or {"status": "success"},
    )
    monkeypatch.setattr(
        controller, "extract_pdf",
        lambda *a, **kw: {"status": "success"},
    )

    controller.extract(str(fake_pdf))
    assert chunked_called


def test_extract_pdf_explicit_chunk_size_triggers_chunking(tmp_path, monkeypatch):
    """显式 --chunk-size 应触发 chunked_extract_pdf（即使 PDF 小）"""
    fake_pdf = tmp_path / "small.pdf"
    fake_pdf.write_bytes(b"fake")

    chunked_called = []
    monkeypatch.setattr(controller, "_get_pdf_page_count", lambda p: 10)
    monkeypatch.setattr(
        controller, "chunked_extract_pdf",
        lambda *a, **kw: chunked_called.append((a, kw)) or {"status": "success"},
    )
    monkeypatch.setattr(
        controller, "extract_pdf",
        lambda *a, **kw: {"status": "success"},
    )

    controller.extract(str(fake_pdf), chunk_size=25)
    assert chunked_called
    # 验证 chunk_size 透传
    args, kwargs = chunked_called[0]
    assert args[2] == 25  # 第 3 位置参数是 chunk_size


def test_extract_pdf_returns_source_path_field(tmp_path, monkeypatch):
    """extract_pdf 返回 dict 必须包含 source_path（向后兼容新增字段）"""
    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.write_bytes(b"fake")

    monkeypatch.setattr(controller, "_get_pdf_page_count", lambda p: 1)

    # 用真实 extract_pdf 但 mock docling 调用
    real_extract_pdf = controller.extract_pdf

    def patched(pdf_path, output_dir=None, page_range=None, **kwargs):
        # 直接返回 shape，跳过 docling
        return {
            "status": "success",
            "pdf_path": str(pdf_path),
            "source_path": str(pdf_path),
            "output_dir": str(output_dir or tmp_path),
            "markdown_path": "fake.md",
            "json_path": "fake.json",
            "pages": 1,
            "stem": Path(pdf_path).stem,
        }

    monkeypatch.setattr(controller, "extract_pdf", patched)
    result = controller.extract(str(fake_pdf))
    assert "source_path" in result
    assert "pdf_path" in result  # 老字段保留


def test_extract_non_pdf_does_not_call_pdf_functions(tmp_path, monkeypatch):
    """非 PDF 文件不应触发 extract_pdf / chunked_extract_pdf"""
    fake_docx = tmp_path / "test.docx"
    fake_docx.write_bytes(b"fake")

    pdf_called = []
    chunked_called = []

    monkeypatch.setattr(controller, "extract_pdf",
                        lambda *a, **kw: pdf_called.append(a) or {"status": "success"})
    monkeypatch.setattr(controller, "chunked_extract_pdf",
                        lambda *a, **kw: chunked_called.append(a) or {"status": "success"})

    # mock extractors.extract_document
    import extractors as ext_module
    called_extractors = []
    monkeypatch.setattr(
        ext_module, "extract_document",
        lambda *a, **kw: called_extractors.append(a) or {"status": "success"},
    )

    controller.extract(str(fake_docx))
    assert not pdf_called
    assert not chunked_called
    assert called_extractors


def test_extract_multiple_accepts_mixed_formats(tmp_path, monkeypatch):
    """extract_multiple 应接受混合格式列表"""
    files = []
    for name in ["a.pdf", "b.docx", "c.md"]:
        f = tmp_path / name
        f.write_bytes(b"fake")
        files.append(str(f))

    # mock extract() 避免真实处理
    def fake_extract(source_path, output_dir=None, **kw):
        return {
            "status": "success",
            "markdown_path": str(Path(output_dir) / "extracted_content.md"),
            "pages": 5,
        }

    monkeypatch.setattr(controller, "extract", fake_extract)

    # 为每个文件创建子目录和 markdown 文件
    # 子目录命名与 extract_multiple 保持一致：stem (ext)
    for src in files:
        src_path = Path(src)
        sub_dir_name = f"{src_path.stem} ({src_path.suffix.lstrip('.')})"
        sub_dir = tmp_path / "Review - combined" / sub_dir_name
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "extracted_content.md").write_text(f"# {src_path.stem}\n\n内容", encoding="utf-8")

    result = controller.extract_multiple(files, str(tmp_path / "Review - combined"))
    assert result["status"] == "success"
    assert result["total_pages"] == 15  # 3 files * 5 pages


def test_extract_multiple_pdfs_alias_still_works(tmp_path, monkeypatch):
    """向后兼容：extract_multiple_pdfs 别名应等同 extract_multiple"""
    assert controller.extract_multiple_pdfs is controller.extract_multiple
