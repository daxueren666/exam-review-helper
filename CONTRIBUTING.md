# 贡献指南

欢迎为 exam-review-helper 贡献代码。本指南说明如何加新功能、写测试、提 PR。

## 如何贡献

1. **Fork → 改 → 提 PR**：Fork 仓库，在分支上改动，提 PR 到 main。
2. **跑测试**：提交前必须 `pytest tests/ -v` 全通过。当前有 74 个单元测试（含 17 个 P0-P1 新功能测试）。
3. **代码风格**：遵循现有风格——
   - 中文注释解释 **WHY**（不写 WHAT，代码本身已说明做了什么）
   - 函数加类型注解（Python 3.10+ 语法，如 `list[str]` 而非 `List[str]`）
   - 每个公开函数加 docstring，说明 Args / Returns / 设计意图
   - 函数 < 50 行，文件 < 500 行
4. **不引入新依赖**：能用现有库（docling / markitdown / charset-normalizer / PyMuPDF）就别加新的。必须加时，同步更新 `requirements.txt` 并在 PR 说明里解释为什么必须加。

## 如何加新输入格式提取器

以加 `.rtf` 支持为例：

1. **在 `scripts/extractors.py` 的 `EXTRACTORS` 字典加扩展名映射**：
   ```python
   EXTRACTORS: Dict[str, Any] = {
       ".docx": extract_docx,
       # ...
       ".rtf": extract_rtf,
   }
   ```

2. **写 `extract_<format>` 函数**，调用 `_extract_text_based` 共享逻辑：
   ```python
   def _decode_rtf(path: Path) -> tuple:
       """RTF → markdown。用 <你的解码库>。"""
       # 解码逻辑，返回 (text, extra_meta_dict)
       return text, {"extractor": "your_lib"}

   def extract_rtf(path: Path, output_dir: Path, strip_images: bool = False) -> Dict[str, Any]:
       """提取 RTF 为 markdown。"""
       return _extract_text_based(path, output_dir, _decode_rtf, "rtf", strip_images=strip_images)
   ```
   `_extract_text_based` 自动处理 `synthesize_pages`、写 `extracted_content.md` + `.json`、返回标准 dict。

3. **在 `tests/test_extractors.py` 加测试**：
   - mock 底层转换库（用 monkeypatch 替换 `_decode_rtf`）测 happy path
   - 真实文件端到端测试：把小 RTF 文件放 `test_data/`，测 `extract_document` 完整流程
   - 至少 1 个边界情况（空文件 / 编码异常 / 不存在文件）

4. **更新 `SKILL.md`** 的格式对照表（"支持的输入格式"章节）。

5. **更新 `references/multi-format-input.md`**：加新格式的技术选型说明、踩坑记录、底层库版本要求。

## 如何加测试

1. **单元测试放 `tests/test_*.py`**，用 pytest。文件名和被测模块对应（`test_extractors.py` 测 `extractors.py`）。
2. **mock 外部依赖用 monkeypatch**：
   ```python
   def test_extract_docx_mock_markitdown(monkeypatch, tmp_path):
       def fake_convert(path):
           return "# 标题\n\n正文内容"
       monkeypatch.setattr("extractors._markitdown_convert", fake_convert)
       # ... 调用 extract_docx，断言输出
   ```
   不要真的调 markitdown / docling——慢且依赖环境。
3. **真实文件测试放 `test_data/`**：小文件（< 50KB），入库。`conftest.py` 提供 `sample_docx_path` / `sample_md_path` / `sample_txt_gbk_path` 等 fixture，文件不存在时 `pytest.skip`。
4. **每个 PR 至少覆盖**：
   - 新功能的 happy path（正常输入产出预期结果）
   - 1 个边界情况（空输入 / 异常输入 / 越界参数）
   - 失败路径（依赖缺失 / 文件不存在 / 解码失败时返回 `{"status": "error", ...}` 而非抛异常）

5. **跑测试**：
   ```bash
   pytest tests/ -v              # 全部
   pytest tests/test_extractors.py -v  # 单个文件
   pytest tests/ -k "docx" -v    # 按关键词
   ```

## 如何加 eval 用例

eval 用例在 `evals/evals.json`，用于 skill-creator 评估 skill 触发准确性和输出质量。

1. **在 `evals/evals.json` 的 `evals` 数组加新对象**，字段：
   - `id`：唯一整数
   - `name`：简短标识（kebab-case）
   - `prompt`：模拟用户输入
   - `expected_output`：期望产物的文字描述
   - `files`：测试文件路径数组（相对仓库根目录）
   - `assertions`：断言数组

2. **assertion 用可执行格式**（`type` + 对应字段），不用自然语言描述：
   ```json
   {
     "name": "markdown_has_page_markers",
     "type": "file_contains",
     "file": "Review - sample/extracted_content.md",
     "pattern": "[PAGE \\d+]"
   }
   ```
   支持的 type：`file_exists` / `file_contains` / `json_field_equals` / `json_field_not_empty` 等。

3. **正向 eval（应触发 skill）和负向 eval（不应触发）都要有**：
   - 正向：用户明确说"复习"/"知识点"/"考前"等，期望 skill 被触发
   - 负向：用户说"做 PPT"/"写 Word 报告"等，期望 skill **不**被触发，不创建 `Review -` 目录

4. **测试文件放 `test_data/`**，路径用相对引用（`test_data/sample.docx`），不用绝对路径。绝对路径（如 `E:/sk2/xxx.pdf`）不可移植，仅在 `_setup_notes` 里标注为环境特定。

## 代码规范

- **Python 3.10+**，用类型注解（`def f(x: list[str]) -> dict[str, Any]:`）
- **中文注释解释 WHY**：为什么这么设计、踩过什么坑、为什么不选另一种方案。不写 WHAT（代码已说明）。
- **函数 < 50 行，文件 < 500 行**。超了就拆。
- **不用 `|| true` 吞错误**（学 NovaForge 的反面教材）。失败要返回 `{"status": "error", "message": ...}` 让调用方决策，不要假装成功。
- **延迟 import 重依赖**：docling / markitdown / charset-normalizer 在函数内 import，避免模块加载时卡住。`controller.py` 和 `extractors.py` 都遵循此模式。
- **Windows 兼容**：stdout/stderr 强制 UTF-8（见 `controller.py` 开头的 `sys.stdout.reconfigure`），路径用 `pathlib.Path` 而非字符串拼接。
- **打印日志到 stderr**，stdout 留给机器可读输出（如子进程的 JSON 结果）。`[Controller]` / `[Extractors]` / `[Pipeline]` 前缀标识来源。

## PR 检查清单

提 PR 前自检：

- [ ] `pytest tests/ -v` 全通过
- [ ] 新功能有测试（happy path + 边界情况）
- [ ] `SKILL.md` 和 `references/` 同步更新（如涉及用户可见行为变化）
- [ ] `ARCHITECTURE.md` 同步更新（如涉及架构变化，如新增脚本/扩展点）
- [ ] 没引入不必要的新依赖
- [ ] 代码风格符合现有规范（中文注释 WHY、类型注解、函数 < 50 行）
- [ ] commit message 说明 why 而非 what
