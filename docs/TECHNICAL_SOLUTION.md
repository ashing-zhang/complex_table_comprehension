# 复杂表格视觉理解与问答系统——AI Coding 技术方案

## 1. 文档定位

本文档用于指导基于 `SPEC.md` 完成“复杂表格识别、结构恢复、内容提取、内容推理及 Excel 结果提交”项目的 AI Coding。

本方案严格以 `SPEC.md` 中定义的题型、输入输出格式、评分规则和模型来源约束为基础；对于 SPEC 未明确规定的工程实现细节，本文采用“可替换、可测试、可观测”的工程化设计给出实现建议。

SPEC 明确要求系统处理图片/PDF 中的复杂表格，包括跨页表格、合并单元格、多级表头、弱边框、页眉页脚干扰、脚注、旋转扫描、单位变化和字段继承等情况；最终任务分为 `structure`、`extract`、`thinking` 三类，并统一生成 `submission.xlsx`。 

---

## 2. SPEC 核心约束

### 2.1 输入

系统接收：

```text
files/
  ├── xxx.pdf
  ├── xxx.png
  └── ...

tests.xlsx
```

`tests.xlsx` 每行至少包含：

| 字段 | 必填 | 用途 |
|---|---:|---|
| `id` | 是 | 题目唯一 ID |
| `file_name` | 是 | 对应图片/PDF |
| `question_type` | 是 | `structure` / `extract` / `thinking` |
| `question` | 是 | 自然语言问题 |
| `table_hint` | 否 | 目标表格提示 |
| `answer_format` | 否 | 输出格式约束 |

### 2.2 输出

最终输出：

```text
submission.xlsx
```

至少包含：

| id | answer |
|---|---|
| 题目 ID | 最终答案 |

每道题一行，不允许删除或重复 `id`。

### 2.3 三种任务

#### structure

恢复：

- `row_count`
- `col_count`
- 单元格文本
- 单元格 `row`
- 单元格 `col`
- `rowspan`
- `colspan`

答案必须是合法 JSON。

#### extract

从表格中定位：

- 单元格
- 行
- 列
- 区域

单值直接输出；多值使用 JSON 数组。

#### thinking

先定位数据，再执行：

- 加总
- 求差
- 比例/增长率
- 条件筛选
- 排序
- 最大/最小值
- 金额、数量、百分比、日期归一化

---

## 3. 总体技术路线

建议不要直接采用：

```text
PDF -> OCR -> LLM -> answer
```

而采用：

```text
tests.xlsx
    │
    ▼
Question Loader
    │
    ▼
Task Router
    │
    ├───────────────┐
    ▼               ▼
Document Resolver   Question Analyzer
    │               │
    ▼               ▼
PDF/Image Loader -> Page Selector
    │
    ▼
Document Preprocessor
    │
    ▼
Table Candidate Detection
    │
    ▼
Table Region / Page Crop
    │
    ▼
Multimodal Qwen
    │
    ▼
Canonical Table Representation
    │
    ├──────────────┬──────────────┐
    ▼              ▼              ▼
Structure Solver  Extract Solver  Thinking Solver
    │              │              │
    └──────────────┴──────────────┘
                   │
                   ▼
              Answer Validator
                   │
                   ▼
              Answer Formatter
                   │
                   ▼
              Submission Writer
                   │
                   ▼
             submission.xlsx
```

核心设计思想：

> **让多模态模型负责“视觉理解与语义理解”，让确定性程序负责“结构约束、计算、格式校验和最终提交”。**

不要让 LLM 单独承担所有工作。

---

# 4. 推荐项目目录

```text
table_agent/
├── README.md
├── SPEC.md
├── TECHNICAL_SOLUTION.md
├── pyproject.toml
├── .env.example
├── configs/
│   ├── default.yaml
│   ├── model.yaml
│   └── prompts.yaml
│
├── data/
│   ├── files/
│   ├── tests.xlsx
│   ├── output/
│   └── debug/
│
├── src/
│   ├── main.py
│   │
│   ├── config/
│   │   ├── settings.py
│   │   └── schemas.py
│   │
│   ├── io/
│   │   ├── question_loader.py
│   │   ├── document_loader.py
│   │   └── submission_writer.py
│   │
│   ├── document/
│   │   ├── pdf_renderer.py
│   │   ├── image_preprocessor.py
│   │   ├── page_selector.py
│   │   └── table_detector.py
│   │
│   ├── vision/
│   │   ├── qwen_client.py
│   │   ├── vision_parser.py
│   │   └── table_parser.py
│   │
│   ├── table/
│   │   ├── models.py
│   │   ├── grid.py
│   │   ├── merge_resolver.py
│   │   ├── header_resolver.py
│   │   └── normalizer.py
│   │
│   ├── task/
│   │   ├── base.py
│   │   ├── structure.py
│   │   ├── extract.py
│   │   └── thinking.py
│   │
│   ├── reasoning/
│   │   ├── question_parser.py
│   │   ├── semantic_locator.py
│   │   ├── calculator.py
│   │   └── value_normalizer.py
│   │
│   ├── validation/
│   │   ├── schema_validator.py
│   │   ├── table_validator.py
│   │   ├── answer_validator.py
│   │   └── consistency.py
│   │
│   ├── prompts/
│   │   ├── structure_prompt.py
│   │   ├── extract_prompt.py
│   │   ├── thinking_prompt.py
│   │   └── repair_prompt.py
│   │
│   ├── pipeline/
│   │   ├── runner.py
│   │   ├── task_pipeline.py
│   │   └── retry.py
│   │
│   └── observability/
│       ├── logger.py
│       ├── trace.py
│       └── metrics.py
│
└── tests/
    ├── unit/
    ├── integration/
    ├── fixtures/
    └── golden/
```

