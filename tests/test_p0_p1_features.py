"""P0-P1 新功能测试：OCR 纠错、公式增强、流水线编排。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import ocr_corrector
import enhance_formulas


# ============ OCR 纠错测试 ============

def test_ocr_corrector_fixes_known_errors():
    """已知 OCR 误判应被纠正"""
    text = "巳知函数 f(x) 在 x=0 处连续，巳经证明。"
    result, corrections = ocr_corrector.correct_ocr_errors(text)
    assert "已知" in result
    assert "已经" in result
    assert "巳知" not in result
    assert "巳经" not in result
    assert len(corrections) >= 2


def test_ocr_corrector_preserves_correct_text():
    """正确的文本不应被改动"""
    text = "已知函数已经定义好，未来将使用。"
    result, corrections = ocr_corrector.correct_ocr_errors(text)
    # "已知""已经"是正确的，不应改
    assert "已知" in result
    assert "已经" in result
    # "未来"含"未"但不应被改成"末"
    assert "未来" in result


def test_ocr_corrector_context_aware():
    """上下文相关纠错：数字上下文的'干'→'千'"""
    text = "约5干3百人"
    result, _ = ocr_corrector.correct_ocr_errors(text)
    assert "5千3百" in result


def test_ocr_corrector_no_false_positive_on_gan():
    """'干'在非数字上下文不应被改（如'干事'）"""
    text = "他是干事处的干事"
    result, _ = ocr_corrector.correct_ocr_errors(text)
    assert "干事" in result


def test_has_ocr_markers_detects_ocr_text():
    """检测 OCR 痕迹"""
    assert ocr_corrector.has_ocr_markers("巳知函数") is True
    assert ocr_corrector.has_ocr_markers("卽使如此") is True
    assert ocr_corrector.has_ocr_markers("正常中文文本") is False


def test_ocr_corrector_empty_input():
    """空输入"""
    result, corrections = ocr_corrector.correct_ocr_errors("")
    assert result == ""
    assert corrections == []


# ============ 公式增强测试 ============

def test_scan_formula_placeholders(tmp_path):
    """扫描公式占位符"""
    md = """[PAGE 1]

正文

<!-- formula-not-decoded -->

更多正文

[PAGE 2]

<!-- formula-not-decoded -->

<!-- formula-not-decoded -->
"""
    md_path = tmp_path / "extracted_content.md"
    md_path.write_text(md, encoding="utf-8")

    counts = enhance_formulas.scan_formula_placeholders(md_path)
    assert counts == {1: 1, 2: 2}


def test_scan_formula_placeholders_no_markers(tmp_path):
    """无占位符时返回空 dict"""
    md = "[PAGE 1]\n\n纯文本无公式"
    md_path = tmp_path / "extracted_content.md"
    md_path.write_text(md, encoding="utf-8")

    counts = enhance_formulas.scan_formula_placeholders(md_path)
    assert counts == {}


def test_enhance_formulas_main_no_placeholders(tmp_path):
    """无占位符时输出空 hints"""
    md_path = tmp_path / "extracted_content.md"
    md_path.write_text("[PAGE 1]\n纯文本", encoding="utf-8")

    # 模拟 main 的核心逻辑
    counts = enhance_formulas.scan_formula_placeholders(md_path)
    hints = {
        "total_placeholders": sum(counts.values()),
        "pages_with_formulas": counts,
        "ocr_results": {},
    }
    assert hints["total_placeholders"] == 0
    assert hints["pages_with_formulas"] == {}


# ============ 图片剥离测试（已在 test_extractors.py 覆盖，这里补集成测试）============

def test_strip_images_cli_flag_exists():
    """--strip-images CLI 选项应存在"""
    import controller
    # 检查 extract 函数签名包含 strip_images
    import inspect
    sig = inspect.signature(controller.extract)
    assert "strip_images" in sig.parameters
    assert "ocr_correct" in sig.parameters


# ============ 流水线编排测试 ============

def test_run_pipeline_detect_mode_stem(tmp_path):
    """自动检测理工科模式"""
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    import run_pipeline

    # 含公式占位符 → 理工科
    md = "[PAGE 1]\n<!-- formula-not-decoded -->\n正文"
    md_path = tmp_path / "test.md"
    md_path.write_text(md, encoding="utf-8")
    assert run_pipeline.detect_mode(md_path) == "stem"


def test_run_pipeline_detect_mode_liberal(tmp_path):
    """自动检测文科模式"""
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    import run_pipeline
    import importlib
    importlib.reload(run_pipeline)

    # 含文科关键词 → 文科
    md = "[PAGE 1]\n毛泽东思想的历史地位和理论意义，观点明确。"
    md_path = tmp_path / "test.md"
    md_path.write_text(md, encoding="utf-8")
    assert run_pipeline.detect_mode(md_path) == "liberal"


def test_run_pipeline_check_checkpoint_empty(tmp_path):
    """无 checkpoint 时返回 checkpoint_exists=False"""
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    import run_pipeline
    import importlib
    importlib.reload(run_pipeline)

    result = run_pipeline.check_checkpoint(tmp_path)
    assert result["checkpoint_exists"] is False
    assert result["completed_segments"] == []


def test_run_pipeline_check_checkpoint_with_files(tmp_path):
    """有 checkpoint 文件时返回已完成段（文件需含 segment_id 字段才算合法）"""
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    import run_pipeline
    import importlib
    importlib.reload(run_pipeline)

    ckpt_dir = tmp_path / ".checkpoint"
    ckpt_dir.mkdir()
    # 合法的 segment notes：含 segment_id
    (ckpt_dir / "notes_seg-001.json").write_text(
        json.dumps({"segment_id": "seg-001", "concepts": []}), encoding="utf-8"
    )
    (ckpt_dir / "notes_seg-002.json").write_text(
        json.dumps({"segment_id": "seg-002", "concepts": []}), encoding="utf-8"
    )
    # 损坏的文件：空 dict 和半截 JSON——不应被计入
    (ckpt_dir / "notes_seg-003.json").write_text("{}", encoding="utf-8")
    (ckpt_dir / "notes_seg-004.json").write_text("{broken", encoding="utf-8")

    result = run_pipeline.check_checkpoint(tmp_path)
    assert result["checkpoint_exists"] is True
    # 只 001/002 算合法，003/004 被跳过
    assert len(result["completed_segments"]) == 2
    assert "notes_seg-001" in result["completed_segments"]
    assert "notes_seg-002" in result["completed_segments"]
