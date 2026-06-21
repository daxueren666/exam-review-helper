---
name: exam-review-helper
description: 期末考试复习助手 - 将 PDF/Word/TXT/Markdown 教材浓缩为精华知识点并生成交互式 HTML 复习文档。适用场景：理工科教材（数学/物理/计算机/化学/工程）与文科教材（政治/哲学/历史/法学/教育学），自动识别模式。原生支持扫描版 PDF（含 OCR）、Word 讲义、纯文本笔记、Markdown 教材。当用户说"帮我复习这个"、"整理知识点"、"期末复习"，或上传学习资料问"总结一下"时主动使用此 skill，即使用户没明说"复习"。
---

# 期末考试复习助手

将 PDF / Word / TXT / Markdown 教材转化为结构化精华复习文档，生成交互式 HTML。

---

## 默认调用模式：对话驱动（零配置）

本 skill **在宿主 agent（Claude Code / Codex / OpenCode）里对话式执行**。宿主自己就是 LLM，按本文档和 `references/` 下的指令执行 5-pass。**不需要 API key、不需要任何外部配置**。

```
用户: "帮我复习这个"（上传 textbook.pdf 或 notes.docx 或 chapter.txt 或 module.md）
  ↓
宿主读 SKILL.md → 检测文件格式 → 按 5-pass 工作流执行
  ↓
[Phase 0] 调用 scripts/controller.py extract <source> → extracted_content.md
          - PDF: docling 提取（含 OCR）
          - DOCX: MarkItDown 提取（mammoth 内核）
          - TXT/MD: charset-normalizer 编码检测 + 直接读取
          - 其他格式见 references/multi-format-input.md
[Phase 1-5] 宿主亲自执行 5-pass（Read prompts/ 下的指令）
[Phase 6] 调用 scripts/controller.py generate 生成 HTML
  ↓
输出 Review - textbook/Review - textbook.html
```

**两个脚本的明确分工**：
- `scripts/controller.py extract <source>` — 多格式提取（PDF 用 docling；DOCX 用 MarkItDown；TXT/MD 用 charset-normalizer）
- `scripts/controller.py generate <json>` — 从 JSON 生成 HTML（确定性任务）
- `scripts/run_pipeline.py <source>` — 5-pass 流水线编排（提取+指引+断点续传+HTML 生成）
- `scripts/enhance_formulas.py <output_dir>` — 公式提取增强（可选，扫描占位符+pix2tex OCR）
- 中间的 5-pass 由宿主 LLM 对话执行（创造性任务）

---

## 5-Pass 工作流概览

| Pass | 角色 | 输入 | 输出 |
|---|---|---|---|
| 0 | Controller（宿主） | PDF/DOCX/TXT/MD | markdown（docling 或 MarkItDown 提取） |
| 1 | Planner | markdown 全文 | SegmentationMap（覆盖全部页码） |
| 2 | Segment Reader × N | 各段独立上下文 | 各段结构化 notes |
| 3 | Merger | N 份 notes | cheat-sheet draft JSON |
| 4 | Fresh Verifier | 原文 + draft | verdict（APPROVED / NOTES / REJECTED） |
| 5 | Reviser（条件触发） | draft + verdict | 修订稿（最多 3 轮） |

**详细执行指令**见 `references/multi-pass-workflow.md`。

> ⚠️ **硬约束**：Pass 1 启动前**必须先 Read `references/common-failure-modes.md`**——否则视为流程未启动，verifier 标准会漂移。

---

## 三个防偷懒原则

> 这些原则不是教条，是基于实际 LLM 失败模式提炼的。理解 why，才能在边界情况做判断。

### 原则 1：Segmentation Map 覆盖全部页码

**要求**：分段方案的 page_start..page_end 并集 = [1, total_pages]，无 gap、无重叠。

**为什么**：LLM 在长上下文里最常见的偷懒是"漏掉后半本"。学生付了一整本的精力，结果只复习到第 7 章。任何 page gap = fail-loud。

**例外**：用户用 `--ranges` 指定了范围时，仅要求覆盖指定范围。

### 原则 2：Verifier 必须是 Fresh Context

**要求**：Pass 4 派 fresh 子代理，不复用 Pass 2 reader 的对话历史。