---

# 5. 核心数据模型

不要让不同模块之间直接传递自由文本。

系统内部应该定义统一的 Canonical Table Representation（CTR）。

## 5.1 Cell

```python
@dataclass
class Cell:
    text: str
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = None
```

其中：

- `row` / `col` 使用 0-based
- `rowspan` 表示纵向覆盖范围
- `colspan` 表示横向覆盖范围
- `bbox` 保存视觉位置
- `confidence` 保存识别置信度

## 5.2 Table

```python
@dataclass
class Table:
    row_count: int
    col_count: int
    cells: list[Cell]
    page_indices: list[int]
    bbox: tuple[float, float, float, float] | None = None
```

## 5.3 Question

```python
@dataclass
class Question:
    id: str
    file_name: str
    question_type: Literal["structure", "extract", "thinking"]
    question: str
    table_hint: str | None
    answer_format: str | None
```

## 5.4 TaskResult

```python
@dataclass
class TaskResult:
    id: str
    answer: str
    confidence: float | None
    evidence: list[str]
    warnings: list[str]
```

---

# 6. 第一阶段：读取题目清单

## 6.1 Question Loader

实现：

```python
questions = load_questions("data/tests.xlsx")
```

要求：

1. 使用 pandas/openpyxl 读取 Excel。
2. 校验必填字段。
3. 校验 `question_type`。
4. 校验 `id` 唯一。
5. 校验 `file_name` 是否存在。
6. 缺失文件不能直接让整个程序崩溃。
7. 对非法题目记录 error 并进入结果处理流程。

## 6.2 ID 原样保留

不要：

```python
int(question_id)
```

建议统一：

```python
str(question_id)
```

避免 Excel 自动类型转换造成 ID 不一致。

---

# 7. 第二阶段：文档加载与预处理

## 7.1 PDF

PDF 必须先转换为页面图像。

建议内部统一：

```python
Document
    -> Page[]
    -> Image
```

这样 PDF 和 PNG/JPG 可以进入完全相同的视觉处理流程。

## 7.2 图片预处理

建议支持：

```text
原图
 │
 ├── resize
 ├── grayscale
 ├── contrast enhancement
 ├── denoise
 ├── deskew
 └── crop
```

但是：

> 预处理不能覆盖原图。

至少保留：

```text
original_image
processed_image
```

因为复杂表格中的浅色文字、弱边框、印章和脚注可能在增强过程中丢失。

---

# 8. 第三阶段：页面定位

不能把整个 PDF 无脑发送给模型。

推荐：

```text
Question
   │
   ▼
Page Selector
   │
   ├── 显式页码
   ├── 文件名
   ├── table_hint
   └── 关键词
   │
   ▼
Candidate Pages
```

## 8.1 页码明确

例如：

```text
请恢复 file_001.pdf 中第 3 页到第 4 页……
```

直接优先处理第 3、4 页。

## 8.2 没有页码

利用：

- `table_hint`
- question 中的关键词
- OCR 文本
- 页面视觉特征

得到：

```python
candidate_pages = [
    PageCandidate(page=3, score=0.91),
    PageCandidate(page=4, score=0.84),
]
```

## 8.3 不要过早过滤

页选择属于召回阶段。

宁可：

```text
top-k pages
```

再由后续模块精定位，也不要只保留一个页面。

---

# 9. 第四阶段：表格候选检测

复杂表格的主要问题不是“有没有表格”，而是：

> **题目需要回答的表格究竟是哪一个。**

因此建议分为：

```text
Page
 │
 ▼
Table Candidate Detection
 │
 ├── Table A
 ├── Table B
 └── Table C
 │
 ▼
Question-Table Matching
 │
 ▼
Target Table
```

## 9.1 候选信息

```python
@dataclass
class TableCandidate:
    page_index: int
    bbox: tuple
    title: str | None
    text_preview: str
    score: float
```

## 9.2 匹配信号

综合：

```text
question
table_hint
table title
表头
表格正文关键词
页面位置
视觉相似度
```

