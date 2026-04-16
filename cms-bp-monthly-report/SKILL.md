---
name: bp-monthly-report
description: >-
  BP个人月度汇报生成与发送工具。基于 BP 目标结构、衡量标准和当月汇报证据，
  按分步流程生成结构固定、证据可追溯的月报初稿。
  当用户需要生成、发送或预览个人BP月度汇报时使用。
---

# BP 个人月度汇报

为 BP 系统中的个人节点生成月度汇报。核心逻辑是**先拆证据、再做判断、最后组装报告**，而不是一步生成整篇。

详细参考：
- 报告模板（BP自查报告）：[references/report-template-bp-self-check.md](references/report-template-bp-self-check.md)
- 灯色判断标准：[references/traffic-light-rules.md](references/traffic-light-rules.md)
- 证据优先级规则：[references/evidence-rules.md](references/evidence-rules.md)

## 报告定位

月报最终输出为**一份 BP 自查报告**，面向员工本人阅读，以"每个 BP 目标"为主线底座，对照承诺逐条检查完成情况，在一个目标内串起"承诺对照、结果、举措、偏差问题与原因"。每个目标给灯色判断；最终给一句话自我结论（优秀/良好/合格/不足）。

## 核心业务概念

### 判断主轴

月报的灯色判断基本单位是**关键举措**，目标灯色从举措聚合得出。关键成果（KR）用于衡量标准参考和差距分析，但**不判灯**。

- **目标**：最终要达到的状态，定义"这条线在做什么"
- **关键成果**：对照衡量标准分析差距、输出判断理由，但不判灯色
- **衡量标准**：说明关键成果怎样算完成、怎样算偏离，是 KR 判断理由的参照系
- **关键举措**：灯色判断的基本单位，是证据抓手和灯色载体

一句话：灯色看"举措推进情况"，KR 只做差距分析输出理由。

### 灯色判断层级

- **排除规则**：基于 `planDateRange`（计划时间范围）与汇报月份的**区间交叉**判断。草稿直接排除；其余状态按计划区间是否与汇报月份有交集决定（`planStartDate <= 月末 AND planEndDate >= 月初`）。这确保回溯历史月份时也能正确判断。详见 [references/traffic-light-rules.md](references/traffic-light-rules.md) 排除规则章节。
- **逐目标判断（Step 3c）**：以目标为维度，逐个精读证据——对**参与自查**的关键举措判灯（含完整四灯判断块），对关键成果只做差距分析输出判断理由（不判灯）。
- **最终报告**：举措级嵌入四灯判断块；KR 级输出判断理由（不嵌入四灯判断块）；目标级灯色从该目标下所有参与自查的**举措**灯色聚合（有红则红，无红有黄则黄，全绿则绿，全黑则黑），每个目标嵌入目标级四灯判断块。
- 举措级和目标级的灯色判断点使用统一的**四灯判断块**格式（见 report-template-bp-self-check.md "四灯判断块标准模板"一节）。

### 灯规则版本



详见 [references/traffic-light-rules.md](references/traffic-light-rules.md) 。

### 证据引用编号

最终报告中引用汇报时使用 `R{序号}` 编号（如 `R201`、`R202`），不直接内联汇报正文或 reportId。编号在 Step 3b 证据台账中分配。

### 证据链接格式

正文中所有 R 编号引用均使用**汇报直链**格式，点击后直接打开对应汇报详情页：

```
[R301](huibao://view?id={reportId})
```

**不使用** `[R301](#R301)` 页内锚点链接（该格式在工作协同中无法跳转）。每个 R 编号对应的 reportId 在 Step 3b 证据台账中确定。

### 灯色 HTML 渲染

最终报告中所有灯色相关文字使用 HTML `<span>` 标签彩色加粗渲染：

| 灯色 | HTML 样式 |
|------|-----------|
| 🟢 | `<span style="color:#2e7d32; font-weight:700;">` |
| 🟡 | `<span style="color:#b26a00; font-weight:700;">` |
| 🔴 | `<span style="color:#c62828; font-weight:700;">` |
| ⚫ | `<span style="color:#212121; font-weight:700;">` |

## 生成流程

**禁止一步生成整篇报告。** 必须按以下步骤顺序执行。

### 第一步：确定目标员工与月份

用户需提供：
- **目标员工**：员工姓名、employeeId 或 groupId（个人分组 ID）
- **汇报月份**：格式 `YYYY-MM`，如 `2026-03`
- **灯规则版本**：`版本一`（默认）或 `版本二`

推荐输入协议：

```yaml
period_id: 1994002024299085826
groupId: 2029384010718834690
report_month: 2026-03
```

若用户只给了姓名，通过 `bp-data-viewer` 的 `search_group_by_name` 在个人分组中按名称匹配定位。若没有 `period_id`，用 `get_all_periods` 取 `status=1` 的启用周期。

### 第一步半：标记生成开始

确定 `groupId` 和月份后，**立即**调用 `update_report_status` 将月报状态标记为"生成中"：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py update_report_status \
  --group_id "{groupId}" \
  --month "{YYYY-MM}" \
  --status 0