**为什么**：让 LLM 自己检查自己 = 自我合理化。它会无意识地放大"我觉得做得不错"的确认偏误。新开 context 才能发现"概念 < 10"、"页码错"等真实问题。

**操作**：用 Agent 工具派发，prompt 见 `prompts/system_verifier.md`。

### 原则 3：Common Failure Modes 强制核查

**要求**：见 `references/common-failure-modes.md`。以下任一命中即 REJECTED：
- **Pass 2 段级**：单段 `concepts < 5`（段级阈值，少于 5 视为偷懒）
- **Pass 3/4 章级**：单章 `concepts < 10`（章级阈值，理工科教材这个数都到不了 = 偷懒）
- 单章 `pitfalls < 3`（没易错点 = 没认真读）
- `> 30%` 的 concepts 无 `related_to`（孤岛概念 = 没建立知识网络）

> **段级 vs 章级阈值区别**：Pass 2 是单段提取（每段 5-80 页），概念下限 5；Pass 3/4 是章节合并后（一章可能含多段），概念下限 10。原"单章 concepts < 10"指的是**章级**（Pass 3/4 合并后），段级（Pass 2 单段）用 5。

**为什么**：这些是历史实测中发现 LLM 最容易偷工减料的指标。卡死下限，逼它认真读。

---

## Skill 边界

- **允许配合**：`pdf` skill（如果宿主有，用于 PDF 提取兜底）
- **禁止**：调用 `dispatching-parallel-agents` 或其他工作流 skill。本 skill 自带调度规则。
- **工具**：仅用 Bash / Read / Write / Edit / Glob / Grep + Agent（如平台支持）

## CLI 子命令

| 子命令 | 用途 |
|---|---|
| `extract <sources...>` | 提取教材（PDF/DOCX/TXT/MD，可混合多文件） |
| `generate <knowledge.json>` | 从知识点 JSON 生成 HTML/MD/JSON（`--format` 选格式） |
| `validate <notes.json \| dir>` | 校验 Pass 2 segment notes 是否合法 |
| `init` | 检查依赖 + 配置文件 + 模板，首次使用时运行 |

全局参数：`--version`、`--config <path>`、`--no-cache`（extract）、`--format`（generate）、`--template`（generate）。

---

## 多格式输入（重要）

本 skill 除 PDF 外，还支持以下格式：

| 格式 | 扩展名 | 提取库 | 页码策略 |
|---|---|---|---|
| PDF | `.pdf` | docling + PyMuPDF | 物理页码（docling `page_items`） |
| Word | `.docx` / `.doc` | MarkItDown（mammoth 内核） | 合成（H1/H2 + 最小 1500 字符） |
| 纯文本 | `.txt` | charset-normalizer（编码检测） | 合成（段落 + 最小 1500 字符） |
| Markdown | `.md` / `.markdown` | charset-normalizer（编码检测） | 合成（H1/H2 + 最小 1500 字符） |

**合成页码说明**：非 PDF 格式无物理页码，extractor 按语义边界（标题/段落）合成
`[PAGE N]` 标记。Pass 1-5 工作流对这些页码的处理与 PDF 一致——`page` 字段指向
`extracted_content.md` 中的 `[PAGE N]` 段落。详见 `references/multi-format-input.md`。

**已知限制**：
- DOCX 的 OMML 公式（Word 公式编辑器）会丢失为 alt 文本——理工科教材建议先转 PDF
- TXT 无结构时 extractor 按段落合成页码，不识别"第N章"模式
- 合成页码与物理页码无关——学生要按老师指定页码复习时，优先用 PDF 输入

---

## 教材模式（自动识别，用户无需选择）

本 skill 支持**两种解析模式**，**宿主自动识别**，用户只需上传教材，不需要手动选文理科：

| 模式 | 适用教材 | Pass 2/4 Prompts | 概念阈值 | 公式要求 |
|---|---|---|---|---|
| **理工科** | 数学/物理/化学/计算机/工程 | `system_reader.md` / `system_verifier.md` | 章级 ≥ 10 | 必须提取，LaTeX 格式 |
| **文科** | 政治/哲学/历史/法学/教育学/文学 | `system_reader_liberal_arts.md` / `system_verifier_liberal_arts.md` | 章级 ≥ 8 | 可选（多数章节无公式） |

