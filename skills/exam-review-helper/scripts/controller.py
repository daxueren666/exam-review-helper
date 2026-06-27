"""
Exam-Review-Helper Controller (简化版 - 对话驱动)

本 controller 只负责**确定性的脚本任务**：
- 多格式提取（PDF 用 docling；DOCX/TXT/MD 用 MarkItDown）
- HTML 生成
- JSON 校验

中间的 5-pass 知识提取由**宿主 LLM 对话执行**（Claude/Codex/OpenCode）。
不需要 API key，不需要外部 LLM 调用。

用法:
    # 提取单个文件（PDF/DOCX/TXT/MD）
    python controller.py extract <source_path>

    # 提取多个文件（可混合格式）
    python controller.py extract a.pdf b.docx c.md

    # 生成 HTML
    python controller.py generate <knowledge_json>

    # 校验 Pass 2 notes JSON
    python controller.py validate <notes.json | dir/>
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional
import re

# Windows GBK 控制台兼容：强制 stdout/stderr 用 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        # 老版本 Python 没 reconfigure
        pass


# ============ Phase: PDF 提取 ============

def fix_heading_hierarchy(md: str) -> str:
    """重建 docling 输出的标题层级。

    docling 把 "## 二、函数" 和 "## 1.函数的概念" 当成同级（都是 ##）。
    但中文教材惯例："一、二、三" 是大节（一级），"1, 2, 3" 是小节（二级）。
    本函数：
    - "## 一、xxx" / "## 第二章 xxx" → "#" (顶级)
    - "## 1.xxx" / "## 1.1 xxx" → "###" (三级)
    - 其他 "##" 保持不变
    """

    cn_num = r'[一二三四五六七八九十百千]+'
    # 顶级标题：一、二、三 / 第一章 / 第1章 / 第N节 / 第N讲 / Chapter N
    pattern_top = re.compile(
        rf'^#+\s+({cn_num}、|第{cn_num}章|第\d+章|第{cn_num}节|第\d+节|第{cn_num}讲|第\d+讲|Chapter\s+\d+)',
        re.IGNORECASE,
    )
    pattern_sub = re.compile(r'^#+\s+(\d+[\.\s])')

    lines = md.split('\n')
    out = []
    for line in lines:
        if pattern_top.match(line):
            # 顶级：# 开头
            content = line.lstrip('#').strip()
            line = '# ' + content
        elif pattern_sub.match(line):
            # 子级：### 开头
            content = line.lstrip('#').strip()
            line = '### ' + content
        out.append(line)
    return '\n'.join(out)


def export_markdown_with_pages(doc) -> str:
    """导出带 [PAGE N] 标记的 markdown，按 docling item 类型重建格式。

    docling 的 doc.export_to_markdown() 不带页码，且阅读顺序可能乱。
    本函数直接遍历 iterate_items，按 item.label 重建 markdown：
      - section_header → ## 标题（fix_heading_hierarchy 后会自动升级/降级）
      - text / paragraph → 段落
      - formula → <!-- formula-not-decoded --> 占位
      - list_item → - 项
      - picture / caption → <!-- image --> / 斜体说明
    """
    try:
        iterator = doc.iterate_items(doc.body, with_groups=True)
    except AttributeError:
        # 老版本 docling 没 iterate_items
        return doc.export_to_markdown()

    lines = []
    prev_page = None

    for item, _level in iterator:
        # 取页码（无 prov 的容器跳过）
        prov = getattr(item, "prov", None) or []
        if not prov:
            continue
        cur_page = prov[0].page_no

        if cur_page != prev_page:
            lines.append(f"\n[PAGE {cur_page}]\n")
            prev_page = cur_page

        label = getattr(item, "label", None) or type(item).__name__
        text = (getattr(item, "text", None) or "").strip()

        if label == "section_header":
            lines.append(f"## {text}")
        elif label in ("title", "Title"):
            lines.append(f"# {text}")
        elif label == "list_item":
            lines.append(f"- {text}")
        elif label == "caption":
            lines.append(f"*{text}*")
        elif label == "formula":
            lines.append("<!-- formula-not-decoded -->")
        elif label == "picture":
            lines.append("<!-- image -->")
        elif label in ("text", "paragraph"):
            if text:
                lines.append(text)
        else:
            # 其他类型（table 等）尝试 item.export_to_markdown()
            try:
                item_md = item.export_to_markdown().strip()
                if item_md:
                    lines.append(item_md)
            except Exception:
                if text:
                    lines.append(text)

    md = "\n\n".join(lines)
    return fix_heading_hierarchy(md)


def extract_pdf(pdf_path: str, output_dir: str = None, page_range: tuple = None,
                ocr_correct: bool = False, ocr_scale: int = None,
                use_pdfium: bool = True) -> Dict[str, Any]:
    """用 docling 提取**单个** PDF 为 markdown + 结构化 JSON

    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录（默认 Review - <stem>/）
        page_range: 可选，(start, end) 页码范围（1-indexed, 闭区间）。
                    用于处理大 PDF 时分块提取，避免 std::bad_alloc。
        ocr_correct: 是否对 OCR 输出做后处理纠错（扫描版 PDF 常见误判修复）。
        ocr_scale: RapidOCR 渲染 scale（默认 None=不 patch 用 docling 默认 3=216DPI）。
                   降到 2（144DPI）可避免高分辨率扫描版 PDF 的 numpy 内存爆炸。
                   144DPI 仍足够 OCR（RapidOCR 检测模型输入 736px 会 resize）。
        use_pdfium: 是否用 PyPdfiumDocumentBackend 替代默认 DoclingParseDocumentBackend。
                    docling-parse 的 C++ 解析层在复杂页面会 std::bad_alloc 崩溃。
                    pdfium 是 Google 的 PDF 库，更稳定，但表格提取质量略降。
                    保留 docling 的版面分析+OCR+公式占位符能力。
    """
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions

    # Monkey patch RapidOCR 的 scale，避免高分辨率扫描版 PDF numpy 内存爆炸
    # 根因：docling 的 rapid_ocr_model.py:307 硬编码 self.scale = 3（216 DPI），
    # 不受 PdfPipelineOptions.images_scale 控制。216 DPI 渲染大页面会产生
    # 1984×1408×3 float64 = 67MB 的 numpy 数组，onnxruntime 推理时爆内存。
    # 降到 scale=2（144 DPI）能减 56% 内存，保留 docling 版面分析+公式占位符+表格。
    if ocr_scale is not None and ocr_scale != 3:
        try:
            from docling.models.stages.ocr.rapid_ocr_model import RapidOcrModel
            _original_init = RapidOcrModel.__init__

            def _patched_init(self, *args, **kwargs):
                _original_init(self, *args, **kwargs)
                self.scale = ocr_scale

            RapidOcrModel.__init__ = _patched_init
        except ImportError:
            print(f"[Controller] 警告：无法 patch RapidOCR scale，使用默认 216 DPI", file=sys.stderr)

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return {"status": "error", "message": f"PDF 不存在: {pdf_path}"}

    if output_dir is None:
        output_dir = pdf_path.parent / f"Review - {pdf_path.stem}"
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        do_formula_enrichment=False,
        generate_picture_images=False,  # 省内存：不缓存页面图片
        generate_page_images=False,
        ocr_options=RapidOcrOptions(),
        images_scale=1.0,  # 72 DPI，默认 2.0 = 144 DPI
    )
    # 选择 PDF 后端：默认 DoclingParseDocumentBackend，崩溃时切 PyPdfiumDocumentBackend
    pdf_format_kwargs = {"pipeline_options": pipeline_options}
    if use_pdfium:
        try:
            from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
            pdf_format_kwargs["backend"] = PyPdfiumDocumentBackend
            print(f"[Controller] 使用 PyPdfiumDocumentBackend（避免 docling-parse std::bad_alloc）", file=sys.stderr)
        except ImportError:
            print(f"[Controller] 警告：PyPdfiumDocumentBackend 不可用，回退到 DoclingParseDocumentBackend", file=sys.stderr)
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(**pdf_format_kwargs)
        }
    )

    range_label = f" p.{page_range[0]}-{page_range[1]}" if page_range else ""
    backend_label = " [pdfium]" if use_pdfium else ""
    print(f"[Controller] 正在提取 PDF: {pdf_path}{range_label}{backend_label}", file=sys.stderr)

    try:
        convert_kwargs = {}
        if page_range is not None:
            convert_kwargs["page_range"] = page_range
        result = converter.convert(str(pdf_path), **convert_kwargs)
    except Exception as e:
        # 预先缓存 size，避免 except 块再 stat() 二次失败
        try:
            size_mb = pdf_path.stat().st_size / 1024 / 1024
        except Exception:
            size_mb = -1
        msg = (
            f"\n[Controller] docling 提取失败: {type(e).__name__}: {e}\n"
            f"  PDF: {pdf_path}\n"
            f"  大小: {size_mb:.1f} MB\n"
        )
        if "bad_alloc" in str(e).lower() or size_mb > 50:
            msg += (
                "  提示：大 PDF 可能触发内存问题。\n"
                "  解决：用 --chunk-size 50 分块提取，或先拆分 PDF。\n"
            )
        return {"status": "error", "message": msg}

    markdown = export_markdown_with_pages(result.document)

    # 可选：OCR 后处理纠错（扫描版 PDF 常见误判）
    if ocr_correct:
        try:
            from ocr_corrector import correct_ocr_errors, has_ocr_markers
            if has_ocr_markers(markdown):
                markdown, corrections = correct_ocr_errors(markdown, verbose=True)
                if corrections:
                    print(f"[Controller] OCR 纠错：{len(corrections)} 类错误已修", file=sys.stderr)
        except ImportError:
            print("[Controller] 警告：ocr_corrector 模块未找到，跳过 OCR 纠错", file=sys.stderr)

    markdown_path = output_dir / "extracted_content.md"
    markdown_path.write_text(markdown, encoding="utf-8")

    doc_dict = result.document.export_to_dict()
    json_path = output_dir / "extracted_content.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(doc_dict, f, ensure_ascii=False, indent=2)

    pages = len(result.document.pages) if hasattr(result.document, "pages") else 0

    # 检测 docling 内部错误（如 std::bad_alloc）导致的部分提取
    # docling 的 bad_alloc 是 C++ 层警告，只打印到 stderr，不抛 Python 异常
    # result.document.pages 可能包含空页（bad_alloc 失败的页仍在 dict 里）
    # 所以用 markdown 实际 [PAGE N] 标记数检测，而不是 len(pages)
    actual_pages = len(re.findall(r'^\[PAGE \d+\]', markdown, re.MULTILINE))
    if page_range is not None:
        expected_pages = page_range[1] - page_range[0] + 1
    else:
        expected_pages = _get_pdf_page_count(pdf_path)
    if expected_pages > 0 and actual_pages < expected_pages:
        missing = expected_pages - actual_pages
        print(
            f"[Controller] 警告：仅提取 {actual_pages}/{expected_pages} 页"
            f"（{missing} 页失败，可能是 std::bad_alloc 内存错误或 OCR 空结果）",
            file=sys.stderr,
        )
        # actual_pages > 0 时返回 partial（而非 error），让上层合并可用结果
        if actual_pages > 0:
            print(f"[Controller] 部分提取成功：{actual_pages}/{expected_pages} 页可用 → {markdown_path}", file=sys.stderr)
            return {
                "status": "partial",
                "pdf_path": str(pdf_path),
                "source_path": str(pdf_path),
                "output_dir": str(output_dir),
                "markdown_path": str(markdown_path),
                "json_path": str(json_path),
                "pages": actual_pages,
                "pages_processed": actual_pages,
                "pages_failed": missing,
                "expected_pages": expected_pages,
                "stem": pdf_path.stem,
            }
        return {
            "status": "error",
            "message": (
                f"docling 仅提取 {actual_pages}/{expected_pages} 页"
                f"（{missing} 页失败，可能是 std::bad_alloc 内存错误）。"
                f" 建议：用 --chunk-size 5 分块提取，或 --backend pymupdf 走 fallback。"
            ),
            "pdf_path": str(pdf_path),
            "pages": actual_pages,
            "expected_pages": expected_pages,
        }

    print(f"[Controller] 提取完成: {actual_pages} 页 → {markdown_path}", file=sys.stderr)

    return {
        "status": "success",
        "pdf_path": str(pdf_path),
        "source_path": str(pdf_path),
        "output_dir": str(output_dir),
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "pages": pages,
        "stem": pdf_path.stem,
    }


def extract_pdf_pymupdf_rapidocr(pdf_path: str, output_dir: str = None,
                                page_range: tuple = None, dpi: int = 150,
                                ocr_correct: bool = False) -> Dict[str, Any]:
    """PyMuPDF + RapidOCR fallback 提取 PDF（绕开 docling）。

    当 docling 因 std::bad_alloc / onnxruntime 内存爆炸崩溃时使用此 fallback。
    完全绕开 docling，用 PyMuPDF 渲染每页为图片 + RapidOCR 直接 OCR。

    优点：稳定，内存可控（图片分辨率可调）
    缺点：失去 docling 的版面分析、表格提取、公式占位符（公式全部丢失为空）

    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录（默认 Review - <stem>/）
        page_range: 可选，(start, end) 页码范围（1-indexed, 闭区间）
        dpi: 渲染分辨率（默认 150，足够 OCR；扫描版可降到 100 省内存）
        ocr_correct: 是否对 OCR 输出做后处理纠错
    """
    import io
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return {"status": "error", "message": f"PDF 不存在: {pdf_path}"}

    if output_dir is None:
        output_dir = pdf_path.parent / f"Review - {pdf_path.stem}"
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import fitz  # PyMuPDF
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:
        return {
            "status": "error",
            "message": f"PyMuPDF/RapidOCR 未安装: {e}. 请运行 pip install PyMuPDF rapidocr-onnxruntime",
        }

    range_label = f" p.{page_range[0]}-{page_range[1]}" if page_range else ""
    print(f"[Controller] PyMuPDF+RapidOCR fallback 提取: {pdf_path}{range_label} @ {dpi}DPI", file=sys.stderr)

    ocr = RapidOCR()
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    with fitz.open(str(pdf_path)) as doc:
        total = doc.page_count
        if page_range is not None:
            start_page, end_page = page_range
        else:
            start_page, end_page = 1, total

        md_parts = []
        pages_ok = 0
        pages_fail = 0
        for page_num in range(start_page, end_page + 1):
            if page_num > total:
                break
            page = doc[page_num - 1]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            try:
                result, _ = ocr(img_bytes)
                if result:
                    lines = [item[1] for item in result]
                    text = "\n".join(lines)
                else:
                    text = ""
                md_parts.append(f"\n\n[PAGE {page_num}]\n\n{text}\n")
                pages_ok += 1
            except Exception as e:
                md_parts.append(f"\n\n[PAGE {page_num}]\n\n<!-- OCR failed: {e} -->\n")
                pages_fail += 1
                print(f"[Controller]   page {page_num} OCR failed: {e}", file=sys.stderr)

    markdown = "".join(md_parts)

    if ocr_correct:
        try:
            from ocr_corrector import correct_ocr_errors, has_ocr_markers
            if has_ocr_markers(markdown):
                markdown, corrections = correct_ocr_errors(markdown, verbose=True)
                if corrections:
                    print(f"[Controller] OCR 纠错：{len(corrections)} 类错误已修", file=sys.stderr)
        except ImportError:
            print("[Controller] 警告：ocr_corrector 模块未找到，跳过 OCR 纠错", file=sys.stderr)

    markdown_path = output_dir / "extracted_content.md"
    markdown_path.write_text(markdown, encoding="utf-8")

    json_data = {
        "schema_name": "PyMuPDFRapidOCRDocument",
        "name": pdf_path.stem,
        "pages": pages_ok,
        "pages_failed": pages_fail,
        "dpi": dpi,
        "backend": "pymupdf_rapidocr",
    }
    json_path = output_dir / "extracted_content.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    status = "success" if pages_fail == 0 else "partial"
    print(f"[Controller] fallback 完成: {pages_ok}/{end_page - start_page + 1} 页 → {markdown_path}", file=sys.stderr)

    return {
        "status": status,
        "pdf_path": str(pdf_path),
        "source_path": str(pdf_path),
        "output_dir": str(output_dir),
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "pages": pages_ok,
        "pages_failed": pages_fail,
        "backend": "pymupdf_rapidocr",
        "stem": pdf_path.stem,
    }


def _get_pdf_page_count(pdf_path: Path) -> int:
    """快速读取 PDF 总页数（不加载 docling）"""
    try:
        import fitz  # PyMuPDF
        with fitz.open(str(pdf_path)) as doc:
            return doc.page_count
    except Exception:
        return 0


def _extract_chunk_in_subprocess(pdf_path: str, output_dir: str, page_start: int, page_end: int,
                                 ocr_scale: int = None) -> Dict[str, Any]:
    """用独立 Python 子进程跑单块提取。

    关键：必须在子进程里跑，因为 docling 的 C++ 后端（docling-parse + onnxruntime）
    内存不被 Python GC 回收。同进程内循环会累积内存直至 std::bad_alloc。
    子进程退出后，OS 直接回收所有内存。
    """
    import subprocess
    import sys as _sys

    # 调用本脚本自身的 _extract_single_chunk 入口
    cmd = [
        _sys.executable, __file__,
        "_extract_single_chunk",
        pdf_path,
        output_dir,
        str(page_start),
        str(page_end),
    ]
    if ocr_scale is not None:
        cmd.append(str(ocr_scale))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,  # 单块 10 分钟超时
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"块 p.{page_start}-{page_end} 超时（>10 分钟）"}

    if result.returncode != 0:
        tail = (result.stderr or "")[-500:]
        return {"status": "error", "message": f"块 p.{page_start}-{page_end} 子进程退出 {result.returncode}:\n{tail}"}

    # 子进程通过 stdout 最后一行打印 JSON 路径
    stdout_lines = [l for l in (result.stdout or "").splitlines() if l.strip()]
    if not stdout_lines:
        return {"status": "error", "message": f"块 p.{page_start}-{page_end} 无输出"}
    last_line = stdout_lines[-1].strip()
    if last_line.startswith("{"):
        try:
            return json.loads(last_line)
        except json.JSONDecodeError:
            pass
    # fallback：子进程没打 JSON，按约定路径推断
    pdf_path_obj = Path(pdf_path)
    out_dir = Path(output_dir)
    md_path = out_dir / "extracted_content.md"
    json_path = out_dir / "extracted_content.json"
    if md_path.exists():
        return {
            "status": "success",
            "markdown_path": str(md_path),
            "json_path": str(json_path),
            "pages": page_end - page_start + 1,
        }
    return {"status": "error", "message": f"块 p.{page_start}-{page_end} 未产生文件"}


def chunked_extract_pdf(pdf_path: str, output_dir: str = None, chunk_size: int = 50,
                        ocr_scale: int = None) -> Dict[str, Any]:
    """分块提取大 PDF，避免 docling-parse C++ 端内存累积导致 std::bad_alloc。

    关键策略：**每块在独立 Python 子进程中跑**。
    Python GC 管不到 docling-parse / onnxruntime 的 C++ 堆，单进程内循环会累积内存直至崩。
    子进程退出后 OS 直接回收所有内存。

    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录
        chunk_size: 每块页数（默认 50，失败可降到 25）
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return {"status": "error", "message": f"PDF 不存在: {pdf_path}"}

    if output_dir is None:
        output_dir = pdf_path.parent / f"Review - {pdf_path.stem}"
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_pages = _get_pdf_page_count(pdf_path)
    if total_pages == 0:
        return {"status": "error", "message": f"无法读取 PDF 页数: {pdf_path}"}

    total_chunks = (total_pages + chunk_size - 1) // chunk_size
    print(
        f"[Controller] 分块提取: {total_pages} 页 / chunk_size={chunk_size} = {total_chunks} 块\n"
        f"  预计耗时：每块 2-5 分钟，总计 {total_chunks * 3}-{total_chunks * 5} 分钟",
        file=sys.stderr,
    )

    all_markdown = []
    all_doc_dicts = []
    pages_processed = 0
    pages_failed = 0
    failed_ranges = []
    chunk_idx = 0

    # 临时子目录存放每块的产物，避免文件名冲突
    chunks_tmp_dir = output_dir / ".chunks"
    chunks_tmp_dir.mkdir(exist_ok=True)

    import time
    overall_start = time.time()

    for start in range(1, total_pages + 1, chunk_size):
        end = min(start + chunk_size - 1, total_pages)
        chunk_idx += 1
        chunk_subdir = chunks_tmp_dir / f"p{start:04d}-{end:04d}"
        chunk_subdir.mkdir(exist_ok=True)

        elapsed = time.time() - overall_start
        avg_per_chunk = elapsed / (chunk_idx - 1) if chunk_idx > 1 else 0
        eta = avg_per_chunk * (total_chunks - chunk_idx + 1)
        print(
            f"[Controller] [{chunk_idx}/{total_chunks}] p.{start}-{end} ..."
            + (f" (已 {elapsed/60:.1f}min, 预计剩 {eta/60:.1f}min)" if chunk_idx > 1 else ""),
            file=sys.stderr,
        )

        chunk_start = time.time()
        chunk_result = _extract_chunk_in_subprocess(
            str(pdf_path), str(chunk_subdir), start, end, ocr_scale=ocr_scale
        )
        print(f"  块耗时 {(time.time() - chunk_start)/60:.1f}min", file=sys.stderr)

        # partial 块（部分页成功）直接接受，保留 docling 的公式占位符和版面分析
        # 只有 error 块（0 页成功）才 fallback 到 PyMuPDF+RapidOCR（会丢失公式占位符）
        if chunk_result.get("status") == "error":
            err = chunk_result.get("message", "")[:300]
            print(f"[Controller]   块失败 p.{start}-{end}: {err}", file=sys.stderr)
            print(f"[Controller]   尝试 PyMuPDF+RapidOCR fallback...", file=sys.stderr)
            fb_result = extract_pdf_pymupdf_rapidocr(
                str(pdf_path), str(chunk_subdir), page_range=(start, end)
            )
            if fb_result.get("status") in ("success", "partial"):
                chunk_md_path = Path(fb_result["markdown_path"])
                chunk_md = chunk_md_path.read_text(encoding="utf-8")
                all_markdown.append(chunk_md)
                pages_processed += fb_result.get("pages", 0)
                pages_failed += fb_result.get("pages_failed", 0)
                print(f"[Controller]   fallback 成功: {fb_result.get('pages',0)} 页", file=sys.stderr)
                continue
            else:
                pages_failed += (end - start + 1)
                failed_ranges.append((start, end))
                print(f"[Controller]   fallback 也失败: {fb_result.get('message','')[:200]}", file=sys.stderr)
                continue
        elif chunk_result.get("status") == "partial":
            # partial 块接受，记录失败页数
            pages_failed += chunk_result.get("pages_failed", 0)

        chunk_md_path = Path(chunk_result["markdown_path"])
        chunk_md = chunk_md_path.read_text(encoding="utf-8")
        all_markdown.append(chunk_md)

        chunk_json_path = Path(chunk_result["json_path"])
        with open(chunk_json_path, "r", encoding="utf-8") as f:
            chunk_dict = json.load(f)
        all_doc_dicts.append(chunk_dict)

        pages_processed += chunk_result.get("pages", 0)

    if not all_markdown:
        return {
            "status": "error",
            "message": f"所有 {len(failed_ranges)} 块都提取失败",
        }

    # 写合并 markdown
    combined_md = "\n\n---\n\n".join(all_markdown)
    markdown_path = output_dir / "extracted_content.md"
    markdown_path.write_text(combined_md, encoding="utf-8")

    # 写合并 JSON（简单合并，pages 字段合并）
    combined_json = {
        "schema_name": all_doc_dicts[0].get("schema_name", "DoclingDocument"),
        "version": all_doc_dicts[0].get("version"),
        "name": pdf_path.stem,
        "origin": all_doc_dicts[0].get("origin"),
        "pages": {},
        "chapters_merged": len(all_doc_dicts),
    }
    for d in all_doc_dicts:
        if isinstance(d.get("pages"), dict):
            combined_json["pages"].update(d["pages"])
    json_path = output_dir / "extracted_content.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(combined_json, f, ensure_ascii=False, indent=2)

    print(
        f"[Controller] 合并完成: {pages_processed}/{total_pages} 页成功"
        f"（{pages_failed} 页失败，{len(failed_ranges)} 块）→ {markdown_path}",
        file=sys.stderr,
    )

    return {
        "status": "success" if pages_failed == 0 else "partial",
        "pdf_path": str(pdf_path),
        "source_path": str(pdf_path),
        "output_dir": str(output_dir),
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "pages": total_pages,
        "pages_processed": pages_processed,
        "pages_failed": pages_failed,
        "failed_ranges": failed_ranges,
        "stem": pdf_path.stem,
    }


