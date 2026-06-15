# Common Failure Modes（防偷懒清单）

> 本文档列出 LLM 在执行 exam-review-helper 时最常见的偷懒/失败模式。
> 宿主应在本 skill 触发后、Pass 1 开始前**通读本文档**，确保不踩这些坑。

---

## 一、必拒（命中即 REJECTED）

以下任何一条命中，Pass 4 Verifier 必须返回 `REJECTED`：

1. **Page gap**：segmentation map 未覆盖 `[1, total_pages]`
2. **单章 concepts < 10（章级）**：合并后某 chapter 的 concepts 不足 10 个
3. **单章 pitfalls < 3**：易错点不足 3 个
4. **> 30% concepts 无 related_to**：概念孤立、未建立关联
5. **任何 concept/formula/pitfall 缺 page 字段**
6. **公式缺失**：原文明显有公式但 draft 未提取
7. **style 不一致**：部分章节用 bullet、部分用 prose
8. **公式 latex 含 unicode 数学符号**（√ ≤ ≥ ∈ ⊂ ∪ ∩ ∀ ∃ → ⇒ ∞ ∂ × ⋅ ∘ α β γ θ λ π ∑ ∫ 等）—— 必须改写为 LaTeX 命令
9. **公式 latex 含 unicode 希腊字母**（α-ω、Α-Ω）—— 必须改写为 `\alpha` 等
10. **核心概念（importance="核心"）缺 `boundary` 或 `variation` 字段** —— 必须补全
11. **易错点泛泛**（warning 是"注意定义域"、"注意符号"这种废话，没有具体计算错误）—— 必须改写
12. **后半本书 silent drop**：后 30% 页面未出现在任何 segment

---

## 二、Common Failure Modes（18 种常见失败）

| # | 失败模式 | 应对 |
|---|---|---|
| 1 | 一把梭哈：不分段直接提取 | 强制走 Pass 1 分段 |
| 2 | 把全文塞进单次对话 | 必须分段或派发子代理 |
| 3 | 复制原文当 definition | 提炼，不复制 |
| 4 | "详见教材第 X 页" 当 definition | 必须给实际内容 |
| 5 | related_to 为空数组 | 至少 1 个 |
| 6 | 把 page 写成 "约 20" 或 null | 必须整数 |
| 7 | importance 全标"核心" | 必须有分级 |
| 8 | 漏掉公式 | 公式是理工科重点 |
| 9 | LaTeX 用 $E=mc^2$ 而非 `\Sigma` | 用标准 LaTeX 命令 |
| 10 | 把章节当 chapter（粒度过粗） | 按实际章节边界 |
| 11 | 把每页当 chapter（粒度过细） | 合并相邻小段 |
| 12 | 在主对话里"自检" | 必须派发 fresh verifier |
| 13 | verifier 复用 reader 上下文 | fresh context 是硬约束 |
| 14 | REJECTED 后只改小问题 | 必须针对每个 issue fix |
| 15 | 3 次仍 REJECTED 静默降级 | 强制 APPROVED_WITH_NOTES + 警告用户 |
| 16 | 用截图代替 LaTeX 图 | 用 LaTeX/MathJax 绘制 |
| 17 | "本段无公式"——除非真的没有 | 检查原文是否有公式 |
| 18 | 后半本书质量明显下降 | 这是长上下文偷懒，必须分段深读 |

---

## 三、Red Flags（命中即停）

以下信号出现时，**立即停止当前 pass，回退重做**：

- 🚨 Pass 1 输出的 segments 数 = 1（一本书切成一段）
- 🚨 Pass 1 输出的 segments 数 > 50（粒度过细）
- 🚨 Pass 2 某段返回 concepts = 0 或 1
- 🚨 Pass 3 合并后 chapters 数 = 0
- 🚨 Pass 4 verifier 在主对话里完成（没派发子代理）
- 🚨 Pass 5 循环次数 = 0（verifier 永远 APPROVED，可疑）
- 🚨 最终 HTML 打不开 / MathJax 未渲染
- 🚨 输出 JSON 解析失败

