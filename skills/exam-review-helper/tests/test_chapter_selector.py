"""chapter_selector 单元测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from chapter_selector import parse_ranges, RangeSpec, ChapterRange


def test_empty_returns_full_book():
    spec = parse_ranges("")
    assert spec.is_full_book is True


def test_full_keywords():
    for s in ["全部", "整本", "全书", "all", "ALL", "  "]:
        spec = parse_ranges(s)
        assert spec.is_full_book is True, f"Failed for: {s!r}"


def test_single_chapter():
    spec = parse_ranges("第3章")
    assert spec.is_full_book is False
    assert len(spec.ranges) == 1
    r = spec.ranges[0]
    assert r.chapter == 3
    assert r.is_whole_chapter() is True


def test_single_number_as_chapter():
    spec = parse_ranges("3")
    assert spec.is_full_book is False
    assert spec.ranges[0].chapter == 3


def test_page_range():
    spec = parse_ranges("15-30")
    assert spec.is_full_book is False
    r = spec.ranges[0]
    assert r.page_start == 15
    assert r.page_end == 30
    assert r.chapter is None


def test_page_range_with_pages_suffix():
    spec = parse_ranges("15-30页")
    r = spec.ranges[0]
    assert r.page_start == 15
    assert r.page_end == 30


def test_chapter_with_pages():
    spec = parse_ranges("第5章的15-30页")
    r = spec.ranges[0]
    assert r.chapter == 5
    assert r.page_start == 15
    assert r.page_end == 30


def test_chapter_with_pages_space():
    spec = parse_ranges("第5章 15-30页")
    r = spec.ranges[0]
    assert r.chapter == 5
    assert r.page_start == 15
    assert r.page_end == 30


def test_multiple_chapters_plus():
    spec = parse_ranges("第3章+第5章+第8章")
    assert len(spec.ranges) == 3
    assert spec.ranges[0].chapter == 3
    assert spec.ranges[1].chapter == 5
    assert spec.ranges[2].chapter == 8


def test_multiple_chapters_comma():
    spec = parse_ranges("3,5,8")
    assert len(spec.ranges) == 3
    chapters = [r.chapter for r in spec.ranges]
    assert chapters == [3, 5, 8]


def test_mixed_chapter_and_pages():
    spec = parse_ranges("第3章+第5章的15-30页+第8章")
    assert len(spec.ranges) == 3
    assert spec.ranges[0].chapter == 3
    assert spec.ranges[0].is_whole_chapter()

    assert spec.ranges[1].chapter == 5
    assert spec.ranges[1].page_start == 15
    assert spec.ranges[1].page_end == 30

    assert spec.ranges[2].chapter == 8
    assert spec.ranges[2].is_whole_chapter()


def test_mixed_with_chinese_comma():
    spec = parse_ranges("第3章、第5章的15-30页，第8章")
    assert len(spec.ranges) == 3


def test_to_llm_hint_full_book_is_empty():
    spec = RangeSpec(is_full_book=True)
    assert spec.to_llm_hint() == ""


def test_to_llm_hint_partial():
    spec = parse_ranges("第3章+第5章15-30页")
    hint = spec.to_llm_hint()
    assert "第3章（整章）" in hint
    assert "第5章 p.15-30" in hint
    assert "用户只要以下范围" in hint


def test_describe():
    assert parse_ranges("").describe() == "全书"
    assert parse_ranges("第3章").describe() == "第3章（整章）"
    assert parse_ranges("15-30").describe() == "p.15-30"
    assert parse_ranges("第5章的15-30页").describe() == "第5章 p.15-30"


def test_invalid_input_falls_back_to_full():
    spec = parse_ranges("xyz无效")
    assert spec.is_full_book is True


def test_covers_page():
    r = ChapterRange(chapter=5, page_start=15, page_end=30)
    assert r.covers_page(15) is True
    assert r.covers_page(30) is True
    assert r.covers_page(20) is True
    assert r.covers_page(14) is False
    assert r.covers_page(31) is False


if __name__ == "__main__":
    # 简单 runner，不依赖 pytest
    import inspect
    funcs = [f for n, f in inspect.getmembers(sys.modules[__name__])
             if n.startswith("test_") and callable(f)]
    passed = 0
    failed = 0
    for func in funcs:
        try:
            func()
            print(f"  [OK] {func.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {func.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERR] {func.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