形成：

```text
table_score =
    semantic_score
    + hint_score
    + keyword_score
    + visual_score
```

具体权重应通过验证集调参，而不是写死在代码中。

---

# 10. 第五阶段：多模态 Qwen 表格理解

SPEC 明确要求模型和工具来源于阿里云云端产品，大模型必须使用阿里云“千问”系列模型。方案因此必须将模型调用封装在独立的 `QwenClient` 中，禁止业务代码直接依赖具体 SDK。 

## 10.1 接口

```python
class QwenClient(Protocol):

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.0,
        response_format: str | None = None,
    ) -> str:
        ...
```

## 10.2 不要让模型直接生成最终 Excel

模型只负责生成中间结果：

```text
Image
 +
Question
 +
Task Instruction
      │
      ▼
Structured JSON
```

然后程序负责：

```text
JSON
 ↓
schema validation
 ↓
logical validation
 ↓
normalization
 ↓
answer formatting
 ↓
Excel
```

---

# 11. Structure Solver

## 11.1 Prompt 目标

模型需要识别：

```json
{
  "row_count": 4,
  "col_count": 3,
  "cells": [
    {
      "text": "项目",
      "row": 0,
      "col": 0,
      "rowspan": 2,
      "colspan": 1
    }
  ]
}
```

## 11.2 关键约束

Prompt 必须明确：

1. 行列从 0 开始。
2. 每个真实单元格只输出一次。
3. 合并单元格只输出左上角。
4. `rowspan` / `colspan` 必须表示真实覆盖范围。
5. `row_count` / `col_count` 是完整逻辑表格尺寸。
6. 局部恢复时只输出要求范围内的 cells。
7. 不能因为视觉空白就随意增加单元格。

## 11.3 两阶段结构恢复

建议：

```text
Stage A:
视觉识别
    ↓
候选 cell + bbox + text

Stage B:
结构推理
    ↓
row/col/grid/merge
```

不要要求一次调用同时完成所有事情。

---

# 12. Table Grid Resolver

LLM 输出后必须由程序重新构建逻辑网格。

例如：

```text
row_count = 4
col_count = 3
```

构造：

```python
grid = [[None for _ in range(3)] for _ in range(4)]
```

对于：

```json
{
  "row": 0,
  "col": 1,
  "rowspan": 1,
  "colspan": 2
}
```

占用：

```text
(0,1)
(0,2)
```

## 12.1 必须检测冲突

例如两个 cell 同时占据：

```text
(1, 2)
```

则结构非法。

validator 必须拒绝。

---

# 13. Extract Solver

内容提取任务不应该直接让模型回答。

推荐：

```text
Question
   │
   ▼
Semantic Locator
   │
   ▼
Target Row / Column / Cell
   │
   ▼
Canonical Table
   │
   ▼
Value Extractor
```

例如：

```text
“请提取 2025 年各个月的销售总额”
```

先解析：

```json
{
  "target": "sales_total",
  "row_filter": null,
  "column_filter": {
    "year": "2025"
  },
  "output": "monthly"
}
```

然后在表格结构中定位。

---

# 14. 多级表头处理

这是整个项目最重要的模块之一。

例如：

```text
          销售额
     ┌─────────────┐
     2025          2026
   ┌──────┐      ┌──────┐
   1月 2月        1月 2月
```

不能只保存：

```text
1月
2月
```

应该生成逻辑列路径：

```text
销售额 > 2025 > 1月
销售额 > 2025 > 2月
销售额 > 2026 > 1月
销售额 > 2026 > 2月
```

推荐：

```python
ColumnPath = list[str]
```

例如：

```python
[
    ["销售额", "2025", "1月"],
    ["销售额", "2025", "2月"],
]
```

这样 extract/thinking 都可以基于语义路径进行定位。

---

# 15. 字段继承

复杂表格经常出现：

```text
类别 | 地区 | 销售额
     | 华东 | 100
     | 华南 | 200
```

视觉上空白的单元格不一定代表缺失。

可能表示：

```text
类别 = 某类别
```

因此增加：

```python
HeaderResolver
```

负责推断：

```text
显式字段
+
合并单元格
+
上下文继承
```

但是：

> 字段继承只能作为“候选语义”，必须保留来源和置信度，不能无条件覆盖原始数据。

---

# 16. Thinking Solver

Thinking 题建议采用：

```text
Question
   │
   ▼
Question Parser
   │
   ▼
Data Locator
   │
   ▼
Typed Values
   │
   ▼
Deterministic Calculator
   │
   ▼
Answer
```

不要：

```text
LLM:
“125000 + 138000 = 263000”
```

而应：

```python
calculator.add([125000, 138000])
```

让 Python 完成计算。

---

# 17. 数值类型系统

建议不要把所有内容都当字符串。

定义：

```python
class ValueType(Enum):
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    PERCENT = "percent"
    DATE = "date"
    MONEY = "money"
    QUANTITY = "quantity"
```

