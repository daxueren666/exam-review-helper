"""pytest 配置和 fixtures。"""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"


@pytest.fixture
def sample_pdf_path():
    """样本 PDF 路径 fixture。需要 test_data/sample.pdf 存在，否则跳过。"""
    test_pdf = TEST_DATA_DIR / "sample.pdf"
    if test_pdf.exists():
        return str(test_pdf)
    pytest.skip("测试 PDF 不存在：test_data/sample.pdf")


@pytest.fixture
def sample_docx_path():
    """样本 DOCX 路径 fixture（test_data/sample.docx，仓库内置）。"""
    p = TEST_DATA_DIR / "sample.docx"
    if p.exists():
        return p
    pytest.skip(f"测试 DOCX 不存在：{p}")


@pytest.fixture
def sample_txt_gbk_path():
    """样本 GBK 编码 TXT fixture（test_data/sample_gbk.txt，仓库内置）。"""
    p = TEST_DATA_DIR / "sample_gbk.txt"
    if p.exists():
        return p
    pytest.skip(f"测试 GBK TXT 不存在：{p}")


@pytest.fixture
def sample_md_path():
    """样本 Markdown fixture（test_data/sample.md，仓库内置）。"""
    p = TEST_DATA_DIR / "sample.md"
    if p.exists():
        return p
    pytest.skip(f"测试 MD 不存在：{p}")


@pytest.fixture
def temp_output_dir(tmp_path):
    """临时输出目录 fixture。"""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return str(output_dir)