def extract_multiple(source_paths: list, output_dir: str = None,
                     chunk_size: int = None, no_chunk: bool = False,
                     strip_images: bool = False, ocr_correct: bool = False) -> Dict[str, Any]:
    """提取**多个**文件并合并为一个 markdown（用于跨资料复习）

    支持混合格式（如 ["a.pdf", "b.docx", "c.md"]）。
    每个文件单独提取，最后串成一个 extracted_content.md。
    章节标题前会标注 [来源: <stem>]
    """
    if not source_paths:
        return {"status": "error", "message": "未提供源文件"}

    if output_dir is None:
        first = Path(source_paths[0])
        output_dir = first.parent / "Review - combined"
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    combined_md = []
    combined_sources = []
    total_pages = 0

    for src_path in source_paths:
        src = Path(src_path)
        # 每个文件单独子目录。用 stem + ext 避免同名不同格式的文件互相覆盖
        # （如 a.docx + a.md 都有 stem "a"，需用 "a.docx" / "a.md" 区分）
        sub_dir = output_dir / f"{src.stem} ({src.suffix.lstrip('.')})"
        result = extract(str(src), str(sub_dir),
                         chunk_size=chunk_size, no_chunk=no_chunk,
                         strip_images=strip_images, ocr_correct=ocr_correct)
        if result.get("status") not in ("success", "partial"):
            print(f"[Controller] 跳过失败的文件: {src}")
            continue

        # 读 markdown 加来源标注
        sub_md = Path(result["markdown_path"]).read_text(encoding="utf-8")
        pages = result.get("pages", 0)
        combined_md.append(f"\n\n# === 来源：{src.stem} ({pages} 页) ===\n\n{sub_md}")
        combined_sources.append({"stem": src.stem, "pages": pages})
        total_pages += pages

    if not combined_md:
        return {"status": "error", "message": "所有文件都提取失败"}

    # 写合并 markdown
    combined_path = output_dir / "extracted_content.md"
    combined_path.write_text("\n".join(combined_md), encoding="utf-8")
    print(f"\n[Controller] 合并完成: {len(combined_sources)} 个文件 / {total_pages} 页")
    print(f"  合并 Markdown: {combined_path}")
    print(f"  来源: {combined_sources}")

    return {
        "status": "success",
        "output_dir": str(output_dir),
        "markdown_path": str(combined_path),
        "sources": combined_sources,
        "total_pages": total_pages,
    }