例如：

```text
125,000
```

内部：

```python
Decimal("125000")
```

而：

```text
12.5%
```

内部：

```python
Decimal("0.125")
```

最终输出再根据题目要求格式化。

---

# 18. Thinking 计算器

统一实现：

```python
add()
subtract()
multiply()
divide()
ratio()
growth_rate()
filter()
sort()
argmax()
argmin()
```

## 18.1 为什么必须确定性计算

LLM 适合：

- 理解题意
- 找数据
- 判断字段关系

不适合承担：

- 大量数字计算
- 精确小数处理
- 排序
- 格式归一

因此：

```text
LLM = semantic reasoning
Python = deterministic computation
```

---

# 19. 单位处理

表格可能存在：

```text
金额（万元）
金额（元）
数量（吨）
数量（千吨）
```

建立：

```python
UnitValue(
    value=Decimal("125"),
    unit="万元"
)
```

如果需要计算：

```text
125 万元
+
30 万元
```

直接计算。

如果：

```text
125 万元
+
300000 元
```

先归一单位。

---

# 20. Answer Validator

最终答案必须经过 validator。

建议分成三层。

## 20.1 Schema Validator

检查 JSON 是否满足：

```text
合法 JSON
字段存在
字段类型正确
```

## 20.2 Structural Validator

检查：

```text
row_count > 0
col_count > 0
row >= 0
col >= 0
rowspan >= 1
colspan >= 1
```

并检测 cell overlap。

## 20.3 Semantic Validator

例如：

```text
row + rowspan <= row_count
col + colspan <= col_count
```

对于 structure：

```text
每个 cell 必须落在合法 grid 中
```

对于 extract：

```text
目标字段必须来自 table evidence
```

对于 thinking：

```text
计算输入必须存在于表格 evidence
```

---

# 21. LLM Repair Loop

如果模型输出非法 JSON：

```text
LLM Output
   │
   ▼
JSON Parse
   │
   ├── success -> continue
   │
   └── failure
          │
          ▼
      Repair Prompt
          │
          ▼
        Qwen
```

最多：

```text
REPAIR_MAX_RETRIES = 2
```

不要无限重试。

---

# 22. Self-Consistency / Verification

对于高风险任务建议增加 verifier。

```text
Primary Solver
      │
      ▼
Candidate Answer
      │
      ▼
Verifier
      │
      ├── PASS -> answer
      │
      └── FAIL -> retry / second extraction
```

Verifier 不需要重新解决整个问题。

它只检查：

```text
答案是否来自正确表格
答案是否符合题目
数字计算是否正确
JSON 是否合法
格式是否正确
```

---

# 23. Prompt 设计

建议所有 Prompt 版本化。

例如：

```text
prompts/
├── structure_v1
├── structure_v2
├── extract_v1
├── thinking_v1
└── repair_v1
```

不要把 Prompt 散落在 Python 代码中。

---

# 24. Structure Prompt 模板

核心内容建议：

```text
你是复杂表格结构恢复模型。

任务：
根据输入表格图像恢复逻辑表格结构。

要求：
1. row/col 从 0 开始。
2. 每个真实单元格只输出一次。
3. 横向合并使用 colspan。
4. 纵向合并使用 rowspan。
5. 被合并覆盖的位置不要输出。
6. row_count 和 col_count 表示完整逻辑表格。
7. 如果题目要求局部结构，只输出指定范围内的 cells。
8. 不要添加图像中不存在的文本。
9. 不要输出解释性文字。

只输出合法 JSON。
```

---

# 25. Extract Prompt 模板

核心原则：

```text
先定位：
文件 -> 页面 -> 表格 -> 表头 -> 行/列 -> 单元格

再输出答案。

禁止根据常识补全表格不存在的数据。
```

要求模型返回 evidence：

```json
{
  "evidence": [
    {
      "row": 3,
      "col": 5,
      "text": "138000"
    }
  ],
  "answer": "138000"
}
```

最终用户答案由程序从结构化结果中生成。

---

# 26. Thinking Prompt 模板

模型只负责生成计算计划：

```json
{
  "operation": "sum",
  "inputs": [
    {
      "row": 3,
      "col": 4
    },
    {
      "row": 4,
      "col": 4
    }
  ],
  "output_format": "integer"
}
```

Python 执行：

```python
result = calculator.execute(plan, table)
```

这样可以显著降低幻觉计算。

---

# 27. Agent / Pipeline 设计

不建议实现一个“大而全”的 ReAct Agent。

这个任务更适合：

```text
Orchestrator
    │
    ├── Document Agent
    ├── Table Agent
    ├── Structure Agent
    ├── Extraction Agent
    ├── Reasoning Agent
    └── Validation Agent
```

但这些 Agent 应该是受控工作流节点，而不是无限自主循环。

---

