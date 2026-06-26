"""公式提取增强（可选）。

docling 默认关闭公式提取（do_formula_enrichment=False，需 18-40GB VRAM），
markdown 中的公式位置显示为 <!-- formula-not-decoded --> 占位符。

本脚本提供两种增强方式：
1. **pix2tex OCR**（可选）：用 LaTeX-OCR 对 PDF 中的公式图片做识别
   - 安装：pip install pix2tex
   - 适合：理工科教材，公式密集
2. **LLM 重建辅助**（默认）：统计占位符位置，输出 formula_hints.json
   - Pass 2 reader 可参考 hints 知道哪些页有公式、大致数量
   - LLM 基于上下文重建（当前 SKILL.md 推荐方式）

用法:
    # 默认：扫描占位符，输出 hints（不需要 pix2tex）
    python scripts/enhance_formulas.py <output_dir>

    # 启用 pix2tex OCR（需先 pip install pix2tex）
    python scripts/enhance_formulas.py <output_dir> --use-pix2tex <pdf_path>
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional


def scan_formula_placeholders(markdown_path: Path) -> Dict[int, int]:
    """扫描 markdown 中的公式占位符，返回 {page_no: count}。

    占位符格式：<!-- formula-not-decoded -->
    页码从 [PAGE N] 标记推断。
    """
    content = markdown_path.read_text(encoding="utf-8")

    # 找所有 [PAGE N] 标记位置
    page_markers = list(re.finditer(r'^\[PAGE (\d+)\]', content, re.MULTILINE))

    # 找所有占位符位置
    placeholders = list(re.finditer(r'<!-- formula-not-decoded -->', content))

    # 统计每页占位符数量
    page_counts: Dict[int, int] = {}
    for ph in placeholders:
        # 找占位符所在的页
        page_no = 1
        for pm in page_markers:
            if pm.start() > ph.start():
                break
            page_no = int(pm.group(1))
        page_counts[page_no] = page_counts.get(page_no, 0) + 1

    return page_counts


def render_pdf_pages(pdf_path: Path, pages: List[int], output_dir: Path) -> Dict[int, Path]:
    """用 PyMuPDF 渲染指定页为图片，返回 {page_no: image_path}。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("错误：PyMuPDF 未安装。pip install PyMuPDF", file=sys.stderr)
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "formula_pages"
    images_dir.mkdir(exist_ok=True)

    result = {}
    doc = fitz.open(str(pdf_path))
    try:
        for page_no in pages:
            if page_no < 1 or page_no > doc.page_count:
                continue
            page = doc[page_no - 1]  # 0-indexed
            pix = page.get_pixmap(dpi=200)  # 200 DPI 足够 OCR
            img_path = images_dir / f"page_{page_no:04d}.png"
            pix.save(str(img_path))
            result[page_no] = img_path
    finally:
        doc.close()

    return result


def ocr_formulas_with_pix2tex(image_paths: Dict[int, Path]) -> Dict[int, List[str]]:
    """用 pix2tex 对页面图片做公式 OCR（可选，需安装 pix2tex）。

    Returns:
        {page_no: [latex_formula, ...]}
    """
    try:
        from pix2tex.cli import LatexOCR
    except ImportError:
        print(
            "pix2tex 未安装。公式 OCR 需要可选依赖：\n"
            "  pip install pix2tex\n"
            "已跳过 OCR，仅输出占位符位置 hints。",
            file=sys.stderr,
        )
        return {}

    print(f"[Formula Enhancer] 加载 pix2tex 模型...", file=sys.stderr)
    model = LatexOCR()

    result: Dict[int, List[str]] = {}
    for page_no, img_path in image_paths.items():
        try:
            from PIL import Image
            img = Image.open(str(img_path))
            # pix2tex 对整页图片会尝试识别所有公式
            # 但整页 OCR 效果有限，理想情况需要先裁剪公式区域
            # 这里简化处理：对整页做 OCR，提取 LaTeX 片段
            latex = model(img)
            if latex and len(latex) > 5:
                result[page_no] = [latex]
                print(f"  page {page_no}: {latex[:60]}...", file=sys.stderr)
        except Exception as e:
            print(f"  page {page_no} OCR 失败: {e}", file=sys.stderr)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="公式提取增强：扫描占位符 + 可选 pix2tex OCR",
    )
    parser.add_argument("output_dir", help="Review - <stem>/ 输出目录")
    parser.add_argument(
        "--use-pix2tex",
        metavar="PDF_PATH",
        default=None,
        help="启用 pix2tex OCR（需 pip install pix2tex），传入原始 PDF 路径",
    )
    parser.add_argument(
        "--pages",
        default=None,
        help="只处理指定页（逗号分隔，如 1,3,5）。默认处理所有有占位符的页",
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    markdown_path = output_dir / "extracted_content.md"

    if not markdown_path.exists():
        print(f"错误：未找到 {markdown_path}", file=sys.stderr)
        sys.exit(1)

    # 1. 扫描占位符
    print(f"[Formula Enhancer] 扫描公式占位符...", file=sys.stderr)
    page_counts = scan_formula_placeholders(markdown_path)
    total = sum(page_counts.values())

    if total == 0:
        print("[Formula Enhancer] 未发现公式占位符（可能是文科教材或原生电子版）")
        # 仍然输出空 hints
        hints = {
            "total_placeholders": 0,
            "pages_with_formulas": {},
            "ocr_results": {},
            "note": "未发现公式占位符。Pass 2 reader 无需重建公式。"
        }
    else:
        print(f"[Formula Enhancer] 发现 {total} 个公式占位符，分布在 {len(page_counts)} 页")
        for p, c in sorted(page_counts.items()):
            print(f"  page {p}: {c} 个", file=sys.stderr)

        hints = {
            "total_placeholders": total,
            "pages_with_formulas": page_counts,
            "ocr_results": {},
            "note": f"{total} 个公式占位符待 Pass 2 reader 基于上下文重建。"
                    f"参考 prompts/system_reader.md 的'公式重建'章节。"
        }

    # 2. 可选：pix2tex OCR
    if args.use_pix2tex:
        pdf_path = Path(args.use_pix2tex)
        if not pdf_path.exists():
            print(f"错误：PDF 不存在 {pdf_path}", file=sys.stderr)
            sys.exit(1)

        # 确定要处理的页
        if args.pages:
            target_pages = [int(p) for p in args.pages.split(",")]
        else:
            target_pages = list(page_counts.keys())

        if target_pages:
            print(f"\n[Formula Enhancer] 渲染 {len(target_pages)} 页图片...", file=sys.stderr)
            images = render_pdf_pages(pdf_path, target_pages, output_dir)

            print(f"[Formula Enhancer] 用 pix2tex OCR 公式...", file=sys.stderr)
            ocr_results = ocr_formulas_with_pix2tex(images)
            hints["ocr_results"] = ocr_results
            hints["note"] = (
                f"pix2tex OCR 完成。{len(ocr_results)} 页有 OCR 结果。"
                f"Pass 2 reader 可参考 ocr_results 字段，但仍需基于上下文判断准确性。"
            )

    # 3. 输出 hints JSON
    hints_path = output_dir / "formula_hints.json"
    hints_path.write_text(
        json.dumps(hints, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[Formula Enhancer] hints 已保存：{hints_path}")
    print(f"[Formula Enhancer] Pass 2 reader 可读此文件获取公式位置信息")


if __name__ == "__main__":
    main()
