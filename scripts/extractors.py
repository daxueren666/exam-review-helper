"""多格式文档提取（非 PDF）。

本模块处理 DOCX/TXT/MD 等非 PDF 格式，产出与 controller.py:extract_pdf 相同的
extracted_content.md + extracted_content.json 双文件结构，让下游 5-pass 流程
对输入格式无感知。

核心契约：
- extracted_content.md 必须包含 [PAGE N] 标记（非 PDF 格式按语义边界合成）
- 返回 dict 必须有 status/source_path/output_dir/markdown_path/json_path/pages/stem

底层库分工：
- DOCX → Microsoft MarkItDown（v0.1.6+, MIT，内部调 mammoth）
- TXT/MD → charset-normalizer（v3.4+，检测 GBK/GB2312/Big5/UTF-8 编码）
  MarkItDown 对 TXT 不做编码检测（按 Latin-1 读取导致中文乱码），所以 TXT/MD 走专用路径。
"""
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def synthesize_pages(markdown: str, min_page_chars: int = 1500) -> str:
    """按 H1/H2 标题切分 markdown，合成 [PAGE N] 标记。

    算法：
    1. 按 ^#{1,2} 切分为 sections（保留标题行）
    2. 累加 sections 到当前页，直到达到 min_page_chars
    3. 单个 section 超 min_page_chars * 4 时，按段落切分
    4. 首行强制 [PAGE 1]

    设计意图：
    - 太小页（< min）与下一节合并，避免"1页1句话"——verifier 会判失败
    - 太大页（> 4x min）按段落切分，避免"1页5000字"——planner 的 5-80 页/段规则会失效
    - 标题锚定保证语义边界（推导不被切断）
    """
    if not markdown.strip():
        return "[PAGE 1]\n"

    max_page_chars = min_page_chars * 4

    # 按 H1/H2 标题切分（# 和 ##，不切 ### 及以下，避免过细）
    heading_pattern = re.compile(r'^(#{1,2})\s+', re.MULTILINE)

    sections = []
    last_end = 0
    for m in heading_pattern.finditer(markdown):
        if m.start() > last_end:
            leading = markdown[last_end:m.start()].strip()
            if leading:
                sections.append(leading)
        next_match = heading_pattern.search(markdown, m.end())
        section_end = next_match.start() if next_match else len(markdown)
        section = markdown[m.start():section_end].strip()
        if section:
            sections.append(section)
        last_end = section_end

    if last_end < len(markdown):
        tail = markdown[last_end:].strip()
        if tail:
            sections.append(tail)

    if not sections:
        sections = [markdown.strip()]

    pages = []
    current_parts: list = []
    current_chars = 0

    def flush_current() -> None:
        nonlocal current_parts, current_chars
        if current_parts:
            pages.append("\n\n".join(current_parts))
            current_parts = []
            current_chars = 0

    for section in sections:
        section_len = len(section)

        if section_len > max_page_chars:
            # 超长 section：先 flush 当前页，再按段落二次切分
            flush_current()
            paragraphs = re.split(r'\n\s*\n', section)
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                if current_chars + len(para) > max_page_chars and current_parts:
                    flush_current()
                current_parts.append(para)
                current_chars += len(para)
        elif current_chars + section_len > min_page_chars and current_parts:
            # 加入此 section 会超 min，且当前页非空 → 新开一页
            flush_current()
            current_parts.append(section)
            current_chars = section_len
        else:
            current_parts.append(section)
            current_chars += section_len

    flush_current()

    if not pages:
        return "[PAGE 1]\n"

    result_parts = []
    for i, page in enumerate(pages, start=1):
        result_parts.append(f"[PAGE {i}]")
        result_parts.append(page)

    return "\n\n".join(result_parts)


def _count_pages(markdown: str) -> int:
    """统计 markdown 中的 [PAGE N] 标记数量。"""
    return len(re.findall(r'^\[PAGE \d+\]', markdown, re.MULTILINE))