```

该调用会在 BP 系统中创建或更新一条月报记录，状态为 `0=生成中`。后续流程中任何步骤失败，都必须调用 `update_report_status --status 2 --fail_reason "失败原因"` 记录失败。

### 第二步：采集 BP 数据（分 2a 当月 + 2b 上月）

#### Step 2a: 采集当月 BP 数据与汇报（按目标维度拆分）

数据采集分两步执行：先拉全局概览（轻量），再逐目标独立采集详情和汇报。每个目标产出一个独立 JSON 文件，后续 Step 3c 逐目标循环时每轮只读一个文件。

##### Step 2a-i: 采集全局概览

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py collect_monthly_overview \
  --group_id "{groupId}" \
  --month "2026-03" \
  --output "/tmp/monthly_overview_{groupId}.json"
```

该命令获取任务树并提取目标列表，输出轻量 JSON。

**输出 JSON 结构**：

| 字段 | 说明 |
|------|------|
| `taskTree` | 精简后的任务树（目标 → 关键成果 → 关键举措） |
| `goals` | 目标摘要列表，每条含 `goalId`、`name`、`fullLevelNumber`、`planDateRange`、`statusDesc` |
| `stats` | 统计信息：`totalGoals`（目标数）、`totalNodes`（总节点数） |

执行完成后，**Read** 此文件获取目标列表，确定有多少个目标需要逐个采集。

##### Step 2a-ii: 逐目标采集数据

读取 Step 2a-i 的 `goals` 列表，对每个目标独立采集：

```bash
# 对每个目标执行（goalId 从 goals 列表中取）
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py collect_goal_data \
  --group_id "{groupId}" \
  --goal_id "{goalId}" \
  --month "2026-03" \
  --output "/tmp/goal_data_{groupId}_{goalId}.json"
```

该命令在脚本内部自动完成：
1. 获取该目标的完整详情（含衡量标准、KR、举措、参与人）
2. 提取该目标下所有节点 ID（目标自身 + KR + 举措）
3. 对每个节点查询当月关联汇报列表
4. 拉取所有去重 reportId 的汇报**原文全文**（不截断）
5. 构建该目标内部的反向索引（reportId → taskId 列表）
6. 输出独立 JSON 文件

**输出 JSON 结构**：

| 字段 | 说明 |
|------|------|
| `goalId` | 目标 ID |
| `goalDetail` | 该目标的完整详情（含 KR 列表、举措列表、衡量标准等） |
| `uniqueReportMap` | reportId → 完整汇报内容的去重主表（**不截断**，保留原文全文） |
| `reportTaskMapping` | reportId → 关联的 taskId 列表（仅该目标范围内的反向索引） |
| `reports` | 按 taskId 分组的汇报引用 |
| `stats` | 统计信息：`nodeCount`、`uniqueReportCount`、`fetchedReportContents` |
| `errors` | 采集过程中的错误记录（如有） |

**汇报内容不截断**：汇报原文完整保存，由 AI 在 Step 3c 读取时按需总结（详见 Step 3c 的汇报摘要指引）。

##### 产出文件一览

```
/tmp/monthly_overview_{groupId}.json         -- 全局概览（Step 2a-i）
/tmp/goal_data_{groupId}_{goalId_1}.json     -- 目标1 数据（Step 2a-ii）
/tmp/goal_data_{groupId}_{goalId_2}.json     -- 目标2 数据（Step 2a-ii）
/tmp/goal_data_{groupId}_{goalId_3}.json     -- 目标3 数据（Step 2a-ii）
...
```

#### Step 2b: 采集上月汇报与评价（参考基线）

当月数据采集完成后，使用 `collect_previous_month_data` 采集上个月的汇报和评价作为参考：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py collect_previous_month_data \
  --group_id "{groupId}" \
  --month "2026-02" \
  --output "/tmp/prev_month_data_{groupId}.json"
