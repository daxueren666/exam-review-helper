#!/usr/bin/env python3
"""可执行的 eval runner。

读取 evals/evals.json，对每个 eval 的 assertions 做可执行检查，
输出 pass/fail 报告。

用法：
    python scripts/run_evals.py                    # 列出所有 eval
    python scripts/run_evals.py --eval-id 4        # 跑指定 eval
    python scripts/run_evals.py --all              # 跑所有 eval
    python scripts/run_evals.py --eval-id 4 --eval-dir /path/to/output

assertion 类型（用 type 字段区分）：
    dir_exists          目录是否存在（path 字段指定相对路径）
    file_exists         文件是否存在
    file_contains       文件是否包含某字符串
    file_not_contains   文件不含某字符串
    json_field_equals   JSON 文件某字段等于某值
    no_dir_matching     不存在匹配某 pattern 的目录
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
EVALS_JSON = SKILL_ROOT / "evals" / "evals.json"


# ---------------------------------------------------------------------------
# 单个 assertion 的执行逻辑
# ---------------------------------------------------------------------------

def _resolve(path_str: str, eval_dir: Path) -> Path:
    """把相对路径解析到 eval_dir 下；绝对路径保持不变。"""
    p = Path(path_str)
    if p.is_absolute():
        return p
    return (eval_dir / path_str).resolve()


def run_assertion(assertion: dict, eval_dir: Path) -> tuple[bool, str]:
    """执行单个 assertion，返回 (passed, message)。

    支持的 type：
        dir_exists / file_exists / file_contains / file_not_contains
        json_field_equals / no_dir_matching
    """
    a_type = assertion.get("type")
    name = assertion.get("name", "<unnamed>")

    if a_type == "dir_exists":
        path = _resolve(assertion["path"], eval_dir)
        if path.is_dir():
            return True, f"目录存在: {path}"
        return False, f"目录不存在: {path}"

    if a_type == "file_exists":
        path = _resolve(assertion["path"], eval_dir)
        # 非空检查（可选）
        require_nonempty = assertion.get("nonempty", False)
        if not path.is_file():
            return False, f"文件不存在: {path}"
        if require_nonempty and path.stat().st_size == 0:
            return False, f"文件为空: {path}"
        return True, f"文件存在: {path}"

    if a_type == "file_contains":
        path = _resolve(assertion["path"], eval_dir)
        if not path.is_file():
            return False, f"文件不存在: {path}"
        text = path.read_text(encoding="utf-8", errors="replace")
        needle = assertion["contains"]
        # min_count 可选：要求至少出现 N 次
        min_count = assertion.get("min_count", 1)
        actual_count = text.count(needle)
        if actual_count >= min_count:
            return True, f"找到 '{needle}' {actual_count} 次 (>= {min_count})"
        return False, f"仅找到 '{needle}' {actual_count} 次 (< {min_count})"

    if a_type == "file_not_contains":
        path = _resolve(assertion["path"], eval_dir)
        if not path.is_file():
            # 文件不存在视为"不包含"——通过
            return True, f"文件不存在，视为不含: {path}"
        text = path.read_text(encoding="utf-8", errors="replace")
        needle = assertion["not_contains"]
        if needle in text:
            return False, f"不应包含 '{needle}'，但找到了"
        return True, f"未包含 '{needle}'"

    if a_type == "json_field_equals":
        path = _resolve(assertion["path"], eval_dir)
        if not path.is_file():
            return False, f"JSON 文件不存在: {path}"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return False, f"JSON 解析失败: {e}"
        field_path = assertion["field"]  # 如 "extractor" 或 "metadata.format"
        expected = assertion["equals"]
        actual = _get_nested(data, field_path)
        if actual == expected:
            return True, f"{field_path} == {expected!r}"
        return False, f"{field_path} 期望 {expected!r}，实际 {actual!r}"

    if a_type == "no_dir_matching":
        pattern = assertion["pattern"]
        # 在 eval_dir 下扫描一级目录
        matched = []
        if eval_dir.is_dir():
            for entry in eval_dir.iterdir():
                if entry.is_dir() and fnmatch.fnmatch(entry.name, pattern):
                    matched.append(entry.name)
        if matched:
            return False, f"不应存在匹配 '{pattern}' 的目录，但找到: {matched}"
        return True, f"无匹配 '{pattern}' 的目录"

    return False, f"未知 assertion type: {a_type!r}"


def _get_nested(data: Any, field_path: str) -> Any:
    """从嵌套 dict 取字段，支持点号路径如 'metadata.format'。"""
    cur = data
    for part in field_path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


# ---------------------------------------------------------------------------
# eval 执行流程
# ---------------------------------------------------------------------------

def load_evals(path: Path = EVALS_JSON) -> dict:
    """加载 evals.json。"""
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def run_eval(eval_obj: dict, eval_dir: Path) -> dict:
    """跑单个 eval，返回结果字典。"""
    results = []
    passed_count = 0
    for assertion in eval_obj.get("assertions", []):
        passed, msg = run_assertion(assertion, eval_dir)
        results.append({
            "name": assertion.get("name", "<unnamed>"),
            "type": assertion.get("type"),
            "passed": passed,
            "message": msg,
        })
        if passed:
            passed_count += 1
    total = len(results)
    return {
        "id": eval_obj.get("id"),
        "name": eval_obj.get("name"),
        "passed": passed_count,
        "total": total,
        "all_passed": passed_count == total and total > 0,
        "results": results,
    }


def print_report(eval_result: dict) -> None:
    """打印单个 eval 的结果。"""
    status = "PASS" if eval_result["all_passed"] else "FAIL"
    print(f"\n[Eval {eval_result['id']}] {eval_result['name']}  ->  {status}")
    print(f"  通过 {eval_result['passed']}/{eval_result['total']}")
    for r in eval_result["results"]:
        mark = "OK " if r["passed"] else "XX "
        print(f"  {mark}{r['name']}: {r['message']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="exam-review-helper eval runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--eval-id", type=int, help="只跑指定 id 的 eval")
    parser.add_argument("--all", action="store_true", help="跑所有 eval")
    parser.add_argument(
        "--eval-dir",
        default=".",
        help="eval 输出目录（skill 产出文件的根目录），默认当前目录",
    )
    parser.add_argument(
        "--evals-file",
        default=str(EVALS_JSON),
        help=f"evals.json 路径，默认 {EVALS_JSON}",
    )
    args = parser.parse_args(argv)

    evals_file = Path(args.evals_file)
    if not evals_file.is_file():
        print(f"错误：evals 文件不存在: {evals_file}", file=sys.stderr)
        return 2

    data = load_evals(evals_file)
    evals = data.get("evals", [])
    eval_dir = Path(args.eval_dir).resolve()

    # 不带参数：列出不跑
    if not args.all and args.eval_id is None:
        print(f"Skill: {data.get('skill_name', '?')}")
        print(f"共 {len(evals)} 个 eval（位于 {evals_file}）")
        print(f"eval-dir: {eval_dir}")
        print("\n可用 eval:")
        for e in evals:
            n_assert = len(e.get("assertions", []))
            env = " (env_specific)" if any(
                a.get("env_specific") for a in e.get("assertions", [])
            ) else ""
            print(f"  [{e['id']}] {e['name']}{env}  ({n_assert} assertions)")
        print("\n用法：")
        print("  python scripts/run_evals.py --eval-id 4 --eval-dir <output-dir>")
        print("  python scripts/run_evals.py --all --eval-dir <output-dir>")
        return 0

    # 选 eval
    if args.eval_id is not None:
        selected = [e for e in evals if e.get("id") == args.eval_id]
        if not selected:
            print(f"错误：找不到 id={args.eval_id} 的 eval", file=sys.stderr)
            return 2
    else:
        selected = evals

    print(f"eval-dir: {eval_dir}")
    all_pass = True
    summary = []
    for e in selected:
        result = run_eval(e, eval_dir)
        print_report(result)
        summary.append(result)
        if not result["all_passed"]:
            all_pass = False

    # 汇总
    print("\n" + "=" * 60)
    print("汇总:")
    for r in summary:
        status = "PASS" if r["all_passed"] else "FAIL"
        print(f"  [Eval {r['id']}] {r['name']}: {status}  ({r['passed']}/{r['total']})")
    total_pass = sum(1 for r in summary if r["all_passed"])
    print(f"\n{total_pass}/{len(summary)} eval 全部通过")

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
