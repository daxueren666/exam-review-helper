"""提取缓存模块。

按源文件内容 hash 缓存提取结果，重跑相同文件秒级返回。
缓存存在 Review - <stem>/.cache/<hash>.json，包含提取的 markdown 路径和元数据。

用法：
    from cache import check_cache, save_cache, compute_file_hash

    file_hash = compute_file_hash(source_path)
    cached = check_cache(output_dir, file_hash)
    if cached:
        return cached  # 秒级返回
    # ... 正常提取 ...
    save_cache(output_dir, file_hash, result)
"""
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def compute_file_hash(file_path: Path, chunk_size: int = 8192) -> str:
    """计算文件内容的 SHA256 hash。

    对大文件分块读取避免内存爆炸。
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()[:16]  # 取前 16 位足够（碰撞概率极低）


def get_cache_dir(output_dir: Path, cache_dir_name: str = ".cache") -> Path:
    """获取缓存目录路径。"""
    return output_dir / cache_dir_name


def get_cache_path(output_dir: Path, file_hash: str, cache_dir_name: str = ".cache") -> Path:
    """获取缓存文件路径。"""
    return get_cache_dir(output_dir, cache_dir_name) / f"{file_hash}.json"


def check_cache(
    output_dir: Path,
    file_hash: str,
    cache_dir_name: str = ".cache",
) -> Optional[Dict[str, Any]]:
    """检查缓存是否存在且有效。

    Returns:
        缓存的 result dict（含 markdown_path 等），或 None（未命中）
    """
    cache_path = get_cache_path(output_dir, file_hash, cache_dir_name)
    if not cache_path.exists():
        return None

    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    # 验证缓存指向的 markdown 文件仍存在
    markdown_path = Path(cached.get("markdown_path", ""))
    if not markdown_path.exists():
        return None  # 缓存失效（输出文件被删）

    print(f"[Cache] 命中缓存（hash={file_hash}），跳过提取", file=sys.stderr)
    return cached


def save_cache(
    output_dir: Path,
    file_hash: str,
    result: Dict[str, Any],
    cache_dir_name: str = ".cache",
) -> None:
    """保存提取结果到缓存。"""
    cache_dir = get_cache_dir(output_dir, cache_dir_name)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = get_cache_path(output_dir, file_hash, cache_dir_name)

    # 只缓存成功结果
    if result.get("status") not in ("success", "partial"):
        return

    try:
        cache_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass  # 缓存写入失败不影响主流程


def clear_cache(output_dir: Path, cache_dir_name: str = ".cache") -> int:
    """清空指定输出目录的缓存。返回删除的文件数。"""
    cache_dir = get_cache_dir(output_dir, cache_dir_name)
    if not cache_dir.exists():
        return 0
    count = 0
    for f in cache_dir.glob("*.json"):
        f.unlink()
        count += 1
    return count
