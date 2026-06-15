"""
HTML 生成脚本 - 从知识点 JSON 生成交互式 HTML 复习文档
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def extract_html_from_markdown(md_path):
    """从 markdown 文件中提取 HTML 模板"""
    content = Path(md_path).read_text(encoding='utf-8')

    # 提取 ```html ... ``` 代码块
    match = re.search(r'```html\n(.*?)\n```', content, re.DOTALL)
    if match:
        return match.group(1)

    raise ValueError(f"未找到 HTML 模板在 {md_path}")


def generate_html(knowledge_path, output_path=None, book_title=None):
    """生成交互式 HTML 文件

    Args:
        knowledge_path: 知识点 JSON 文件路径
        output_path: 输出 HTML 文件路径（可选，默认同目录）
        book_title: 教材名称（可选，从JSON推断）
    """
    knowledge_path = Path(knowledge_path)

    # 读取知识点数据
    with open(knowledge_path, 'r', encoding='utf-8') as f:
        knowledge_data = json.load(f)

    # 推断输出路径
    if output_path is None:
        output_dir = knowledge_path.parent
        pdf_name = knowledge_path.stem.replace("_knowledge", "")

        # 使用规范命名
        if output_dir.name.startswith("Review - "):
            output_path = output_dir / f"Review - {pdf_name}.html"
        else:
            output_path = output_dir / f"{pdf_name}_review.html"

    # 推断教材名称
    if book_title is None:
        book_title = knowledge_data.get("source", "教材")

    # 读取 HTML 模板
    template_path = Path(__file__).parent.parent / "references" / "html-template.md"
    template = extract_html_from_markdown(template_path)

    # 替换占位符（防 </script> 注入：把 </ 转 <\/，浏览器 JSON.parse 自动还原）
    json_str = json.dumps(knowledge_data, ensure_ascii=False, indent=2)
    json_str = json_str.replace("</", "<\\/")
    html_content = template.replace("__DATA_PLACEHOLDER__", json_str)
    html_content = html_content.replace("[教材名称]", book_title)
    html_content = html_content.replace(
        "[时间戳]",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    )

    # 写入文件
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding='utf-8')

    print(f"HTML 文件已生成: {output_path}")
    return str(output_path)


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("用法: python generate_html.py <knowledge_json> [output_html] [book_title]")
        print("\n示例:")
        print("  python generate_html.py knowledge.json")
        print("  python generate_html.py knowledge.json review.html")
        print("  python generate_html.py knowledge.json review.html '高等数学'")
        sys.exit(1)

    knowledge_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    book_title = sys.argv[3] if len(sys.argv) > 3 else None

    result = generate_html(knowledge_path, output_path, book_title)
    print(f"\n[OK] 成功生成: {result}")


if __name__ == "__main__":
    main()
