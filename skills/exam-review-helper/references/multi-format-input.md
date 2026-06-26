# 多格式输入说明

本 skill 除 PDF 外，还支持 Word/TXT/Markdown 输入。所有格式最终都产出同样的
`extracted_content.md`（带 `[PAGE N]` 标记），下游 5-pass 流程对输入格式无感知。

## 支持格式对照表

| 格式 | 扩展名 | 提取库 | 页码策略 |
|---|---|---|---|
| PDF | `.pdf` | docling + PyMuPDF | 物理页码（docling `page_items`） |
| Word | `.docx` / `.doc` | MarkItDown（mammoth 内核） | 合成（H1/H2 + 最小 1500 字符） |
| 纯文本 | `.txt` | charset-normalizer（编码检测） | 合成（段落 + 最小 1500 字符） |
| Markdown | `.md` / `.markdown` | charset-normalizer（编码检测） | 合成（H1/H2 + 最小 1500 字符） |

**为什么 TXT/MD 不用 MarkItDown？** 实测发现 MarkItDown 对 TXT 不做编码检测，
按 Latin-1 读取中文 GBK 文件会乱码。所以 TXT/MD 走 charset-normalizer 专用路径
（PDF/DOCX 是二进制格式，无此问题）。

## 页码合成算法（`synthesize_pages`）

非 PDF 格式没有物理页码，但 5-pass 流程强制要求每条 concept/formula/pitfall
都有 `page` 字段（见 `SKILL.md` MUST 交付标准 + `common-failure-modes.md` item 5）。
解决方法：按语义边界合成 `[PAGE N]` 标记。

### 算法步骤

1. **按 H1/H2 标题切分**：正则 `^#{1,2}\s+` 把 markdown 切成 sections（保留标题行）。
   不切 ### 及以下，避免过细。
2. **累加到最小页**：把 sections 累加到当前页，直到达到 `min_page_chars`（默认 1500）。
   短节与下一节合并，避免"1 页 1 句话"。
3. **超长节二次切分**：单个 section 超 `min_page_chars * 4`（~6000 字符）时，
   在段落边界（`\n\n`）切分，避免"1 页 5000 字"。
4. **首行强制 `[PAGE 1]`**：即使输入为空也会产出至少一页。

### 参数调优

`min_page_chars=1500` 是基于以下考量：
- 典型教材一页约 500-800 中文字符 / 1000-1500 英文词
- 1500 字符 ≈ 1-2 页内容，granularity 足够 planner 切出 5-80 页/段的 segment
- 太小（如 500）→ 页数过多，verifier 抽样失真
- 太大（如 5000）→ 页数过少，planner 强制切 mid-derivation

如需调整，修改 `scripts/extractors.py:synthesize_pages` 的 `min_page_chars` 参数。

## `extracted_content.json` Schema 差异

| 字段 | PDF (DoclingDocument) | 其他 (MultiFormatDocument) |
|---|---|---|
| `schema_name` | `"DoclingDocument"` | `"MultiFormatDocument"` |
| `pages` | docling 的页对象数组 | `{"1": {"page_no": 1}, ...}` 简化字典 |
| `origin` | PDF 路径 | 源文件路径 |
| `extractor` | 无 | `"markitdown"` |
| `format` | 无 | `"docx"` / `"txt"` / `"markdown"` |

下游消费者（如 `multi-pass-workflow.md` 的"从 pages 推断总页数"）只读 `pages` 字段长度，
两种 schema 都兼容。

## 已知限制

### DOCX 的 OMML 公式会丢失

Word 的公式编辑器（OMML 格式）在 MarkItDown/mammoth 的转换路径中会被转成
alt 文本或直接丢失。理工科教材若有大量 Word 公式：

- **建议**：先用 Word 另存为 PDF，再用 PDF 路径处理（docling 会标记为
  `<!-- formula-not-decoded -->` 占位符，Pass 2 reader 可基于上下文重建）
- **接受**：公式较少的人文社科讲义可直接用 DOCX 路径

### TXT 无结构时的处理

纯文本没有 markdown 标题，`synthesize_pages` 会：
1. 把整篇作为一个 section
2. 若超过 6000 字符，按段落（`\n\n`）切分
3. 若短于 1500 字符，单页输出

若 TXT 内容有"第N章"等中文模式但未转为 `##` 标题，extractor 不会自动识别——
合成页码会按段落均匀切分。如需识别章节边界，用户可手动把 TXT 内容转成 MD 格式。

### 合成页码 vs 物理页码

合成页码不对应任何物理实体——它们是 extractor 创造的语义段落编号。这满足
verifier 的契约（"page N 必须在 extracted_content.md 中存在 `[PAGE N]` 标记"），
但与原书的物理页码无关。若用户引用"教材第 47 页"，合成页码无法对应。

**何时需要物理页码**：学生要按老师指定的页码复习时。此时应优先使用 PDF 输入。

## 失败处理

| 失败场景 | 表现 | 应对 |
|---|---|---|
| markitdown 未安装 | `ImportError: markitdown 未安装...` | `pip install 'markitdown[docx]>=0.1.6'` |
| DOCX 损坏 | `DOCX 提取失败（KeyError/zipfile.BadZipFile: ...）` | 提示用户检查文件，或先修复 DOCX |
| TXT 编码异常 | 输出乱码但不崩溃 | 后续可加 `--encoding` CLI 参数手动指定 |
| 空 MD 文件 | 产出 `[PAGE 1]` 单页空 markdown | 正常处理，Pass 1 planner 会输出空 segments |

## 后续扩展（不在 MVP 内）

加 PPTX/XLSX/EPUB/RTF 支持只需：
1. `requirements.txt` 改为 `markitdown[docx,pptx,xlsx]`
2. `scripts/extractors.py` 的 `EXTRACTORS` 字典加新扩展名映射
3. 新增 `extract_pptx` / `extract_xlsx` / `extract_epub` / `extract_rtf` 函数（每个 10-20 行）

注意：EPUB 通过 MarkItDown 的路径不依赖 EbookLib（用 beautifulsoup4 直接解析 XHTML），
无 AGPL 许可证风险。
