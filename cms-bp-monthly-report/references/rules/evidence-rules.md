# 证据优先级规则

> **MANDATORY RULES**
> 本文件中的所有规则为强制约束。
> 违反任何一条规则将导致报告验证失败。

本文件定义月报生成过程中，如何对汇报数据进行去重、分级、归集，以及证据链接的生成和引用格式。

## 脚本 vs AI 职责分工

| 规则项 | 执行者 | 阶段 |
|--------|--------|------|
| reportId 去重 | **脚本** (`build_goal_evidence`) | Phase 3.5 |
| 证据分级（主证据/辅证） | **脚本** (`build_goal_evidence`) | Phase 3.5 |
| R 编号分配 | **脚本** (`build_goal_evidence`) | Phase 3.5 |
| RP 编号分配 | **脚本** (`build_evidence_ledger`) | Phase 8 |
| 按节点归集 | **脚本** (`build_goal_evidence`) | Phase 3.5 |
| 内容聚合（相似汇报合并） | **AI** | Phase 5/10 中酌情处理 |
| 证据充分性评估 | **脚本**初判 + **AI**复核 | Phase 3.5 / Phase 5 |
| 汇报链接生成 | **脚本** | Phase 3.5 |

## 一、去重规则

### 1. reportId 去重

同一条汇报（相同 reportId）可能关联到多个 BP 节点。在统计"汇报数量"时，以 reportId 为唯一键，**同一条汇报只计一次**。

> **脚本自动处理**：`build_goal_evidence` 在目标维度内去重，`build_evidence_ledger` 在全局合并时再次去重。

### 2. 内容聚合

内容高度相似的汇报（如同一模板发给不同人、同一事项的批量发送），合并为**一个独立工作事项**。

**兜底规则**：若无法确定是否为同一事项，默认**不合并**（宁可多不可少）。

> **AI 在 Phase 5/10 中处理**：结合 progressMarkdown 中的汇报内容判断是否为同一事项。

### 3. 月报中的汇报计数

月报附录 A.1 统计摘要应体现两层口径 + 分级：
- 经 reportId 去重后最终采纳的条数
- 其中按证据级别分：本人主证据 X 份、他人关联辅证 Y 份

> **脚本自动计算**：`build_goal_evidence` 和 `build_evidence_ledger` 自动统计。

## 二、证据分级

按以下优先级从高到低排列。高优先级证据的判断权重高于低优先级。

### 第一优先级：本人手动汇报（主证据）

**定义**：承接人本人主动撰写并提交的汇报。

**识别方式**：汇报作者（authorId，从 Markdown 提取）与当前员工的 employeeId 一致。

> **脚本自动判断**：`build_goal_evidence --employee_id` 参数用于此判断。

### 第二优先级：他人关联汇报（辅证）

**定义**：其他人的汇报被关联到了当前员工的 BP 节点。

**识别方式**：汇报作者（authorId）与当前员工的 employeeId 不一致。

## 三、归集规则

### 1. 月份归集口径

以汇报的**发出时间**为准。脚本通过 `getReportProgressMarkdown` 的 `month` 参数按月过滤。

### 2. 节点归集

每个 KR/举措独立调用 `getReportProgressMarkdown`，返回的 Markdown 即为该节点关联的汇报。

**交叉引用**：脚本在 `goal_evidence.md` 中自动按节点归集，AI 在判灯时引用对应 R 编号。

## 四、特殊情况处理

### 作者信息缺失

若 Markdown 中未提取到 authorId：
- 默认将该汇报视为"本人汇报"
- 在证据台账中标注"作者信息缺失，默认归为本人"

### 汇报内容为空

若 progressMarkdown 为空或仅有标题无实质内容 → 该举措标记黑灯。

> **脚本自动处理**：`collect_goal_progress` 中的 `_judge_black_lamp` 函数。

## 五、证据链接与附录输出

### 1. 汇报链接生成

每条证据在分配 R 编号的同时，必须生成对应的汇报查看链接：

- **格式**：`huibao://view?id={reportId}`
- **reportId 来源**：从 `getReportProgressMarkdown` 返回的 Markdown 中正则提取，字符串原样使用，**严禁做任何数值转换**

> **脚本自动生成**：`build_goal_evidence` 自动提取 reportId 并生成链接。

### 2. 正文证据引用格式

正文中所有证据引用使用**汇报直链**格式。**正文只展示编号，不附带书名号标题**：

- **当月证据（R 编号）**：`[R0301](huibao://view?id={reportId})`
- **上月参考（RP 编号）**：`[RP01](huibao://view?id={reportRecordId})`
- **R 和 RP 编号使用不同前缀，严禁混用**

### 3. 附录证据索引格式

- R 编号列直接展示文本（如 `R0301`）
- 汇报链接列保持 `[查看汇报](huibao://view?id={reportId})` 格式
- **严禁伪造或编造**

### 4. 证据台账作为附录唯一数据源

`build_evidence_ledger` 生成的 `evidence_ledger.md` 是报告附录的**唯一数据源**：

- 拼接报告附录时，`assemble_report` 脚本直接读取此文件并原样搬入
- 若台账文件不存在或为空，必须回退重新执行对应步骤，**不得跳过或伪造**
