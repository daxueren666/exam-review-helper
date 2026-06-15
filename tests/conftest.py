"""pytest 配置和 fixtures。"""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def sample_pdf_path():
    """样本 PDF 路径 fixture。需要 test_data/sample.pdf 存在，否则跳过。"""
    test_pdf = Path(__file__).parent.parent / "test_data" / "sample.pdf"
    if test_pdf.exists():
        return str(test_pdf)
    pytest.skip("测试 PDF 不存在：test_data/sample.pdf")


@pytest.fixture
def temp_output_dir(tmp_path):
    """临时输出目录 fixture。"""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return str(output_dir)