# 向后兼容别名
extract_multiple_pdfs = extract_multiple


def extract(source_path: str, output_dir: str = None,
            chunk_size: int = None, no_chunk: bool = False,
            strip_images: bool = False, ocr_correct: bool = False,
            use_cache: bool = True, backend: str = None) -> Dict[str, Any]:
    """顶层提取分发器。按扩展名路由。

    - .pdf → extract_pdf / chunked_extract_pdf / extract_pdf_pymupdf_rapidocr
    - .docx → extractors.extract_document（MarkItDown/mammoth 内核）
    - .txt/.md → extractors.extract_document（charset-normalizer 编码检测）

    非 PDF 格式忽略 chunk_size / no_chunk / backend 参数（仅对 PDF 生效）。
    strip_images 对 DOCX 有效（剥离 base64 图片为独立文件）。
    ocr_correct 对 PDF 有效（扫描版 OCR 后纠错常见误判）。
    use_cache: 是否使用提取缓存（默认 True，--no-cache 可关闭）。
    backend: PDF 提取后端，auto（默认）/ docling / pymupdf。
        - auto: docling 优先，块失败时自动 PyMuPDF+RapidOCR fallback；重试链走完仍 partial 时整体 fallback
        - docling: 仅 docling（含 per-chunk fallback）
        - pymupdf: 直接 PyMuPDF+RapidOCR，跳过 docling（最稳定，但无版面/表格/公式）
    """
    from config import get_config
    cfg = get_config()
    if backend is None:
        backend = cfg.pdf_backend() if hasattr(cfg, "pdf_backend") else "auto"

    path = Path(source_path)
    if not path.exists():
        return {"status": "error", "message": f"文件不存在: {path}"}

    # === 安全：文件大小检查 ===
    size_mb = path.stat().st_size / 1024 / 1024
    max_mb = cfg.max_file_size_mb(path.suffix)
    if size_mb > max_mb:
        return {
            "status": "error",
            "message": f"文件过大：{size_mb:.1f}MB > 限制 {max_mb}MB（{path.suffix}）。"
                       f"可在 config.yaml 的 extraction.max_{path.suffix.lstrip('.')}_size_mb 调整。",
        }

    # === 确定输出目录 ===
    if output_dir is None:
        output_dir = path.parent / f"Review - {path.stem}"
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # === 缓存检查 ===
    if use_cache and cfg.cache_enabled():
        from cache import check_cache, compute_file_hash, save_cache
        file_hash = compute_file_hash(path)
        cached = check_cache(output_dir, file_hash, cfg.cache_dir_name())
        if cached is not None:
            return cached

    # === 提取（带重试）===
    ext = path.suffix.lower()
    # 读 config 的 ocr_scale（PDF 专用，降低 RapidOCR 渲染 scale 避免 numpy 内存爆炸）
    ocr_scale = cfg.ocr_scale() if ext == ".pdf" else None
    # pymupdf 后端直接走 fallback，不需 docling 重试
    if ext == ".pdf" and backend == "pymupdf":
        print("[Controller] backend=pymupdf，直接用 PyMuPDF+RapidOCR 提取", file=sys.stderr)
        result = extract_pdf_pymupdf_rapidocr(str(path), str(output_dir), ocr_correct=ocr_correct)
    else:
        result = _do_extract(path, output_dir, chunk_size, no_chunk, strip_images, ocr_correct, cfg, ocr_scale=ocr_scale)

    # === 重试逻辑：PDF chunked 失败时减小 chunk_size 重试 ===
    # error 或 partial（失败比例高）都触发重试
    if result.get("status") in ("error", "partial") and ext == ".pdf" and not no_chunk and backend != "pymupdf":
        # 优化：error 状态（docling 完全失败或失败比例高）直接跳过重试，让整体 fallback 接管
        # 因为 chunk_size 减小解决不了"单页内存爆炸"问题
        if result.get("status") == "error" and backend == "auto":
            print(f"[Controller] docling 失败（error），跳过重试，直接整体 fallback", file=sys.stderr)
        else:
            max_retries = cfg.max_retries()
            shrink = cfg.retry_chunk_shrink()
            for retry_i in range(max_retries):
                # 优化：如果失败比例 > 50%，说明 chunk_size 减小无效，直接整体 fallback
                if result.get("status") == "partial":
                    processed = result.get("pages_processed", 0)
                    failed = result.get("pages_failed", 0)
                    total = processed + failed
                    if total > 0 and failed / total > 0.5:
                        print(f"[Controller] 失败比例 {failed}/{total} > 50%，跳过重试，直接整体 fallback", file=sys.stderr)
                        break
                current_chunk = (chunk_size or cfg.chunk_size()) // (shrink ** (retry_i + 1))
                if current_chunk < 5:
                    break  # chunk 太小没意义
                print(
                    f"[Controller] 第 {retry_i + 1} 次重试：chunk_size={current_chunk}",
                    file=sys.stderr,
                )
                result = _do_extract(path, output_dir, current_chunk, False, strip_images, ocr_correct, cfg, ocr_scale=ocr_scale)
                status = result.get("status")
                if status == "success":
                    break
                if status == "partial":
                    # partial 时检查失败比例：失败 < 10% 可接受，否则继续重试更小 chunk
                    processed = result.get("pages_processed", 0)
                    failed = result.get("pages_failed", 0)
                    total = processed + failed
                    if total > 0 and failed / total < 0.1:
                        print(f"[Controller] 接受 partial：{processed}/{total} 页成功（失败 {failed} 页 < 10%）", file=sys.stderr)
                        break
                    # 失败多，继续重试

    # === 整体 fallback：docling 重试链走完仍 partial/error，且 backend=auto，用 PyMuPDF+RapidOCR 兜底 ===
    # === 整体 fallback：仅当 docling 完全失败（error，0 页成功）才走 PyMuPDF+RapidOCR ===
    # 注意：partial 状态（部分页成功）不触发 fallback，因为 pdfium partial 仍有公式占位符，
    # fallback 到 PyMuPDF+RapidOCR 会丢失公式占位符（降质量）。只有 0 页成功才 fallback。
    if (result.get("status") == "error" and ext == ".pdf" and backend == "auto"
            and result.get("backend") != "pymupdf_rapidocr"):
        print(f"[Controller] docling 完全失败，整体 fallback 到 PyMuPDF+RapidOCR", file=sys.stderr)
        fb = extract_pdf_pymupdf_rapidocr(str(path), str(output_dir),
                                          dpi=cfg.fallback_dpi(), ocr_correct=ocr_correct)
        if fb.get("status") in ("success", "partial"):
            result = fb

    # === 保存缓存 ===
    if use_cache and cfg.cache_enabled() and result.get("status") in ("success", "partial"):
        try:
            save_cache(output_dir, file_hash, result, cfg.cache_dir_name())
        except Exception as e:
            # 缓存失败不影响主流程，仅提示
            print(f"[Controller] 缓存写入失败（不影响本次结果）: {e}", file=sys.stderr)

    return result


