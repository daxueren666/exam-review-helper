# Exam Review Helper

> 把 PDF / Word / TXT / Markdown 教材浓缩成交互式 HTML 复习文档的 Claude Code / Codex CLI Skill。
> 自动识别文科/理工科，5-pass 深度提取，原生支持扫描版 PDF OCR。

![screenshot](docs/screenshot.png)

## 这是什么

一个在 Claude Code 或 Codex CLI 里调用的 skill。你上传教材说"帮我复习这个"，它会：

1. **提取**：PDF（含扫描版 OCR）/ Word / TXT / MD，自动识别格式
2. **5-pass 深度提取**：概念 / 公式 / 易错点 / 典型例题，自动识别文科/理工科
3. **生成交互式 HTML**：MathJax 公式 + 暗黑模式 + 搜索 + 笔记 + 进度追踪

不需要额外配 API key——5-pass 由宿主调用的 LLM 执行，用你登录宿主时的认证。

## 安装

**1. clone 到 skills 目录**（按你的平台选路径）：

```bash
# Claude Code 用户
git clone https://github.com/daxueren666/exam-review-helper.git \
  ~/.claude/skills/exam-review-helper

# Codex CLI 用户
git clone https://github.com/daxueren666/exam-review-helper.git \
  ~/.agents/skills/exam-review-helper
```

Windows 把 `~/` 换成 `%USERPROFILE%\`。

**2. 装 Python 依赖 + 检查环境**：

```bash
cd ~/.claude/skills/exam-review-helper   # 或 ~/.agents/skills/exam-review-helper
pip install -r requirements.txt
python scripts/controller.py init
```

首次提取 PDF 会下载约 200MB docling 模型（一次性）。

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

- [SKILL.md](SKILL.md) — skill 主指令（Claude Code / Codex 自动加载）
- [references/multi-pass-workflow.md](references/multi-pass-workflow.md) — 5-pass 详细流程
- [references/multi-format-input.md](references/multi-format-input.md) — 多格式输入说明
- [references/advanced-features.md](references/advanced-features.md) — 高级功能（图片剥离/OCR/流水线/断点续传/公式增强）
- [references/common-failure-modes.md](references/common-failure-modes.md) — 防偷懒清单
- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构说明
- [CONTRIBUTING.md](CONTRIBUTING.md) — 贡献指南

## 开发

```bash
pytest tests/ -v                   # 120 个单元测试
python scripts/run_evals.py --all  # 跑 eval 套件
```

## 许可证

[MIT](LICENSE)
