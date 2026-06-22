# 架构文档

本 skill 把教材（PDF/DOCX/TXT/MD）变成考前复习 HTML。整体由 7 个 Python 脚本 + 一组 prompts + 宿主 LLM 的 5-pass 工作流组成。脚本只承担**确定性任务**（提取、校验、渲染），LLM 推理由宿主对话执行。

## 数据流

```
源文件(PDF/DOCX/TXT/MD)
    ↓
controller.py:extract()  ←── 分发器，按扩展名路由
    ├── .pdf → extract_pdf (docling) / chunked_extract_pdf (大文件分块)
    └── 其他 → extractors.py:extract_document
                 ├── .docx → MarkItDown (mammoth)
                 └── .txt/.md → charset-normalizer
    ↓
extracted_content.md (带 [PAGE N] 标记)
    ↓
[5-pass LLM 工作流 - 宿主执行]
    Pass 1: system_segment.md → 分段
    Pass 2: system_reader.md (或 _liberal_arts.md) → 每段提取
    Pass 3: system_merger.md → 合并
    Pass 4: system_verifier.md (或 _liberal_arts.md) → 核查
    Pass 5: system_reviser.md → 修订
    ↓
<stem>_knowledge.json
    ↓
generate_html.py → Review - <stem>.html
```

## 7 个脚本的职责

| 脚本 | 职责 | 输入 | 输出 |
|---|---|---|---|
| controller.py | 主入口 + PDF 提取 + CLI | 源文件/JSON | markdown/HTML |
| extractors.py | 非 PDF 格式提取 | DOCX/TXT/MD | markdown |
| generate_html.py | JSON → HTML 渲染 | knowledge.json | HTML 文件 |
| chapter_selector.py | 章节范围解析 | 自然语言范围 | RangeSpec |
| run_pipeline.py | 5-pass 流水线编排 | 源文件 | 指引+HTML |
| enhance_formulas.py | 公式占位符扫描 | output_dir | formula_hints.json |
| ocr_corrector.py | OCR 后处理纠错 | 文本 | 纠错后文本 |

### 各脚本要点

**controller.py** — 主入口和 PDF 提取的核心。`extract()` 是顶层分发器，按扩展名路由到 PDF 路径或非 PDF 路径。PDF 路径有两套：`extract_pdf`（单次提取）和 `chunked_extract_pdf`（大文件分块）。分块的关键是**每块在独立子进程里跑**——docling 的 C++ 后端内存不被 Python GC 回收，单进程循环会累积到 `std::bad_alloc`。子进程退出后 OS 直接回收内存。CLI 提供 `extract` / `generate` / `validate` 三个子命令，加 `--strip-images` / `--ocr-correct` / `--chunk-size` 等选项。

**extractors.py** — 非 PDF 格式提取。`EXTRACTORS` 字典是扩展名 → extractor 函数的分发表，新增格式只需在此加映射。`_extract_text_based` 是共享骨架，三个具体 extractor（docx/txt/markdown）只差解码方式：DOCX 走 `_markitdown_convert`（mammoth 内核），TXT/MD 走 `_decode_text_file`（charset-normalizer）。`synthesize_pages()` 按标题边界合成 `[PAGE N]` 标记，让下游 5-pass 对输入格式无感知。

**generate_html.py** — 把 knowledge JSON 渲染为交互式 HTML。模板是独立的 `templates/default.html` 文件，`load_template` 读取后替换 `__DATA_PLACEHOLDER__` / `[教材名称]` / `[时间戳]` 占位符。防 `</script>` 注入：把 `</` 转成 `<\/`，浏览器 JSON.parse 自动还原。支持 `--template` 自定义模板。

**chapter_selector.py** — 解析学生的自然语言章节范围（"第3章+第5章15-30页"）为 `RangeSpec` dataclass。支持全书、整章、页码范围、多章、混合四种组合。`to_llm_hint()` 转成提示文本供 Pass 1 使用。

**run_pipeline.py** — 5-pass 流水线的**编排层**（不是真自动化，LLM 推理仍由宿主执行）。`detect_mode()` 自动判断理工科 vs 文科：有 `<!-- formula-not-decoded -->` 占位符或大量数学符号 → stem；有"观点/理论/意义"等文科关键词 → liberal。`check_checkpoint()` 检查 `.checkpoint/notes_seg-*.json`，Pass 2 跳过已完成段。检测到 `*_knowledge.json` 后自动调 `generate_html` 生成 HTML。