def _do_extract(path, output_dir, chunk_size, no_chunk, strip_images, ocr_correct, cfg,
                ocr_scale: int = None) -> Dict[str, Any]:
    """实际提取逻辑（不含缓存/重试），由 extract() 调用。"""

    if path.suffix.lower() == ".pdf":
        use_chunked = False
        effective_chunk_size = chunk_size or cfg.chunk_size()
        auto_mb = cfg.auto_chunk_size_mb()
        auto_pages = cfg.auto_chunk_pages()

        if not no_chunk:
            size_mb = path.stat().st_size / 1024 / 1024
            page_count = _get_pdf_page_count(path)
            if chunk_size:
                use_chunked = True
            elif size_mb > auto_mb or page_count > auto_pages:
                use_chunked = True
                print(
                    f"[Controller] 检测到大 PDF（{size_mb:.1f}MB / {page_count} 页），"
                    f"自动启用分块提取（chunk={effective_chunk_size}）",
                    file=sys.stderr,
                )

        if use_chunked:
            return chunked_extract_pdf(str(path), str(output_dir), effective_chunk_size, ocr_scale=ocr_scale)
        return extract_pdf(str(path), str(output_dir), ocr_correct=ocr_correct, ocr_scale=ocr_scale)

    # 非 PDF：chunk_size / no_chunk 不适用，仅提示
    if chunk_size is not None or no_chunk:
        print(
            "[Controller] 提示：--chunk-size / --no-chunk 仅对 PDF 生效，"
            f"对 {path.suffix} 文件无作用",
            file=sys.stderr,
        )
    from extractors import extract_document
    return extract_document(str(path), str(output_dir), strip_images=strip_images)


