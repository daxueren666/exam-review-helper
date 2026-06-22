# Exam Review Helper

> 把 PDF / Word / TXT / Markdown 教材浓缩成交互式 HTML 复习文档的 [Claude Code Skill](https://docs.claude.com/en/docs/claude-code/skills)。
> 原生支持扫描版 PDF、Word 讲义、纯文本笔记、Markdown 教材，**自动识别文科/理工科模式**，5-pass 深度提取，缓存加速，多格式输出。

![screenshot](docs/screenshot.png)

## 这是什么

一个在 Claude Code 里调用的 skill。学生上传 PDF / Word / TXT / MD 教材说"帮我复习这个"，它会：

1. **多格式提取**：PDF 用 docling（含 OCR）；DOCX 用 MarkItDown；TXT/MD 用 charset-normalizer 编码检测
2. **自动模式识别**：理工科（数学/物理/化学/计算机）vs 文科（政治/哲学/历史/法学/教育学）——概念阈值、公式要求、验证重点不同
3. **5-pass 工作流**深度提取概念 / 公式 / 易错点 / 典型例题
4. **生成单个交互式 HTML**（MathJax 公式渲染 + 暗黑模式 + 侧边导航 + 错题本 + 进度追踪）
5. **缓存加速**：相同文件二次提取秒级返回（按内容 hash 缓存）

整个流程**不需要额外配 API key**——5-pass 由宿主 agent（Claude Code / Codex CLI）调用的 LLM 执行，用你登录宿主时的认证。

## 快速开始

### 1. 安装 skill

本 skill 同时支持 **Claude Code** 和 **Codex CLI**——两者都遵循 open agent skills 标准（SKILL.md 格式相同），只是发现路径不同。按你用的平台选一个：

**Claude Code 用户：**

```bash
# macOS / Linux
git clone https://github.com/daxueren666/exam-review-helper.git \
  ~/.claude/skills/exam-review-helper

# Windows
git clone https://github.com/daxueren666/exam-review-helper.git \
  %USERPROFILE%\.claude\skills\exam-review-helper
```

**Codex CLI 用户：**

```bash
# macOS / Linux
git clone https://github.com/daxueren666/exam-review-helper.git \
  ~/.agents/skills/exam-review-helper

# Windows
git clone https://github.com/daxueren666/exam-review-helper.git \
  %USERPROFILE%\.agents\skills\exam-review-helper
```

两个平台都用同一个仓库，SKILL.md 不用改——`name` + `description` 字段两边都认，说"帮我复习"会自动触发。

### 2. 安装 Python 依赖

```bash
cd ~/.claude/skills/exam-review-helper   # 或 ~/.agents/skills/exam-review-helper
pip install -r requirements.txt
python scripts/controller.py init   # 检查依赖 + 配置文件 + 模板
```

首次运行会下载约 200MB 的 docling 模型文件（一次性）。

### 3. 在 Claude Code 里使用

打开 Claude Code，直接对话：

```
帮我复习这本教材（上传 textbook.pdf）
```

或指定其他格式：

```
帮我复习这个 Word 讲义（上传 notes.docx）
整理这个 TXT 笔记（上传 chapter.txt）
把这个 Markdown 做成复习网页（上传 module.md）
```

或指定范围：

```
只复习第3章 + 第5章的 15-30 页
```

Claude 会自动调用本 skill，输出：

```
<source-directory>/Review - textbook/
├── extracted_content.md       # 多格式提取的 markdown（统一带 [PAGE N] 标记）
├── extracted_content.json     # 结构化数据（schema 随格式不同）
├── textbook_knowledge.json    # 5-pass 知识点 JSON
└── Review - textbook.html     # 最终交互式 HTML
```

直接双击 HTML 打开即可复习。

## 支持的输入格式

| 格式 | 扩展名 | 提取库 | 页码策略 |
|---|---|---|---|
| PDF | `.pdf` | docling + PyMuPDF | 物理页码（含 OCR） |
| Word | `.docx` / `.doc` | MarkItDown（mammoth 内核） | 合成（H1/H2 + 最小 1500 字符） |
| 纯文本 | `.txt` | charset-normalizer（编码检测） | 合成（段落 + 最小 1500 字符） |
| Markdown | `.md` / `.markdown` | charset-normalizer（编码检测） | 合成（H1/H2 + 最小 1500 字符） |

**混合格式批量处理**：支持一次提取多个文件（可混合格式）：

```bash
python scripts/controller.py extract a.pdf b.docx c.md
```

详见 [`references/multi-format-input.md`](references/multi-format-input.md)。

## 输出格式

`generate` 子命令支持三种输出格式（`--format` 参数）：

| 格式 | 用途 | 文件 |
|---|---|---|
| `html`（默认） | 交互式复习网页（MathJax + 搜索 + 笔记 + 进度） | `Review - <stem>.html` |
| `md` | 纯 Markdown（便于版本控制 / 二次编辑） | `Review - <stem>.md` |
| `json` | 格式化 JSON（便于程序消费） | `Review - <stem>.json` |

```bash
python scripts/controller.py generate knowledge.json --format md
python scripts/controller.py generate knowledge.json --format json --template custom.html
```

## 5-Pass 工作流

| Pass | 角色 | 输入 | 输出 |
|---|---|---|---|
| 0 | Controller（Python 脚本） | PDF/DOCX/TXT/MD | markdown（docling 或 charset-normalizer 提取） |
| 1 | Planner（LLM） | markdown 全文 | SegmentationMap（覆盖全部页码） |
| 2 | Segment Reader × N（LLM 并行） | 各段独立上下文 | 各段结构化 notes |
| 3 | Merger（LLM） | N 份 notes | cheat-sheet draft JSON |
| 4 | Fresh Verifier（LLM，独立 context） | 原文 + draft | APPROVED / NOTES / REJECTED |
| 5 | Reviser（LLM，条件触发） | draft + verdict | 修订稿（最多 3 轮） |

详细执行指令见 [`references/multi-pass-workflow.md`](references/multi-pass-workflow.md)。

## 文科 / 理工科自动识别

skill 会根据提取后的 markdown 内容自动判断教材类型，**用户无需手动选择**：

| 模式 | 适用教材 | 概念阈值 | 公式要求 | 验证重点 |
|---|---|---|---|---|
| **理工科** | 数学/物理/化学/计算机/工程 | 章级 ≥ 10 | 必须提取，LaTeX 格式 | 计算错误、公式误用 |
| **文科** | 政治/哲学/历史/法学/教育学/文学 | 章级 ≥ 8 | 可选（多数章节无公式） | 观点辨析、史实错误 |

识别规则：统计 markdown 中"理论/观点/思想/主义/制度"等文科关键词 vs 数学符号密度，取较高的模式。

## 关键特性

- **多格式输入**：PDF（含扫描版 OCR）/ Word / TXT / Markdown，中文编码自动检测（GBK/GB2312/Big5）
- **大 PDF 支持**：自动分块提取，每块在独立 Python 子进程里跑（绕开 docling C++ 后端的内存泄漏），实测 270 页零失败
- **文科/理科自动识别**：不同模式用不同 prompts 和验证规则，无需用户手动选
- **章节范围选择**：自然语言解析 "第3章 + 第5章 15-30 页 + 第8章"，反向范围自动纠正
- **防偷懒机制**：Fresh verifier + common-failure-modes checklist + Rationalization Table，卡死 concepts/pitfalls 下限
- **HTML 交互**：MathJax 公式、暗黑模式、侧边导航、错题本、状态按钮（已掌握/待复习/不会）、搜索、笔记、进度追踪
- **提取缓存**：按源文件内容 SHA256 hash 缓存，重跑相同文件秒级返回
- **断点续传**：5-pass 中断后重跑自动跳过已完成段（`.checkpoint/` 目录）
- **OCR 纠错**：扫描版 PDF 提取后自动修正常见汉字误判（巳→已、末→未 等，上下文感知）
- **公式增强**：扫描公式占位符，可选集成 pix2tex 做 LaTeX OCR
- **多输出格式**：HTML / Markdown / JSON 三选一
- **安全加固**：文件大小限制、HTML XSS 转义、Markdown XSS 过滤、base64 图片大小限制
- **配置文件**：所有阈值集中在 `config.yaml`，不用改源码就能调
- **JSON 校验**：`validate` 命令精确报错（line:col + unicode 检查）

## 目录结构

```
exam-review-helper/
├── SKILL.md                       Skill 入口（Claude Code 自动加载）
├── config.yaml                    配置文件（所有阈值集中可调）
├── pyproject.toml                 pip 打包元数据
├── requirements.txt               Python 依赖
├── templates/
│   └── default.html               HTML 模板（外置，可自定义）
│
├── prompts/                       5-pass 系统提示词
│   ├── system_segment.md          Pass 1：分段
│   ├── system_reader.md           Pass 2：理工科每段深读
│   ├── system_reader_liberal_arts.md   Pass 2：文科每段深读
│   ├── system_merger.md           Pass 3：合并
│   ├── system_verifier.md         Pass 4：理工科核查
│   ├── system_verifier_liberal_arts.md Pass 4：文科核查
│   └── system_reviser.md          Pass 5：修订
│
├── references/                    参考文档
│   ├── multi-pass-workflow.md     工作流详细指令
│   ├── multi-format-input.md      多格式输入说明
│   ├── common-failure-modes.md    防偷懒清单 + Rationalization Table
│   └── advanced-features.md       高级功能（图片剥离/OCR 纠错/流水线/断点续传/公式增强）
│
├── scripts/                       确定性脚本
│   ├── controller.py              extract / generate / validate / init 命令
│   ├── extractors.py              多格式提取（DOCX/TXT/MD）
│   ├── generate_html.py           JSON → HTML/MD/JSON
│   ├── run_pipeline.py            5-pass 流水线编排
│   ├── run_evals.py               eval 自动化 runner
│   ├── cache.py                   提取缓存
│   ├── config.py                  配置加载
│   ├── chapter_selector.py        范围解析
│   ├── enhance_formulas.py        公式提取增强
│   └── ocr_corrector.py           OCR 纠错
│
├── evals/evals.json               9 个 eval（含负向触发，可执行 assertion）
├── test_data/                     eval 用的测试文件（sample.docx/md/txt）
└── tests/                         单元测试（99 个，全通过）
    ├── conftest.py
    ├── test_chapter_selector.py   范围解析测试
    ├── test_extractors.py         多格式提取测试
    ├── test_p0_p1_features.py     P0-P1 新功能测试
    ├── test_run_evals.py          eval runner 测试
    └── test_pdf_regression.py     PDF 回归测试
```

## 脚本命令

```bash
# 提取单文件（自动识别格式：PDF/DOCX/TXT/MD）
python scripts/controller.py extract input.pdf       # 或 input.docx / input.txt / input.md

# 提取多文件（可混合格式）
python scripts/controller.py extract a.pdf b.docx c.md

# 大 PDF 手动指定块大小（默认 50）
python scripts/controller.py extract big_textbook.pdf --chunk-size 25

# 强制不分块（小 PDF 用）
python scripts/controller.py extract small.pdf --no-chunk

# DOCX 剥离 base64 图片为独立文件（减小 markdown 体积）
python scripts/controller.py extract notes.docx --strip-images

# 扫描版 PDF 开启 OCR 纠错
python scripts/controller.py extract scanned.pdf --ocr-correct

# 禁用缓存（强制重新提取）
python scripts/controller.py extract book.pdf --no-cache

# 用自定义配置文件
python scripts/controller.py --config my.yaml extract book.pdf

# 从 JSON 生成 HTML（默认）/ Markdown / JSON
python scripts/controller.py generate knowledge.json
python scripts/controller.py generate knowledge.json --format md
python scripts/controller.py generate knowledge.json --format json --template custom.html

# 校验 notes JSON（精确报错 + unicode 检查）
python scripts/controller.py validate notes.json

# 检查依赖 + 配置 + 模板
python scripts/controller.py init

# 显示版本号
python scripts/controller.py --version

# 一键流水线（提取 + 指引 5-pass + 生成 HTML，带断点续传）
python scripts/run_pipeline.py textbook.pdf
```

## 运行测试

```bash
pytest tests/ -v                    # 99 个单元测试
python scripts/run_evals.py --all   # 跑所有 eval（需配合 test_data/）
```

## 适用场景

**适合**：理工科教材（数学、物理、化学、计算机、工程）、文科教材（政治、哲学、历史、法学、教育学）、讲义、课件 PDF（含扫描版）、Word 笔记、纯文本资料、Markdown 教材。

**不适合**：纯文字书（小说、传记）、PPT 转的 PDF（布局太碎）、单次查询（"第5页讲了什么"）。

**已知限制**：
- DOCX 的 Word 公式编辑器（OMML）公式会丢失为 alt 文本——理工科教材建议先转 PDF
- TXT 无结构时按段落合成页码，不识别"第N章"模式
- 合成页码与物理页码无关——学生要按老师指定页码复习时，优先用 PDF 输入
- 分块提取模式（大 PDF）不支持 `--ocr-correct`（OCR 纠错在合并后由调用方处理）

## 依赖

- Python 3.10+
- docling >= 2.10（PDF 提取 + OCR + 版面分析）
- PyMuPDF >= 1.23（页码 + 分块）
- markitdown[docx] >= 0.1.6（DOCX 提取，微软 2026-05 新库）
- charset-normalizer >= 3.4（TXT/MD 编码检测）
- PyYAML >= 6.0（配置文件）
- python-pptx + transformers >= 5.0（docling 间接依赖，必须 pin）

## 开发

跑测试 + 校验：

```bash
pytest tests/ -v
python scripts/controller.py validate tests/fixtures/sample_knowledge.json
```

贡献指南见 [`CONTRIBUTING.md`](CONTRIBUTING.md)，架构说明见 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

## 许可证

[MIT](LICENSE)