**enhance_formulas.py** — 公式增强（可选）。`scan_formula_placeholders()` 扫描 markdown 中的 `<!-- formula-not-decoded -->` 占位符，按页统计输出 `formula_hints.json`，供 Pass 2 reader 参考哪些页有公式。`--use-pix2tex` 可选启用 LaTeX-OCR 对公式图片做识别（需独立安装 pix2tex，默认不走此路径）。

**ocr_corrector.py** — 扫描版 PDF 的 OCR 后处理。`HIGH_CONFIDENCE_FIXES` 是上下文无关的高置信度纠错字典（"巳知"→"已知"），`CONTEXT_FIXES` 是上下文相关的正则替换。原则：**保守纠错**——宁可漏纠不可错纠。`has_ocr_markers()` 判断文本是否有典型 OCR 误判特征，由 controller 的 `--ocr-correct` 触发。

## 关键设计决策

### 1. 为什么 PDF 用 docling 而非 markitdown

docling 自带 OCR（rapidocr）和版面分析（layout），能处理扫描版 PDF 和复杂版面。markitdown 对 PDF 的支持基于 pdfminer，不做 OCR，扫描版 PDF 输出空白。代价：docling 重（依赖 onnxruntime），但教材场景几乎都涉及扫描版或带表格/公式的复杂版面，OCR 是刚需。

### 2. 为什么 TXT/MD 用 charset-normalizer 而非 markitdown

markitdown 对 TXT **不做编码检测**——按 Latin-1 读取，中文 GBK 文件全部乱码。这是实测踩过的坑（见 `test_data/sample_gbk.txt`）。charset-normalizer 能识别 UTF-8/GBK/GB2312/Big5/GB18030 等中文编码。DOCX 是二进制格式（zip 包），编码问题由 mammoth 处理，所以 DOCX 走 markitdown 没问题。

### 3. 为什么 5-pass 用 prompts/ 而非硬编码

prompts 是独立 `.md` 文件，每个 pass 一个。好处：**可替换**（用户可改 prompt 适配自己的学科）、**可审计**（git diff 看 prompt 变化）、**可扩展**（加文科模式只需加两个文件，不动代码）。如果硬编码在 Python 里，任何 prompt 调整都要改代码 + 跑测试 + 发版本。

### 4. 为什么 HTML 模板是独立 .html 文件

模板放在 `templates/default.html`（独立 HTML 文件，不是塞在 .md 里）。好处：编辑器有语法高亮、版本对比清晰、用户可用 `--template` 自定义。早期版本曾把模板塞在 `references/html-template.md` 的 ```html 代码块里用正则提取，但模板越来越大（2500+ 行），.md 包裹的优势减弱，已外置。

### 5. 合成页码算法为什么是 H1/H2 + 1500 字符

`synthesize_pages()` 按 `#{1,2}` 标题切分 section，累加到 1500 字符为一页，单 section 超 6000 字符按段落二次切分。设计意图：
- **H1/H2 锚定**保证语义边界——推导过程不被页码切断，verifier 检查"段内概念"时不会跨语义单元
- **1500 字符下限**避免"1页1句话"——太小页会让 verifier 判失败（概念数不足）
- **6000 字符上限**避免"1页5000字"——太大页会让 Pass 1 分段规则（5-80 页/段）失效
- 不切 `###` 及以下，避免过细——`###` 通常是子小节，切了反而打断推导

## 扩展点

### 加新输入格式

在 `scripts/extractors.py` 的 `EXTRACTORS` 字典加扩展名映射，写 `extract_<format>(path, output_dir, strip_images=False)` 函数。函数内部调用 `_extract_text_based()`，传入自己的 `decoder_fn`（返回 `(text, extra_meta_dict)`）。decoder 屏蔽格式差异，共享骨架负责合成页码和写输出。详细步骤见 [CONTRIBUTING.md](CONTRIBUTING.md#如何加新输入格式提取器)。

### 加新输出格式

在 `scripts/generate_html.py` 加 format 分支。当前只渲染 HTML，未来加 EPUB/PDF 输出时，建议抽 `render_html()` / `render_epub()` 等函数，由 CLI `--format` 参数路由。

### 加新教材模式

在 `prompts/` 加 `system_reader_<mode>.md` + `system_verifier_<mode>.md`。`run_pipeline.py` 的 `detect_mode()` 加新模式的检测规则，`get_pass_guidance()` 加新模式的参数（概念阈值、公式是否必须等）。现有模式：`stem`（理工科，概念阈值 10，公式必须）、`liberal`（文科，概念阈值 8，公式可选）。