# ============ Phase: HTML 生成 ============

def validate_notes(notes_path: str) -> Dict[str, Any]:
    """校验 Pass 2 segment notes JSON 是否合法。

    用于：Pass 2 子 agent 输出后立即校验，避免 Pass 3 merger 读到坏 JSON 崩。

    Returns:
        {"status": "ok"/"error", "file": ..., "errors": [...]}
    """
    notes_path = Path(notes_path)
    if not notes_path.exists():
        return {"status": "error", "file": str(notes_path), "errors": ["文件不存在"]}

    errors = []
    try:
        with open(notes_path, "r", encoding="utf-8") as f:
            raw = f.read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            # 给出具体行+列+上下文
            line = e.lineno
            col = e.colno
            # 提取出错行
            lines = raw.splitlines()
            ctx = lines[line - 1] if 0 < line <= len(lines) else ""
            pointer = " " * (col - 1) + "^"
            errors.append(f"JSON 语法错误 line {line} col {col}: {e.msg}\n  {ctx}\n  {pointer}")
            return {"status": "error", "file": str(notes_path), "errors": errors}
    except Exception as e:
        return {"status": "error", "file": str(notes_path), "errors": [f"读取失败: {e}"]}

    # Schema 校验
    required_top = ["segment_id", "page_range", "concepts"]
    for key in required_top:
        if key not in data:
            errors.append(f"缺字段: {key}")

    if "concepts" in data and isinstance(data["concepts"], list):
        for i, c in enumerate(data["concepts"]):
            if not isinstance(c, dict):
                errors.append(f"concepts[{i}] 不是 dict")
                continue
            for req in ["name", "page"]:
                if req not in c:
                    errors.append(f"concepts[{i}] 缺字段: {req}")
            # 检查 unicode 数学符号（√ ≤ ≥ 等）
            for field in ["name", "definition"]:
                val = c.get(field, "")
                if isinstance(val, str):
                    bad = [ch for ch in "√≤≥∈∉⊂⊃∪∩∀∃→⇒⇔∞∂∇⋅∘" if ch in val]
                    if bad:
                        errors.append(f"concepts[{i}].{field} 含 unicode 数学符号: {bad}")

    if "formulas" in data and isinstance(data["formulas"], list):
        for i, f in enumerate(data["formulas"]):
            if not isinstance(f, dict):
                continue
            latex = f.get("latex", "")
            if isinstance(latex, str):
                bad = [ch for ch in "√≤≥∈∉⊂⊃∪∩∀∃→⇒⇔∞∂∇⋅∘" if ch in latex]
                if bad:
                    errors.append(f"formulas[{i}].latex 含 unicode: {bad}")

    return {
        "status": "ok" if not errors else "error",
        "file": str(notes_path),
        "errors": errors,
        "stats": {
            "concepts": len(data.get("concepts", [])),
            "formulas": len(data.get("formulas", [])),
            "pitfalls": len(data.get("pitfalls", [])),
        },
    }


