# 5-Pass 工作流详细指令

> 本文档是 `SKILL.md` 的核心扩展，描述 Pass 0-5 的具体执行方式。
> 宿主 agent（Claude Code / Codex / OpenCode）按本文档执行。

---

## 角色映射

| 角色 | 实现 | 备注 |
|---|---|---|
| Controller | 宿主自己（主对话） | 编排、合并、最终交付 |
| Planner | 宿主单次推理 | Pass 1 |
| Segment Reader | 派发 N 个子代理（Agent 工具） | 并发或顺序 |
| Merger | 宿主单次推理 | Pass 3 |
| Verifier | 派发 1 个 fresh 子代理 | **必须新上下文** |
| Reviser | 宿主单次推理 | 条件触发 |

**关键**：Verifier 必须是 fresh 子代理，不允许复用 reader 对话历史。这是防偷懒的核心。

---

## Pass 0: 文档提取

```bash
python scripts/controller.py extract input.pdf       # 或 input.docx / input.txt / input.md
```

输出：
- `Review - input/extracted_content.md`（全文 markdown，含 `[PAGE N]` 标记）
- `Review - input/extracted_content.json`（结构化数据，schema 随格式不同——PDF 是 DoclingDocument，其他是 MultiFormatDocument）

**Page 标注**：markdown 中包含 `[PAGE N]` 标记。
- PDF：物理页码（docling `page_items`）
- DOCX/TXT/MD：合成页码（按 H1/H2 + 最小 1500 字符，详见 `references/multi-format-input.md`）

若无 `[PAGE N]` 标记（极少见，docling 旧版本），从 `extracted_content.json` 的 `pages` 字段长度推断总页数。

**失败处理**：
- docling 装不上 → 提示用户用 PyMuPDF 兜底（功能受限，仅文字版 PDF 可用）
- markitdown 装不上 → 提示 `pip install 'markitdown[docx]>=0.1.6'`（仅影响 DOCX）
- charset-normalizer 装不上 → 提示 `pip install 'charset-normalizer>=3.4.0'`（影响 TXT/MD）
- OCR 质量差 → 警告用户但不中止
- DOCX 损坏 → 提示用户检查文件或先修复

---

## Pass 1: 分段（Segmentation Map）

### 输入
- `extracted_content.md` 全文
- `total_pages`（从 extracted_content.json 推断）

### 任务
通读全文，输出分段方案。每段是一个**可独立深读**的内容单元。

### 输出格式
```json
{
  "total_pages_observed": 256,
  "segments": [
    {
      "id": "seg-001",
      "title": "第1章 函数与极限",
      "page_start": 1,
      "page_end": 45,
      "rationale": "完整一章，主题独立",
      "topic_type": "concept",
      "expected_density": "high"
    }
  ]
}
```

### 硬约束
- 所有 segment 的 `[page_start, page_end]` 并集 = `[1, total_pages]`
- 无 gap、无重叠
- 单段 5-80 页（超 80 必须再切，少于 5 应合并邻段）
- 每个 segment 必须有 `rationale`

### 系统提示词
完整版见 `prompts/system_segment.md`。对话模式下，宿主可直接读该文件作为本 Pass 的指令。

---

## Pass 2: Segment Reader（× N）

### 并发策略
- **平台支持 Agent 工具**：派发 N 个子代理并发，每子代理独立上下文
- **不支持或子代理成本高**：宿主自己顺序处理，但**每段处理时只加载该段内容**（不要把全文塞进单次对话）

### 每个 Reader 的输入
- 整本 PDF 的 markdown（用于跨段引用，但聚焦本段）
- 当前 segment 的元信息（id / title / page_range / rationale）

### 每个 Reader 的输出
```json
{
  "segment_id": "seg-001",
  "segment_title": "第1章 函数与极限",
  "page_range": "1-45",
  "summary": "本段核心摘要（50-150 字）",
  "concepts": [
    {
      "name": "函数",
      "definition": "设 x 和 y 是两个变量...",
      "importance": "核心",
      "page": 20,
      "related_to": ["映射", "定义域"]
    }
  ],
  "formulas": [
    {
      "name": "极限的 ε-δ 定义",
      "latex": "\\lim_{x \\to x_0} f(x) = A",
      "explanation": "...",
      "conditions": "x_0 是聚点",
      "page": 28
    }
  ],
  "examples": [{"title", "description", "key_point", "page"}],
  "pitfalls": [{"warning", "correction", "example", "page"}],
  "connections": [{"type", "concept", "chapter_ref"}]
}
```

### 硬约束
- concepts ≥ 5（少于 5 视为偷懒）
- 每条必须有 `page` 字段
- 公式必须转 LaTeX
- `related_to` 至少 1 个

### 系统提示词
完整版见 `prompts/system_reader.md`。

---

## Pass 3: Merger

### 输入
N 份 segment notes（Pass 2 输出数组）

