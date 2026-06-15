# HTML 模板

exam-review-helper 生成的复习 HTML 模板。

- 主布局：CSS Grid（sidebar + main）
- 字体：中文优先（PingFang SC / Microsoft YaHei）
- 暗黑模式：CSS variables + localStorage 持久化
- 公式：MathJax + 独立可滚动卡片
- 响应式：mobile 下 sidebar 折叠为抽屉

## 目录

> 本文件较长（1493 行）。Claude 不需要全读，按需跳转。

### 1. CSS 部分（行 32-720）
- **1.1 设计 token**（`:root` + `[data-theme="dark"]`）—— 行 33-100
  - 主色：`--primary` / `--accent`
  - 背景：`--bg` / `--bg-card` / `--bg-soft`
  - 文字：`--text` / `--text-soft`
  - 语义色：`--diff-*` / `--status-*`（难度 + 状态）
  - 阴影：`--shadow` / `--shadow-hover` / `--shadow-card`
- **1.2 基础布局** —— 行 118-160
  - `body` / `.app`（CSS Grid）/ `.header`
- **1.3 侧边栏** —— 行 188-280
  - `.sidebar` / `.nav-list` / `.nav-item`（带章节 checkbox）
  - `.progress-stats` / `.progress-bar`
- **1.4 主区域** —— 行 281-370
  - `.chapter` / `.chapter-header` / `.chapter-title`
  - `.chapter-summary` / `.section-label` / `.deep-only`
- **1.5 卡片系统** —— 行 373-430
  - `.card-grid` / `.card`（含 hover 浮起 + 阴影）
  - `.card.importance-core/major/minor`（左侧颜色编码）
  - `.card.mastered`（已掌握样式）
- **1.6 难度标签** —— 行 418-430
  - `.diff-tag.diff-basic/intermediate/advanced`
- **1.7 状态按钮**（3 态）—— 行 431-490
  - `.status-btn` + `.status-btn[data-status].active`
- **1.8 卡片状态** —— 行 491-500
  - `.card.status-mastered/review/hard`（左边框颜色）
- **1.9 banner 系统** —— 行 501-520
  - `.range-banner`（黄色范围提示）
  - `.filter-banner`（蓝色筛选提示）
- **1.10 学习模式 + 专注模式** —— 行 521-580
  - `.mode-switcher` / `.mode-btn`
  - `body.focus-mode *`（专注模式覆盖）
- **1.11 番茄钟** —— 行 580-590
- **1.12 响应式**（@media）—— 行 600-720

### 2. HTML 结构（行 720-820）
- `<header>` 含书名 + mode-switcher + focus-toggle + theme-toggle
- `<div class="top-progress">` sticky 进度条
- `<div class="range-banner">` 范围提示
- `<aside class="sidebar">` 含搜索 + 章节导航 + 复习进度
- `<main class="main">` 内容区

### 3. JS 部分（行 820-1490）
- **3.1 数据加载** —— `<script id="knowledge-data">` JSON 解析
- **3.2 工具函数** —— `escapeHtml` / `pageTag` / `wrapFormulaDelimiters`
- **3.3 渲染函数**：
  - `renderConcepts`（含 difficulty + boundary + variation + status 按钮）
  - `renderFormulas` / `renderPitfalls` / `renderExamples` / `renderConnections`
- **3.4 状态管理**：
  - `conceptStatus`（mastered/review/hard 三态）
  - `migrateMastered`（兼容旧 mastered Set）
  - `setConceptStatus` + `saveConceptStatus`
- **3.5 事件委托**：
  - `[data-action="concept-status"]` → setConceptStatus
- **3.6 进度更新**：
  - `updateProgress`（按概念数）
  - `updateChapterProgress`（按章数）
  - `renderMistakeBook`（错题本动态渲染）
- **3.7 章节筛选**：
  - `.nav-chapter-checkbox` 切换章节显隐
  - "全选/全不选"链接
- **3.8 学习模式**：`setMode('quick'/'standard'/'deep')`
- **3.9 专注模式 + 番茄钟**：startPomodoro / stopPomodoro
- **3.10 历史进度续学**：localStorage 记录 scroll 位置
- **3.11 主题切换**：data-theme="dark" 切换

### 4. 关键约定（必读）

- **数据注入**：`__DATA_PLACEHOLDER__` 被 `generate_html.py` 替换为 JSON
- **暗黑模式**：所有颜色必须用 `var(--xxx)`，禁止硬编码
- **状态系统**：concept 状态存 localStorage，跨会话保留
- **章节筛选**：用户选择存 `chapter-visibility`，下次打开恢复