def generate_html(knowledge_path: str, output_path: str = None,
                  fmt: str = "html", template_path: str = None) -> Dict[str, Any]:
    """从 knowledge JSON 生成 HTML/MD/JSON（调 generate_html.py 子进程）"""
    import subprocess

    knowledge_path = Path(knowledge_path).resolve()
    if not knowledge_path.exists():
        return {"status": "error", "message": f"JSON 不存在: {knowledge_path}"}

    cmd = [sys.executable, str(Path(__file__).parent / "generate_html.py"), str(knowledge_path)]
    if output_path:
        cmd.append(str(Path(output_path).resolve()))
    if fmt and fmt != "html":
        cmd.extend(["--format", fmt])
    if template_path:
        cmd.extend(["--template", str(Path(template_path).resolve())])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return {"status": "error", "message": result.stderr}

    # 推断输出路径
    if output_path is None:
        output_dir = knowledge_path.parent
        stem = knowledge_path.stem.replace("_knowledge", "")
        ext = {"html": ".html", "md": ".md", "json": ".json"}.get(fmt, ".html")
        if output_dir.name.startswith("Review - "):
            out_file = output_dir / f"Review - {stem}{ext}"
        else:
            out_file = output_dir / f"{stem}_review{ext}"
    else:
        out_file = Path(output_path)

    print(f"[Controller] 生成完成: {out_file}")

    return {
        "status": "success",
        "html_path": str(out_file),  # 向后兼容字段名（实际 ext 由 fmt 决定）
        "output_path": str(out_file),
        "format": fmt,
    }