# 28. 推荐 Orchestrator

```python
async def solve(question: Question) -> TaskResult:

    document = document_loader.load(question.file_name)

    pages = page_selector.select(
        document=document,
        question=question,
    )

    tables = table_detector.detect(
        pages=pages,
        hint=question.table_hint,
    )

    target_table = table_matcher.select(
        question=question,
        tables=tables,
    )

    canonical_table = table_parser.parse(
        target_table,
    )

    if question.question_type == "structure":
        result = structure_solver.solve(
            question,
            canonical_table,
        )

    elif question.question_type == "extract":
        result = extract_solver.solve(
            question,
            canonical_table,
        )

    elif question.question_type == "thinking":
        result = thinking_solver.solve(
            question,
            canonical_table,
        )

    result = answer_validator.validate(
        question,
        result,
        canonical_table,
    )

    return result
```

---

# 29. 为什么需要 Canonical Table Representation

如果 structure / extract / thinking 各自直接调用视觉模型：

```text
structure -> image -> LLM
extract   -> image -> LLM
thinking  -> image -> LLM
```

会产生：

- 重复视觉理解
- 重复 token 成本
- 不同任务之间结果不一致
- 难以 debug

更合理：

```text
image
  ↓
canonical table
  ↓
structure/extract/thinking
```

一次视觉理解，多任务复用。

---

# 30. 跨页表格

SPEC 明确存在跨页表格。

因此：

```text
Page 1
Page 2
Page 3
```

不能简单视为三个独立表格。

需要：

```text
Page Table A
Page Table A continuation
Page Table A continuation
        │
        ▼
CrossPageTableMerger
```

## 30.1 判断续表

信号：

- 表头重复
- 列数一致
- 列标题相似
- 页面相邻
- 表格位置连续
- 内容语义连续

## 30.2 合并策略

优先保留：

```text
global row index
```

例如：

```text
page 1: rows 0-20
page 2: rows 21-45
```

而不是重新从 0 开始。

---

# 31. 旋转扫描

对于旋转页面：

```text
orientation detector
       │
       ├── 0°
       ├── 90°
       ├── 180°
       └── 270°
```

自动选择方向后再进入 OCR/视觉模型。

但必须保存：

```python
rotation_angle
```

避免 bbox 坐标系统错乱。

---

# 32. 弱边框表格

不能依赖：

```text
horizontal line
vertical line
```

判断表格结构。

应该综合：

```text
文本排列
x/y 坐标
文字对齐
间距
字体
视觉区域
表头语义
```

因此 `table_parser` 应设计为视觉+语义混合解析器。

---

# 33. 页眉页脚和脚注

文档中可能存在：

```text
公司名称
报表名称
页码
日期
脚注
单位
```

必须区分：

```text
document metadata
table metadata
table content
footnote
```

不要简单把页面 OCR 全部塞给模型。

建议保留：

```python
PageRegion(
    type="header/footer/table/footnote/body"
)
```

---

# 34. Evidence-first 设计

所有答案都应该能追溯到 evidence。

例如：

```json
{
  "answer": "138000",
  "evidence": [
    {
      "page": 3,
      "bbox": [100, 200, 300, 240],
      "row": 5,
      "col": 2,
      "text": "138000"
    }
  ]
}
```

最终 `submission.xlsx` 不需要 evidence。

但 debug 文件必须保留。

---

# 35. Debug 数据

每道题建议保存：

```text
debug/
  <id>/
    question.json
    page_candidates.json
    table_candidates.json
    cropped_table.png
    raw_qwen_response.json
    canonical_table.json
    reasoning_plan.json
    validation.json
    final_answer.json
```

这样出现错题时可以回答：

```text
错在：
1. 页面召回
2. 表格定位
3. OCR/视觉识别
4. 结构恢复
5. 语义定位
6. 计算
7. 格式化
```

---

# 36. 可观测性

至少记录：

```text
question_id
file_name
question_type
page_count
candidate_page_count
selected_page
candidate_table_count
selected_table
model_name
model_latency
input_tokens
output_tokens
retry_count
validation_status
final_answer
```

如果 API 返回成本信息，也记录：

```text
estimated_cost
```

---

# 37. 错误分类

建立统一错误枚举：

```python
class ErrorCode(Enum):
    FILE_NOT_FOUND = "file_not_found"
    INVALID_EXCEL = "invalid_excel"
    PDF_PARSE_ERROR = "pdf_parse_error"
    IMAGE_ERROR = "image_error"
    PAGE_NOT_FOUND = "page_not_found"
    TABLE_NOT_FOUND = "table_not_found"
    MODEL_ERROR = "model_error"
    INVALID_JSON = "invalid_json"
    STRUCTURE_INVALID = "structure_invalid"
    VALUE_NOT_FOUND = "value_not_found"
    CALCULATION_ERROR = "calculation_error"
    FORMAT_ERROR = "format_error"
```

---

