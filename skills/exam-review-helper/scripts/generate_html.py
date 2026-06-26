"""
HTML / Markdown / JSON 生成脚本 - 从知识点 JSON 生成复习文档

支持三种输出格式：
  --format html  (默认)  交互式 HTML（MathJax + 暗黑模式 + 搜索）
  --format md            纯 Markdown（便于版本控制 / 二次编辑）
  --format json          格式化 JSON（便于程序消费）

安全：所有用户可控字段（book_title、chapter_title 等）做 HTML 转义防 XSS。
"""
import html as html_lib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def _escape_html(text: str) -> str:
    """HTML 转义防 XSS。转义 < > & " ' 五个字符。"""
    if not isinstance(text, str):
        return text
    return html_lib.escape(text, quote=True)


def _sanitize_markdown(text: str) -> str:
    """Markdown 输出的 XSS 过滤。

    Markdown 不执行 JS，但渲染时仍可能被滥用：
    - `[x](javascript:...)` 链接
    - `![x](x onerror=...)` 图片
    - `<script>...</script>` 内联标签

    本函数过滤这些危险模式，保留正常 Markdown 语法。
    """
    if not isinstance(text, str):
        return text
    # 1. 删除 <script>...</script> 块
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    # 2. 删除 javascript: 协议（链接/图片 URL 中）
    text = re.sub(r'(?i)\bjavascript\s*:', '', text)
    # 3. 删除 on* 事件属性（如 onerror=）
    text = re.sub(r'(?i)\son\w+\s*=', '', text)
    return text


def load_template(template_path: Optional[str] = None) -> str:
    """加载 HTML 模板。优先级：--template 参数 > templates/default.html。"""
    skill_root = Path(__file__).parent.parent

    if template_path:
        # 用户指定的自定义模板
        p = Path(template_path)
        if not p.is_absolute():
            p = skill_root / p
        if p.exists():
            return p.read_text(encoding="utf-8")
        raise ValueError(f"模板文件不存在: {p}")

    # 默认模板
    default = skill_root / "templates" / "default.html"
    if default.exists():
        return default.read_text(encoding="utf-8")

    raise FileNotFoundError(f"未找到 HTML 模板: {default}")