### 任务
合并为统一的 `chapters` JSON。**不是简单拼接**：
1. 消除冗余（同一概念多段出现的合并）
2. 补全跨段关联（connections）
3. 章节归并（细粒度 segment 按教材实际章节边界归并）
4. 风格统一（definition 长度、importance 分级一致）

### 输出
见 SKILL.md 的 JSON Schema。

### 硬约束
- chapters ≥ 1
- 每 chapter concepts ≥ 10
- page 字段不丢失
- 跨章关联 ≥ 3 条

### 系统提示词
完整版见 `prompts/system_merger.md`。

---

## Pass 4: Fresh Verifier

### 关键约束
**必须是 fresh 子代理**。不允许在 Controller 主对话里"自检"。原因：自检 = 自我合理化 = 偷懒。

### 派发方式
```
宿主: Agent({
  description: "Fresh Verifier for exam-review",
  prompt: "你是独立验证者。[附 Pass 3 输出的 draft JSON] + [附 extracted_content.md 原文]。
           任务：核查 draft 是否忠实于原文。
           按下方 JSON Schema 严格返回结果。"
})
```

### Verifier 必须返回的 JSON Schema

```json
{
  "verdict": "APPROVED" | "APPROVED_WITH_NOTES" | "REJECTED",
  "coverage_findings": [
    {
      "area": "章节/公式/易错点/概念",
      "issue": "具体问题描述",
      "severity": "high" | "medium" | "low"
    }
  ],
  "accuracy_findings": [
    {
      "page": 123,
      "field": "concept" | "formula" | "pitfall" | "example",
      "issue": "页码错误/内容错误/LaTeX 不规范"
    }
  ],
  "missing_or_weak_areas": [
    {
      "type": "missing_formula | missing_concept | weak_pitfall | weak_boundary | weak_variation",
      "location": "章节标题 + 页码范围",
      "fix_hint": "提示 reviser 怎么修"
    }
  ]
}
```

**字段说明**：
- `verdict`：总判定（参考 SKILL.md 的三条硬约束 + common-failure-modes.md 的 Red Flags）
- `coverage_findings`：覆盖率问题（漏章、漏公式、概念数不足）
- `accuracy_findings`：准确性问题（页码错、内容错、LaTeX 含 unicode）
- `missing_or_weak_areas`：缺失或薄弱区域（reviser 直接消费此字段做修订）

Reviser 拿到 `verdict=REJECTED` 时，必须针对 `missing_or_weak_areas` 列出的每条 issue 给出 fix。

### Verdict 判据
- `APPROVED`: 覆盖完整、页码准确、风格统一
- `APPROVED_WITH_NOTES`: 小瑕疵但不影响复习（如个别 definition 偏长）
- `REJECTED`: 重大问题（page gap / 漏公式 / 概念数不足 / style 不一致）

### 必查项
- [ ] 所有 segment 是否都体现在 chapters 中
- [ ] 公式密集段是否漏公式
- [ ] 核心术语是否有英文括注（理工科）
- [ ] 采样 5-10 条 page，对照原文确认真实存在
- [ ] style 是否一致（不混 prose / bullet）

### 系统提示词
完整版见 `prompts/system_verifier.md`。

---

## Pass 5: Reviser（条件触发）

### 触发条件
- Pass 4 返回 `REJECTED`
- 或 `APPROVED_WITH_NOTES` 但 notes 涉及关键问题

### 流程
```
for round in 1..3:
    verdict = Pass 4 result
    if verdict == APPROVED or APPROVED_WITH_NOTES:
        return draft
    draft = revise(draft, verdict.issues)  # 针对性修订
    verdict = Pass 4(draft)  # 重新派发 fresh verifier
return draft  # 3 次仍 REJECTED → 强制 APPROVED_WITH_NOTES 落盘
```

### 修订原则
- **只改有问题的部分**——不要重写整个 draft
- **保留已通过的部分**
- **针对每个 issue 给出 fix**

### 系统提示词
完整版见 `prompts/system_reviser.md`。

---

## 常见调度问题

### Q: 平台不支持 Agent 工具怎么办？
A: 宿主自己顺序处理每段，但**清空上下文后再加载下一段**（避免长上下文偷懒）。

### Q: PDF 超长（500+ 页）？
A: Pass 1 输出更多 segment（10-20 个）。Pass 2 必须并发（顺序会超时）。如不并发，告诉用户"预计耗时 30+ 分钟"。

### Q: 用户中断了怎么办？
A: 已完成的 segment notes 保存到 `Review - <stem>/.checkpoint/`。重试时跳过已完成段。

### Q: 某段提取质量明显差？
A: 标记该段，Pass 4 强制 REJECTED + 列入 issues，Pass 5 针对性重做。不要静默接受低质量段落。

### Q: 非 PDF 格式怎么算页码？
A: DOCX/TXT/MD 无物理页码，extractor 按语义边界（H1/H2 + 最小 1500 字符）合成 `[PAGE N]` 标记。Pass 1 的分段、Pass 4 的页码核查都基于这些合成页码——语义等同于 PDF 的物理页。详见 `references/multi-format-input.md`。