# 38. 失败处理策略

不要因为单道题失败导致整个批次失败。

推荐：

```text
Question 1 -> success
Question 2 -> success
Question 3 -> failure
Question 4 -> success
```

最终：

```text
Question 3
answer = ""
```

这符合 SPEC 对无法作答题目的规定。

---

# 39. Submission Writer

最终：

```python
rows = [
    {
        "id": q.id,
        "answer": result.answer,
    }
]
```

使用 pandas/openpyxl 写：

```text
submission.xlsx
```

必须在写出之前执行：

```text
ID 完整性检查
ID 唯一性检查
行数检查
answer 存在性检查
JSON 合法性检查
```

---

# 40. Submission Preflight

提交前必须自动执行：

```text
[1] tests.xlsx question count
        ↓
[2] submission row count
        ↓
[3] ID set equality
        ↓
[4] duplicate ID check
        ↓
[5] empty answer statistics
        ↓
[6] structure JSON validation
        ↓
[7] JSON answer schema validation
        ↓
[8] final Excel readable check
```

如果失败：

```text
禁止生成最终 submission
```

---

# 41. 评分导向的优化

SPEC 的最终得分：

```text
正确题数 / 总题数 × 100
```

因此优化目标不是：

```text
平均答案质量
```

而是：

```text
maximize(correct_questions)
```

这意味着：

1. 必须优先提高整个 pipeline 的稳定性。
2. 不能只追求少数复杂题的极致效果。
3. 失败题必须尽量隔离。
4. 必须自动验证提交文件。
5. 对不同题型分别统计 accuracy。

---

# 42. 内部 Evaluation

建议建立：

```text
evaluation/
├── structure_eval.py
├── extract_eval.py
├── thinking_eval.py
└── report.py
```

至少统计：

```text
overall_accuracy
structure_accuracy
extract_accuracy
thinking_accuracy
```

进一步统计：

```text
single_page_accuracy
cross_page_accuracy
merged_cell_accuracy
multi_header_accuracy
rotated_accuracy
weak_border_accuracy
numeric_reasoning_accuracy
```

这些细分指标用于定位系统瓶颈。

---

# 43. Golden Dataset

不要一开始就对整个数据集运行。

先准备：

```text
tests/fixtures/
```

包含：

```text
simple_structure
merged_header
multi_level_header
cross_page
weak_border
rotation
numeric_reasoning
multiple_tables
```

每个 fixture 都保存：

```text
input
expected
```

---

# 44. 单元测试重点

## 44.1 Grid

测试：

```text
rowspan
colspan
overlap
out-of-bound
```

## 44.2 Header

测试：

```text
multi-level header
merged header
empty inherited cell
```

## 44.3 Calculator

测试：

```text
整数
Decimal
百分比
增长率
单位换算
排序
最大/最小值
```

## 44.4 Answer Formatter

测试：

```text
structure JSON
single value
array
empty string
date
money
percentage
```

---

# 45. Integration Test

至少覆盖：

```text
tests.xlsx
    ↓
Question Loader
    ↓
Document Loader
    ↓
Vision
    ↓
Table Parser
    ↓
Task Solver
    ↓
Validator
    ↓
submission.xlsx
```

并验证最终 Excel 内容。

---

# 46. AI Coding 实施顺序

不要一次性让 AI Coding 生成整个项目。

推荐严格分阶段。

## Phase 1：基础骨架

实现：

```text
config
question_loader
document_loader
submission_writer
schemas
logging
```

目标：

```text
tests.xlsx -> 空 submission.xlsx
```

---

## Phase 2：文档处理

实现：

```text
PDF renderer
image loader
image preprocessing
page selector
```

目标：

```text
PDF -> Page images
```

---

## Phase 3：Qwen Client

只实现：

```text
QwenClient
```

要求：

- timeout
- retry
- rate limit
- structured output
- logging
- exception handling

不要把 SDK 调用散落到业务代码。

---

## Phase 4：Structure Pipeline

优先实现：

```text
image
 -> Qwen
 -> JSON
 -> grid validation
 -> structure answer
```

因为 structure 最能验证视觉表格解析能力。

---

## Phase 5：Extract Pipeline

复用：

```text
Canonical Table
```

实现：

```text
Question Parser
Semantic Locator
Value Extractor
```

---

## Phase 6：Thinking Pipeline

加入：

```text
reasoning plan
calculator
unit normalization
```

---

## Phase 7：Cross-page

实现：

```text
CrossPageTableMerger
```

---

## Phase 8：Validation

实现完整：

```text
Schema Validator
Table Validator
Answer Validator
Submission Preflight
```

---

## Phase 9：Evaluation

建立：

```text
golden tests
offline evaluation
error analysis
```

---

## Phase 10：性能优化

最后才做：

```text
parallel processing
cache
batching
image compression
candidate pruning
prompt compression
```

---

# 47. 推荐缓存体系

