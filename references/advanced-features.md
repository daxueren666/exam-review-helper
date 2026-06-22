# 高级功能（P0-P1 增强）

> 本文档详细说明 exam-review-helper 的高级功能。SKILL.md 只列出功能名，详细用法在这里。

## 1. 图片剥离（`--strip-images`）

DOCX 提取时图片以 base64 内嵌，导致 markdown 体积膨胀。`--strip-images` 把图片存为独立文件，markdown 用 `![](images/img_001.png)` 引用：

```bash
python controller.py extract textbook.docx --strip-images
```

适用：DOCX 教材（尤其含大量图片的文科教材，如毛泽东思想概论 37 页剥离后图片占 0 字节而非膨胀 markdown）。

## 2. OCR 后处理纠错（`--ocr-correct`）

扫描版 PDF 经 rapidocr 提取后，常见汉字误判（巳→已、末→未 等）。`--ocr-correct` 自动修正常见 OCR 错误：

```bash
python controller.py extract scanned_textbook.pdf --ocr-correct
```

纠错策略：高置信度（上下文无关）+ 上下文相关（如数字上下文的"干"→"千"）。保守纠错——宁可漏纠不可错纠。

## 3. 5-pass 流水线编排（`scripts/run_pipeline.py`）

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

## 4. 断点续传

5-pass 中断后可恢复。宿主在 Pass 2 每完成一个 segment 时存：
```
Review - <stem>/.checkpoint/segmentation_map.json  # Pass 1 结果
Review - <stem>/.checkpoint/notes_seg-001.json     # Pass 2 第 1 段
Review - <stem>/.checkpoint/notes_seg-002.json     # Pass 2 第 2 段
...
```

重跑 `run_pipeline.py` 会检测已完成段并跳过，继续未完成段。

## 5. 公式提取增强（`scripts/enhance_formulas.py`，可选）

扫描公式占位符并输出 `formula_hints.json`，供 Pass 2 reader 参考：

```bash
# 默认：扫描占位符位置（不需要 pix2tex）
python scripts/enhance_formulas.py "Review - textbook/"

# 启用 pix2tex OCR（需 pip install pix2tex）
python scripts/enhance_formulas.py "Review - textbook/" --use-pix2tex textbook.pdf
```

输出 `formula_hints.json` 包含：每页公式数量、可选的 OCR 结果。Pass 2 reader 可读此文件知道哪些页有公式。
