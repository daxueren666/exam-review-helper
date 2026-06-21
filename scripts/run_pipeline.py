"""5-pass 流水线自动化编排脚本。

本脚本不是真正的"自动化"（5-pass 的 LLM 推理仍由宿主执行），
而是提供一个**结构化编排层**：
1. Phase 0: 自动提取文档（调 controller.extract）
2. 自动检测模式（理工科 vs 文科）
3. 输出详细的 Pass 1-5 执行指引（哪个 prompt、什么输入输出、检查什么）
4. 断点续传：检查 .checkpoint/ 下已完成的 segment notes，跳过已完成段
5. Phase 6: 检测到 knowledge.json 后自动生成 HTML

用法:
    python scripts/run_pipeline.py <source> [--mode auto|stem|liberal] [--strip-images]

典型流程:
    # 1. 启动流水线（自动提取 + 打印 5-pass 指引）
    python scripts/run_pipeline.py textbook.pdf

    # 2. 宿主按指引执行 5-pass，生成 knowledge.json

    # 3. 重新运行（检测到 knowledge.json，自动生成 HTML）
    python scripts/run_pipeline.py textbook.pdf
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional


def detect_mode(markdown_path: Path) -> str:
    """自动检测教材模式：理工科 vs 文科。

    判断依据：
    - 有 <!-- formula-not-decoded --> 占位符 → 理工科
    - 有大量数学符号（∑ ∫ √ ≤ ≥ 等） → 理工科
    - 否则 → 文科
    """
    content = markdown_path.read_text(encoding="utf-8")

    # 公式占位符 = docling PDF 提取的理工科教材
    if "<!-- formula-not-decoded -->" in content:
        return "stem"

    # 数学符号密集 = 理工科
    math_symbols = "∑∫√≤≥∈⊂∪∩∀∃→⇒⇔∞∂∇×÷±⋅∘αβγδεθλμπσφω"
    math_count = sum(1 for ch in content if ch in math_symbols)
    if math_count > 20:
        return "stem"

    # 文科特征：大量中文 + 观点/理论/意义 等词
    liberal_keywords = ["观点", "理论", "意义", "思想", "历史地位", "基本经验", "本质"]
    liberal_count = sum(content.count(kw) for kw in liberal_keywords)
    if liberal_count >= 5:
        return "liberal"

    return "stem"  # 默认理工科


def get_pass_guidance(mode: str, markdown_path: Path, total_pages: int) -> str:
    """生成 Pass 1-5 的详细执行指引。"""
    reader_prompt = "system_reader.md" if mode == "stem" else "system_reader_liberal_arts.md"
    verifier_prompt = "system_verifier.md" if mode == "stem" else "system_verifier_liberal_arts.md"
    concept_threshold = "10（章级）/ 5（段级）" if mode == "stem" else "8（章级）/ 5（段级）"
    formula_note = "**公式必须提取**，转 LaTeX" if mode == "stem" else "公式可选（多数章节为空）"

    return f"""
=== 5-Pass 执行指引（{mode} 模式）===

教材：{markdown_path.name}
总页数：{total_pages}
模式：{mode}（概念阈值 {concept_threshold}；{formula_note}）

【Pass 1: 分段 Segmentation Map】
  输入：读 {markdown_path}
  任务：通读全文，按章节/主题分段，每段 5-80 页
  约束：所有 segment 的 [page_start, page_end] 并集 = [1, {total_pages}]，无 gap
  输出：SegmentationMap JSON（含 segments 数组）
  检查点：存到 .checkpoint/segmentation_map.json

【Pass 2: Segment Reader × N】
  输入：各段 markdown（聚焦本段，但可引用全文）
  系统提示词：读 prompts/{reader_prompt}
  任务：每段提取 concepts/formulas/examples/pitfalls/connections
  约束：段级 concepts ≥ 5；每条有 page 字段
  输出：每段一个 notes_seg-XXX.json
  检查点：存到 .checkpoint/notes_seg-XXX.json（断点续传用）
  ⚠️ 已完成的 segment 会跳过（见 .checkpoint/ 目录）

【Pass 3: Merger】
  输入：N 份 segment notes
  系统提示词：读 prompts/system_merger.md
  任务：合并为 chapters JSON，消除冗余，补全跨段关联
  约束：章级 concepts ≥ {concept_threshold.split('（')[0]}；跨章 connections ≥ 3
  输出：<stem>_knowledge.json

【Pass 4: Fresh Verifier】
  ⚠️ 必须派 fresh 子代理（Agent 工具），不复用 Pass 2 上下文
  输入：extracted_content.md 原文 + draft knowledge.json
  系统提示词：读 prompts/{verifier_prompt}
  任务：独立核查 draft 是否忠实原文
  输出：verdict JSON（APPROVED / APPROVED_WITH_NOTES / REJECTED）

【Pass 5: Reviser（条件触发）】
  触发：Pass 4 返回 REJECTED
  系统提示词：读 prompts/system_reviser.md
  任务：针对每个 issue 修订，最多 3 轮

【Phase 6: 生成 HTML】
  完成 knowledge.json 后，重新运行本脚本自动生成 HTML：
    python scripts/run_pipeline.py {markdown_path.parent.parent.name}/...

  或手动执行：
    python scripts/controller.py generate <stem>_knowledge.json