```

该命令在脚本内部自动完成：
1. 调用 2.31 `listMonthlyReports` 获取上月所有月报的 `reportTypeDesc` + `reportRecordId`
2. 对每个 `reportRecordId`，通过工作协同接口拉取汇报正文
3. 调用 2.32 `getMonthlyEvaluation` 获取上月评价的翻译后 Markdown（自评 + 上级评价）
4. 将全部数据写入一个聚合 JSON 文件

**输出 JSON 结构**：

| 字段 | 说明 |
|------|------|
| `reports` | 上月各类型月报列表，每条含 `reportTypeDesc`、`reportRecordId`、`title`、`content` |
| `evaluations` | 上月评价 Markdown 列表，每条含 `evaluationTypeDesc`（自评/上级评价）和 `evaluationMarkdown` |
| `stats` | 统计信息：报告数、评价数 |
| `errors` | 采集过程中的错误记录（如有） |

**使用方式**：
- 上月报告正文作为本月汇报的纵向对比基线（上月做了什么 → 本月进展了什么）
- 上月评价 Markdown 中的评分和评语可用于本月灯色判断的辅助参考（上级评价要求、上月偏差是否已改善）
- 若上月数据为空（首月汇报），跳过此步骤，不影响后续流程

### 第三步：生成月报内容（分 4 个子步骤）

读取采集数据后，**必须按以下 4 个子步骤顺序执行**，不可跳步：3a → 3b → 3c → 3d。

核心设计：**全局的事情全局做（编号、去重），局部的事情局部做（判断、结论）**。Step 3c 以目标为维度逐个精读证据、判灯、组装章节，避免全量处理时证据"串台"。

#### Step 3a: 构建 BP 锚点图

从 `/tmp/monthly_overview_{groupId}.json` 读取任务树构建全局骨架，从各 `/tmp/goal_data_{groupId}_{goalId}.json` 的 `goalDetail` 中提取每个目标的详情。

对每个目标，提取：
- 目标名称、编号（fullLevelNumber）
- 上级组织 BP 对齐关系（upwardTaskList）
- 下属关键成果列表，每个关键成果提取：
  - 名称、编号
  - **衡量标准**（measureStandard，去除 HTML 标签）
  - 监督人、承接人
  - 计划时间范围（planDateRange）
  - 当前状态（statusDesc）
- 下属关键举措列表，每个举措提取：
  - 名称、编号
  - 计划时间范围（planDateRange）
  - 当前状态（statusDesc）

将此骨架写入 `/tmp/bp_anchor_{groupId}.md`，作为后续判断的锚点。

#### Step 3b: 构建证据台账（含 R 编号分配）

遍历所有 `/tmp/goal_data_{groupId}_{goalId}.json` 文件，汇总全局汇报数据。由于同一条汇报可能出现在多个目标文件中（关联到不同目标的节点），R 编号分配必须全局去重。

严格按 [references/evidence-rules.md](references/evidence-rules.md) 执行：

1. **按 reportId 全局去重**：从所有目标文件的 `uniqueReportMap` 中汇总，同一条汇报（相同 reportId）只算一次
2. **内容聚合**：内容高度相似的汇报（同一模板发给不同人）合并为一个工作事项，记录发送次数和对象列表
3. **证据分级**：
   - 本人手动汇报（type=manual，作者是承接人本人）→ 主证据
   - 他人手动汇报（type=manual，作者非本人）→ 辅证
   - AI 汇报（type=ai）→ 仅辅助摘要，不能单独作为强结论依据
4. **分配 R 编号**：对去重聚合后的每个独立工作事项，按顺序分配 `R{月份}{序号}` 编号。例如 3 月月报的第 1 条证据编号为 `R301`，第 2 条为 `R302`；1 月月报为 `R101`、`R102`。编号规则：
   - 月份取汇报月份的数字（1月=1，12月=12）
   - 序号从 01 开始连续递增
   - 每条编号附带汇报标题全文，格式：`R{编号}`《[汇报标题]》
   - **每条编号必须同时记录汇报链接**，格式：`huibao://view?id={reportId}`，其中 `{reportId}` 取自 `uniqueReportMap` 中该条汇报的原始 reportId（字符串原样，不做任何转换）。若一条工作事项由多条汇报聚合而成，取其中**第一条**的 reportId 生成链接
5. **分配 RP 编号**（上月参考引用）：从 Step 2b 采集的上月数据中，对每条上月汇报按顺序分配 `RP{序号}` 编号（`RP01`、`RP02`...）。编号规则：
   - 序号从 01 开始，按 `reports` 列表顺序递增
   - 每条 RP 编号记录 `reportTypeDesc`（类型描述）、汇报标题和 `reportRecordId`（用于生成 `huibao://view?id={reportRecordId}` 链接）
   - RP 编号仅用于基线引用和附录 A.3，**不参与**当月证据分级和灯色判断
   - 若 Step 2b 无数据（首月），不分配 RP 编号
6. **按节点归集**：利用 `reportTaskMapping` 确定每条汇报关联了哪些目标/关键成果/关键举措。一条汇报的内容如果明确涉及其他目标的关键词，应在对应节点的分析中交叉引用
7. **月份归集口径**：以汇报的 `createTime` 为准，不依赖关联时间或正文时间推断

将证据台账写入 `/tmp/evidence_ledger_{groupId}.md`，格式为：

```markdown
## 证据台账

### R 编号索引

| R 编号 | 汇报标题 | 证据级别 | 汇报链接 | 关联节点 |
|--------|---------|---------|---------|---------|
| R301 | 《[汇报标题]》 | 主证据 | [查看汇报](huibao://view?id=xxxxxxxxxxxxx) | 目标X / KRY |
| R302 | 《[汇报标题]》 | 辅证 | [查看汇报](huibao://view?id=xxxxxxxxxxxxx) | 举措Z |
| ... | ... | ... | ... | ... |

### 统计摘要
- 命中原始工作汇报：N 份
- 经批量通知归并后最终采纳：M 份
- 其中本人主证据：X 份、他人手动汇报：Y 份、AI 汇报：Z 份

### 按目标归集（逐 KR/举措明细）

#### 目标 [fullLevelNumber]: [目标名称]

**关键成果：**

| KR 编号 | KR 名称 | 关联 R 编号 | 证据级别分布 | 证据充分性 |
|---------|---------|------------|-------------|-----------|
| [fullLevelNumber] | [名称] | R301, R303 | 主证据×2 | 充分 |
| [fullLevelNumber] | [名称] | R302 | 辅证×1 | 仅辅证 |
| [fullLevelNumber] | [名称] | — | — | 无证据 |

**关键举措：**

| 举措编号 | 举措名称 | 关联 R 编号 | 证据级别分布 | 证据充分性 |
|---------|---------|------------|-------------|-----------|
| [fullLevelNumber] | [名称] | R301 | 主证据×1 | 充分 |
| [fullLevelNumber] | [名称] | — | — | 无证据 |

#### 目标 [fullLevelNumber]: [目标名称]
（同上结构）
```

