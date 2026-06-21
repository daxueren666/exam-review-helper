"""OCR 后处理纠错。

扫描版 PDF 经 rapidocr 提取后，常见汉字误判。本模块提供上下文感知的纠错：
- 高置信度纠错：已知 OCR 错误 + 上下文支持 → 自动修
- 低置信度：仅记录，不改

设计原则：
- 保守纠错——宁可漏纠不可错纠（错纠比不纠更误事）
- 上下文校验——单字替换必须符合常用词搭配
- 可关闭——--no-ocr-correct 跳过

常见 rapidocr 误判（基于实测同济高数扫描版）：
- 巳↔已↔己（己很少用，多数应为"已"）
- 末↔未（"未"更常见于数学）
- 土↔士（看上下文）
- 干↔千（数字上下文用"千"）
- 候→侯（"时候"应为"时候"，但"侯"少单用）
- 乌↔鸟
- 面积→百积（极罕见）
"""
import re
from typing import List, Tuple


# 高置信度纠对：key 是 OCR 误判，value 是正确字
# 仅列"几乎一定是 OCR 错"的——必须是 OCR 误判概率远大于合法用法的词
# 单字"巳""末"不列入：地支"巳时""辛巳"、"期末""周末"等合法用法多，错纠代价大
HIGH_CONFIDENCE_FIXES = {
    # 数学上下文常见误判（带上下文的双字词）
    "巳知": "已知",
    "巳经": "已经",
    "末知": "未知",
    "末来": "未来",
}


# 上下文相关纠错：(误判模式, 正确模式)——用正则匹配
CONTEXT_FIXES = [
    # "千"误判为"干"——数字上下文
    (r'(\d)干(\d)', r'\1千\2'),  # 5干3 → 5千3（千位分隔）
    (r'干(\d)', r'千\1'),  # 干200 → 千200
    # "已"误判为"巳"——时态上下文
    (r'巳(\d)', r'已\1'),  # 巳1 → 已1（"已1个"等）
    # "士"误判为"土"——学位上下文
    (r'博士土', r'博士生'),  # 博士土 → 博士生（"生"误判为"土"）
    # "即"误判为"卽"——古字
    (r'卽', r'即'),
    # "真"误判为"眞"——古字
    (r'眞', r'真'),
    # "说"误判为"説"——日文异体
    (r'説明', r'说明'),
]


def correct_ocr_errors(text: str, verbose: bool = False) -> Tuple[str, List[str]]:
    """纠正 OCR 常见误判。

    Args:
        text: OCR 提取的文本
        verbose: 是否打印纠错日志

    Returns:
        (corrected_text, corrections_log)
        corrections_log 是 ["巳知→已知 (3处)", ...] 格式
    """
    corrections: List[str] = []
    result = text

    # 1. 上下文无关的高置信度纠错
    for wrong, right in HIGH_CONFIDENCE_FIXES.items():
        count = result.count(wrong)
        if count > 0:
            result = result.replace(wrong, right)
            corrections.append(f"{wrong}→{right} ({count}处)")

    # 2. 上下文相关纠错
    for pattern, replacement in CONTEXT_FIXES:
        new_result, count = re.subn(pattern, replacement, result)
        if count > 0:
            wrong_desc = pattern.replace(r'\d', '').replace(r'(', '').replace(r')', '')
            right_desc = replacement.replace(r'\1', '').replace(r'\2', '')
            corrections.append(f"上下文 {wrong_desc}→{right_desc} ({count}处)")
            result = new_result

    if verbose and corrections:
        print(f"[OCR Corrector] 纠正 {len(corrections)} 类错误：", file=__import__('sys').stderr)
        for c in corrections:
            print(f"  - {c}", file=__import__('sys').stderr)

    return result, corrections


def has_ocr_markers(text: str) -> bool:
    """检测文本是否像 OCR 输出（有常见 OCR 痕迹）。

    用于判断是否需要纠错——原生电子版文本不需要。
    """
    # 扫描版 PDF 的 OCR 输出常有这些痕迹
    ocr_indicators = [
        "巳",  # 巳 极少在正常文本出现，多数是 已 的误判
        "卽", "眞",  # 古异体字，OCR 常误判
    ]
    return any(ind in text for ind in ocr_indicators)