def write_extracted_output(
    output_dir: Path,
    stem: str,
    markdown: str,
    source_path: Path,
    pages: int,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """写 extracted_content.md + extracted_content.json，返回与 extract_pdf 一致的 dict。

    JSON schema 与 PDF 的 DoclingDocument 不同（用 MultiFormatDocument），但保留
    pages 字段，让 multi-pass-workflow.md 的"从 pages 推断总页数"逻辑能工作。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = output_dir / "extracted_content.md"
    markdown_path.write_text(markdown, encoding="utf-8")

    doc_dict = {
        "schema_name": "MultiFormatDocument",
        "name": stem,
        "origin": str(source_path),
        "pages": {str(i): {"page_no": i} for i in range(1, pages + 1)},
        "page_count": pages,
        **(extra_meta or {}),
    }
    json_path = output_dir / "extracted_content.json"
    json_path.write_text(
        json.dumps(doc_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"[Extractors] 提取完成: {pages} 页 → {markdown_path}",
        file=sys.stderr,
    )

    return {
        "status": "success",
        "source_path": str(source_path),
        "output_dir": str(output_dir),
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "pages": pages,
        "stem": stem,
        **(extra_meta or {}),
    }


def _markitdown_convert(path: Path) -> str:
    """用 MarkItDown 转换文件为 markdown。

    延迟 import：markitdown 是新依赖，未装时给出明确提示而不是 ImportError 堆栈。
    仅用于 DOCX（markitdown 内部调 mammoth，质量可靠）。
    TXT/MD 不走此路径——markitdown 对 TXT 不做编码检测，中文 GBK 会乱码。
    """
    try:
        from markitdown import MarkItDown
    except ImportError as e:
        raise ImportError(
            "markitdown 未安装。请运行: pip install 'markitdown[docx]>=0.1.6'"
        ) from e
    md = MarkItDown()
    result = md.convert(str(path))
    return result.text_content


def _decode_text_file(path: Path) -> tuple:
    """用 charset-normalizer 检测编码并解码文本文件。

    返回 (decoded_text, encoding_name)。支持 UTF-8/GBK/GB2312/Big5 等。
    用于 TXT/MD——markitdown 对这些格式不做编码检测，中文 GBK 会乱码。
    """
    from charset_normalizer import from_path
    detected = from_path(str(path)).best()
    return str(detected), detected.encoding


def _strip_base64_images(markdown: str, images_dir: Path) -> tuple:
    """把 markdown 中的 base64 内嵌图片替换为文件引用，清理截断占位符。

    两种情况：
    1. 完整 base64：![](data:image/png;base64,iVBORw0KGgo...) → 存为 images/img_NNN.png
    2. MarkItDown 截断占位符：![](data:image/jpeg;base64...) → 替换为 <!-- image -->

    安全：单张图片超过 config 的 max_base64_image_mb 限制时跳过解码，替换为注释。

    Returns:
        (stripped_markdown, image_count_saved)
    """
    import base64

    # 从 config 读取图片大小限制
    try:
        from config import get_config
        max_img_mb = get_config().max_base64_image_mb()
    except Exception:
        max_img_mb = 50  # 默认 50MB

    images_dir.mkdir(parents=True, exist_ok=True)
    img_count = 0

    def replace_full(m):
        nonlocal img_count
        mime_type = m.group(1)
        b64_data = m.group(2)
        ext = mime_type.split('/')[-1].lower()
        if ext == 'jpeg':
            ext = 'jpg'
        if ext not in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'tiff'):
            ext = 'png'

        # 安全：检查 base64 数据大小（粗略估算：base64 长度 * 3/4 = 原始字节数）
        estimated_size_mb = len(b64_data) * 3 / 4 / 1024 / 1024
        if estimated_size_mb > max_img_mb:
            return f'<!-- image (skipped: {estimated_size_mb:.1f}MB > {max_img_mb}MB limit) -->'

        img_path = images_dir / f"img_{img_count + 1:03d}.{ext}"
        try:
            img_path.write_bytes(base64.b64decode(b64_data))
            img_count += 1
        except Exception:
            return '<!-- image (decode failed) -->'
        return f'![image](images/{img_path.name})'

    # 1. 匹配完整 base64 图片：![alt](data:image/png;base64,xxxx)
    full_pattern = re.compile(
        r'!\[[^\]]*\]\(data:(image/[\w.+-]+);base64,([A-Za-z0-9+/=\s]+)\)'
    )
    result = full_pattern.sub(replace_full, markdown)

    # 2. 清理 MarkItDown 截断占位符：![](data:image/...;base64...)
    # 这些不含实际图片数据，对 5-pass 无用，替换为注释
    truncated_pattern = re.compile(
        r'!\[[^\]]*\]\(data:image/[\w.+-]+;base64\.\.\.\)'
    )
    result = truncated_pattern.sub('<!-- image -->', result)

    return result, img_count


# ---- 解码器：每个返回 (text, extra_meta_dict)，供 _extract_text_based 复用 ----

def _decode_docx(path: Path) -> tuple:
    """DOCX → markdown via MarkItDown（mammoth 内核）"""
    return _markitdown_convert(path), {"extractor": "markitdown"}


def _decode_text_with_encoding(path: Path) -> tuple:
    """TXT/MD 共用：charset-normalizer 解码 + 记录编码"""
    text, encoding = _decode_text_file(path)
    return text, {"extractor": "charset-normalizer", "encoding": encoding}


def _extract_text_based(
    path: Path,
    output_dir: Path,
    decoder_fn,
    format_name: str,
    strip_images: bool = False,
) -> Dict[str, Any]:
    """共享提取逻辑：解码 → (可选剥离图片) → synthesize_pages → write_output。

    extract_docx / extract_txt / extract_markdown 三个函数 90% 逻辑相同，
    差异只在解码方式（MarkItDown vs charset-normalizer）和 format 字段。
    本函数消除重复，decoder_fn 屏蔽差异。

    strip_images: 是否剥离 base64 内嵌图片为独立文件。DOCX 提取建议开启，
    避免 base64 膨胀 markdown 体积导致 5-pass 上下文过长。
    """
    print(f"[Extractors] 正在提取 {format_name.upper()}: {path}", file=sys.stderr)
    try:
        text, decoder_meta = decoder_fn(path)
    except Exception as e:
        return {
            "status": "error",
            "message": f"{format_name.upper()} 提取失败（{type(e).__name__}: {e}）",
            "source_path": str(path),
        }

    if strip_images:
        text, img_count = _strip_base64_images(text, output_dir / "images")
        decoder_meta["images_stripped"] = img_count
        print(f"[Extractors] 剥离 {img_count} 张图片 → {output_dir / 'images'}", file=sys.stderr)

    markdown = synthesize_pages(text)
    pages = _count_pages(markdown)

    return write_extracted_output(
        output_dir, path.stem, markdown, path, pages,
        extra_meta={"format": format_name, **decoder_meta},
    )


def extract_docx(path: Path, output_dir: Path, strip_images: bool = False) -> Dict[str, Any]:
    """提取 DOCX 为 markdown。MarkItDown 内部调 mammoth，质量与直接用 mammoth 一致。

    strip_images=True 时把 base64 图片剥离为独立文件，大幅减小 markdown 体积。
    """
    return _extract_text_based(path, output_dir, _decode_docx, "docx", strip_images=strip_images)


def extract_txt(path: Path, output_dir: Path, strip_images: bool = False) -> Dict[str, Any]:
    """提取 TXT 为 markdown。

    用 charset-normalizer 检测编码（UTF-8/GBK/GB2312/Big5/GB18030）。
    MarkItDown 对 TXT 不做编码检测（按 Latin-1 读取导致中文乱码），所以走专用路径。
    """
    return _extract_text_based(path, output_dir, _decode_text_with_encoding, "txt", strip_images=strip_images)


def extract_markdown(path: Path, output_dir: Path, strip_images: bool = False) -> Dict[str, Any]:
    """提取 Markdown。

    用 charset-normalizer 检测编码（MD 文件可能是 UTF-8 或 GBK）。
    MD 已是 markdown 格式，无需 markitdown 转换——直接读文本 + synthesize_pages。
    """
    return _extract_text_based(path, output_dir, _decode_text_with_encoding, "markdown", strip_images=strip_images)


# 格式分发表（.doc 走 docx 提取器，mammoth 对 .doc 支持有限但能尝试）
EXTRACTORS: Dict[str, Any] = {
    ".docx": extract_docx,
    ".doc": extract_docx,
    ".txt": extract_txt,
    ".md": extract_markdown,
    ".markdown": extract_markdown,
}


def extract_document(
    source_path: str,
    output_dir: Optional[str] = None,
    strip_images: bool = False,
) -> Dict[str, Any]:
    """按扩展名分发到对应 extractor。

    Args:
        source_path: 源文件路径
        output_dir: 输出目录（默认 Review - <stem>/）
        strip_images: 是否剥离 base64 图片为独立文件（DOCX 建议 True）

    Returns:
        与 controller.py:extract_pdf 相同 shape 的 dict，包含
        status/source_path/output_dir/markdown_path/json_path/pages/stem
    """
    path = Path(source_path)
    if not path.exists():
        return {"status": "error", "message": f"文件不存在: {path}"}

    # === 安全：文件大小检查（从 config 读取限制）===
    try:
        from config import get_config
        cfg = get_config()
        size_mb = path.stat().st_size / 1024 / 1024
        max_mb = cfg.max_file_size_mb(path.suffix)
        if size_mb > max_mb:
            return {
                "status": "error",
                "message": f"文件过大：{size_mb:.1f}MB > 限制 {max_mb}MB（{path.suffix}）",
                "source_path": str(path),
            }
    except Exception:
        pass  # config 不可用时不阻断

    ext = path.suffix.lower()
    extractor = EXTRACTORS.get(ext)
    if extractor is None:
        supported = "/".join(EXTRACTORS.keys())
        return {
            "status": "error",
            "message": f"不支持的格式: {ext}（支持: {supported}）",
            "source_path": str(path),
        }

    if output_dir is None:
        output_dir = path.parent / f"Review - {path.stem}"
    else:
        output_dir = Path(output_dir)

    return extractor(path, output_dir, strip_images=strip_images)