**关键要求**：
- 证据台账是最终报告附录的**唯一数据源**。Step 3d 拼接附录时必须直接读取此文件，不得重新生成或凭记忆补写
- "按目标归集"部分是 Step 3c 逐目标处理的**输入索引**。每个目标循环开始时，先读取该目标对应的证据子集（R 编号 + 充分性），再从 `uniqueReportMap` 中读取对应汇报正文进行精读判断

#### Step 3c: 逐目标精读判断与章节组装

**核心原则**：以目标为维度，每次只聚焦一个目标的锚点和证据，在同一轮上下文中完成"精读证据 → 判灯 → 写章节"的完整闭环，避免全量处理时证据串台。

##### 预处理：目标级排除判断

在进入逐目标循环前，先对所有目标执行排除规则（详见 [references/traffic-light-rules.md](references/traffic-light-rules.md)）：
- 草稿目标直接排除
- 计划区间与汇报月份无交集的目标排除
- 目标参与自查但其下**所有** KR 和举措均被排除 → 该目标也排除

将被排除的目标记录到**全局跳过列表**（`/tmp/excluded_goals_{groupId}.md`）：

```markdown
## 本月不参与自查的节点

| 节点类型 | 名称 | 编号 | 计划时间范围 | 排除原因 |
|---------|------|------|-------------|---------|
| 目标 | [名称] | [编号] | [planDateRange] | 计划期未覆盖本月 / 草稿 |
| 关键成果 | [名称] | [编号] | [planDateRange] | 计划期未覆盖本月 / 草稿 |
| 关键举措 | [名称] | [编号] | [planDateRange] | 计划期未覆盖本月 / 草稿 |
```

##### 逐目标循环

对每个**参与自查的目标**，按以下 7 步闭环执行，产出一个独立的目标章节文件：

```
for 每个参与自查的目标 (goalIndex = 1, 2, 3, ...):
    (i)   读取输入
    (ii)  排除判断
    (iii) 逐 KR 精读分析（不判灯，只输出判断理由）
    (iv)  逐举措判灯
    (v)   聚合目标级灯色（从举措灯色聚合）
    (vi)  组装目标报告章节
    (vii) 写入文件
```

**(i) 读取该目标的输入**

每个目标的数据来源明确、互不干扰：
- **目标数据文件**：直接读取 `/tmp/goal_data_{groupId}_{goalId}.json`，包含该目标的完整详情（`goalDetail`）和所有关联汇报原文（`uniqueReportMap`）
- **锚点**（从 Step 3a）：该目标的名称、编号、衡量标准、KR/举措结构
- **证据子集**（从 Step 3b 的"按目标归集"）：该目标下每个 KR/举措关联的 R 编号和证据充分性
- **汇报正文**（从目标数据文件的 `uniqueReportMap`）：读取该目标关联的所有 R 编号对应的汇报原文内容。对超长汇报执行 AI 摘要（详见下方"汇报内容摘要指引"）

**(ii) 该目标下的 KR/举措排除判断**

按 traffic-light-rules.md 的排除规则，判断该目标下哪些 KR/举措参与自查、哪些排除。被排除的 KR/举措记录到该目标的跳过子列表。

**(iii) 逐 KR 精读分析**

对每个**参与自查的关键成果**，精读其关联的汇报正文，对照衡量标准，生成 KR 分析卡片。**KR 不判灯色**，只输出详细判断理由。

**关键成果卡**：

```markdown
### KR卡: [关键成果名称] ([编号])

- 衡量标准：[从 measureStandard 提取]
- 计划时间范围：[planDateRange]
- 本月主证据：[R编号列表]
- 本月辅证：[R编号列表]
- 距离衡量标准的差距：[基于证据判断]
- 判断理由：[详细分析该成果目前的完成情况、与衡量标准的差距、主要支撑和不足，供目标级结论参考]
```

**(iv) 逐举措精读判灯**

对每个**参与自查的关键举措**，精读其关联的汇报正文，评估对 KR 的支撑度，生成举措判断卡片。

**关键举措卡**：

```markdown
### Action卡: [举措名称] ([编号])

- 计划时间范围：[planDateRange]
- 当前状态：[statusDesc]
- 本月推进动作：[从证据提取，引用R编号]
- 对关键成果的支撑情况：[说明支撑了哪个 KR，强/中/弱]
- 灯色判断：[🟢/🟡/🔴/⚫]
- 判断依据：
```

**(v) 聚合目标级灯色**

从该目标下所有参与自查的**举措**卡片灯色聚合：有任一红灯则红；无红灯有黄灯则黄；全绿则绿；全黑灯则黑。

**(vi) 组装该目标的报告章节**

按 [references/report-template-bp-self-check.md](references/report-template-bp-self-check.md) 的目标明细结构，组装该目标的完整报告章节，包含以下 **4 个必需子章节**：