# ============ CLI ============

def _cmd_init():
    """init 子命令：检查依赖 + 生成配置模板。"""
    print("=== exam-review-helper 初始化检查 ===\n")

    # 1. 检查 Python 依赖
    deps = [
        ("docling", "PDF 提取（含 OCR）"),
        ("markitdown", "DOCX 提取"),
        ("charset_normalizer", "TXT/MD 编码检测"),
        ("fitz", "PyMuPDF（PDF 页数）"),
        ("yaml", "PyYAML（配置文件）"),
    ]
    all_ok = True
    for mod_name, desc in deps:
        try:
            __import__(mod_name)
            print(f"  ✅ {mod_name:25s} {desc}")
        except ImportError:
            print(f"  ❌ {mod_name:25s} {desc} —— pip install {mod_name.replace('_', '-')}")
            all_ok = False

    # 2. 检查 config.yaml
    skill_root = Path(__file__).parent.parent
    config_path = skill_root / "config.yaml"
    if config_path.exists():
        print(f"\n  ✅ config.yaml 已存在: {config_path}")
    else:
        print(f"\n  ⚠️  config.yaml 不存在（将用内置默认值）")

    # 3. 检查 templates/default.html
    template_path = skill_root / "templates" / "default.html"
    if template_path.exists():
        print(f"  ✅ templates/default.html 已存在")
    else:
        print(f"  ⚠️  templates/default.html 不存在（generate 命令将失败）")

    # 4. 总结
    print("\n=== 总结 ===")
    if all_ok:
        print("所有依赖已安装，skill 可正常使用。")
    else:
        print("部分依赖缺失，请按上方提示安装。")
        print("完整安装：pip install -r requirements.txt")

    print("\n用法：python controller.py extract textbook.pdf")