视觉任务成本高，应加入缓存。

建议：

```text
cache/
├── document/
├── page/
├── table/
├── qwen/
└── answer/
```

Cache key：

```text
sha256(
    file_content
    +
    question
    +
    model
    +
    prompt_version
)
```

Prompt 修改后自动失效。

---

# 48. 并发控制

不要直接：

```python
asyncio.gather(*all_questions)
```

可能造成 API 限流。

使用：

```python
Semaphore(MAX_CONCURRENCY)
```

并根据实际 API 限额调节。

推荐配置：

```yaml
concurrency:
  max_workers: 4
  qwen_concurrency: 2
```

具体值必须通过实际服务限制确定。

---

# 49. Retry Policy

只对临时错误 retry：

```text
timeout
429
temporary server error
```

不要对：

```text
invalid question
file not found
invalid JSON schema
```

无限 retry。

建议：

```text
attempt 1
   ↓
exponential backoff
   ↓
attempt 2
   ↓
exponential backoff
   ↓
attempt 3
```

---

# 50. 模型调用策略

建议将模型能力分成：

```text
Vision Understanding
Question Understanding
Table Reasoning
Verification
```

实际是否使用不同 Qwen 模型/服务，由配置决定。

例如：

```yaml
models:
  vision: "<Qwen vision model>"
  reasoning: "<Qwen model>"
  verifier: "<Qwen model>"
```

不要把模型名称硬编码到业务逻辑中。

---

# 51. 配置示例

```yaml
project:
  name: table-agent

data:
  tests: data/tests.xlsx
  files: data/files
  output: data/output/submission.xlsx

model:
  provider: aliyun
  vision_model: "<Qwen model>"
  reasoning_model: "<Qwen model>"
  temperature: 0

pipeline:
  max_retries: 2
  enable_verifier: true
  enable_cache: true

concurrency:
  max_workers: 4
  qwen_concurrency: 2

debug:
  save_intermediate: true
  save_images: true
```

注意：具体模型名称和云端产品应根据比赛实际可用的阿里云服务进行配置，不应在代码中假设某个未经赛事确认的具体型号。

---

# 52. 安全与合规

SPEC 明确要求模型和工具来源于阿里云云端产品，大模型必须使用阿里云“千问”系列，不得使用非阿里云来源的大模型、第三方闭源模型或本地私有模型完成答题。

因此项目中应：

1. 禁止接入 OpenAI 等非允许模型作为正式答题模型。
2. 禁止本地私有模型作为正式答题模型。
3. 将 provider 限制在配置层。
4. 记录每次模型调用的 provider/model。
5. 最终运行前检查 provider 是否符合比赛要求。

---

# 53. 不推荐的架构

## 53.1 一个 Prompt 解决全部问题

```text
PDF -> 巨型 Prompt -> 最终答案
```

问题：

- 难 debug
- 难验证
- 数值计算容易出错
- 结构和语义耦合
- 成本高

---

## 53.2 纯 OCR

```text
PDF -> OCR -> Text -> LLM
```

问题：

复杂表格真正需要的是：

```text
2D spatial structure
+
cell relationship
+
merged cells
+
multi-level headers
```

纯 OCR 很容易丢失这些信息。

---

## 53.3 纯视觉模型

```text
Image -> VLM -> final answer
```

问题：

模型可能视觉识别正确，但：

```text
计算错误
格式错误
JSON 错误
```

所以必须引入确定性后处理。

---

# 54. 最终推荐架构

最终建议形成：

```text
                 ┌──────────────────┐
                 │     tests.xlsx   │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │ Question Loader  │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │    Orchestrator  │
                 └────────┬─────────┘
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
      ┌──────────────┐          ┌───────────────┐
      │Document      │          │Question       │
      │Pipeline      │          │Analyzer       │
      └──────┬───────┘          └───────┬───────┘
             │                          │
             └────────────┬─────────────┘
                          ▼
                 ┌──────────────────┐
                 │ Table Candidate  │
                 │ Detection        │
                 └────────┬─────────┘
                          ▼
                 ┌──────────────────┐
                 │ Qwen Vision      │
                 └────────┬─────────┘
                          ▼
                 ┌──────────────────┐
                 │ Canonical Table  │
                 │ Representation   │
                 └────────┬─────────┘
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
        Structure      Extract      Thinking
          Solver        Solver        Solver
             │            │            │
             └────────────┼────────────┘
                          ▼
                 ┌──────────────────┐
                 │ Deterministic    │
                 │ Validator        │
                 └────────┬─────────┘
                          ▼
                 ┌──────────────────┐
                 │ Answer Formatter │
                 └────────┬─────────┘
                          ▼
                 ┌──────────────────┐
                 │ submission.xlsx  │
                 └──────────────────┘
```

---

# 55. AI Coding 总提示词

建议把下面的 Prompt 作为 Cursor / Claude Code / Codex 类 Coding Agent 的项目级指导原则：

