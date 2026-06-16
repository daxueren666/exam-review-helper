# Exam Review Helper

> 把 PDF 教材浓缩成交互式 HTML 复习文档的 [Claude Code Skill](https://docs.claude.com/en/docs/claude-code/skills)。
> 原生支持扫描版 PDF、章节范围选择、5-pass 深度提取。

![screenshot](docs/screenshot.png)

## 这是什么

一个在 Claude Code 里调用的 skill。学生上传 PDF 教材说"帮我复习这本"，它会：

1. 用 docling 把 PDF（含扫描版）提取成 markdown
2. 5-pass 工作流深度提取概念 / 公式 / 易错点 / 典型例题
3. 生成单个交互式 HTML（MathJax 公式渲染 + 暗黑模式 + 侧边导航 + 错题本 + 进度追踪）

整个流程**不需要 API key**——Claude Code 本身就是 LLM，skill 直接对话执行 5-pass。

## 快速开始

### 1. 安装 skill

把本仓库 clone 到 Claude Code 的 skills 目录：

```bash
git clone https://github.com/daxueren666/exam-review-helper.git \
  ~/.claude/skills/exam-review-helper
```

或在 Windows：

```bash
git clone https://github.com/daxueren666/exam-review-helper.git \
  %USERPROFILE%\.claude\skills\exam-review-helper
```

### 2. 安装 Python 依赖

```bash
cd ~/.claude/skills/exam-review-helper
pip install -r requirements.txt
```

首次运行会下载约 200MB 的 docling 模型文件（一次性）。

### 3. 在 Claude Code 里使用

打开 Claude Code，直接对话：

```
帮我复习这本教材（上传 textbook.pdf）
```

或指定范围：

```
只复习第3章 + 第5章的 15-30 页
```

Claude 会自动调用本 skill，输出：

```
<source-directory>/Review - textbook/
├── extracted_content.md       # docling 提取的 markdown
├── extracted_content.json     # docling 结构化数据
├── textbook_knowledge.json    # 5-pass 知识点 JSON
└── Review - textbook.html     # 最终交互式 HTML
```

直接双击 HTML 打开即可复习。

## 5-Pass 工作流

| Pass | 角色 | 输入 | 输出 |
|---|---|---|---|
| 0 | Controller（Python 脚本） | PDF | markdown（docling 提取） |
| 1 | Planner（LLM） | markdown 全文 | SegmentationMap（覆盖全部页码） |
| 2 | Segment Reader × N（LLM 并行） | 各段独立上下文 | 各段结构化 notes |
| 3 | Merger（LLM） | N 份 notes | cheat-sheet draft JSON |
| 4 | Fresh Verifier（LLM，独立 context） | 原文 + draft | APPROVED / NOTES / REJECTED |
| 5 | Reviser（LLM，条件触发） | draft + verdict | 修订稿（最多 3 轮） |

详细执行指令见 [`references/multi-pass-workflow.md`](references/multi-pass-workflow.md)。

## 关键特性

- **大 PDF 支持**：自动分块提取，每块在独立 Python 子进程里跑（绕开 docling C++ 后端的内存泄漏），实测 270 页零失败
- **章节范围选择**：自然语言解析 "第3章 + 第5章 15-30 页 + 第8章"，反向范围自动纠正
- **防偷懒机制**：Fresh verifier + common-failure-modes checklist，卡死 concepts/pitfalls 下限
- **HTML 交互**：MathJax 公式、暗黑模式、侧边导航、错题本、状态按钮（已掌握/待复习/不会）、搜索、笔记、进度追踪
- **JSON 校验**：`validate` 命令精确报错（line:col + unicode 检查）

## 目录结构

```
exam-review-helper/
├── SKILL.md                       Skill 入口（Claude Code 自动加载）
├── requirements.txt               Python 依赖
│
├── prompts/                       5-pass 系统提示词
│   ├── system_segment.md          Pass 1：分段
│   ├── system_reader.md           Pass 2：每段深读
│   ├── system_merger.md           Pass 3：合并
│   ├── system_verifier.md         Pass 4：核查
│   └── system_reviser.md          Pass 5：修订
│
├── references/                    参考文档
│   ├── multi-pass-workflow.md     工作流详细指令
│   ├── common-failure-modes.md    防偷懒清单
│   └── html-template.md           HTML 模板
│
├── scripts/                       确定性脚本
│   ├── controller.py              extract / generate / validate 三命令
│   ├── generate_html.py           JSON → HTML
│   └── chapter_selector.py        范围解析
│
├── evals/evals.json               skill-creator 评估用例
└── tests/                         单元测试（17 个，全通过）
    ├── conftest.py
    └── test_chapter_selector.py
```

## 脚本命令

```bash
# 提取 PDF（小文件单进程，大文件自动分块）
python scripts/controller.py extract input.pdf

# 手动指定块大小（默认 50）
python scripts/controller.py extract big_textbook.pdf --chunk-size 25

# 强制不分块
python scripts/controller.py extract small.pdf --no-chunk

# 从 JSON 生成 HTML
python scripts/controller.py generate knowledge.json

# 校验 notes JSON（精确报错 + unicode 检查）
python scripts/controller.py validate notes.json
```

## 运行测试

```bash
pytest tests/ -v
```

## 适用场景

**适合**：理工科教材（数学、物理、化学、计算机、工程）、讲义、课件 PDF（含扫描版）。

**不适合**：纯文字书（小说、传记）、PPT 转的 PDF（布局太碎）、单次查询（"第5页讲了什么"）。

## 依赖

- Python 3.10+
- docling >= 2.10（PDF 提取 + OCR + 版面分析）
- PyMuPDF >= 1.23（页码 + 分块）
- python-pptx + transformers >= 5.0（docling 间接依赖，必须 pin）

## 开发

跑测试 + 校验：

```bash
pytest tests/ -v
python scripts/controller.py validate tests/fixtures/sample_knowledge.json
```

## 许可证

[MIT](LICENSE)