=== 关键防偷懒原则 ===
1. Segmentation 必须覆盖全部 {total_pages} 页（无 gap）
2. Verifier 必须 fresh context（派子代理，不自检）
3. Pass 1 前必须读 references/common-failure-modes.md
4. 每条 concept/formula/pitfall 必须有 page 字段
"""


def check_checkpoint(output_dir: Path) -> dict:
    """检查断点续传状态：已完成的 segment notes。"""
    checkpoint_dir = output_dir / ".checkpoint"
    if not checkpoint_dir.exists():
        return {"checkpoint_exists": False, "completed_segments": [], "segmentation_map": None}

    seg_map_path = checkpoint_dir / "segmentation_map.json"
    segmentation_map = None
    if seg_map_path.exists():
        try:
            segmentation_map = json.loads(seg_map_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    # 只把可解析且非空的 notes 计入"已完成"——避免崩溃残留的半截文件被当成已完成
    completed = []
    for f in sorted(checkpoint_dir.glob("notes_seg-*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            # 至少要有 segment_id 字段，才算合法的 segment notes
            if isinstance(data, dict) and data.get("segment_id"):
                completed.append(f.stem)
            else:
                print(f"[Pipeline] 跳过无效 checkpoint（缺 segment_id）: {f.name}", file=sys.stderr)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[Pipeline] 跳过损坏 checkpoint: {f.name}（{e}）", file=sys.stderr)
    return {
        "checkpoint_exists": True,
        "completed_segments": completed,
        "segmentation_map": segmentation_map,
    }


def main():
    parser = argparse.ArgumentParser(
        description="5-pass 流水线编排：提取 → 指引 5-pass → 生成 HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source", help="源文件路径（PDF/DOCX/TXT/MD）")
    parser.add_argument(
        "--mode",
        choices=["auto", "stem", "liberal"],
        default="auto",
        help="教材模式：auto（自动检测）/ stem（理工科）/ liberal（文科）",
    )
    parser.add_argument("--strip-images", action="store_true", help="剥离 DOCX base64 图片")
    parser.add_argument("--output-dir", default=None, help="输出目录（默认 Review - <stem>/）")
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="跳过提取，只检查 knowledge.json 并生成 HTML（5-pass 完成后用）",
    )

    args = parser.parse_args()

    # 延迟 import 避免未装依赖时报错
    sys.path.insert(0, str(Path(__file__).parent))
    from controller import extract, generate_html

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"错误：文件不存在 {source_path}", file=sys.stderr)
        sys.exit(1)

    # 确定输出目录
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = source_path.parent / f"Review - {source_path.stem}"

    # === Phase 6 检测：如果 knowledge.json 已存在，直接生成 HTML ===
    knowledge_candidates = list(output_dir.glob("*_knowledge.json"))
    if args.generate_only or knowledge_candidates:
        if knowledge_candidates:
            knowledge_path = knowledge_candidates[0]
            print(f"\n[Pipeline] 检测到 knowledge.json：{knowledge_path.name}")
            print("[Pipeline] 跳过提取和 5-pass，直接生成 HTML...")
            result = generate_html(str(knowledge_path))
            if result.get("status") == "success":
                print(f"\n[Pipeline] HTML 生成完成：{result['html_path']}")
                sys.exit(0)
            else:
                print(f"[Pipeline] HTML 生成失败：{result.get('message')}", file=sys.stderr)
                sys.exit(1)
        elif args.generate_only:
            print(f"错误：未找到 knowledge.json 在 {output_dir}", file=sys.stderr)
            sys.exit(1)

    # === Phase 0: 提取 ===
    print(f"\n[Pipeline] === Phase 0: 文档提取 ===")
    print(f"[Pipeline] 源文件：{source_path}")
    print(f"[Pipeline] 输出目录：{output_dir}")

    extract_result = extract(
        str(source_path),
        str(output_dir) if args.output_dir else None,
        strip_images=args.strip_images,
    )

    if extract_result.get("status") not in ("success", "partial"):
        print(f"[Pipeline] 提取失败：{extract_result.get('message')}", file=sys.stderr)
        sys.exit(1)

    markdown_path = Path(extract_result["markdown_path"])
    total_pages = extract_result.get("pages", 0)
    print(f"[Pipeline] 提取完成：{total_pages} 页 → {markdown_path.name}")

    # === 模式检测 ===
    mode = args.mode
    if mode == "auto":
        mode = detect_mode(markdown_path)
        print(f"[Pipeline] 自动检测模式：{mode}")
    else:
        print(f"[Pipeline] 指定模式：{mode}")

    # === 断点续传检查 ===
    checkpoint = check_checkpoint(output_dir)
    if checkpoint["checkpoint_exists"]:
        completed = checkpoint["completed_segments"]
        if completed:
            print(f"[Pipeline] 发现断点续传：已完成 {len(completed)} 段 ({', '.join(completed)})")
            print("[Pipeline] Pass 2 将跳过以上已完成段，继续未完成段")
        if checkpoint["segmentation_map"]:
            seg_count = len(checkpoint["segmentation_map"].get("segments", []))
            print(f"[Pipeline] 发现已存 SegmentationMap：{seg_count} 段")

    # === 输出 5-pass 指引 ===
    print(get_pass_guidance(mode, markdown_path, total_pages))

    # === 提示下一步 ===
    print("=== 下一步 ===")
    print("1. 按 Pass 1-5 指引执行（读相应 prompts/，把 notes 存到 .checkpoint/）")
    print("2. 生成 <stem>_knowledge.json 后，重新运行本脚本自动生成 HTML：")
    print(f"   python scripts/run_pipeline.py {source_path} --generate-only")
    print()


if __name__ == "__main__":
    main()