`generate_html.py` 通过正则提取本文档的 ` ```html ` 代码块作为模板，并把整份知识点 JSON 通过 `__DATA_PLACEHOLDER__` 注入到 `<script id="knowledge-data">` 中。

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>期末复习笔记 - [教材名称]</title>
<script>
    MathJax = {
        loader: { load: ['[tex]/mhchem'] },
        tex: {
            inlineMath: [['$', '$'], ['\\(', '\\)']],
            displayMath: [['$$', '$$'], ['\\[', '\\]']],
            packages: { '[+]': ['mhchem'] }
        },
        svg: { fontCache: 'global' }
    };
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
<style>
:root {
    /* C. 现代笔记 - 主色系（精炼到 3 色）*/
    --primary: #2563eb;
    --primary-light: #dbeafe;
    --accent: #f59e0b;
    --bg: #fafaf8;            /* 温和米色（不是纯白）*/
    --bg-soft: #f4f4f1;
    --bg-card: #ffffff;
    --text: #0f172a;          /* 更深，对比度更高 */
    --text-soft: #64748b;
    --border: #e2e8f0;
    --code-bg: #f1f5f9;
    /* 多层阴影（更柔和）*/
    --shadow: 0 1px 2px rgba(15,23,42,0.04), 0 2px 8px rgba(15,23,42,0.04);
    --shadow-hover: 0 4px 12px rgba(15,23,42,0.08), 0 8px 24px rgba(15,23,42,0.06);
    --shadow-card: 0 1px 3px rgba(15,23,42,0.05), 0 1px 2px rgba(15,23,42,0.03);
    --radius: 12px;           /* 圆角加大 */
    --radius-sm: 6px;
    --importance-core: #dc2626;
    --importance-major: var(--accent);
    --importance-minor: var(--text-soft);
    --pitfall-bg: #fef2f2;
    --pitfall-border: #fecaca;
    --formula-bg: #f0f9ff;
    --formula-border: #bae6fd;
    --example-bg: #f0fdf4;
    --example-border: #bbf7d0;
    /* frontend-design 语义 token */
    --diff-basic-bg: #e6f4ea;        --diff-basic-text: #34a853;
    --diff-intermediate-bg: #fef3c7; --diff-intermediate-text: #92400e;
    --diff-advanced-bg: #fee2e2;     --diff-advanced-text: #b91c1c;
    --status-mastered-bg: #e6f4ea;   --status-mastered-text: #34a853;
    --status-review-bg: #fef3c7;     --status-review-text: #92400e;
    --status-hard-bg: #fee2e2;       --status-hard-text: #b91c1c;
    --range-banner-bg: linear-gradient(90deg,#fef3c7,#fde68a);
    --range-banner-text: #92400e;
    --range-banner-border: var(--accent);
    --filter-banner-bg: #dbeafe;
    --filter-banner-text: #1e40af;
    --btn-hover-bg: #f1f5f9;
    --mistake-book-bg: linear-gradient(135deg, #fff5f5, #ffeaea);
    --mistake-book-border: #ea4335;
    --mistake-book-title: #ea4335;
    --text-muted: #5f6368;
    --mode-switcher-bg: #f1f3f4;
}

[data-theme="dark"] {
    --primary: #60a5fa;
    --primary-light: #1e3a8a;
    --bg: #0f172a;
    --bg-soft: #1e293b;
    --bg-card: #1e293b;
    --text: #f1f5f9;
    --text-soft: #94a3b8;
    --border: #334155;
    --code-bg: #334155;
    --shadow: 0 1px 3px rgba(0,0,0,0.4);
    --shadow-hover: 0 4px 12px rgba(0,0,0,0.5);
    --pitfall-bg: #450a0a;
    --pitfall-border: #7f1d1d;
    --formula-bg: #082f49;
    --formula-border: #0c4a6e;
    --example-bg: #052e16;
    --example-border: #14532d;
    /* frontend-design 暗模式语义 token */
    --diff-basic-bg: rgba(129,201,149,0.15);       --diff-basic-text: #81c995;
    --diff-intermediate-bg: rgba(253,214,99,0.15); --diff-intermediate-text: #fdd663;
    --diff-advanced-bg: rgba(242,139,130,0.15);    --diff-advanced-text: #f28b82;
    --status-mastered-bg: rgba(129,201,149,0.2);   --status-mastered-text: #81c995;
    --status-review-bg: rgba(253,214,99,0.2);      --status-review-text: #fdd663;
    --status-hard-bg: rgba(242,139,130,0.2);       --status-hard-text: #f28b82;
    --range-banner-bg: linear-gradient(90deg,#3d2f00,#2a1f00);
    --range-banner-text: #fdd663;
    --range-banner-border: #b06000;
    --filter-banner-bg: #1e3a5f;
    --filter-banner-text: #8ab4f8;
    --btn-hover-bg: #2d3a4f;
    --mistake-book-bg: linear-gradient(135deg, #3a1515, #2a0e0e);
    --mistake-book-border: #f28b82;
    --mistake-book-title: #f28b82;
    --text-muted: #9aa0a6;
    --mode-switcher-bg: #2d3a4f;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

html {
    scroll-behavior: smooth;
}

body {
    font-family: "Inter", "PingFang SC", "Microsoft YaHei", "Source Han Sans CN",
                 -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "Helvetica Neue", Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.7;
    font-size: 15px;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    font-feature-settings: "cv02", "cv03", "cv04", "cv11";
}

.app {
    display: grid;
    grid-template-columns: 280px 1fr;
    grid-template-rows: 60px 1fr;
    grid-template-areas:
        "header header"
        "sidebar main";
    min-height: 100vh;
}

.header {
    grid-area: header;
    background: var(--bg-card);
    border-bottom: 1px solid var(--border);
    padding: 0 1.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: var(--shadow);
}

.header-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 60%;
}

.header-actions {
    display: flex;
    gap: 0.5rem;
    align-items: center;
}

.btn-icon {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 0.5rem 0.75rem;
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 0.875rem;
    transition: all 0.2s;
}

.btn-icon:hover {
    background: var(--bg-soft);
    border-color: var(--primary);
    color: var(--primary);
}

.sidebar {
    grid-area: sidebar;
    background: var(--bg-card);
    border-right: 1px solid var(--border);
    padding: 1.25rem;
    overflow-y: auto;
    height: calc(100vh - 60px);
    position: sticky;
    top: 60px;
}

.sidebar-section {
    margin-bottom: 1.5rem;
}

.sidebar-title {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-soft);
    margin-bottom: 0.5rem;
}

.search-box {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--bg);
    color: var(--text);
    font-size: 0.875rem;
    font-family: inherit;
}

.search-box:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px var(--primary-light);
}

.nav-list {
    list-style: none;
}

.nav-item {
    padding: 0.5rem 0.75rem;
    border-radius: var(--radius);
    cursor: pointer;
    color: var(--text-soft);
    font-size: 0.875rem;
    border-left: 3px solid transparent;
    margin-bottom: 0.125rem;
    transition: all 0.15s;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.nav-item:hover {
    background: var(--bg-soft);
    color: var(--text);
}

.nav-item.active {
    background: var(--primary-light);
    color: var(--primary);
    border-left-color: var(--primary);
    font-weight: 500;
}

.progress-stats {
    font-size: 0.75rem;
    color: var(--text-soft);
    padding: 0.5rem 0.75rem;
    background: var(--bg-soft);
    border-radius: var(--radius);
}

.progress-bar {
    height: 6px;
    background: var(--border);
    border-radius: 3px;
    overflow: hidden;
    margin-top: 0.5rem;
}

.progress-fill {
    height: 100%;
    background: var(--primary);
    transition: width 0.3s;
}

.main {
    grid-area: main;
    padding: 2rem 3rem;
    max-width: 900px;
    margin: 0 auto;
    width: 100%;
}

.book-header {
    margin-bottom: 2.5rem;
    padding-bottom: 1.5rem;
    border-bottom: 2px solid var(--border);
}

.book-title {
    font-size: 1.875rem;
    font-weight: 700;
    color: var(--text);
    margin-bottom: 0.5rem;
    line-height: 1.3;
}

.book-meta {
    color: var(--text-soft);
    font-size: 0.875rem;
}

.chapter {
    margin-bottom: 3rem;
    scroll-margin-top: 80px;
}

.chapter-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 1.5rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border);
    gap: 1rem;
    flex-wrap: wrap;
}

.chapter-title {
    font-size: 1.75rem;
    font-weight: 700;
    letter-spacing: -0.025em;
    color: var(--text);
    line-height: 1.3;
}

.chapter-page {
    color: var(--text-soft);
    font-size: 0.875rem;
    background: var(--bg-soft);
    padding: 0.25rem 0.75rem;
    border-radius: var(--radius);
    flex-shrink: 0;
}

/* 深度模式专属字段（默认隐藏） */
.deep-only { display: none; }
body.mode-deep .deep-only { display: block; }

.chapter-summary {
    color: var(--text-soft);
    margin-bottom: 1.5rem;
    padding: 1rem 1.25rem;
    background: var(--bg-soft);
    border-left: 4px solid var(--primary);
    border-radius: 0 var(--radius) var(--radius) 0;
    font-size: 0.9375rem;
}

.section-label {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text);
    margin: 1.75rem 0 0.875rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.section-label::before {
    content: '';
    width: 4px;
    height: 1.125rem;
    background: var(--primary);
    border-radius: 2px;
}

.card-grid {
    display: grid;
    gap: 0.875rem;
}

.card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem 1.5rem;
    box-shadow: var(--shadow-card);
    transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s;
    position: relative;
    overflow: hidden;
}

.card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-hover);
    border-color: var(--primary);
}

.card.importance-core {
    border-left: 4px solid var(--importance-core);
}

.card.importance-major {
    border-left: 4px solid var(--importance-major);
}

.card.importance-minor {
    border-left: 4px solid var(--importance-minor);
}

.card.mastered {
    opacity: 0.55;
    background: var(--bg-soft);
}

.card.mastered .card-title-text::after {
    content: ' ✓';
    color: #10b981;
    font-weight: 600;
}

/* 难度标签 */
.diff-tag {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 8px;
    font-size: 11px;
    font-weight: 600;
    margin-left: 6px;
}
.diff-tag.diff-basic { background: var(--diff-basic-bg); color: var(--diff-basic-text); }
.diff-tag.diff-intermediate { background: var(--diff-intermediate-bg); color: var(--diff-intermediate-text); }
.diff-tag.diff-advanced { background: var(--diff-advanced-bg); color: var(--diff-advanced-text); }

/* 3 态状态按钮 */
.status-buttons {
    display: flex;
    gap: 6px;
    margin-top: 12px;
    flex-wrap: wrap;
}
.status-btn {
    padding: 4px 10px;
    font-size: 12px;
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--text);
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.15s;
}
.status-btn:hover { background: var(--btn-hover-bg); }
.status-btn:active { transform: scale(0.96); }
.status-btn.active { font-weight: 600; }
.status-btn[data-status="mastered"].active {
    background: var(--status-mastered-bg);
    color: var(--status-mastered-text);
    border-color: var(--status-mastered-text);
}
.status-btn[data-status="review"].active {
    background: var(--status-review-bg);
    color: var(--status-review-text);
    border-color: var(--status-review-text);
}
.status-btn[data-status="hard"].active {
    background: var(--status-hard-bg);
    color: var(--status-hard-text);
    border-color: var(--status-hard-text);
}

/* 卡片状态 */
.card.status-mastered { border-left: 4px solid var(--status-mastered-text); opacity: 0.7; }
.card.status-review { border-left: 4px solid var(--status-review-text); }
.card.status-hard {
    border-left: 4px solid var(--status-hard-text);
    background: var(--bg-soft);
}

/* range-banner / filter-banner class 化 */
.range-banner {
    background: var(--range-banner-bg);
    border-left: 4px solid var(--range-banner-border);
    padding: 10px 20px;
    font-size: 14px;
    color: var(--range-banner-text);
}
.filter-banner {
    background: var(--filter-banner-bg);
    color: var(--filter-banner-text);
    padding: 10px 16px;
    border-radius: 6px;
    margin: 12px 0;
    font-size: 13px;
}

/* 微交互加强（.card 的基础定义见上方，这里只补充 hover 增强）*/
.card:hover {
    transform: translateY(-2px);
}
button:focus-visible, .mode-btn:focus-visible {
    outline: 2px solid var(--primary);
    outline-offset: 2px;
}
.mode-btn { transition: all 0.15s; }
.mode-btn:hover { background: var(--btn-hover-bg); }

/* 错题本 section */
.mistake-book {
    background: var(--mistake-book-bg);
    border: 2px solid var(--mistake-book-border);
    border-radius: 8px;
    padding: 16px 20px;
    margin: 24px 0;
}
.mistake-book h2 {
    color: var(--mistake-book-title);
    margin: 0 0 12px 0;
    border: none;
    padding: 0;
}

/* 学习模式切换器 */
.mode-switcher {
    display: flex;
    gap: 4px;
    background: var(--mode-switcher-bg);
    padding: 3px;
    border-radius: 6px;
}
.mode-btn {
    padding: 4px 10px;
    font-size: 12px;
    border: none;
    background: transparent;
    cursor: pointer;
    border-radius: 4px;
    color: var(--text-muted);
}
.mode-btn.active {
    background: var(--bg-card);
    color: var(--primary, #1a73e8);
    font-weight: 600;
    box-shadow: 0 1px 2px rgba(0,0,0,0.1);
}

/* 专注模式 */
body.focus-mode .sidebar { display: none !important; }
body.focus-mode .main { margin-left: 0 !important; max-width: 800px; margin: 0 auto; }
body.focus-mode .card { font-size: 1.05rem; }
body.focus-mode .top-progress { background: #1e1e1e; color: #e8eaed; }
body.focus-mode .progress-stats-top, body.focus-mode .progress-fill-top { color: #8ab4f8; }
body.focus-mode .mode-switcher { background: var(--bg-soft); }
body.focus-mode .mode-btn { color: var(--text-soft); }
body.focus-mode .mode-btn.active { background: var(--primary); color: white; }

/* 番茄钟 */
.pomodoro-timer {
    display: none;
    background: var(--primary);
    color: white;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
}
body.focus-mode .pomodoro-timer { display: inline-block; }

.card-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    cursor: pointer;
}

.card-title-text {
    flex: 1;
    min-width: 0;
    font-weight: 600;
    letter-spacing: -0.01em;
}

.card-page {
    font-size: 0.75rem;
    color: var(--text-soft);
    background: var(--bg-soft);
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    flex-shrink: 0;
    font-weight: 400;
}

.card-body {
    color: var(--text);
    font-size: 0.9375rem;
    line-height: 1.7;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

.card-body p {
    margin-bottom: 0.5rem;
}

.card-body p:last-child {
    margin-bottom: 0;
}

.card-body strong {
    color: var(--primary);
    font-weight: 600;
}

.card-body code {
    background: var(--code-bg);
    padding: 0.125rem 0.375rem;
    border-radius: 4px;
    font-family: "JetBrains Mono", "Cascadia Code", Consolas, monospace;
    font-size: 0.875em;
}

.related-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
    margin-top: 0.625rem;
    padding-top: 0.625rem;
    border-top: 1px dashed var(--border);
}

.related-tag {
    font-size: 0.75rem;
    color: var(--text-soft);
    background: var(--bg-soft);
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.15s;
}

.related-tag:hover {
    color: var(--primary);
    background: var(--primary-light);
}

.formula-block {
    background: var(--formula-bg);
    border: 1px solid var(--formula-border);
    border-radius: var(--radius);
    padding: 1rem 1.25rem;
    margin: 0.75rem 0;
    overflow-x: auto;
    overflow-y: hidden;
}

.formula-block mjx-container {
    overflow-x: auto;
    overflow-y: hidden;
    padding: 0.25rem 0;
}

.formula-name {
    font-size: 0.8125rem;
    color: var(--text-soft);
    margin-bottom: 0.5rem;
    font-weight: 500;
}

.formula-explanation {
    font-size: 0.875rem;
    color: var(--text-soft);
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px dashed var(--formula-border);
}

.pitfall-card {
    background: var(--pitfall-bg);
    border-left: 4px solid var(--importance-core);
}

.pitfall-warning {
    color: var(--importance-core);
    font-weight: 600;
}

.example-card {
    background: var(--example-bg);
    border-left: 4px solid #10b981;
}

.example-key-point {
    background: rgba(16, 185, 129, 0.1);
    padding: 0.5rem 0.75rem;
    border-radius: var(--radius);
    margin-top: 0.5rem;
    font-size: 0.875rem;
}

.connections-list {
    list-style: none;
    margin-top: 0.5rem;
}

.connections-list li {
    padding: 0.375rem 0;
    font-size: 0.875rem;
    color: var(--text-soft);
    border-bottom: 1px dashed var(--border);
}

.connections-list li:last-child {
    border-bottom: none;
}

.empty-state {
    text-align: center;
    padding: 3rem 1rem;
    color: var(--text-soft);
    font-size: 0.9375rem;
}

.mobile-toggle {
    display: none;
}

.sidebar-backdrop {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.4);
    z-index: 150;
}

.sidebar-backdrop.show {
    display: block;
}

@media (max-width: 900px) {
    .app {
        grid-template-columns: 1fr;
        grid-template-areas:
            "header"
            "main";
    }

    .sidebar {
        position: fixed;
        top: 60px;
        left: -300px;
        width: 280px;
        height: calc(100vh - 60px);
        z-index: 200;
        transition: left 0.25s ease;
        box-shadow: 2px 0 8px rgba(0,0,0,0.15);
    }

    .sidebar.open {
        left: 0;
    }

    .mobile-toggle {
        display: inline-flex;
    }

    .main {
        padding: 1.25rem;
        max-width: 100%;
    }

    .book-title {
        font-size: 1.5rem;
    }

    .card {
        padding: 0.875rem 1rem;
    }

    .formula-block {
        padding: 0.75rem 1rem;
        font-size: 0.9em;
    }
}

@media print {
    .header, .sidebar, .sidebar-backdrop, .mobile-toggle, .btn-icon {
        display: none !important;
    }

    .app {
        grid-template-columns: 1fr;
        grid-template-areas: "main";
    }

    .main {
        max-width: 100%;
        padding: 0;
    }

    .card, .formula-block {
        break-inside: avoid;
        box-shadow: none;
    }

    body {
        font-size: 11pt;
        line-height: 1.5;
    }
}
</style>
</head>
<body>
<div class="app">
    <header class="header">
        <div style="display: flex; align-items: center; gap: 0.75rem; min-width: 0; flex: 1;">
            <button class="btn-icon mobile-toggle" id="sidebar-toggle" aria-label="切换目录">☰</button>
            <div class="header-title" id="book-title-display">[教材名称]</div>
        </div>
        <div class="header-actions" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <div class="mode-switcher" id="mode-switcher">
                <button class="mode-btn" data-mode="quick">⚡速通</button>
                <button class="mode-btn active" data-mode="standard">📖标准</button>
                <button class="mode-btn" data-mode="deep">🎓深度</button>
            </div>
            <button id="focus-toggle" class="mode-btn" style="background:var(--blue,#1a73e8);color:white;padding:6px 12px;border-radius:4px;border:none;cursor:pointer;font-size:13px;">🎯专注</button>
            <div class="pomodoro-timer" id="pomodoro-timer">🍅 25:00</div>
            <button class="btn-icon" id="theme-toggle" aria-label="切换主题">🌙</button>
            <button class="btn-icon" onclick="window.print()" aria-label="打印">🖨</button>
        </div>
    </header>

    <div class="top-progress" style="position:sticky; top:0; z-index:50; background:var(--bg-card); border-bottom:1px solid var(--border); padding:8px 20px; display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
        <span style="font-size:13px; color:var(--text-soft); white-space:nowrap;">复习进度</span>
        <div class="progress-stats" id="progress-stats-top" style="font-size:13px; font-weight:600; color:var(--primary, #1a73e8); white-space:nowrap;">已掌握 0 / 0</div>
        <div class="progress-bar" style="flex:1; min-width:120px; max-width:300px; height:8px; background:var(--bg-soft); border-radius:4px; overflow:hidden;">
            <div class="progress-fill" id="progress-fill-top" style="width:0%; height:100%; background:linear-gradient(90deg,var(--primary),var(--status-mastered-text)); transition:width 0.3s ease;"></div>
        </div>
    </div>

    <div id="range-banner" class="range-banner" style="display:none;">
        📖 本次范围：<span id="range-text"></span>
    </div>

    <aside class="sidebar" id="sidebar">
        <div class="sidebar-section">
            <div class="sidebar-title">搜索</div>
            <input type="text" class="search-box" id="search-input" placeholder="搜索概念 / 公式...">
        </div>

        <div class="sidebar-section">
            <div class="sidebar-title" style="display:flex;justify-content:space-between;align-items:center;">
                <span>章节导航</span>
                <span style="font-size:11px;">
                    <a href="#" id="select-all-chapters" style="color:var(--primary);text-decoration:none;margin-right:6px;">全选</a>
                    <a href="#" id="select-none-chapters" style="color:var(--text-muted);text-decoration:none;">全不选</a>
                </span>
            </div>
            <ul class="nav-list" id="nav-list"></ul>
        </div>

        <div class="sidebar-section">
            <div class="sidebar-title">复习进度</div>
            <div class="progress-stats" id="progress-stats">已掌握 0 / 0</div>
            <div class="progress-bar"><div class="progress-fill" id="progress-fill" style="width: 0%"></div></div>
        </div>
    </aside>

    <div class="sidebar-backdrop" id="sidebar-backdrop"></div>

    <main class="main" id="main-content">
        <div class="empty-state">加载中...</div>
    </main>
</div>

<script id="knowledge-data" type="application/json">__DATA_PLACEHOLDER__</script>
<script>
(function() {
  try {
    const dataEl = document.getElementById('knowledge-data');
    if (!dataEl) {
        document.getElementById('main-content').innerHTML = '<div class="empty-state">错误: 未找到数据脚本</div>';
        return;
    }
    const data = JSON.parse(dataEl.textContent);
    const main = document.getElementById('main-content');
    const navList = document.getElementById('nav-list');

    // 安全的 localStorage 包装（隐私模式 / 配额满 / Safari iframe 会抛 SecurityError）
    function safeLS(key, defaultValue) {
        try {
            const v = localStorage.getItem(key);
            return v === null ? defaultValue : v;
        } catch (e) {
            return defaultValue;
        }
    }
    function safeLSSet(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* 配额满静默忽略 */ }
    }
    function safeLSJSON(key, defaultValue) {
        try {
            const v = localStorage.getItem(key);
            return v ? JSON.parse(v) : defaultValue;
        } catch (e) {
            return defaultValue;
        }
    }

    document.title = document.title.replace('[教材名称]', data.source || '复习笔记');
    document.getElementById('book-title-display').textContent = data.source || '复习笔记';

    // 显示范围提示（如果 metadata 有范围信息）
    const meta = data.metadata || {};
    if (meta.range_description && meta.range_description !== '全书') {
        const banner = document.getElementById('range-banner');
        document.getElementById('range-text').textContent = meta.range_description;
        banner.style.display = 'block';
    }

    const mastered = new Set(safeLSJSON('mastered-concepts', []));

    if (!data.chapters || data.chapters.length === 0) {
        main.innerHTML = '<div class="empty-state">暂无内容</div>';
        return;
    }

    function escapeHtml(str) {
        if (str == null) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function pageTag(page) {
        if (page == null) return '';
        if (Array.isArray(page)) page = page.join(',');
        return '<span class="card-page">p.' + page + '</span>';
    }

    function importanceClass(imp) {
        const v = (imp || '').toLowerCase();
        if (v === '核心' || v === 'critical' || v === 'high') return 'importance-core';
        if (v === '重要' || v === 'major' || v === 'medium') return 'importance-major';
        return 'importance-minor';
    }

    function difficultyClass(diff) {
        const v = (diff || '').toLowerCase();
        if (v === '基础' || v === 'basic') return 'diff-basic';
        if (v === '进阶' || v === 'intermediate') return 'diff-intermediate';
        if (v === '高难' || v === 'advanced' || v === 'hard') return 'diff-advanced';
        return '';
    }

    function difficultyTag(diff) {
        if (!diff) return '';
        const cls = difficultyClass(diff);
        const labels = {'diff-basic':'基础','diff-intermediate':'进阶','diff-advanced':'高难'};
        return '<span class="diff-tag ' + cls + '">' + (labels[cls] || escapeHtml(diff)) + '</span>';
    }

    // 3 态状态管理：mastered / review / hard
    function getConceptStatus() {
        return safeLSJSON('concept-status', {});
    }
    function saveConceptStatus(status) {
        safeLSSet('concept-status', JSON.stringify(status));
    }
    // 兼容旧 mastered Set
    function migrateMastered() {
        const status = getConceptStatus();
        let changed = false;
        mastered.forEach(function(id) {
            if (!status[id]) { status[id] = 'mastered'; changed = true; }
        });
        if (changed) saveConceptStatus(status);
        return status;
    }
    const conceptStatus = migrateMastered();

    function setConceptStatus(id, status) {
        if (status === null) {
            delete conceptStatus[id];
        } else {
            conceptStatus[id] = status;
        }
        saveConceptStatus(conceptStatus);
        const card = document.querySelector('[data-id="' + CSS.escape(id) + '"]');
        if (card) {
            card.classList.remove('status-mastered','status-review','status-hard');
            if (status) card.classList.add('status-' + status);
            const btns = card.querySelectorAll('.status-btn[data-action="concept-status"]');
            btns.forEach(function(b) { b.classList.remove('active'); });
            if (status) {
                const activeBtn = card.querySelector('.status-btn[data-status="' + status + '"]');
                if (activeBtn) activeBtn.classList.add('active');
            }
        }
        updateProgress();
        renderMistakeBook();
    }

    function statusButtons(id) {
        const st = conceptStatus[id];
        const safeId = escapeHtml(id);
        return '<div class="status-buttons" data-concept-id="' + safeId + '" style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;">' +
            '<button class="status-btn' + (st==='mastered'?' active':'') + '" data-action="concept-status" data-status="mastered" title="已掌握">✅ 已掌握</button>' +
            '<button class="status-btn' + (st==='review'?' active':'') + '" data-action="concept-status" data-status="review" title="待复习">🔍 待复习</button>' +
            '<button class="status-btn' + (st==='hard'?' active':'') + '" data-action="concept-status" data-status="hard" title="我不会 - 加入错题本">❌ 我不会</button>' +
            '</div>';
    }

    function renderConcepts(concepts) {
        if (!concepts || !concepts.length) return '';
        const cards = concepts.map((c) => {
            const id = c.id || c.name || ('c-' + Math.random().toString(36).slice(2, 9));
            const st = conceptStatus[id];
            const statusClass = st ? (' status-' + st) : '';
            const diffCls = difficultyClass(c.difficulty);
            const related = (c.related_to || []).map(function(r) {
                return '<span class="related-tag">' + escapeHtml(r) + '</span>';
            }).join('');
            const elements = (c.elements || []).map(function(e) {
                return '<p>• ' + escapeHtml(e) + '</p>';
            }).join('');
            const points = (c.points || []).map(function(p) {
                return '<p>• ' + escapeHtml(p) + '</p>';
            }).join('');
            const formula = c.formula ? '<div class="formula-block">' + escapeHtml(c.formula) + '</div>' : '';
            return '<div class="card ' + importanceClass(c.importance) + diffCls + statusClass + '" data-id="' + escapeHtml(id) + '" data-search="' + escapeHtml((c.name || '') + ' ' + (c.definition || '')) + '">' +
                '<div class="card-title">' +
                    '<span class="card-title-text">' + escapeHtml(c.name || c.concept || '') + '</span>' +
                    difficultyTag(c.difficulty) +
                    pageTag(c.page) +
                '</div>' +
                '<div class="card-body">' +
                    (c.definition ? '<p>' + escapeHtml(c.definition) + '</p>' : '') +
                    elements + points + formula +
                    (c.types ? '<p><strong>类型:</strong> ' + escapeHtml(c.types.join('、')) + '</p>' : '') +
                    (c.boundary ? '<div class="deep-only" style="margin-top:8px;padding:8px 12px;background:var(--bg-soft);border-left:3px solid var(--status-review-text);border-radius:4px;"><strong style="color:var(--status-review-text);">⚠ 适用边界：</strong> ' + escapeHtml(c.boundary) + '</div>' : '') +
                    (c.variation ? '<div class="deep-only" style="margin-top:6px;padding:8px 12px;background:var(--bg-soft);border-left:3px solid var(--primary);border-radius:4px;"><strong style="color:var(--primary);">🔄 变形/等价表述：</strong> ' + escapeHtml(c.variation) + '</div>' : '') +
                    statusButtons(id) +
                '</div>' +
                (related ? '<div class="related-tags">' + related + '</div>' : '') +
            '</div>';
        }).join('');
        return '<div class="card-grid">' + cards + '</div>';
    }

    function renderFormulas(formulas) {
        if (!formulas || !formulas.length) return '';
        const cards = formulas.map(function(f, idx) {
            const raw = f.latex || f.formula || '';
            const wrapped = wrapFormulaDelimiters(raw);
            return '<div class="card formula-card" data-search="' + escapeHtml((f.name || '') + ' ' + (f.explanation || '')) + '">' +
                '<div class="card-title">' +
                    '<span class="card-title-text">' + escapeHtml(f.name || '') + '</span>' +
                    pageTag(f.page) +
                '</div>' +
                '<div class="formula-block">' + escapeHtml(wrapped) + '</div>' +
                (f.explanation ? '<div class="formula-explanation">' + escapeHtml(f.explanation) + '</div>' : '') +
                (f.conditions ? '<div class="formula-explanation"><strong>适用条件:</strong> ' + escapeHtml(f.conditions) + '</div>' : '') +
            '</div>';
        }).join('');
        return '<div class="card-grid">' + cards + '</div>';
    }

    // 事件委托：处理 concept-status 按钮
    document.addEventListener('click', function(e) {
        const btn = e.target.closest('[data-action="concept-status"]');
        if (!btn) {
            // 错题本"移除"按钮
            const mbBtn = e.target.closest('[data-action="mb-promote"]');
            if (mbBtn) {
                setConceptStatus(mbBtn.dataset.target, 'mastered');
            }
            return;
        }
        const container = btn.closest('[data-concept-id]');
        if (container) {
            setConceptStatus(container.dataset.conceptId, btn.dataset.status);
        }
    });

    function wrapFormulaDelimiters(latex) {
        if (!latex) return '';
        latex = cleanUnicodeMath(latex);
        const s = latex.trim();
        if (/^\$\$[\s\S]+\$\$$/.test(s)) return s;
        if (/^\$[^$]+\$/.test(s)) return s;
        if (/^\\\[[\s\S]+\\\]$/.test(s)) return s;
        if (/^\\\([\s\S]+\\\)$/.test(s)) return s;
        return '$$' + s + '$$';
    }

    function cleanUnicodeMath(s) {
        if (!s) return s;
        const map = {
            '√': '\\sqrt ', '≤': ' \\leq ', '≥': ' \\geq ',
            '∈': ' \\in ', '∉': ' \\notin ', '⊂': ' \\subset ', '⊃': ' \\supset ',
            '⊆': ' \\subseteq ', '⊇': ' \\supseteq ',
            '∪': ' \\cup ', '∩': ' \\cap ', '∅': ' \\emptyset ',
            '∀': ' \\forall ', '∃': ' \\exists ',
            '→': ' \\to ', '←': ' \\leftarrow ', '↔': ' \\leftrightarrow ',
            '⇒': ' \\Rightarrow ', '⇐': ' \\Leftarrow ', '⇔': ' \\Leftrightarrow ',
            '↦': ' \\mapsto ',
            '∞': ' \\infty ', '∂': ' \\partial ', '∇': ' \\nabla ',
            '×': ' \\times ', '÷': ' \\div ', '±': ' \\pm ', '∓': ' \\mp ',
            '⋅': ' \\cdot ', '∘': ' \\circ ', '⋆': ' \\star ',
            '…': ' \\ldots ', '⋯': ' \\cdots ', '⋮': ' \\vdots ', '⋱': ' \\ddots ',
            '≤f': ' \\le ', '≥f': ' \\ge ',
            'α': ' \\alpha ', 'β': ' \\beta ', 'γ': ' \\gamma ', 'δ': ' \\delta ',
            'ε': ' \\varepsilon ', 'ϵ': ' \\epsilon ', 'ζ': ' \\zeta ', 'η': ' \\eta ',
            'θ': ' \\theta ', 'ϑ': ' \\vartheta ', 'ι': ' \\iota ', 'κ': ' \\kappa ',
            'λ': ' \\lambda ', 'μ': ' \\mu ', 'ν': ' \\nu ', 'ξ': ' \\xi ',
            'π': ' \\pi ', 'ϖ': ' \\varpi ', 'ρ': ' \\rho ', 'ϱ': ' \\varrho ',
            'σ': ' \\sigma ', 'ς': ' \\varsigma ', 'τ': ' \\tau ', 'υ': ' \\upsilon ',
            'φ': ' \\varphi ', 'ϕ': ' \\phi ', 'χ': ' \\chi ', 'ψ': ' \\psi ',
            'ω': ' \\omega ',
            'Γ': ' \\Gamma ', 'Δ': ' \\Delta ', 'Θ': ' \\Theta ', 'Λ': ' \\Lambda ',
            'Ξ': ' \\Xi ', 'Π': ' \\Pi ', 'Σ': ' \\Sigma ', 'Υ': ' \\Upsilon ',
            'Φ': ' \\Phi ', 'Ψ': ' \\Psi ', 'Ω': ' \\Omega ',
            '–': '-', '—': '-', '‘': "'", '’': "'", '“': '"', '”': '"'
        };
        let out = s;
        for (const k in map) {
            if (map.hasOwnProperty(k)) {
                out = out.split(k).join(map[k]);
            }
        }
        return out.replace(/\s+/g, ' ').trim();
    }

    function renderPitfalls(pitfalls) {
        if (!pitfalls || !pitfalls.length) return '';
        const cards = pitfalls.map(function(p) {
            return '<div class="card pitfall-card" data-search="' + escapeHtml((p.warning || '') + ' ' + (p.correction || '')) + '">' +
                '<div class="card-title">' +
                    '<span class="card-title-text pitfall-warning">⚠ ' + escapeHtml(p.warning || '') + '</span>' +
                    pageTag(p.page) +
                '</div>' +
                '<div class="card-body">' +
                    (p.correction ? '<p><strong>正确做法:</strong> ' + escapeHtml(p.correction) + '</p>' : '') +
                    (p.example ? '<p><strong>错误示例:</strong> ' + escapeHtml(p.example) + '</p>' : '') +
                '</div>' +
            '</div>';
        }).join('');
        return '<div class="card-grid">' + cards + '</div>';
    }

    function renderExamples(examples) {
        if (!examples || !examples.length) return '';
        const cards = examples.map(function(e) {
            return '<div class="card example-card" data-search="' + escapeHtml((e.title || '') + ' ' + (e.description || '')) + '">' +
                '<div class="card-title">' +
                    '<span class="card-title-text">' + escapeHtml(e.title || '') + '</span>' +
                    pageTag(e.page) +
                '</div>' +
                '<div class="card-body">' +
                    (e.description ? '<p>' + escapeHtml(e.description) + '</p>' : '') +
                    (e.key_point ? '<div class="example-key-point"><strong>关键:</strong> ' + escapeHtml(e.key_point) + '</div>' : '') +
                '</div>' +
            '</div>';
        }).join('');
        return '<div class="card-grid">' + cards + '</div>';
    }

    function renderConnections(connections) {
        if (!connections || !connections.length) return '';
        const items = connections.map(function(c) {
            const prefix = c.type === 'prerequisite' ? '前置:' : (c.type === 'foundation' ? '铺垫:' : '');
            const ref = c.from_chapter || c.for_chapter || c.chapter_ref || '';
            return '<li>' + prefix + ' ' + escapeHtml(c.concept || '') + (ref ? ' (' + escapeHtml(ref) + ')' : '') + '</li>';
        }).join('');
        return '<ul class="connections-list">' + items + '</ul>';
    }

    const html = data.chapters.map(function(ch, idx) {
        const chid = ch.chapter_id || ('chapter-' + (idx + 1));
        return '<section class="chapter" id="' + chid + '">' +
            '<div class="chapter-header">' +
                '<h2 class="chapter-title">' + escapeHtml(ch.chapter_title || '') + '</h2>' +
                (ch.page_range ? '<span class="chapter-page">pp.' + escapeHtml(ch.page_range) + '</span>' : '') +
            '</div>' +
            (ch.summary ? '<div class="chapter-summary">' + escapeHtml(ch.summary) + '</div>' : '') +
            (ch.concepts && ch.concepts.length ? '<h3 class="section-label">核心概念</h3>' + renderConcepts(ch.concepts) : '') +
            (ch.formulas && ch.formulas.length ? '<h3 class="section-label">重要公式</h3>' + renderFormulas(ch.formulas) : '') +
            (ch.examples && ch.examples.length ? '<h3 class="section-label">典型例题</h3>' + renderExamples(ch.examples) : '') +
            (ch.pitfalls && ch.pitfalls.length ? '<h3 class="section-label">易错点</h3>' + renderPitfalls(ch.pitfalls) : '') +
            (ch.connections && ch.connections.length ? '<h3 class="section-label section-connections">章节关联（深度）</h3>' + renderConnections(ch.connections) : '') +
        '</section>';
    }).join('');

    main.innerHTML = html;

    // 分章 MathJax typeset（避免一次性 typeset 数千公式卡死浏览器）
    if (window.MathJax && MathJax.typesetPromise) {
        const chapters = main.querySelectorAll('.chapter');
        if (chapters.length > 1) {
            // 异步分批 typeset
            let i = 0;
            function typesetNext() {
                if (i >= chapters.length) return;
                const ch = chapters[i++];
                MathJax.typesetPromise([ch]).then(typesetNext).catch(function(e) {
                    console.warn('MathJax typeset failed at chapter', i, e);
                    typesetNext();
                });
            }
            // 用 requestIdleCallback 避免阻塞首屏
            (window.requestIdleCallback || function(cb) { setTimeout(cb, 50); })(typesetNext);
        } else {
            MathJax.typesetPromise([main]).catch(function(e) {
                console.warn('MathJax typeset failed:', e);
            });
        }
    }

    navList.innerHTML = data.chapters.map(function(ch, idx) {
        const chid = ch.chapter_id || ('chapter-' + (idx + 1));
        const title = escapeHtml(ch.chapter_title || ('第' + (idx+1) + '章'));
        const pg = ch.page_range ? '<span style="color:var(--text-muted);font-size:11px;">p.' + escapeHtml(String(ch.page_range)) + '</span>' : '';
        return '<li class="nav-item" data-target="' + chid + '" style="display:flex;align-items:flex-start;gap:8px;padding:8px 10px;cursor:pointer;border-radius:4px;">'
            + '<input type="checkbox" class="nav-chapter-checkbox" data-target="' + chid + '" checked style="margin-top:3px;flex-shrink:0;cursor:pointer;accent-color:#1a73e8;">'
            + '<div style="flex:1;min-width:0;"><div>' + title + '</div>' + pg + '</div></li>';
    }).join('');

    // 章节复选框：实时筛选显示
    const chapterVisibility = safeLSJSON('chapter-visibility', {});
    navList.querySelectorAll('.nav-chapter-checkbox').forEach(function(cb) {
        const chid = cb.dataset.target;
        if (chapterVisibility[chid] === false) {
            cb.checked = false;
            const ch = document.getElementById(chid);
            if (ch) ch.style.display = 'none';
            cb.closest('.nav-item').style.opacity = '0.4';
        }
        cb.addEventListener('change', function() {
            const target = document.getElementById(chid);
            if (target) {
                target.style.display = cb.checked ? '' : 'none';
            }
            cb.closest('.nav-item').style.opacity = cb.checked ? '1' : '0.4';
            chapterVisibility[chid] = cb.checked;
            safeLSSet('chapter-visibility', JSON.stringify(chapterVisibility));
            updateChapterProgress();
        });
        // 阻止 checkbox 点击冒泡到 nav-item（避免触发滚动）
        cb.addEventListener('click', function(e) { e.stopPropagation(); });
    });

    navList.querySelectorAll('.nav-item').forEach(function(item) {
        item.addEventListener('click', function(e) {
            if (e.target.tagName === 'INPUT') return;
            const target = document.getElementById(item.dataset.target);
            if (target && target.style.display !== 'none') {
                target.scrollIntoView({ behavior: 'smooth' });
                document.getElementById('sidebar').classList.remove('open');
                document.getElementById('sidebar-backdrop').classList.remove('show');
            }
        });
    });

    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                const id = entry.target.id;
                navList.querySelectorAll('.nav-item').forEach(function(item) {
                    item.classList.toggle('active', item.dataset.target === id);
                });
            }
        });
    }, { rootMargin: '-80px 0px -70% 0px' });

    document.querySelectorAll('.chapter').forEach(function(ch) { observer.observe(ch); });

    document.getElementById('search-input').addEventListener('input', function(e) {
        const q = e.target.value.trim().toLowerCase();
        document.querySelectorAll('[data-search]').forEach(function(el) {
            if (!q) { el.style.display = ''; return; }
            const text = (el.dataset.search || '').toLowerCase();
            el.style.display = text.includes(q) ? '' : 'none';
        });
    });

    const themeToggle = document.getElementById('theme-toggle');
    const savedTheme = safeLS('theme', 'light');
    document.documentElement.setAttribute('data-theme', savedTheme);
    themeToggle.textContent = savedTheme === 'dark' ? '☀' : '🌙';

    themeToggle.addEventListener('click', function() {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        safeLSSet('theme', next);
        themeToggle.textContent = next === 'dark' ? '☀' : '🌙';
        if (window.MathJax && MathJax.typesetPromise) {
            MathJax.typesetPromise();
        }
    });

    document.getElementById('sidebar-toggle').addEventListener('click', function() {
        document.getElementById('sidebar').classList.toggle('open');
        document.getElementById('sidebar-backdrop').classList.toggle('show');
    });
    document.getElementById('sidebar-backdrop').addEventListener('click', function() {
        document.getElementById('sidebar').classList.remove('open');
        document.getElementById('sidebar-backdrop').classList.remove('show');
    });

    window.toggleMastered = function(id) {
        if (mastered.has(id)) {
            mastered.delete(id);
        } else {
            mastered.add(id);
        }
        safeLSSet('mastered-concepts', JSON.stringify(Array.from(mastered)));
        updateProgress();
        const card = document.querySelector('[data-id="' + CSS.escape(id) + '"]');
        if (card) card.classList.toggle('mastered');
    };

    function updateProgress() {
        const total = document.querySelectorAll('.card[data-id]').length;
        const masteredCount = Object.values(conceptStatus).filter(s => s === 'mastered').length;
        const reviewCount = Object.values(conceptStatus).filter(s => s === 'review').length;
        const hardCount = Object.values(conceptStatus).filter(s => s === 'hard').length;
        const pct = total ? Math.round(masteredCount * 100 / total) : 0;
        const statsSidebar = document.getElementById('progress-stats');
        const fillSidebar = document.getElementById('progress-fill');
        if (statsSidebar) statsSidebar.textContent = '✅'+masteredCount+' / 🔍'+reviewCount+' / ❌'+hardCount+' / 共 '+total;
        if (fillSidebar) fillSidebar.style.width = pct + '%';
        updateChapterProgress();
    }

    function renderMistakeBook() {
        const hardIds = Object.keys(conceptStatus).filter(id => conceptStatus[id] === 'hard');
        let book = document.getElementById('mistake-book');
        if (hardIds.length === 0) {
            if (book) book.remove();
            return;
        }
        if (!book) {
            book = document.createElement('section');
            book.id = 'mistake-book';
            book.className = 'mistake-book';
            const main = document.getElementById('main-content');
            main.appendChild(book);
        }
        // 不用 outerHTML 克隆（克隆的按钮点击会更新原卡片，副本永远不变）
        // 改为基于 conceptStatus 重新渲染简化卡片
        const hardCards = hardIds.map(id => {
            // 在已渲染的 concepts 中找到对应数据
            const card = document.querySelector('.card[data-id="' + CSS.escape(id) + '"]');
            if (!card) return '';
            const name = card.querySelector('.card-title-text')?.textContent || '(未命名)';
            const def = card.querySelector('.concept-def')?.textContent || '';
            const page = card.querySelector('.page-tag')?.textContent || '';
            return '<div class="card concept-card status-hard" data-id="mb-' + escapeHtml(id) + '" data-mb-for="' + escapeHtml(id) + '">' +
                '<div class="card-header"><span class="card-title-text">' + escapeHtml(name) + '</span>' +
                (page ? '<span class="page-tag">' + escapeHtml(page) + '</span>' : '') + '</div>' +
                '<div class="concept-def">' + escapeHtml(def) + '</div>' +
                '<div class="status-buttons">' +
                '<button class="status-btn" data-action="mb-promote" data-target="' + escapeHtml(id) + '" title="标记为已掌握，从错题本移除">✅ 已掌握</button>' +
                '</div></div>';
        }).join('');
        book.innerHTML = '<h2>❌ 我的错题本（' + hardIds.length + ' 个）</h2>' +
            '<p style="color:var(--text-muted);font-size:13px;margin-bottom:12px;">点击"✅ 已掌握"可从错题本移除</p>' +
            '<div class="card-grid">' + hardCards + '</div>';
    }

    function updateChapterProgress() {
        const allChapters = document.querySelectorAll('.chapter');
        const visibleChapters = Array.from(allChapters).filter(ch => ch.style.display !== 'none');
        const totalChapters = allChapters.length;
        const visibleCount = visibleChapters.length;

        // 章级进度：当前可见章 / 总章数
        const statsTop = document.getElementById('progress-stats-top');
        const fillTop = document.getElementById('progress-fill-top');
        if (statsTop) {
            statsTop.textContent = '正在复习 ' + visibleCount + ' / ' + totalChapters + ' 章';
        }
        if (fillTop) {
            fillTop.style.width = (totalChapters ? Math.round(visibleCount * 100 / totalChapters) : 0) + '%';
        }

        // 主区域顶部加提示条（如果没有）
        let banner = document.getElementById('chapter-filter-banner');
        if (!banner) {
            banner = document.createElement('div');
            banner.id = 'chapter-filter-banner';
            banner.className = 'filter-banner';
            banner.style.cssText = '';
            const main = document.getElementById('main-content');
            main.insertBefore(banner, main.firstChild);
        }
        if (visibleCount < totalChapters) {
            banner.textContent = '📋 当前显示 ' + visibleCount + ' / ' + totalChapters + ' 章（其他章已在侧边栏取消勾选）。改回去请到左侧"章节导航"勾选。';
            banner.style.display = 'block';
        } else {
            banner.style.display = 'none';
        }
    }

    // 全选/全不选按钮
    document.getElementById('select-all-chapters').addEventListener('click', function(e) {
        e.preventDefault();
        document.querySelectorAll('.nav-chapter-checkbox').forEach(function(cb) {
            cb.checked = true;
            cb.dispatchEvent(new Event('change'));
        });
    });
    document.getElementById('select-none-chapters').addEventListener('click', function(e) {
        e.preventDefault();
        document.querySelectorAll('.nav-chapter-checkbox').forEach(function(cb) {
            cb.checked = false;
            cb.dispatchEvent(new Event('change'));
        });
    });

    updateProgress();
    renderMistakeBook();

    // === 学习模式切换 (#1) ===
    const modeSwitcher = document.getElementById('mode-switcher');
    if (modeSwitcher) {
        const savedMode = safeLS('learn-mode', 'standard');
        setMode(savedMode);
        modeSwitcher.querySelectorAll('.mode-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                setMode(btn.dataset.mode);
            });
        });
    }
    function setMode(mode) {
        document.body.classList.remove('mode-quick','mode-standard','mode-deep');
        document.body.classList.add('mode-' + mode);
        if (modeSwitcher) {
            modeSwitcher.querySelectorAll('.mode-btn').forEach(function(b) {
                b.classList.toggle('active', b.dataset.mode === mode);
            });
        }
        safeLSSet('learn-mode', mode);

        // 三档差异化：
        // 速通 ⚡：只看核心，隐藏 examples / connections / 高难 / 次要概念 / 公式条件 / 关联标签
        // 标准 📖：常规复习，显示主要内容（默认）
        // 深度 🎓：精读模式，额外显示 boundary / variation / connections / 章节摘要
        const show = function(sel, yes) {
            document.querySelectorAll(sel).forEach(function(el) {
                el.style.display = yes ? '' : 'none';
            });
        };

        const isQuick = mode === 'quick';
        const isDeep = mode === 'deep';

        // 速通隐藏的元素（标准和深度都显示）
        show('.example-card', !isQuick);
        show('.related-tags', !isQuick);
        show('.diff-advanced', !isQuick);
        show('.importance-minor', !isQuick);  // 次要概念
        show('.formula-explanation', !isQuick);  // 公式详细解释
        show('.chapter-summary', !isQuick);  // 章节摘要

        // 深度独有：boundary / variation / connections
        // 这些字段在概念卡里默认 hidden（CSS .deep-only），只在 mode-deep 下显示
        show('.deep-only', isDeep);

        // 深度模式：connections 章节
        show('.section-connections', isDeep);
    }

    // === 专注模式 + 番茄钟 (#8) ===
    let pomodoroInterval = null;
    let pomodoroSeconds = 25 * 60;
    document.getElementById('focus-toggle').addEventListener('click', function() {
        document.body.classList.toggle('focus-mode');
        const isFocus = document.body.classList.contains('focus-mode');
        this.textContent = isFocus ? '✕ 退出专注' : '🎯 专注';
        if (isFocus && !pomodoroInterval) startPomodoro();
        else if (!isFocus) stopPomodoro();
    });
    function startPomodoro() {
        pomodoroSeconds = 25 * 60;
        updatePomodoroDisplay();
        pomodoroInterval = setInterval(function() {
            pomodoroSeconds--;
            updatePomodoroDisplay();
            if (pomodoroSeconds <= 0) {
                alert('🍅 25 分钟到！休息 5 分钟');
                stopPomodoro();
                document.body.classList.remove('focus-mode');
                document.getElementById('focus-toggle').textContent = '🎯 专注';
            }
        }, 1000);
    }
    function stopPomodoro() {
        if (pomodoroInterval) { clearInterval(pomodoroInterval); pomodoroInterval = null; }
    }
    function updatePomodoroDisplay() {
        const m = Math.floor(pomodoroSeconds / 60);
        const s = pomodoroSeconds % 60;
        const el = document.getElementById('pomodoro-timer');
        if (el) el.textContent = '🍅 ' + String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
    }

    // === 历史进度续学 (#5) ===
    const lastScroll = safeLS('last-scroll-position', null);
    if (lastScroll && parseInt(lastScroll) > 500) {
        setTimeout(function() {
            if (confirm('📍 上次复习到这里，要继续吗？')) {
                window.scrollTo(0, parseInt(lastScroll));
            }
        }, 500);
    }
    let scrollTimer = null;
    window.addEventListener('scroll', function() {
        if (scrollTimer) clearTimeout(scrollTimer);
        scrollTimer = setTimeout(function() {
            safeLSSet('last-scroll-position', window.scrollY);
        }, 1000);
    });

    const ts = document.createElement('div');
    ts.style.cssText = 'text-align:center;color:var(--text-soft);font-size:0.75rem;padding:2rem 0;border-top:1px solid var(--border);margin-top:3rem';
    ts.textContent = '生成时间: [时间戳]';
    main.appendChild(ts);
  } catch (err) {
    console.error('[exam-review-helper] 渲染失败:', err);
    const main = document.getElementById('main-content');
    if (main) {
        main.innerHTML = '<div class="empty-state" style="color:#dc2626;padding:2rem;text-align:left;">' +
            '<strong>渲染失败:</strong> ' + (err && err.message ? err.message : err) +
            '<br><br>请按 F12 打开开发者工具查看完整错误。</div>';
    }
  }
})();
</script>
</body>
</html>
```