def main():
    # 隐藏入口：子进程跑单块提取（不走 argparse）
    if len(sys.argv) > 1 and sys.argv[1] == "_extract_single_chunk":
        pdf_path = sys.argv[2]
        output_dir = sys.argv[3]
        try:
            page_start = int(sys.argv[4])
            page_end = int(sys.argv[5])
        except (ValueError, IndexError):
            print(json.dumps({"status": "error", "message": "参数必须是整数"}))
            sys.exit(2)
        if page_start < 1 or page_end < page_start:
            print(json.dumps({"status": "error", "message": f"页码范围无效: {page_start}-{page_end}"}))
            sys.exit(2)
        # 可选第 6 参数：ocr_scale（降低 RapidOCR 渲染 scale 避免 numpy 内存爆炸）
        ocr_scale = None
        if len(sys.argv) > 6:
            try:
                ocr_scale = int(sys.argv[6])
            except ValueError:
                pass
        # 注意：分块子进程模式不支持 ocr_correct（ocr_correct 仅在单进程 extract_pdf 生效）
        # 因为分块提取走 chunked_extract_pdf → 多子进程并行，每块独立提取后合并，
        # OCR 纠错在合并后由调用方对完整 markdown 调用 ocr_corrector.correct_ocr_errors
        result = extract_pdf(pdf_path, output_dir, page_range=(page_start, page_end), ocr_scale=ocr_scale)
        # 通过 stdout 最后一行打印 JSON 结果
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0 if result.get("status") == "success" else 1)

    parser = argparse.ArgumentParser(
        description="exam-review-helper 控制器（对话驱动版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
5-pass 知识提取由宿主 LLM 对话执行，不在本脚本内。

典型流程:
  1. python controller.py extract textbook.pdf   # 或 notes.docx / chapter.txt / module.md
       → 生成 Review - textbook/extracted_content.md
  2. [宿主 LLM 执行 5-pass，参考 SKILL.md + prompts/ + references/]
       → 生成 Review - textbook/textbook_knowledge.json
  3. python controller.py generate Review - textbook/textbook_knowledge.json
       → 生成 Review - textbook/Review - textbook.html

高级:
  python controller.py --version              # 显示版本
  python controller.py --config my.yaml extract book.pdf  # 用自定义配置
  python controller.py init                   # 检查依赖 + 生成配置模板
  python controller.py generate k.json --format md  # 输出 Markdown 而非 HTML
        """,
    )
    parser.add_argument("--version", action="store_true", help="显示版本号并退出")
    parser.add_argument("--config", default=None, help="配置文件路径（默认读 config.yaml）")

    sub = parser.add_subparsers(dest="command", required=False)

    p_extract = sub.add_parser(
        "extract",
        help="提取教材（支持 PDF/DOCX/TXT/MD，可多个文件混合）",
    )
    p_extract.add_argument(
        "sources",
        nargs="+",
        help="源文件路径（可多个，支持混合格式：a.pdf b.docx c.md）",
    )
    p_extract.add_argument("--output-dir", default=None, help="输出目录（默认 Review - <stem>/ 或 Review - combined/）")
    p_extract.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="分块提取的每块页数（推荐 50）。不传则自动判断：>100 页或 >50MB 的 PDF 自动启用",
    )
    p_extract.add_argument(
        "--no-chunk",
        action="store_true",
        help="禁用自动分块（即使 PDF 很大）",
    )
    p_extract.add_argument(
        "--strip-images",
        action="store_true",
        help="剥离 base64 内嵌图片为独立文件（DOCX 建议，可减小 markdown 体积 90%%）",
    )
    p_extract.add_argument(
        "--ocr-correct",
        action="store_true",
        help="对扫描版 PDF 的 OCR 输出做后处理纠错（修正常见汉字误判）",
    )
    p_extract.add_argument(
        "--no-cache",
        action="store_true",
        help="禁用提取缓存（强制重新提取）",
    )
    p_extract.add_argument(
        "--backend",
        choices=["auto", "docling", "pymupdf"],
        default=None,
        help="PDF 提取后端：auto（默认，docling 优先+自动 fallback）/ docling（仅 docling）/ pymupdf（直接 PyMuPDF+RapidOCR，最稳定但无版面/表格/公式）。扫描版 PDF 建议 auto 或 pymupdf",
    )

    p_gen = sub.add_parser("generate", help="从 knowledge JSON 生成 HTML/MD/JSON")
    p_gen.add_argument("knowledge_json", help="knowledge JSON 路径")
    p_gen.add_argument("--output", default=None, help="输出路径（可选，默认同目录）")
    p_gen.add_argument(
        "--format",
        choices=["html", "md", "json"],
        default="html",
        help="输出格式（默认 html）",
    )
    p_gen.add_argument("--template", default=None, help="自定义 HTML 模板路径（仅 --format=html 有效）")

    p_val = sub.add_parser("validate", help="校验 Pass 2 segment notes JSON 是否合法")
    p_val.add_argument("notes_path", help="notes JSON 文件路径（或目录，目录则校验 notes_*.json）")
    p_val.add_argument("--strict", action="store_true", help="严格模式：有任何 warning 都 exit 1")

    p_init = sub.add_parser("init", help="检查依赖 + 生成配置模板")

    args = parser.parse_args()

    # --version
    if args.version:
        try:
            from config import get_config
            version = get_config().get("skill.version", "1.0.0") or "1.0.0"
        except Exception:
            version = "1.0.0"
        print(f"exam-review-helper {version}")
        sys.exit(0)

    # 加载配置（所有子命令都需要）
    if args.config:
        from config import load_config
        load_config(args.config)
    else:
        from config import load_config
        load_config()

    # init 子命令
    if args.command == "init":
        _cmd_init()
        sys.exit(0)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "extract":
        use_cache = not args.no_cache
        if len(args.sources) == 1:
            result = extract(
                args.sources[0],
                args.output_dir,
                chunk_size=args.chunk_size,
                no_chunk=args.no_chunk,
                strip_images=args.strip_images,
                ocr_correct=args.ocr_correct,
                use_cache=use_cache,
                backend=args.backend,
            )
        else:
            result = extract_multiple(
                args.sources,
                args.output_dir,
                chunk_size=args.chunk_size,
                no_chunk=args.no_chunk,
                strip_images=args.strip_images,
                ocr_correct=args.ocr_correct,
            )
    elif args.command == "generate":
        result = generate_html(args.knowledge_json, args.output,
                               fmt=args.format, template_path=args.template)
    elif args.command == "validate":
        target = Path(args.notes_path)
        if target.is_dir():
            # 校验目录下所有 notes_*.json
            notes_files = sorted(target.glob("notes_*.json"))
            if not notes_files:
                print(f"[Controller] 目录下无 notes_*.json: {target}", file=sys.stderr)
                sys.exit(1)
            all_errors = []
            ok_count = 0
            for nf in notes_files:
                r = validate_notes(str(nf))
                if r["status"] == "ok":
                    ok_count += 1
                    s = r.get("stats", {})
                    print(f"  ✅ {nf.name}: {s.get('concepts', 0)} concepts / {s.get('formulas', 0)} formulas / {s.get('pitfalls', 0)} pitfalls")
                else:
                    print(f"  ❌ {nf.name}:")
                    for err in r["errors"]:
                        print(f"     {err}")
                    all_errors.extend(r["errors"])
            print(f"\n[Controller] {ok_count}/{len(notes_files)} 文件通过校验")
            if all_errors:
                sys.exit(1 if args.strict else 0)
            sys.exit(0)
        else:
            result = validate_notes(args.notes_path)
            if result["status"] == "ok":
                s = result.get("stats", {})
                print(f"✅ {result['file']}: {s.get('concepts', 0)} concepts / {s.get('formulas', 0)} formulas / {s.get('pitfalls', 0)} pitfalls")
                sys.exit(0)
            else:
                print(f"❌ {result['file']}:")
                for err in result["errors"]:
                    print(f"  {err}")
                sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    status = result.get("status", "error")
    if status == "success":
        sys.exit(0)
    elif status == "partial":
        # 部分成功：打印警告但 exit 0（已生成可用产物）
        print(
            f"[Controller] 警告：{result.get('pages_failed', 0)} 页提取失败，"
            f"失败范围：{result.get('failed_ranges', [])}",
            file=sys.stderr,
        )
        sys.exit(0)
    else:
        print(f"错误: {result.get('message', '未知')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