- **承诺与实际对照**：必须包含 `承诺口径` / `本月实际` / `差异点（若有）` / `证据` 四个字段，证据引用格式为 `[R编号](huibao://view?id={reportId})《汇报标题》`
- **关键成果达成与举措推进**：每个 KR 输出完整分析单元，必须包含 `衡量标准` / `本月结果` / `距离衡量标准` / `环比上月` / `证据` / `判断理由` 六个子字段（KR 不嵌入四灯判断块）；KR 下按「└ 支撑举措」层级展开，每个支撑举措必须包含 `推进动作摘要` / `对结果支撑【强/中/弱】` / `当前进度（含量化）` / `证据` / `嵌入举措级四灯判断块` 五个子字段。目标下若有部分被排除的 KR/举措，在该目标明细末尾一句话带过
- **偏差问题与原因分析**：若有偏差必须包含 `问题现象` / `影响` / `原因假设` / `当前应对` / `证据` 五个字段；若全绿则写"本目标本期无重大偏差"
- **目标级综合灯色结论**：`结论一句话：` + 嵌入四灯判断块

**(vii) 写入目标章节文件**

将判断卡片（作为内部过程记录）和报告章节一起写入 `/tmp/goal_section_{groupId}_{goalIndex}.md`，格式为：

```markdown
<!-- 内部判断过程（不搬入最终报告） -->
## 判断卡片

### KR卡: ...
（判断卡片内容）

### Action卡: ...
（判断卡片内容）

---
<!-- 以下为最终报告章节（搬入最终报告） -->
## 报告章节

##### [fullLevelNumber]｜[BP目标全称]

（完整的 4 个子章节内容）
```

##### 汇报内容摘要指引

由于 Step 2a-ii 采集的汇报保留了原文全文（不截断），AI 在读取每个目标的数据文件时，需要对超长汇报进行摘要处理：

**触发条件**：汇报原文（`content` 字段）超过 2000 字时执行摘要。

**摘要保留内容**：
- 关键数据和量化指标（如完成率、金额、人数等）
- 时间节点和里程碑进展
- 结论性表述和决策结果
- 与该目标衡量标准直接相关的内容
- 问题/风险/偏差的描述

**摘要去除内容**：
- HTML 标签和格式噪音
- 重复段落和冗余信息
- 无实质内容的客套话和模板化开场白
- 与当前目标无关的内容（若汇报跨多个目标，只保留与当前目标相关的部分）

**摘要输出**：用自然语言重写为精简版本，控制在 500-800 字以内，保留原文中的关键数据原样不改。摘要仅用于 AI 判断，不直接出现在最终报告正文中。

#### Step 3d: 报告拼接与合规性校验

所有目标章节文件生成完成后，执行最终拼接和校验。

##### (i) 聚合灯色统计

读取所有 `/tmp/goal_section_{groupId}_{goalIndex}.md` 文件，提取每个目标的灯色结论，统计绿/黄/红/黑灯数量。

##### (ii) 生成全局章节

按 [references/report-template-bp-self-check.md](references/report-template-bp-self-check.md) **逐字段严格对照**组装全局部分。**模板是最终报告的精确结构定义，当 SKILL 描述与模板有冲突时，以模板为准。**