### 自动识别规则（宿主在 Phase 0 提取后自动判断）

1. **看 `extracted_content.md` 有无 `<!-- formula-not-decoded -->` 占位符** → 有 = 理工科
2. **看有无数学符号**（∑ ∫ √ ≤ ≥ ∈ α β 等，>20 个） → 有 = 理工科
3. **看有无文科关键词**（"观点/理论/意义/思想/历史地位"等，≥5 次） → 有 = 文科
4. **默认** → 理工科

用户全程不需要做任何选择，宿主读完 markdown 就知道用哪套 prompts。

### 也可用脚本辅助判断

```bash
python scripts/run_pipeline.py textbook.pdf   # 自动检测并打印模式
```

### 文科模式的特点

1. **概念定义更深**：必须包含核心观点 + 形成背景（至少 100 字），不是字面复述
2. **公式可选**：`formulas` 可为空数组（文科教材正常情况）
3. **易混淆点**重概念辨析（如"毛泽东思想 ≠ 毛泽东晚年的错误"），不是计算错误
4. **理论体系关联强化**：`connections` 至少 2 条，体现理论传承关系
5. **典型论述/案例**替代理工科的"例题"
6. **verifier 不因 formulas 为空而 REJECTED**

### 模式不影响的部分

- Phase 0 提取（docling/MarkItDown 不变）
- Pass 1 分段（逻辑相同）
- Pass 3 合并（逻辑相同）
- Pass 5 修订（逻辑相同）
- HTML 生成（模板相同，MathJax 在文科模式下不渲染任何东西但不报错）

---

## 输出目录规范

```
<source-directory>/
├── textbook.pdf           (或 notes.docx / chapter.txt / module.md)
└── Review - textbook/
    ├── extracted_content.md       # 多格式提取（统一带 [PAGE N] 标记）
    ├── extracted_content.json     # 结构化数据（schema 随格式不同）
    ├── textbook_knowledge.json    # 5-pass 知识点 JSON
    └── Review - textbook.html     # 最终 HTML
```

**禁止**：在源文件目录散落中间文件。所有产物必须在 `Review - <stem>/` 内。

---

## 输出 JSON Schema（HTML 模板兼容）

```json
{
  "source": "<教材名>",
  "chapters": [
    {
      "chapter_id": "chapter-1",
      "chapter_title": "第1章 函数与极限",
      "page_range": "1-45",
      "summary": "本章核心摘要（100-200 字）",
      "concepts": [{"name", "definition", "importance", "page", "related_to", "boundary", "variation"}],
      "formulas": [{"name", "latex", "explanation", "conditions", "page", "derivation_steps", "confidence"}],
      "examples": [{"title", "description", "key_point", "page"}],
      "pitfalls": [{"warning", "correction", "example", "page"}],
      "connections": [{"type", "concept", "chapter_ref"}]
    }
  ],
  "_note": "核心概念（importance='核心'）boundary 和 variation 必填",
  "metadata": {}
}
```

---

## 快速依赖检查

宿主首次执行时检查 `docling` 和 `markitdown` 是否可用，缺则提示：

```bash
pip install -r requirements.txt
```

requirements.txt 已 pin 所有必需依赖：
- `docling` + `PyMuPDF` + `rapidocr-onnxruntime`：PDF 提取与 OCR
- `markitdown[docx]`：DOCX 提取（微软 2026-05 新出的统一库，内部调 mammoth）
- `charset-normalizer`：TXT/MD 编码检测（GBK/GB2312/Big5/UTF-8）
- `python-pptx` / `transformers>=5.0`：docling 间接依赖（必须 pin）

首次运行 docling 会下载约 200MB 模型文件（一次性）。

如果 docling 装不上（网络问题、系统不兼容）：提示用户改用 PyMuPDF 直接提取文字版 PDF（但失去 OCR 和版面分析能力，质量会下降）。DOCX/TXT/MD 不受影响——它们走 MarkItDown / charset-normalizer 路径，不依赖 docling。

---

## 大 PDF 处理（重要）

docling 的 C++ 后端（docling-parse + onnxruntime）在单进程内会累积内存，处理 100+ 页 PDF 时容易在第 13 页附近触发 `std::bad_alloc`。

