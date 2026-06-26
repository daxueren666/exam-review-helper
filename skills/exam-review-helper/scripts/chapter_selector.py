"""
章节范围解析器

把学生的自然语言范围（"第3章+第5章15-30页"）解析为标准结构。

支持的格式：
    "全部" / "整本" / "all" / "" → 全书
    "第3章" / "3章" / "3"        → 整章（章号待 LLM 解析）
    "1-3"                        → 页码范围
    "第3章的15-30页"             → 章内页码
    "第3章+第5章"                → 多章
    "3,5,8"                      → 多章
    "第3章 第15-30页"            → 章内页码
    "第3章+第5章的15-30页+第8章" → 混合
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ChapterRange:
    """单个范围项"""
    chapter: Optional[int] = None   # 章号（用于显示，可为 None）
    page_start: Optional[int] = None  # 起始页（None = 整章待 LLM 解析）
    page_end: Optional[int] = None    # 结束页

    def is_whole_chapter(self) -> bool:
        """是否整章（页码待定，需要 LLM 解析）"""
        return self.page_start is None or self.page_end is None

    def covers_page(self, page: int) -> bool:
        if self.is_whole_chapter():
            return False
        return self.page_start <= page <= self.page_end

    def describe(self) -> str:
        if self.is_whole_chapter():
            return f"第{self.chapter}章（整章）" if self.chapter else "未知范围"
        if self.chapter:
            return f"第{self.chapter}章 p.{self.page_start}-{self.page_end}"
        return f"p.{self.page_start}-{self.page_end}"


@dataclass
class RangeSpec:
    """范围规约：解析后的最终结构"""
    is_full_book: bool = True                  # 是否全书
    ranges: List[ChapterRange] = field(default_factory=list)

    def describe(self) -> str:
        if self.is_full_book:
            return "全书"
        return " + ".join(r.describe() for r in self.ranges)

    def to_llm_hint(self) -> str:
        """转成给 LLM 的提示文本"""
        if self.is_full_book:
            return ""
        lines = [r.describe() for r in self.ranges]
        return "用户只要以下范围（其他章节请跳过）：\n" + "\n".join(f"  - {l}" for l in lines)


def parse_ranges(input_str: str) -> RangeSpec:
    """解析自然语言范围字符串

    Args:
        input_str: 学生的自然语言输入

    Returns:
        RangeSpec: 解析后的范围规约
    """
    if not input_str:
        return RangeSpec(is_full_book=True)

    s = input_str.strip()

    # 全书关键词
    if s.lower() in ("", "全部", "整本", "全书", "all", "all chapters", "whole"):
        return RangeSpec(is_full_book=True)

    # 切分多个范围项
    parts = _split_parts(s)

    ranges: List[ChapterRange] = []
    for part in parts:
        r = _parse_single(part)
        if r is not None:
            ranges.append(r)

    if not ranges:
        # 解析失败，退回全书
        return RangeSpec(is_full_book=True)

    return RangeSpec(is_full_book=False, ranges=ranges)


def _split_parts(s: str) -> List[str]:
    """按常见分隔符切分"""
    import re
    # 用 + , ， 、 ； ; 和 以及 切分（但保留页码范围中的 - —）
    parts = re.split(r'[+,，、；;]|和|以及|还有|加上', s)
    return [p.strip() for p in parts if p.strip()]


def _parse_single(part: str) -> Optional[ChapterRange]:
    """解析单个范围项"""
    import re

    # 模式 1: "第3章的15-30页" / "第3章 15-30页"
    m = re.search(
        r'第?\s*(\d+)\s*章.*?(\d+)\s*[-–—到至~]\s*(\d+)\s*页?',
        part
    )
    if m:
        ps, pe = int(m.group(2)), int(m.group(3))
        if ps > pe:
            ps, pe = pe, ps  # 反向范围自动纠正
        return ChapterRange(
            chapter=int(m.group(1)),
            page_start=ps,
            page_end=pe,
        )

    # 模式 2: 纯页码范围 "15-30页" / "15-30"
    m = re.match(r'^(\d+)\s*[-–—到至~]\s*(\d+)\s*页?$', part)
    if m:
        ps, pe = int(m.group(1)), int(m.group(2))
        if ps > pe:
            ps, pe = pe, ps
        return ChapterRange(
            page_start=ps,
            page_end=pe,
        )

    # 模式 3: 第N章（整章）
    m = re.search(r'第?\s*(\d+)\s*章', part)
    if m:
        return ChapterRange(chapter=int(m.group(1)))

    # 模式 4: 单个数字 = 第N章（猜测）
    m = re.match(r'^(\d+)$', part)
    if m:
        return ChapterRange(chapter=int(m.group(1)))

    return None
