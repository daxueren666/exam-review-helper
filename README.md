# Exam Review Helper

![version](https://img.shields.io/github/v/release/daxueren666/exam-review-helper) ![license](https://img.shields.io/github/license/daxueren666/exam-review-helper) ![stars](https://img.shields.io/github/stars/daxueren666/exam-review-helper)

> 把 PDF / Word / TXT / Markdown 教材浓缩成交互式 HTML 复习文档的 Claude Code / Codex CLI Skill。
> 自动识别文科/理工科，5-pass 深度提取，原生支持扫描版 PDF OCR。

![screenshot](skills/exam-review-helper/docs/screenshot.png)

## 这是什么

一个在 Claude Code 或 Codex CLI 里调用的 skill。你上传教材说"帮我复习这个"，它会：

1. **提取**：PDF（含扫描版 OCR）/ Word / TXT / MD，自动识别格式
2. **5-pass 深度提取**：概念 / 公式 / 易错点 / 典型例题，自动识别文科/理工科
3. **生成交互式 HTML**：MathJax 公式 + 暗黑模式 + 搜索 + 笔记 + 进度追踪

不需要额外配 API key——5-pass 由宿主调用的 LLM 执行，用你登录宿主时的认证。

## v1.2 稳定性更新

**修复扫描版大 PDF 的 docling `std::bad_alloc` 崩溃**（[docling issue #3671](https://github.com/docling-project/docling/issues/3671)）：

- **默认用 pdfium 后端**：绕开 docling-parse C++ 解析层（崩溃根源），保留版面分析+公式占位符+表格能力
- **ocr_scale=2**：降低 RapidOCR 渲染分辨率（216→144 DPI），减少 numpy 内存 56%，不降 OCR 质量
- **三层 fallback**：pdfium → per-chunk PyMuPDF+RapidOCR → 整体 PyMuPDF+RapidOCR
- **partial 接受**：部分页成功时保留 docling 公式占位符，不盲目 fallback 降质量

详见 [release v1.2.1](https://github.com/daxueren666/exam-review-helper/releases/tag/v1.2.1)。

## v1.3 深度 bug 修复

v1.2 解决了 docling 崩溃的表面问题，但 `controller.py` 的状态机、重试逻辑、fallback 触发条件、多文件模式等路径上仍藏着多个边界情况 bug。v1.3 经过 **5 轮 fresh agent 独立审查 + 实测验证**，累计修复 15 个 bug，高严重性全部清零。

### 修复趋势（5 轮收敛）

| 轮次 | 高 | 中 | 低 | 总计 |
|---|---|---|---|---|
| 第一轮 | 2 | 3 | 0 | 5 |
| 第二轮 | 1 | 2 | 0 | 3 |
| 第三轮 | 0 | 2 | 2 | 4 |
| 第四轮 | 0 | 0 | 0 | 0 |
| 第五轮 | 0 | 1 | 3 | 4 |
| **最终** | **0** | **0** | **0** | **0** |

### 关键修复

**状态机与 fallback**：
- partial + 高失败率（>50%）现在正确触发整体 fallback 到 PyMuPDF+RapidOCR（之前只 error 才触发，partial 静默返回残缺产物）
- 第一次 partial 失败率 <10% 直接接受，避免不必要的完整重跑（之前 98/100 页会触发 4 块重试，耗时从 16 分钟爆炸到 35+ 分钟）
- 子进程 `sys.exit` 与父进程 `returncode` 检查对齐：partial 也 exit 0，避免 partial 块的 docling 结果被误判为 error 丢弃

**返回字段一致性**：
- `extract_pdf` success 路径 `pages` 字段统一用 `actual_pages`（之前用 `len(result.document.pages)` 含空页，与 partial 路径语义不一致）
- `extract_pdf_pymupdf_rapidocr` 返回 dict 补全 `pages_processed`/`expected_pages` 字段
- `extract_multiple` 返回 dict 补全 `pages_failed`/`failed_ranges`/`pages_processed` 字段
- `page_range` 越界时按实际可处理页数判定 status（之前 `page_range=(50,100)` 对 80 页 PDF 会误报 success，丢失 21 页无报错）

**多文件模式**：
- `extract_multiple` 透传 `backend` 和 `use_cache` 参数（之前 `--no-cache` 和 `--backend` 在多文件模式下被静默丢弃）
- `extract_multiple` 状态判定区分 success/partial/error（之前永远返回 success，即使 N-1 个文件失败）

**子进程与防御**：
- 子进程 fallback 推断路径用 `[PAGE N]` 计数验证实际页数（之前仅检查 md 文件存在就报 success，可能掩盖残缺内容）
- `_extract_chunk_in_subprocess` 加 page_range 越界防御
- `chunked_extract_pdf` 全 fallback 时 `all_doc_dicts[0]` 加空列表守卫，避免 IndexError
- `chunk_result["markdown_path"]` 改用 `.get()`，避免极端情况 KeyError
- fallback 块的 doc_dict 现在加入 `all_doc_dicts`，避免合并 JSON 时 pages 元数据不全

**可配置性**：
- `use_pdfium` 现在可在 `config.yaml` 配置（之前硬编码 True，docling-parse 后端不可选，与文档矛盾）
- `--backend pymupdf` 直接路径现在透传 `dpi=cfg.fallback_dpi()`

**其他**：
- `validate` 目录扫描 glob 从 `notes_*.json` 改为 `*_notes.json`，匹配 `seg-XXX_notes.json` 命名约定
- 删除死代码 `pages = len(result.document.pages)`
- `file_hash` 预声明 `None`，提升可维护性

### 验证

每轮修复后派 fresh agent（无上下文）独立审查 + 实测：静态代码审查 + pymupdf 返回字段测试 + page_range 越界测试 + 子进程无效参数测试 + 多文件 no-cache 测试 + generate 烟雾测试 + validate 目录模式测试。第五轮所有实测 PASS，静态审查零新高危 bug。

## 安装

**前置要求**：
- **GitHub CLI 2.90+**（`gh --version` 检查，用于 `gh skill install`）
- **Python 3.10+**（`python --version` 检查，docling/transformers 需要）
- **联网**（pip 安装 + 首次提取 PDF 时下载 docling 模型）
- **约 1GB 磁盘空间**（Python 依赖 ~800MB + docling 模型 ~200MB）

**1. 用 `gh skill install` 安装**（推荐，自动更新）：

```bash
# Claude Code 用户（user scope 全局可用）
gh skill install daxueren666/exam-review-helper --agent claude-code --scope user

# Codex CLI 用户
gh skill install daxueren666/exam-review-helper --agent codex --scope user

# 锁定到特定版本（生产环境推荐）
gh skill install daxueren666/exam-review-helper --agent claude-code --pin v1.2.1
```

**更新到最新版本**：

```bash
gh skill update exam-review-helper     # 更新单个
gh skill update --all                  # 更新全部已装 skill
```

**2. 装 Python 依赖 + 检查环境**：

`gh skill install` 装到 `~/.claude/skills/exam-review-helper/`（user scope）。进入该目录装依赖：

```bash
cd ~/.claude/skills/exam-review-helper
pip install -r requirements.txt
python scripts/controller.py init
```

`pip install` 会下载 docling、transformers、markitdown、rapidocr 等包（约 800MB，需要联网）。

**3. 首次提取 PDF 时**：docling 会自动下载约 200MB 模型文件（一次性，后续提取不再下载）。

<details>
<summary><b>开发用：git clone 方式</b></summary>

```bash
git clone https://github.com/daxueren666/exam-review-helper.git
cd exam-review-helper/skills/exam-review-helper
pip install -r requirements.txt
python scripts/controller.py init
```

注意：仓库结构是 `skills/exam-review-helper/`（符合 [Agent Skills spec](https://agentskills.io/specification)），所以 clone 后要进入子目录。

</details>

## 使用

在 Claude Code 或 Codex CLI 里直接对话：

```
帮我复习这个（上传 textbook.pdf）
整理这个 Word 讲义（上传 notes.docx）
把 this.md 做成复习网页
只复习第3章 + 第5章的 15-30 页
```

skill 会自动触发，产出在教材同目录下：

```
Review - textbook/
├── extracted_content.md       提取的 markdown
├── textbook_knowledge.json    5-pass 知识点
└── Review - textbook.html     最终交互式 HTML
```

双击 HTML 打开即可复习。

## 支持格式

| 格式 | 扩展名 | 提取方式 |
|---|---|---|
| PDF | `.pdf` | docling（含扫描版 OCR） |
| Word | `.docx` / `.doc` | MarkItDown（mammoth 内核） |
| 纯文本 | `.txt` | charset-normalizer（自动检测 GBK/UTF-8） |
| Markdown | `.md` | charset-normalizer |

支持混合批量处理：`python scripts/controller.py extract a.pdf b.docx c.md`

## 核心特性

- **多格式输入**：PDF / Word / TXT / MD，中文编码自动检测
- **文科/理工科自动识别**：不同模式用不同概念阈值和验证规则，用户无需选择
- **大 PDF 分块提取**：自动分块在独立子进程跑，绕开 docling 内存泄漏
- **防偷懒机制**：Fresh verifier + 失败模式清单 + Rationalization Table
- **缓存加速**：相同文件二次提取秒级返回
- **断点续传**：5-pass 中断后重跑跳过已完成段
- **OCR 纠错**：扫描版 PDF 提取后自动修正常见汉字误判（上下文感知）
- **安全加固**：文件大小限制 + HTML XSS 转义 + base64 图片限制
- **配置文件**：所有阈值在 `config.yaml`，不用改源码

## CLI 命令速查

```bash
# 提取（自动识别格式）
python scripts/controller.py extract textbook.pdf
python scripts/controller.py extract big.pdf --chunk-size 25       # 大 PDF 手动分块
python scripts/controller.py extract scanned.pdf --ocr-correct      # 扫描版纠错
python scripts/controller.py extract notes.docx --strip-images      # DOCX 剥离图片

# 生成 HTML / Markdown / JSON
python scripts/controller.py generate knowledge.json
python scripts/controller.py generate knowledge.json --format md

# 校验 / 检查依赖 / 版本
python scripts/controller.py validate notes.json
python scripts/controller.py init
python scripts/controller.py --version
```

## 文档

- [SKILL.md](skills/exam-review-helper/SKILL.md) — skill 主指令（Claude Code / Codex 自动加载）
- [references/multi-pass-workflow.md](skills/exam-review-helper/references/multi-pass-workflow.md) — 5-pass 详细流程
- [references/multi-format-input.md](skills/exam-review-helper/references/multi-format-input.md) — 多格式输入说明
- [references/advanced-features.md](skills/exam-review-helper/references/advanced-features.md) — 高级功能（图片剥离/OCR/流水线/断点续传/公式增强）
- [references/common-failure-modes.md](skills/exam-review-helper/references/common-failure-modes.md) — 防偷懒清单
- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构说明
- [CONTRIBUTING.md](CONTRIBUTING.md) — 贡献指南

## 开发

```bash
cd skills/exam-review-helper
pytest tests/ -v                   # 120 个单元测试
python scripts/run_evals.py --all  # 跑 eval 套件
```

## 许可证

[MIT](LICENSE)