**controller.py 自动检测**：
- PDF > 50MB 或 > 100 页 → 自动启用分块提取
- 每块在**独立 Python 子进程**里跑（OS 直接回收 C++ 堆）
- 默认 chunk_size=50，可用 `--chunk-size 25` 更激进

```bash
# 自动判断（推荐）
python controller.py extract big_textbook.pdf

# 手动指定块大小
python controller.py extract big_textbook.pdf --chunk-size 25

# 强制不分块（小 PDF 用）
python controller.py extract small.pdf --no-chunk
```

**已知限制**：
- 公式提取 `do_formula_enrichment` 默认关闭（docling 自带方案需 18-40GB VRAM）
- 公式在 markdown 中显示为 `<!-- formula-not-decoded -->` 占位符
- Pass 2 readers 需基于上下文重建公式（实测可行）

---

## 高级功能（P0-P1 增强）

### 1. 图片剥离（`--strip-images`）

DOCX 提取时图片以 base64 内嵌，导致 markdown 体积膨胀。`--strip-images` 把图片存为独立文件，markdown 用 `![](images/img_001.png)` 引用：

```bash
python controller.py extract textbook.docx --strip-images
```

适用：DOCX 教材（尤其含大量图片的文科教材，如毛泽东思想概论 37 页剥离后图片占 0 字节而非膨胀 markdown）。

### 2. OCR 后处理纠错（`--ocr-correct`）

扫描版 PDF 经 rapidocr 提取后，常见汉字误判（巳→已、末→未 等）。`--ocr-correct` 自动修正常见 OCR 错误：

```bash
python controller.py extract scanned_textbook.pdf --ocr-correct
```

纠错策略：高置信度（上下文无关）+ 上下文相关（如数字上下文的"干"→"千"）。保守纠错——宁可漏纠不可错纠。

### 3. 5-pass 流水线编排（`scripts/run_pipeline.py`）

封装"提取 → 5-pass 指引 → 生成 HTML"全流程：

```bash
# 启动流水线（自动提取 + 检测模式 + 打印 5-pass 指引）
python scripts/run_pipeline.py textbook.pdf

# 自动检测模式（stem 理工科 / liberal 文科）
python scripts/run_pipeline.py textbook.pdf --mode auto

# 5-pass 完成后，自动生成 HTML
python scripts/run_pipeline.py textbook.pdf --generate-only
```

功能：
- **自动模式检测**：根据 markdown 内容判断理工科/文科
- **断点续传**：检查 `.checkpoint/` 下已完成的 segment notes，跳过已完成段
- **5-pass 指引**：打印详细的 Pass 1-5 执行步骤（哪个 prompt、什么输入输出）
- **HTML 自动生成**：检测到 `*_knowledge.json` 后自动调 `generate`

### 4. 断点续传

5-pass 中断后可恢复。宿主在 Pass 2 每完成一个 segment 时存：
```
Review - <stem>/.checkpoint/segmentation_map.json  # Pass 1 结果
Review - <stem>/.checkpoint/notes_seg-001.json     # Pass 2 第 1 段
Review - <stem>/.checkpoint/notes_seg-002.json     # Pass 2 第 2 段
...
```

重跑 `run_pipeline.py` 会检测已完成段并跳过，继续未完成段。

### 5. 公式提取增强（`scripts/enhance_formulas.py`，可选）

扫描公式占位符并输出 `formula_hints.json`，供 Pass 2 reader 参考：

```bash
# 默认：扫描占位符位置（不需要 pix2tex）
python scripts/enhance_formulas.py "Review - textbook/"

# 启用 pix2tex OCR（需 pip install pix2tex）
python scripts/enhance_formulas.py "Review - textbook/" --use-pix2tex textbook.pdf
```

输出 `formula_hints.json` 包含：每页公式数量、可选的 OCR 结果。Pass 2 reader 可读此文件知道哪些页有公式。

---

---

## 章节范围选择（重要）

**学生上传整本 PDF 时，开始 5-pass 之前必须问一句**：

> "你要复习全书，还是指定章节？"
> "可以说：第3章 / 第3章+第5章 / 第5章 15-30页 / 1-3章"

### 学生回答格式（自然语言，支持以下任意组合）

