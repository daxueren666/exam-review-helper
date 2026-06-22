"""generate_html.py 单元测试。

覆盖：
- _escape_html / _sanitize_markdown 的 XSS 防护
- generate_html 的模板占位符替换 + JSON 注入防护（</script> 和 <!--）
- generate_markdown 的 XSS 过滤
- generate_json 的格式化输出
- 空 chapters 边界
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import generate_html


# ============ _escape_html ============

def test_escape_html_basic():
    assert generate_html._escape_html("<script>") == "&lt;script&gt;"


def test_escape_html_quotes():
    assert generate_html._escape_html('"hello"') == "&quot;hello&quot;"
    assert generate_html._escape_html("it's") == "it&#x27;s"


def test_escape_html_non_string():
    assert generate_html._escape_html(123) == 123


# ============ _sanitize_markdown ============

def test_sanitize_removes_script_block():
    text = '<script>alert(1)</script>正常文本'
    result = generate_html._sanitize_markdown(text)
    assert "<script>" not in result
    assert "alert(1)" not in result
    assert "正常文本" in result


def test_sanitize_removes_javascript_protocol():
    text = '[link](javascript:evil)'
    result = generate_html._sanitize_markdown(text)
    assert "javascript:" not in result


def test_sanitize_removes_onerror():
    text = '<img onerror=alert(1) src=x>'
    result = generate_html._sanitize_markdown(text)
    assert "onerror=" not in result


def test_sanitize_preserves_normal_markdown():
    text = '## 标题\n\n**粗体** 和 `代码`'
    result = generate_html._sanitize_markdown(text)
    assert result == text


# ============ generate_html ============

def _make_knowledge(tmp_path, data):
    """构造临时 knowledge.json 文件。"""
    p = tmp_path / "test_knowledge.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _minimal_knowledge():
    return {
        "source": "测试教材",
        "chapters": [{
            "chapter_title": "第1章",
            "page_range": "1-5",
            "concepts": [{"name": "概念A", "importance": "high", "page": 1, "definition": "定义A"}],
        }],
    }


def test_generate_html_creates_file(tmp_path):
    kpath = _make_knowledge(tmp_path, _minimal_knowledge())
    out = tmp_path / "out.html"
    r = generate_html.generate_html(str(kpath), str(out))
    assert r["status"] == "success"
    assert out.exists()
    assert "MathJax" in out.read_text(encoding="utf-8")


def test_generate_html_escapes_book_title(tmp_path):
    """含 XSS 的 book_title 必须被转义。"""
    kpath = _make_knowledge(tmp_path, _minimal_knowledge())
    out = tmp_path / "out.html"
    generate_html.generate_html(str(kpath), str(out), book_title='<script>alert(1)</script>')
    content = out.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;" in content


def test_generate_html_prevents_script_injection_in_json(tmp_path):
    r"""JSON 中 </script> 必须被替换为 <\/script>。"""
    data = _minimal_knowledge()
    data["chapters"][0]["concepts"][0]["definition"] = '</script><script>alert(1)</script>'
    kpath = _make_knowledge(tmp_path, data)
    out = tmp_path / "out.html"
    generate_html.generate_html(str(kpath), str(out))
    content = out.read_text(encoding="utf-8")
    # 原始 </script> 不应出现在 JSON 数据区（模板里的 </script> 标签除外）
    # 检查注入的 alert 是否被 neutralize
    assert "<\\/script><script>alert(1)<\\/script>" in content or "alert(1)" not in content


def test_generate_html_prevents_comment_injection(tmp_path):
    r"""JSON 中 <!-- 必须被替换为 <\!--。"""
    data = _minimal_knowledge()
    data["chapters"][0]["concepts"][0]["definition"] = '<!--evil-->'
    kpath = _make_knowledge(tmp_path, data)
    out = tmp_path / "out.html"
    generate_html.generate_html(str(kpath), str(out))
    content = out.read_text(encoding="utf-8")
    # <!-- 应被转义（在 JSON 数据里）
    assert "<\\!--" in content


def test_generate_html_empty_chapters(tmp_path):
    """空 chapters 数组不应崩溃。"""
    data = {"source": "空教材", "chapters": []}
    kpath = _make_knowledge(tmp_path, data)
    out = tmp_path / "out.html"
    r = generate_html.generate_html(str(kpath), str(out))
    assert r["status"] == "success"
    assert out.exists()


def test_generate_html_missing_file(tmp_path):
    """knowledge.json 不存在时返回 error。"""
    r = generate_html.generate_html(str(tmp_path / "nonexistent.json"))
    assert r["status"] == "error"


# ============ generate_markdown ============

def test_generate_markdown_creates_file(tmp_path):
    kpath = _make_knowledge(tmp_path, _minimal_knowledge())
    out = tmp_path / "out.md"
    r = generate_html.generate_markdown(str(kpath), str(out))
    assert r["status"] == "success"
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "测试教材" in content
    assert "第1章" in content


def test_generate_markdown_sanitizes_xss(tmp_path):
    """MD 中的 XSS 必须被过滤。"""
    data = _minimal_knowledge()
    data["chapters"][0]["concepts"][0]["definition"] = '<script>alert(1)</script>[link](javascript:evil)'
    kpath = _make_knowledge(tmp_path, data)
    out = tmp_path / "out.md"
    generate_html.generate_markdown(str(kpath), str(out))
    content = out.read_text(encoding="utf-8")
    assert "<script>" not in content
    assert "javascript:" not in content


def test_generate_markdown_empty_chapters(tmp_path):
    data = {"source": "空", "chapters": []}
    kpath = _make_knowledge(tmp_path, data)
    out = tmp_path / "out.md"
    r = generate_html.generate_markdown(str(kpath), str(out))
    assert r["status"] == "success"


# ============ generate_json ============

def test_generate_json_passthrough(tmp_path):
    """JSON 格式直接输出，内容原样保留。"""
    data = _minimal_knowledge()
    kpath = _make_knowledge(tmp_path, data)
    out = tmp_path / "out.json"
    r = generate_html.generate_json(str(kpath), str(out))
    assert r["status"] == "success"
    output = json.loads(out.read_text(encoding="utf-8"))
    assert output["source"] == "测试教材"
    assert output["chapters"][0]["chapter_title"] == "第1章"


# ============ generate（统一入口）============

def test_generate_dispatch_html(tmp_path):
    kpath = _make_knowledge(tmp_path, _minimal_knowledge())
    out = tmp_path / "out.html"
    r = generate_html.generate(str(kpath), str(out), fmt="html")
    assert r["status"] == "success"
    assert out.exists()


def test_generate_dispatch_md(tmp_path):
    kpath = _make_knowledge(tmp_path, _minimal_knowledge())
    out = tmp_path / "out.md"
    r = generate_html.generate(str(kpath), str(out), fmt="md")
    assert r["status"] == "success"


def test_generate_dispatch_json(tmp_path):
    kpath = _make_knowledge(tmp_path, _minimal_knowledge())
    out = tmp_path / "out.json"
    r = generate_html.generate(str(kpath), str(out), fmt="json")
    assert r["status"] == "success"


def test_generate_invalid_format(tmp_path):
    kpath = _make_knowledge(tmp_path, _minimal_knowledge())
    r = generate_html.generate(str(kpath), fmt="invalid")
    assert r["status"] == "error"