1. **元数据头**：填入周期、员工姓名、基线引用（RP 编号超链接，若首月则写"首月，无基线"）、证据说明（含 R 和 RP 编号说明）、灯规则版本
2. **第 1 章 总体自查结论**：
   - **1.1 结论**：必须包含 `一句话优势：` 和 `一句话短板：` 两个带标签的行，不可写成一整段
   - **1.2 灯色分布概览**：使用 ` ```text ` 代码块，按目标级统计绿/黄/红/黑灯数量共 5 行。**被排除规则排除的目标不计入灯色统计**，单独注明"★ 未启动：[N] 个目标"
   - **1.3 本月最关键偏差点**：每条偏差必须包含 `偏差点` + `影响` + `原因假设` + `下月纠偏方向` 四个子字段（可选，最多 3 条；若无偏差可不写本节）
3. **第 2 章 目标级自查明细**：
   - **2.1 目标清单总览表**：必须 7 列（目标编号 / BP目标 / 本月承诺口径 / 本月实际 / 证据引用 / 目标灯色 / 结论一句话）。**所有目标均列入**，被排除的目标灯色用 `<span style="color:#2e7d32; font-weight:700;">★</span>`（绿色五角星）标记、结论写"未启动"、证据引用留空、承诺口径和本月实际写"—"
   - **2.2 目标明细**：从各 `/tmp/goal_section_{groupId}_{goalIndex}.md` 中提取"报告章节"部分，按目标顺序拼接（仅对参与自查的目标展开明细）
4. **第 3 章 年度结果预判评分**：**严格按模板输出，仅包含一个年度结果预判评分链接**，格式为 `[点击进入本月：年度结果预判评分](https://sg-al-cwork-web.mediportal.com.cn/BP-manager/web/dist/#/monthly-review/self?groupId={groupId}&month={month})`。**不得**在此章节添加自我定性、结论解释或任何额外文字
5. **附录：证据索引**：从 `/tmp/evidence_ledger_{groupId}.md` 直接读取 R 编号索引表原样搬入，包含 A.1 统计摘要 + A.2 证据索引表 + **A.3 上月参考索引**（RP 编号表 + 上月评价 Markdown 原文嵌入；若首月则写"首月汇报，无上月参考基线。"）

##### (iii) 语言清洗检查

见下方"语言清洗检查"规则。

##### (iv) 写入最终报告

写入 `/tmp/report_selfcheck_{groupId}.md`。

##### (v) 合规性校验（发送前必须执行）

对写入的报告文件逐项校验以下清单，**任一项不通过则回退修正后重新校验**，全部通过后方可进入发送流程：

| 序号 | 校验项             | 校验标准                                                                                                                       |
|----|-----------------|----------------------------------------------------------------------------------------------------------------------------|
| 2  | **1.0 灯判断块**    | 黄灯、红灯、黑灯判断块，必须严格按照[references/report-template-bp-self-check.md](references/report-template-bp-self-check.md) 四灯判断块标准模板结构输出 |
| 1  | **1.1 结论格式**    | 必须包含 `一句话优势：` 和 `一句话短板：` 两个带标签的独立行                                                                                         |
| 2  | **1.2 灯色分布格式**  | 必须使用 ` ```text ` 代码块，包含 🟢/🟡/🔴/⚫/★ 未启动 共 5 行                                                                             |
| 3  | **1.3 偏差点子字段**  | 每条偏差必须有 `偏差点` / `影响` / `原因假设` / `下月纠偏方向` 4 个子字段                                                                            |
| 4  | **2.1 总览表列数**   | 必须 7 列：目标编号 / BP目标 / 本月承诺口径 / 本月实际 / 证据引用 / 目标灯色 / 结论一句话。所有目标均列入，被排除目标用 ★ 标记、结论写"未启动"、证据引用留空                               |
| 5  | **目标明细 4 子章节**  | 每个参与自查的目标必须包含：承诺与实际对照 → 关键成果达成与举措推进 → 偏差问题与原因分析 → 目标级综合灯色结论                                                                |
| 6a | **KR 级完整分析单元**  | 每个参与自查的 KR 必须有 6 个子字段：衡量标准 / 本月结果 / 距离衡量标准 / 环比上月 / 证据 / 判断理由（KR 不嵌入四灯判断块）                                                 |
| 6b | **举措级层级结构**     | 每个举措必须有 5 个子字段：推进动作摘要 / 对结果支撑【强/中/弱】 / 当前进度（含量化：完成度百分比或里程碑阶段）/ 证据 / 举措级四灯判断块                                               |
| 7  | **证据引用带标题**     | 正文中 R 引用格式：`[R编号](huibao://...)《汇报标题》`，不可只写链接不带标题                                                                          |
| 8  | **四灯判断块行数**     | 绿灯 = 2 行；黄灯/红灯 = 8 行（含人工判断等占位）；黑灯 = 9 行（额外含类型建议）。仅适用于举措级和目标级，KR 级无四灯判断块                                                    |
| 9  | **第 3 章仅含链接**   | Section 3 严格按模板：仅输出一个年度结果预判评分链接，不得包含自我定性、结论解释或其他文字                                                                         |
| 10 | **附录 A.2 条数一致** | R 编号总数必须等于证据台账中的条数，不可多也不可少                                                                                                 |
| 11 | **语言清洗 5 条规则**  | 无技术字段泄漏、无空值直出、无模板括号注释、无系统流程说明、无 HTML 注释                                                                                    |
| 12 | **数据完整性**       | 各目标章节中的所有 R 编号、灯色判断、偏差字段是否完整搬入正文，不可遗漏                                                                                      |
| 13 | **编码完整性**       | 各个目标、成果、举措编码完整、正确                                                                                                          |

#### Step 4: 发送→保存

**校验通过后直接发送**，无需等待用户确认。

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py send_report \
  --receiver_emp_id "{employeeId}" \
  --title "{员工姓名} {YYYY年M月} BP自查报告" \
  --content_file "/tmp/report_selfcheck_{groupId}.md"
```

> `--sender_id` 无需手动指定。脚本会自动通过第一个接收人的 empId 查询组织架构获取 corpId，匹配对应企业的 AI 助理（400001/400002/400003）。仅在需要覆盖时才传 `--sender_id`。

记录返回的 `data.id` → 记为 `report_record_id`，生成报告链接：`huibao://view?id={report_record_id}`

##### 保存到 BP 系统

发送成功后，保存到 BP 系统：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py save_monthly_report \
  --group_id "{groupId}" \
  --month "{YYYY-MM}" \
  --content_file "/tmp/report_selfcheck_{groupId}.md" \
  --report_record_id "{report_record_id}"
```

##### 状态说明

`save_monthly_report` 接口默认将 `generateStatus` 设为 `1=成功`，因此保存成功即代表整个流程完成，**无需再单独调用 `update_report_status --status 1`**。

**失败处理**：若上述任何步骤失败（数据采集、报告生成、发送、保存），必须立即更新状态为"失败"并记录原因：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py update_report_status \
  --group_id "{groupId}" \
  --month "{YYYY-MM}" \
  --status 2 \
  --fail_reason "具体失败原因描述"
```

##### 语言清洗检查（报告组装完成后、写入文件前必须执行）

对全文逐段扫描，确认以下五条规则全部通过后才能写入文件：

1. **禁止技术字段泄漏**：正文中不得出现 API 原始字段名，包括但不限于：
   `reportId`、`authorEmpId`、`createTime`、`taskId`、`groupId`、`employeeId`、`type=manual`、`type=ai`、`contentHtml`、`planDateRange`、`statusDesc`、`measureStandard`、`fullLevelNumber`、`upwardTaskList`、`reportTaskMapping`。
   如需表达相关含义，必须改用自然语言。

2. **句式自然化**：所有描述采用"主语 + 谓语 + 宾语"的自然句式。以下表述**严禁出现**：
   - ~~"XX 为空"~~ → "本月尚未收到相关汇报"
   - ~~"数据不完整"~~ → "当前可获取的信息有限，建议补充"
   - ~~"举证原数据不完整"~~ → "本月关联的工作汇报内容较少，尚不足以全面评估"
   - ~~"本月最关键的进展为空"~~ → "本月暂无可明确标注的关键进展，建议关注 XX 方向"
   - ~~"无关联汇报"~~ → "本月该事项下暂未收到工作汇报"

3. **禁止空值直出**：空字段必须改写为有引导意义的自然语句。

4. **禁止模板括号注释泄漏**：最终报告是直接发送给员工阅读的，章节标题中的括号说明文字一律不得出现在最终报告中。以下为必须清洗的映射表：
   - ~~`（目标主线）`~~ → 标题中不加此后缀
   - ~~`（先给结论，再给依据）`~~ → 删除
   - ~~`（四档）`~~ → 删除
   - ~~`（目标级）`~~ → 删除
   - ~~`（可选，最多 3 条）`~~ → 删除
   - ~~`（本报告主体，按目标动态生成）`~~ → 删除
   - ~~`（承诺 vs 实际，表格）`~~ → 删除
   - ~~`（逐目标展开：承诺对照 + 结果 + 举措 + 偏差问题）`~~ → 删除
   - ~~`（可验收口径）`~~ → 删除
   - ~~`（按成果层级展开）`~~ → 删除
   - ~~`（若无偏差写"本目标本期无重大偏差"）`~~ → 删除
   - ~~`（必填）`~~ → 删除
   - ~~`（必须输出）`~~ → 删除
   - ~~`（两句以内）`~~ → 删除
   - 通用规则：**任何以中文括号 `（）` 包裹的、用于指导 AI 生成行为的说明文字**，一律不输出

5. **禁止系统流程说明泄漏**：以下内容不得出现在最终报告中：
   - "以下自 Step 3b 证据台账原样搬入"或类似提及内部步骤编号（Step 3a/3b/3c/3d 等）的文字
   - "字段与台账一致；R 列已加页内锚点"等内部实现说明（含任何提及"页内锚点"的文字）
   - "约束：本章小节数量必须随…"等以"约束："开头的系统提示
   - "AI 指引："开头的任何文字
   - 任何 `<!-- ... -->` HTML 注释标签及其内容

##### 附录搬运规则

- 报告的证据索引附录必须从 `/tmp/evidence_ledger_{groupId}.md` **直接读取并原样搬入**
- 若台账文件不存在或为空，必须回退重新执行对应步骤，**不得跳过或伪造**

## 工具脚本

### bp-data-viewer（数据底座，已有）

所有 BP 数据查询通过 `bp-data-viewer` 的 `bp_api.py` 执行，详见 [bp-data-viewer SKILL.md](../bp-data-viewer/SKILL.md)。

### monthly_report_api.py（本 Skill 新增）

工作协同侧的汇报操作脚本，从工作区根目录执行：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py <action> [options]
```

| action | 说明 | 必填参数 | 可选参数 |
|--------|------|----------|----------|
| `collect_monthly_overview` | 采集全局概览：任务树 + 目标列表 + 统计（Step 2a-i） | `--group_id`、`--month` | `--output` |
| `collect_goal_data` | 按目标采集详情 + 汇报原文，不截断（Step 2a-ii） | `--goal_id`、`--month` | `--group_id`、`--output` |
| `collect_monthly_data` | [旧版] 一次性采集全量数据到单个 JSON，向后兼容 | `--group_id`、`--month` | `--output` |
| `collect_previous_month_data` | 采集上月汇报+评价（类型+正文+评价Markdown），作为本月参考基线 | `--group_id`、`--month`（上月YYYY-MM） | `--output` |
| `get_report_content` | 获取单条汇报正文内容 | `--report_id` | 无 |
| `send_report` | 发送报告（工作协同） | `--receiver_emp_id`、`--title`、`--content_file` | `--sender_id` |
| `save_monthly_report` | 保存月报到 BP 系统 | `--group_id`、`--month`、`--content_file`、`--report_record_id` | 无 |
| `update_report_status` | 更新月报生成状态（0=生成中, 1=成功, 2=失败） | `--group_id`、`--month`、`--status` | `--fail_reason`（status=2 时必填） |

## 批量生成

遍历全公司员工生成月报：

1. `get_all_periods` → 获取启用周期
2. `get_group_tree --only_personal` → 获取所有个人分组
3. 遍历每个个人分组，对每人执行：`collect_monthly_overview` → `collect_goal_data` × N → 分步生成报告 → 发送 → 保存到 BP 系统

**注意**：批量生成前必须征得用户明确同意，并告知预计耗时。

## 重要约束

### 通用约束

- 所有 ID 参数保持字符串原样传递，**严禁 parseInt 或 Number 转换**
- **严禁测试发送**：`send_report` 接口会将内容真实推送给员工，**绝对不允许**用测试数据、占位内容或 debug 用途调用此接口。只有在报告内容已完整生成且 Step 3d 合规性校验全部通过的情况下，才能调用 `send_report`。任何"试一下接口通不通"的行为都是禁止的
- **校验通过后直接发送**：报告必须走完"逐目标组装 → 拼接 → 合规性校验（Step 3d）→ 发送 → 保存"完整周期。校验通过后**不再**等待用户确认，直接发送
- **禁止一步生成整篇报告**，必须走 3a → 3b → 3c（逐目标循环）→ 3d（拼接+校验）四步
- 灯色文字使用 HTML `<span>` 彩色加粗渲染
- 灯色判断必须严格按 [references/traffic-light-rules.md](references/traffic-light-rules.md) 标准（注意灯规则版本）
- 证据处理必须严格按 [references/evidence-rules.md](references/evidence-rules.md) 标准
- 汇报计数以 reportId 去重后为准，内容相似的批量发送按一个工作事项计算
- 月份归集以汇报的 `createTime` 为准，不依赖关联时间

### 发送与保存约束

- **发送报错重试机制**：以下两种错误脚本会自动等待 60 秒后重试一次（API 按分钟限流）：
  - **"汇报人ID有误"**：先检查 appKey 是否与 sender 匹配，确认 key 正确后等待 60 秒再重试
  - **resultCode=401 且参数正确**：视为接口限流，等待 60 秒后重试
- 发送后必须记录 `data.id` 并生成 `huibao://view?id={data.id}` 链接
- **发送人和 appKey 根据接收人的企业自动匹配**（corpId → sender + appKey 映射）：
  - `1509805893730611201` → sender=`400001`，appKey=`5xmsXv311OVq121d5hzb5yGJ6sO5AB04`
  - `1509805893730611202` → sender=`400002`，appKey=`1xmsXv2yv11OVqkd3zb5yG441sO5AB04`
  - `1515978849561276500` → sender=`400003`，appKey=`5xmsXvVyv11dskd5hzb5ys6ssswqAB04`
  - 若多个接收人则以第一个接收人的企业为准，匹配失败时回退到默认 `400002`。汇报接收人是员工本人（`employeeId`），**不是** `groupId`
- **查询数据**使用用户提供的 key（`BP_OPEN_API_APP_KEY`），**发送汇报**使用与 sender 对应的机器人 key（已内置，自动匹配）

### 报告（BP自查报告）约束

- 目标数量必须与实际 BP 目标数量一致，**不可写死**
- **排除规则**：基于 `planDateRange` 区间交叉判断——草稿直接排除，其余按计划区间是否与汇报月份有交集决定。被排除的目标不生成明细章节、不计入灯色统计，在 2.1 总览表中用 ★ 标记为"未启动"
- 灯色判断到**举措级**和**目标级**：每个参与自查的举措嵌入举措级四灯判断块，目标级灯色从举措灯色聚合得出；KR 级不判灯，只输出详细判断理由
- 每个参与自查的目标嵌入目标级四灯判断块
- 报告以"目标"为底座组织内容，不把"目标/结果/举措/问题"拆成独立章节分别看
- 目标清单总览表展示所有目标（含被排除目标），被排除目标用绿色五角星 ★ 标记、结论写"未启动"、不填证据引用

### 证据引用约束

- 正文中**当月**证据引用使用 `[R编号](huibao://view?id={reportId})` 格式，点击直接打开对应汇报详情页
- 正文中**上月参考**引用使用 `[RP编号](huibao://view?id={reportRecordId})` 格式，RP 编号仅出现在元数据头基线行和附录 A.3
- `R` 编号（当月证据）和 `RP` 编号（上月参考）使用不同前缀，**严禁混用**
- **不使用** `[R编号](#R编号)` 页内锚点链接（在工作协同中无法跳转）
- 附录证据索引表中 R 编号直接展示文本（不需要 `<span id>` 锚点标签），汇报链接列保持 `[查看汇报](huibao://view?id={reportId})` 格式
- 汇报链接 reportId 从 `uniqueReportMap` 原样取用，reportRecordId 从 `collect_previous_month_data` 输出原样取用，**严禁伪造或编造**
- 附录 A.1 + A.2 必须从证据台账文件（`/tmp/evidence_ledger_{groupId}.md`）**直接读取并原样搬入**，确保条数完全一致
- 附录 A.3 从 Step 2b 采集的上月数据生成，若首月则整节替换为"首月汇报，无上月参考基线。"
- 附件读取为待接入能力，**不可伪造**

## 环境配置

复用 `bp-data-viewer` 的环境变量：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BP_OPEN_API_APP_KEY` | 数据查询用 API 密钥（**必填**） | 无（用户提供） |
| `BP_OPEN_API_BASE_URL` | API 地址 | `https://sg-al-cwork-web.mediportal.com.cn/open-api` |

> 发送汇报的机器人 appKey 已按 sender（400001/400002/400003）内置在脚本中，根据接收人企业自动匹配，无需配置。

## 错误处理

- BP 数据获取失败时，提示用户检查 `BP_OPEN_API_APP_KEY` 配置
- 报告发送失败时，保留报告文件，提示用户可手动重试
- **"汇报人ID有误"或 401 限流**：脚本自动检查 key 并等待 60 秒后重试一次；若重试仍失败，保留报告内容并提示用户排查
- 某个目标下无汇报数据时，在报告中标注"本月暂未收到工作汇报"并按灯色规则判断，不中断整体流程