| 学生说 | 解析为 |
|---|---|
| `全部` / `整本` / `all` / `（不指定）` | 全书 |
| `第3章` / `3章` / `3` | 整章 |
| `15-30页` / `15-30` | 页码范围 |
| `第5章的15-30页` / `第5章 15-30页` | 章内页码 |
| `第3章+第5章` / `3,5,8` | 多章 |
| `第3章+第5章的15-30页+第8章` | 混合（章 + 章内页 + 章） |

### 实现方式

**对话驱动**（默认且唯一）：把学生的自然语言回答直接传给 Pass 1 的 prompt。LLM 自己解析"第3章"对应 markdown 中哪几页。

如需程序化解析（测试 / 自定义流程），可用 `scripts/chapter_selector.py`：

```python
from chapter_selector import parse_ranges
spec = parse_ranges("第3章+第5章15-30页+第8章")
print(spec.describe())  # "第3章（整章） + 第5章 p.15-30 + 第8章（整章）"
print(spec.to_llm_hint())  # 给 LLM 的范围提示文本
```

支持的反向范围自动纠正（"30-15" → "15-30"）。

宿主在执行 Pass 1 时，把范围作为 user message 的一部分：

```
[total_pages]: 256
[本次范围]: 第3章 + 第5章 p.15-30 + 第8章
[PDF 全文]: ...

请**只对范围内**生成 segment。如果学生说"第N章"，
请根据 markdown 中实际章节标题确定该章页码范围。
```

### 范围模式下的硬约束放宽

- ✅ 不要求 segmentation 覆盖 [1, total_pages]
- ✅ 允许范围外有 page gap
- ❌ 仍然禁止 segment 之间重叠
- ❌ 范围内不允许漏段（如果学生要"第3章"，必须包含第3章全部内容）

### HTML 输出层

生成的 HTML **只包含选中章节**。HTML 顶部加一行：

```
📖 本次范围：第3章 + 第5章 p.15-30 + 第8章
```

让学生明确知道本次复习覆盖了什么。

---

## 标准对话流（参考）

```
用户: 帮我复习这本教材（上传 textbook.pdf）

宿主:
  [Pass 0] 调用 docling 提取 PDF → extracted_content.md
  [Pass 1] 通读全文，输出分段方案（10 段，覆盖 1-256 页）
           等待用户确认或直接继续
  [Pass 2] 派发 10 个 segment reader 子代理（或顺序处理）
  [Pass 3] 合并 10 份 notes 为 chapters JSON
  [Pass 4] 派发 fresh verifier 子代理，对照原文核查
  [Pass 5] 若 REJECTED，修订后重新核查（最多 3 轮）
  [Phase 6] 调用 scripts/controller.py generate 生成最终 HTML
  → 输出 Review - textbook/Review - textbook.html
```

---

## 参考文档

| 文档 | 用途 |
|---|---|
| `references/multi-pass-workflow.md` | **Pass 1-5 详细执行指令**（核心） |
| `references/multi-format-input.md` | 多格式输入说明（DOCX/TXT/MD 页码合成、限制） |
| `references/common-failure-modes.md` | 防偷懒清单 + Red Flags + Rationalization Table |
| `references/html-template.md` | HTML 模板 |

---

## MUST 交付标准

执行完成时**必须**满足：

- `Review - <stem>/` 目录存在
- `extracted_content.md` 存在（文档提取成功）
- `<stem>_knowledge.json` 存在且 schema 合法
- `Review - <stem>.html` 存在且可打开
- HTML 包含 MathJax CDN 引用
- HTML 包含侧边导航、暗黑模式切换
- JSON 中每条 concept / formula / pitfall 都有 `page` 字段
- 无 page gap（segmentation map 覆盖全部页）

不满足任意一条 = 交付失败，**不允许静默降级**。

### 以下情况不算完成（即使声称完成也视为失败）

- ❌ 只在对话里给了总结，**没生成实际文件**
- ❌ 文件路径不存在就声称完成
- ❌ HTML 无法打开（MathJax CDN 缺失、JS 报错未捕获）
- ❌ JSON schema 不合法（缺 `chapter_id` / `page` 字段）
- ❌ 静默降级（page gap、漏章不报告）
- ❌ 聊天代输出（"我已经在脑子里完成了"）
- ❌ 跳过 verifier 直接报告完成