```text
你正在实现一个复杂表格视觉理解与问答系统。

必须严格遵守 SPEC.md。

实现原则：

1. 不修改 SPEC 中定义的输入输出格式。
2. 不改变 structure / extract / thinking 三类任务的语义。
3. 所有模块必须通过明确的数据模型通信。
4. 禁止让业务代码直接调用 Qwen SDK，统一通过 QwenClient。
5. 禁止让 LLM 直接生成最终 submission.xlsx。
6. LLM 负责视觉理解、语义理解和推理计划。
7. Python 负责确定性计算、结构验证、格式验证和 Excel 输出。
8. structure 必须经过 grid validation。
9. extract 必须保存 evidence。
10. thinking 必须保存计算输入和 reasoning plan。
11. 所有模型输出必须经过 schema validation。
12. 非法输出允许有限次数 repair，但禁止无限循环。
13. 每道题失败不能影响其他题。
14. 必须支持 debug 中间产物保存。
15. 所有模型调用必须记录 model/provider/prompt version。
16. 必须使用阿里云允许范围内的 Qwen 模型和云端工具。
17. 不得引入未经允许的第三方大模型作为正式答题模型。
18. 优先保证正确率和稳定性，而不是代码复杂度。
19. 新增功能必须补充 unit test 或 integration test。
20. 不要为了“看起来更智能”而增加没有验证依据的 Agent loop。

开发顺序：

Phase 1: project skeleton
Phase 2: Excel/document loader
Phase 3: PDF/image preprocessing
Phase 4: Qwen client
Phase 5: structure solver
Phase 6: canonical table
Phase 7: extract solver
Phase 8: thinking solver
Phase 9: validator
Phase 10: submission writer
Phase 11: evaluation
Phase 12: performance optimization

每完成一个 Phase：
1. 运行测试；
2. 检查类型；
3. 检查日志；
4. 检查失败恢复；
5. 再进入下一阶段。

不要一次生成整个项目。
```

---

# 56. MVP 验收标准

第一版不要追求所有复杂情况。

MVP 必须先做到：

```text
✓ 能读取 tests.xlsx
✓ 能读取 PDF / PNG
✓ 能调用合规 Qwen
✓ 能定位简单表格
✓ 能恢复简单 structure
✓ 能回答简单 extract
✓ 能完成简单 thinking
✓ 能生成合法 submission.xlsx
✓ ID 完整且不重复
✓ structure JSON 合法
✓ 数值计算由 Python 完成
✓ 单题失败不影响全局
```

完成后再逐步增加：

```text
→ 多级表头
→ 合并单元格
→ 跨页
→ 旋转
→ 弱边框
→ 字段继承
→ 多表格
→ 复杂 reasoning
```

---

# 57. 最重要的工程原则

整个项目最核心的设计不是“使用一个更强的 VLM”，而是：

```text
视觉模型
    ↓
结构化中间表示
    ↓
确定性程序
    ↓
最终答案
```

即：

> **把“看懂表格”和“保证答案正确”拆开。**

对于 `structure`，重点是：

```text
视觉识别 + Grid Constraint
```

对于 `extract`，重点是：

```text
Semantic Retrieval + Evidence
```

对于 `thinking`，重点是：

```text
Semantic Retrieval + Deterministic Computation
```

最终形成：

```text
Qwen
  = perception + semantic reasoning

Python
  = structure constraint + calculation + validation + formatting

Pipeline
  = orchestration + retry + observability
```

这比单纯构建一个“大模型 Agent”更适合本赛题的自动评分目标。

---

# 58. 第一版开发完成后的执行命令

建议最终提供：

```bash
# 安装
pip install -e .

# 单元测试
pytest tests/unit -q

# 集成测试
pytest tests/integration -q

# 小规模运行 (CONFIG 切换场景; 也可改用 scripts/debug_smoke.sh)
CONFIG=configs/smoke.yaml python -m src.main

# 全量运行 (默认 yaml, 等价于 scripts/run_full.sh)
python -m src.main

# 提交前检查
CONFIG=configs/validate.yaml python -m src.main

# 一次性覆盖个别参数 (env var 优先级 > yaml)
LIMIT=20 OUTPUT=data/output/x.xlsx python -m src.main
```

---

# 59. 最终交付物

项目完成后至少应包含：

```text
SPEC.md
TECHNICAL_SOLUTION.md
README.md

src/
tests/

configs/

data/
  tests.xlsx
  files/
  output/
  debug/
```

以及：

```text
submission.xlsx
```

最终运行日志应能够回答：

```text
每道题用了哪个文件？
定位到了哪一页？
选择了哪个表格？
Qwen 输出了什么？
Canonical Table 是什么？
最终答案是什么？
验证是否通过？
是否发生 retry？
```

这套可追溯链路是后续提升比赛正确率最重要的基础设施。