def generate_html(
    knowledge_path: str,
    output_path: Optional[str] = None,
    book_title: Optional[str] = None,
    template_path: Optional[str] = None,
) -> Dict[str, Any]:
    """生成交互式 HTML 文件。

    Args:
        knowledge_path: 知识点 JSON 文件路径
        output_path: 输出 HTML 路径（可选，默认同目录）
        book_title: 教材名称（可选，从 JSON 推断）
        template_path: 自定义模板路径（可选，默认 templates/default.html）

    Returns:
        {"status": "success", "html_path": ...} 或 {"status": "error", "message": ...}
    """
    knowledge_path = Path(knowledge_path)
    if not knowledge_path.exists():
        return {"status": "error", "message": f"JSON 不存在: {knowledge_path}"}

    # 读取知识点数据
    with open(knowledge_path, "r", encoding="utf-8") as f:
        knowledge_data = json.load(f)

    # 推断输出路径
    if output_path is None:
        output_dir = knowledge_path.parent
        source_name = knowledge_path.stem.replace("_knowledge", "")
        if output_dir.name.startswith("Review - "):
            output_path = output_dir / f"Review - {source_name}.html"
        else:
            output_path = output_dir / f"{source_name}_review.html"

    # 推断教材名称（XSS 转义——用户可控字段）
    if book_title is None:
        book_title = knowledge_data.get("source", "教材")
    book_title_escaped = _escape_html(str(book_title))

    # 加载模板
    try:
        template = load_template(template_path)
    except (ValueError, FileNotFoundError) as e:
        return {"status": "error", "message": str(e)}

    # 替换占位符
    # 防 </script> 注入：JSON 中的 </ 转 <\/，浏览器 JSON.parse 自动还原
    # 防 <!-- 注入：HTML 注释开标签可触发老浏览器解析 quirks，转成 <\!--
    json_str = json.dumps(knowledge_data, ensure_ascii=False, indent=2)
    json_str = json_str.replace("</", "<\\/").replace("<!--", "<\\!--")

    html_content = template.replace("__DATA_PLACEHOLDER__", json_str)
    html_content = html_content.replace("[教材名称]", book_title_escaped)
    html_content = html_content.replace(
        "[时间戳]",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    # 写入文件
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")

    print(f"HTML 文件已生成: {output_path}")
    return {"status": "success", "html_path": str(output_path)}


def generate_markdown(knowledge_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    """生成纯 Markdown 文档（便于版本控制 / 二次编辑）。"""
    knowledge_path = Path(knowledge_path)
    with open(knowledge_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if output_path is None:
        output_dir = knowledge_path.parent
        source_name = knowledge_path.stem.replace("_knowledge", "")
        output_path = output_dir / f"Review - {source_name}.md"

    lines = []
    source = data.get("source", "教材")
    lines.append(f"# {source} - 复习笔记\n")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    for ch in data.get("chapters", []):
        lines.append(f"\n---\n")
        title = ch.get("chapter_title", "未命名章节")
        page_range = ch.get("page_range", "")
        lines.append(f"\n## {title}（p.{page_range}）\n")

        summary = ch.get("summary", "")
        if summary:
            lines.append(f"**本章摘要**：{summary}\n")

        # 概念
        concepts = ch.get("concepts", [])
        if concepts:
            lines.append(f"\n### 核心概念（{len(concepts)} 个）\n")
            for c in concepts:
                name = c.get("name", "")
                importance = c.get("importance", "")
                page = c.get("page", "")
                definition = c.get("definition", "")
                lines.append(f"- **{name}**（{importance}，p.{page}）：{definition}")
                boundary = c.get("boundary", "")
                if boundary:
                    lines.append(f"  - 边界：{boundary}")
                variation = c.get("variation", "")
                if variation:
                    lines.append(f"  - 变形：{variation}")

        # 公式
        formulas = ch.get("formulas", [])
        if formulas:
            lines.append(f"\n### 重要公式（{len(formulas)} 个）\n")
            for f in formulas:
                name = f.get("name", "")
                latex = f.get("latex", "")
                page = f.get("page", "")
                explanation = f.get("explanation", "")
                lines.append(f"- **{name}**（p.{page}）：`{latex}`")
                if explanation:
                    lines.append(f"  - {explanation}")

        # 例题/案例
        examples = ch.get("examples", [])
        if examples:
            lines.append(f"\n### 典型例题/案例（{len(examples)} 个）\n")
            for ex in examples:
                title = ex.get("title", "")
                desc = ex.get("description", "")
                key = ex.get("key_point", "")
                page = ex.get("page", "")
                lines.append(f"- **{title}**（p.{page}）：{desc}")
                if key:
                    lines.append(f"  - 要点：{key}")

        # 易错点
        pitfalls = ch.get("pitfalls", [])
        if pitfalls:
            lines.append(f"\n### 易错点/易混淆点（{len(pitfalls)} 个）\n")
            for p in pitfalls:
                warning = p.get("warning", "")
                correction = p.get("correction", "")
                example = p.get("example", "")
                page = p.get("page", "")
                lines.append(f"- ⚠️ **{warning}**（p.{page}）")
                if correction:
                    lines.append(f"  - 正确：{correction}")
                if example:
                    lines.append(f"  - 例子：{example}")

        # 关联
        connections = ch.get("connections", [])
        if connections:
            lines.append(f"\n### 理论关联\n")
            for conn in connections:
                ctype = conn.get("type", "")
                concept = conn.get("concept", "")
                ref = conn.get("chapter_ref", "")
                lines.append(f"- [{ctype}] {concept} → {ref}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = _sanitize_markdown("\n".join(lines))
    output_path.write_text(content, encoding="utf-8")

    print(f"Markdown 文件已生成: {output_path}")
    return {"status": "success", "md_path": str(output_path)}


def generate_json(knowledge_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    """输出格式化 JSON（便于程序消费）。"""
    knowledge_path = Path(knowledge_path)
    with open(knowledge_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if output_path is None:
        output_dir = knowledge_path.parent
        source_name = knowledge_path.stem.replace("_knowledge", "")
        output_path = output_dir / f"Review - {source_name}.json"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"JSON 文件已生成: {output_path}")
    return {"status": "success", "json_path": str(output_path)}


def generate(
    knowledge_path: str,
    output_path: Optional[str] = None,
    book_title: Optional[str] = None,
    fmt: str = "html",
    template_path: Optional[str] = None,
) -> Dict[str, Any]:
    """统一生成入口，按 fmt 分发到 html/markdown/json 生成器。"""
    if fmt == "html":
        return generate_html(knowledge_path, output_path, book_title, template_path)
    elif fmt == "md":
        return generate_markdown(knowledge_path, output_path)
    elif fmt == "json":
        return generate_json(knowledge_path, output_path)
    else:
        return {"status": "error", "message": f"不支持的格式: {fmt}（支持: html/md/json）"}


def main():
    """命令行入口。"""
    if len(sys.argv) < 2:
        print("用法: python generate_html.py <knowledge_json> [output] [book_title] [--format html|md|json] [--template PATH]")
        print("\n示例:")
        print("  python generate_html.py knowledge.json")
        print("  python generate_html.py knowledge.json --format md")
        print("  python generate_html.py knowledge.json --format html --template custom.html")
        sys.exit(1)

    knowledge_path = sys.argv[1]
    output_path = None
    book_title = None
    fmt = "html"
    template_path = None

    # 解析剩余参数（支持位置参数和 --flag）
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--format":
            fmt = args[i + 1]
            i += 2
        elif arg == "--template":
            template_path = args[i + 1]
            i += 2
        elif arg == "--book-title":
            book_title = args[i + 1]
            i += 2
        elif not arg.startswith("--") and output_path is None:
            output_path = arg
            i += 1
        elif not arg.startswith("--") and book_title is None:
            book_title = arg
            i += 1
        else:
            i += 1

    result = generate(knowledge_path, output_path, book_title, fmt, template_path)
    if result.get("status") == "success":
        path_key = [k for k in result if k.endswith("_path")]
        print(f"\n[OK] 成功生成: {result.get(path_key[0]) if path_key else 'done'}")
    else:
        print(f"\n[ERROR] {result.get('message')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
