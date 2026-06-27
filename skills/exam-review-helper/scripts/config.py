"""配置加载模块。

从 config.yaml 读取配置，提供 get_config() 全局访问。
未找到配置文件时用内置默认值。

用法：
    from config import get_config
    cfg = get_config()
    min_chars = cfg.extraction_min_page_chars()
"""
import os
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None  # PyYAML 未装时用默认值


# === 内置默认值（与 config.yaml 一致，作为 fallback）===
_DEFAULTS = {
    "extraction": {
        "min_page_chars": 1500,
        "max_page_chars_multiplier": 4,
        "chunk_size": 50,
        "auto_chunk_size_mb": 50,
        "auto_chunk_pages": 100,
        "cache_enabled": True,
        "cache_dir_name": ".cache",
        "max_retries": 3,
        "retry_chunk_shrink": 2,
        "pdf_backend": "auto",
        "fallback_dpi": 150,
        "ocr_scale": 2,
        "max_pdf_size_mb": 2048,
        "max_docx_size_mb": 100,
        "max_txt_size_mb": 50,
        "max_md_size_mb": 50,
        "max_base64_image_mb": 50,
    },
    "html": {
        "template_path": "templates/default.html",
        "default_format": "html",
    },
    "thresholds": {
        "stem_concept_min": 10,
        "liberal_concept_min": 8,
        "segment_concept_min": 5,
        "pitfall_min": 3,
        "liberal_connection_min": 2,
        "related_to_max_isolated_pct": 30,
    },
    "output": {
        "verbose": False,
        "quiet": False,
    },
}


class Config:
    """配置访问器。支持点号链式访问，如 cfg.get('extraction.min_page_chars')。"""

    def __init__(self, data: dict):
        self._data = data

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """点号链式取值。如 get('extraction.min_page_chars')。"""
        keys = dotted_key.split(".")
        val = self._data
        for k in keys:
            if not isinstance(val, dict) or k not in val:
                return default
            val = val[k]
        return val

    # 常用配置的快捷方法
    def extraction_min_page_chars(self) -> int:
        return self.get("extraction.min_page_chars", 1500)

    def extraction_max_page_chars(self) -> int:
        return self.extraction_min_page_chars() * self.get("extraction.max_page_chars_multiplier", 4)

    def chunk_size(self) -> int:
        return self.get("extraction.chunk_size", 50)

    def auto_chunk_size_mb(self) -> float:
        return self.get("extraction.auto_chunk_size_mb", 50)

    def auto_chunk_pages(self) -> int:
        return self.get("extraction.auto_chunk_pages", 100)

    def cache_enabled(self) -> bool:
        return self.get("extraction.cache_enabled", True)

    def cache_dir_name(self) -> str:
        return self.get("extraction.cache_dir_name", ".cache")

    def max_retries(self) -> int:
        return self.get("extraction.max_retries", 3)

    def retry_chunk_shrink(self) -> int:
        return self.get("extraction.retry_chunk_shrink", 2)

    def pdf_backend(self) -> str:
        return self.get("extraction.pdf_backend", "auto")

    def use_pdfium(self) -> bool:
        return self.get("extraction.use_pdfium", True)

    def fallback_dpi(self) -> int:
        return self.get("extraction.fallback_dpi", 150)

    def ocr_scale(self) -> int:
        return self.get("extraction.ocr_scale", 2)

    def max_file_size_mb(self, ext: str) -> float:
        """按扩展名返回最大文件大小（MB）"""
        mapping = {
            ".pdf": self.get("extraction.max_pdf_size_mb", 2048),
            ".docx": self.get("extraction.max_docx_size_mb", 100),
            ".doc": self.get("extraction.max_docx_size_mb", 100),
            ".txt": self.get("extraction.max_txt_size_mb", 50),
            ".md": self.get("extraction.max_md_size_mb", 50),
            ".markdown": self.get("extraction.max_md_size_mb", 50),
        }
        return mapping.get(ext.lower(), 100)

    def max_base64_image_mb(self) -> float:
        return self.get("extraction.max_base64_image_mb", 50)

    def html_template_path(self) -> str:
        return self.get("html.template_path", "templates/default.html")

    def html_default_format(self) -> str:
        return self.get("html.default_format", "html")

    def verbose(self) -> bool:
        return self.get("output.verbose", False)

    def quiet(self) -> bool:
        return self.get("output.quiet", False)

    def stem_concept_min(self) -> int:
        return self.get("thresholds.stem_concept_min", 10)

    def liberal_concept_min(self) -> int:
        return self.get("thresholds.liberal_concept_min", 8)

    def segment_concept_min(self) -> int:
        return self.get("thresholds.segment_concept_min", 5)


# 全局单例
_config: Optional[Config] = None


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并：override 覆盖 base。"""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(config_path: Optional[str] = None) -> Config:
    """加载配置。优先级：--config 参数 > skill 目录的 config.yaml > 内置默认值。"""
    global _config

    data = {}
    # 确定配置文件路径
    candidates = []
    if config_path:
        candidates.append(Path(config_path))
    # skill 根目录的 config.yaml
    skill_root = Path(__file__).parent.parent
    candidates.append(skill_root / "config.yaml")
    # 当前工作目录的 config.yaml
    candidates.append(Path.cwd() / "config.yaml")

    for path in candidates:
        if path.exists() and yaml is not None:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    file_data = yaml.safe_load(f) or {}
                data = _deep_merge(data, file_data)
                if _config is None or config_path:  # 只在首次或显式指定时打印
                    pass  # 静默加载
                break
            except Exception:
                continue

    # 合并默认值（保证缺失字段有默认）
    merged = _deep_merge(_DEFAULTS, data)
    _config = Config(merged)
    return _config


def get_config() -> Config:
    """获取全局配置单例。首次调用时自动加载。"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """重置全局配置（测试用）。"""
    global _config
    _config = None