---

## 四、Rationalization Table（借口 vs 真相）

LLM 在偷懒时常用的合理化说辞，逐条戳穿：

| 借口 | 真相 |
|---|---|
| "我可以一次性总结整本 PDF" | 长文档必须分段，否则后段覆盖会漂移 |
| "section-level 页码够了" | 这是查找型任务，point-level 页码才有用 |
| "英文术语太明显，不用括注" | 双语标注是交付物，不是装饰 |
| "cheat sheet 必须密集排版" | 这里 cheat sheet = 简洁，不是难读 |
| "文字够了，图可以省" | 某些概念必须有图才讲得清 |
| "用截图代替 LaTeX 图也行" | 优先用可复现的 LaTeX/MathJax |
| "只要最终公式对了就行" | 例题模式和解题技巧同样重要 |
| "用户只说'总结一下'，对话回复够了" | skill 触发后必须产出文件，除非用户明说不要 |
| "我心里有草稿了，可以报告完成" | 草稿必须落盘成 JSON |
| "可以先跳过 xelatex 直接报完成" | 完成要求实际产物存在 |
| "把文件放源 PDF 旁边更简单" | 所有产物必须集中在 `Review - <stem>/` |
| "临时 txt 放 PDF 旁边没事" | 临时文件也算产物，必须在输出目录内 |
| "应该加载 dispatching-parallel-agents skill 帮忙" | 不要加载其他 skill，本 skill 自带调度规则 |
| "PDF 编译成功 = 任务完成" | 编译成功不等于覆盖率和可读性达标 |

---

## 五、自检 Checklist（Pass 4 Verifier 必用）

Pass 4 verifier 子代理必须逐项核查：

### 覆盖率
- [ ] segmentation map 覆盖 `[1, total_pages]` 全部页
- [ ] 每个 segment 都在 chapters 中有体现
- [ ] 公式密集段（如积分、级数）的公式没漏

### 页码
- [ ] 随机抽 5-10 条 concept / formula，对照原文确认 page 真实
- [ ] 无 "约 X" / "X 页附近" / null 之类的模糊页码
- [ ] page 字段是整数

### 内容
- [ ] concept definition 是实际内容，不是"详见..."
- [ ] formula 是标准 LaTeX 命令
- [ ] pitfalls 基于概念特点合理推断，不是凭空捏造

### Style
- [ ] 所有 chapter 用同一风格（bullet 或 prose，不混用）
- [ ] importance 分级一致（核心/重要/了解）
- [ ] definition 长度一致（10-200 字）

### 关联
- [ ] related_to 至少 1 个，理想 2-3 个
- [ ] connections 至少 3 条跨章关联
- [ ] 核心概念（importance="核心"）有 variation 字段

---

## 六、防"自我合理化"原则

LLM 最大的失败模式不是技术错误，而是**自我合理化**——给自己的偷懒找借口。

防御策略：
1. **Verifier 必须 fresh context**——自己核查自己必然走过场
2. **量化标准**（concepts ≥ 10（章级）而非"足够多"）——避免主观判断。注意段级（Pass 2 单段）阈值是 5，章级（Pass 3/4 合并后）阈值是 10
3. **Red Flag 即停**——不要尝试"再优化一下"，回退重做
4. **Common Failure Modes 清单化**——把已知失败模式列出来对照

如果发现自己有如下想法，**立即停下**：
- "这一段内容不多，少提取几个概念也行"
- "后半本书用户可能不看，质量差点没事"
- "verifier 我自己跑一下就行，不用派子代理"
- "用户没说要英文术语，可以不括注"
- "这个公式太复杂，简化成中文描述就行"

这些都是偷懒信号。**回退到 SKILL.md 重读硬约束**。
