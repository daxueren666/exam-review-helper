"""测试 run_evals.py 的核心逻辑。"""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_evals  # noqa: E402

SKILL_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# evals.json 合法性
# ---------------------------------------------------------------------------

def test_evals_json_is_valid_and_has_9_evals():
    """evals.json 是合法 JSON，且包含 9 个 eval。"""
    data = run_evals.load_evals()
    assert "skill_name" in data
    assert "evals" in data
    evals = data["evals"]
    assert len(evals) == 9, f"期望 9 个 eval，实际 {len(evals)}"
    ids = [e["id"] for e in evals]
    assert ids == [1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_evals_json_assertions_have_type():
    """所有 assertion 都有 type 字段且 type 合法。"""
    valid_types = {
        "dir_exists", "file_exists", "file_contains", "file_not_contains",
        "json_field_equals", "no_dir_matching",
    }
    data = run_evals.load_evals()
    for ev in data["evals"]:
        for a in ev["assertions"]:
            assert "type" in a, f"eval {ev['id']} assertion {a.get('name')} 缺 type"
            assert a["type"] in valid_types, f"未知 type: {a['type']}"


def test_evals_json_preserves_setup_notes():
    """_setup_notes 字段保留。"""
    data = run_evals.load_evals()
    assert "_setup_notes" in data
    notes = data["_setup_notes"]
    assert "test_files" in notes
    assert "negative_evals" in notes
    assert "mixed_format" in notes


def test_negative_evals_use_negative_assertions():
    """eval 8/9 用 no_dir_matching / file_not_contains。"""
    data = run_evals.load_evals()
    for ev in data["evals"]:
        if ev["id"] in (8, 9):
            types = {a["type"] for a in ev["assertions"]}
            assert "no_dir_matching" in types or "file_not_contains" in types, \
                f"eval {ev['id']} 应有负向 assertion"


# ---------------------------------------------------------------------------
# dir_exists
# ---------------------------------------------------------------------------

def test_dir_exists_pass(tmp_path):
    (tmp_path / "Review - sample").mkdir()
    a = {"name": "x", "type": "dir_exists", "path": "Review - sample/"}
    passed, msg = run_evals.run_assertion(a, tmp_path)
    assert passed, msg


def test_dir_exists_fail(tmp_path):
    a = {"name": "x", "type": "dir_exists", "path": "Review - missing/"}
    passed, msg = run_evals.run_assertion(a, tmp_path)
    assert not passed
    assert "不存在" in msg


# ---------------------------------------------------------------------------
# file_exists
# ---------------------------------------------------------------------------

def test_file_exists_pass(tmp_path):
    (tmp_path / "f.txt").write_text("hello", encoding="utf-8")
    a = {"name": "x", "type": "file_exists", "path": "f.txt"}
    passed, _ = run_evals.run_assertion(a, tmp_path)
    assert passed


def test_file_exists_nonempty_fail(tmp_path):
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    a = {"name": "x", "type": "file_exists", "path": "empty.txt", "nonempty": True}
    passed, msg = run_evals.run_assertion(a, tmp_path)
    assert not passed
    assert "空" in msg


# ---------------------------------------------------------------------------
# file_contains / file_not_contains
# ---------------------------------------------------------------------------

def test_file_contains_pass(tmp_path):
    (tmp_path / "r.html").write_text("hello MathJax world", encoding="utf-8")
    a = {"name": "x", "type": "file_contains", "path": "r.html", "contains": "MathJax"}
    passed, _ = run_evals.run_assertion(a, tmp_path)
    assert passed


def test_file_contains_min_count(tmp_path):
    (tmp_path / "r.md").write_text("[PAGE 1] a [PAGE 2] b [PAGE 3] c", encoding="utf-8")
    a = {"name": "x", "type": "file_contains", "path": "r.md",
         "contains": "[PAGE", "min_count": 2}
    passed, _ = run_evals.run_assertion(a, tmp_path)
    assert passed


def test_file_contains_min_count_fail(tmp_path):
    (tmp_path / "r.md").write_text("[PAGE 1] only one", encoding="utf-8")
    a = {"name": "x", "type": "file_contains", "path": "r.md",
         "contains": "[PAGE", "min_count": 2}
    passed, msg = run_evals.run_assertion(a, tmp_path)
    assert not passed


def test_file_not_contains_pass(tmp_path):
    (tmp_path / "f.txt").write_text("clean content", encoding="utf-8")
    a = {"name": "x", "type": "file_not_contains", "path": "f.txt",
         "not_contains": "secret"}
    passed, _ = run_evals.run_assertion(a, tmp_path)
    assert passed


def test_file_not_contains_fail(tmp_path):
    (tmp_path / "f.txt").write_text("has secret data", encoding="utf-8")
    a = {"name": "x", "type": "file_not_contains", "path": "f.txt",
         "not_contains": "secret"}
    passed, _ = run_evals.run_assertion(a, tmp_path)
    assert not passed


def test_file_not_contains_missing_file_passes(tmp_path):
    """文件不存在视为不含——通过。"""
    a = {"name": "x", "type": "file_not_contains", "path": "missing.txt",
         "not_contains": "x"}
    passed, _ = run_evals.run_assertion(a, tmp_path)
    assert passed


# ---------------------------------------------------------------------------
# json_field_equals
# ---------------------------------------------------------------------------

def test_json_field_equals_top_level(tmp_path):
    (tmp_path / "k.json").write_text(
        json.dumps({"extractor": "markitdown", "format": "docx"}),
        encoding="utf-8",
    )
    a = {"name": "x", "type": "json_field_equals", "path": "k.json",
         "field": "extractor", "equals": "markitdown"}
    passed, _ = run_evals.run_assertion(a, tmp_path)
    assert passed


def test_json_field_equals_nested(tmp_path):
    (tmp_path / "k.json").write_text(
        json.dumps({"metadata": {"format": "docx"}}),
        encoding="utf-8",
    )
    a = {"name": "x", "type": "json_field_equals", "path": "k.json",
         "field": "metadata.format", "equals": "docx"}
    passed, _ = run_evals.run_assertion(a, tmp_path)
    assert passed


def test_json_field_equals_fail(tmp_path):
    (tmp_path / "k.json").write_text(
        json.dumps({"extractor": "docling"}), encoding="utf-8")
    a = {"name": "x", "type": "json_field_equals", "path": "k.json",
         "field": "extractor", "equals": "markitdown"}
    passed, msg = run_evals.run_assertion(a, tmp_path)
    assert not passed
    assert "期望" in msg


def test_json_field_equals_missing_field(tmp_path):
    (tmp_path / "k.json").write_text(json.dumps({}), encoding="utf-8")
    a = {"name": "x", "type": "json_field_equals", "path": "k.json",
         "field": "missing", "equals": "x"}
    passed, _ = run_evals.run_assertion(a, tmp_path)
    assert not passed


# ---------------------------------------------------------------------------
# no_dir_matching
# ---------------------------------------------------------------------------

def test_no_dir_matching_pass(tmp_path):
    """eval-dir 下没有匹配 pattern 的目录——通过。"""
    (tmp_path / "other").mkdir()
    a = {"name": "x", "type": "no_dir_matching", "pattern": "Review - *"}
    passed, _ = run_evals.run_assertion(a, tmp_path)
    assert passed


def test_no_dir_matching_fail(tmp_path):
    """eval-dir 下存在匹配 pattern 的目录——失败（负向 eval）。"""
    (tmp_path / "Review - my_novel").mkdir()
    a = {"name": "x", "type": "no_dir_matching", "pattern": "Review - my_novel*"}
    passed, msg = run_evals.run_assertion(a, tmp_path)
    assert not passed
    assert "Review - my_novel" in msg


# ---------------------------------------------------------------------------
# run_eval 集成
# ---------------------------------------------------------------------------

def test_run_eval_all_pass(tmp_path):
    (tmp_path / "Review - sample").mkdir()
    (tmp_path / "Review - sample" / "extracted_content.md").write_text(
        "[PAGE 1] hi", encoding="utf-8")
    (tmp_path / "Review - sample" / "Review.html").write_text(
        "MathJax here", encoding="utf-8")
    ev = {
        "id": 99, "name": "test",
        "assertions": [
            {"name": "a", "type": "dir_exists", "path": "Review - sample/"},
            {"name": "b", "type": "file_contains",
             "path": "Review - sample/extracted_content.md", "contains": "[PAGE"},
            {"name": "c", "type": "file_contains",
             "path": "Review - sample/Review.html", "contains": "MathJax"},
        ],
    }
    result = run_evals.run_eval(ev, tmp_path)
    assert result["all_passed"] is True
    assert result["passed"] == 3
    assert result["total"] == 3


def test_run_eval_partial_fail(tmp_path):
    (tmp_path / "Review - sample").mkdir()
    ev = {
        "id": 99, "name": "test",
        "assertions": [
            {"name": "a", "type": "dir_exists", "path": "Review - sample/"},
            {"name": "b", "type": "file_exists",
             "path": "Review - sample/missing.md"},
        ],
    }
    result = run_evals.run_eval(ev, tmp_path)
    assert result["all_passed"] is False
    assert result["passed"] == 1
    assert result["total"] == 2


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def test_main_list_mode_no_args(capsys):
    """不带参数应列出所有 eval，返回 0。"""
    rc = run_evals.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "共 9 个 eval" in out
    assert "basic-pdf-review" in out


def test_main_eval_id_not_found(capsys):
    rc = run_evals.main(["--eval-id", "999"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "999" in err


def test_main_help_works():
    """--help 不抛异常（argparse 会 SystemExit 0）。"""
    with pytest.raises(SystemExit) as exc:
        run_evals.main(["--help"])
    assert exc.value.code == 0
