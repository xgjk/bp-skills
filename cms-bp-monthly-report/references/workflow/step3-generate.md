# Step 3: 生成月报内容

> 本文件为强制约束。AI 执行 Step 3 的所有子步骤时必须严格遵守。

---

## Step 3a: 构建 BP 锚点图

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

---

## Step 3b: 构建证据台账（含 R 编号分配）

遍历所有 `/tmp/goal_data_{groupId}_{goalId}.json` 文件的 `reportIndex` 字段，汇总全局汇报数据。R 编号分配必须全局去重。

> **数据来源说明**：`reportIndex` 是轻量索引，每条汇报包含标题、作者、时间、前 300 字预览（`contentPreview`）、字符数（`charCount`）和关联节点列表（`relatedNodes`，标注了具体关联的 KR/举措名称和编号）。汇报全文不在此文件中，需要精读时在 Step 3c 通过 `get_report_text` 按需加载。

**严格按 [evidence-rules.md](../rules/evidence-rules.md) 执行**以下全部操作：

1. **按 reportId 全局去重**：从所有目标文件的 `reportIndex` 中汇总，同一条汇报只算一次
2. **内容聚合**：标题相同且同一天发送的汇报，根据 `contentPreview`（前 300 字预览）判断是否描述同一事项，若是则合并为一个工作事项。**兜底规则：若无法确定是否为同一事项，默认不合并（宁可多不可少）。**
3. **证据分级**：严格按 evidence-rules.md 的二级优先级执行（第一优先级：本人手动主证据；第二优先级：他人关联辅证）
4. **分配 R 编号**：对去重聚合后的每个独立工作事项，按顺序分配 `R{MM}{序号}` 编号。编号规则：
   - 月份统一两位补零（01-12），序号从 01 开始连续递增
   - 每条编号附带汇报标题全文，格式：`R{编号}`《[汇报标题]》
   - **每条编号必须同时记录汇报链接**，格式：`huibao://view?id={reportId}`（字符串原样，不做任何转换）。聚合场景取按 `createTime` 最早的一条
5. **分配 RP 编号**（上月参考引用）：从 Step 2b 数据中，按 `reports` 列表顺序分配 `RP{序号}` 编号。RP 编号仅用于基线引用和附录 A.3，**不参与**当月证据分级和灯色判断。首月不分配
6. **按节点归集**：利用 `reportIndex` 中每条汇报的 `relatedNodes` 字段确定其关联的具体 KR/举措。交叉引用标注
7. **月份归集口径**：以汇报的发出时间（`businessTime`/`createTime`）为准

将证据台账写入 `/tmp/evidence_ledger_{groupId}.md`，格式为：

```markdown
## 证据台账

### R 编号索引

| R 编号 | 汇报标题 | 证据级别 | 汇报链接 | 关联节点 |
|--------|---------|---------|---------|---------|
| R0301 | 《[汇报标题]》 | 主证据 | [查看汇报](huibao://view?id=xxxxxxxxxxxxx) | 目标X / KRY |
| ... | ... | ... | ... | ... |

### 统计摘要
- 原始工作汇报：N 份
- 经批量通知归并后最终采纳：M 份
- 其中本人主证据：X 份、他人关联辅证：Y 份

### 按目标归集（逐 KR/举措明细）

#### 目标 [fullLevelNumber]: [目标名称]

**关键成果：**

| KR 编号 | KR 名称 | 关联 R 编号 | 证据级别分布 | 证据充分性 |
|---------|---------|------------|-------------|-----------|
| [fullLevelNumber] | [名称] | R0301, R0303 | 主证据×2 | 充分 |

**关键举措：**

| 举措编号 | 举措名称 | 关联 R 编号 | 证据级别分布 | 证据充分性 |
|---------|---------|------------|-------------|-----------|
| [fullLevelNumber] | [名称] | R0301 | 主证据×1 | 充分 |
```

**关键要求**：
- 证据台账是最终报告附录的**唯一数据源**，Step 3d 拼接附录时必须直接读取此文件
- "按目标归集"部分是 Step 3c 逐目标处理的**输入索引**

---

## Step 3c: 逐目标精读判断与章节组装

**核心原则**：以目标为维度逐个完成"精读证据 → 判灯 → 写章节"的闭环，避免证据串台。

### 预处理：目标级排除判断（以目标维度为准）

按 [traffic-light-rules.md](../rules/traffic-light-rules.md) 的排除规则，**先对所有目标执行排除判断**。只看目标自身的 `planDateRange` 与汇报月份的区间交叉，不单独看其下 KR/举措的时间范围。目标被排除（★未启动）后，其下所有 KR 和举措一律不判断。

仅对通过目标级排除判断（结果为"参与"）的目标，才进一步对其下 KR/举措执行排除判断。

将被排除的节点记录到 `/tmp/excluded_goals_{groupId}.md`：

```markdown
## 本月不参与自查的节点

### 目标级排除（★ 未启动，其下 KR/举措一律不判断）

| 目标名称 | 编号 | 计划时间范围 | 排除原因 |
|---------|------|-------------|---------|
| [名称] | [编号] | [planDateRange] | 目标计划期未覆盖本月 / 草稿 |

### KR/举措级排除（仅针对参与自查的目标下的子节点）

| 节点类型 | 名称 | 编号 | 所属目标 | 计划时间范围 | 排除原因 |
|---------|------|------|---------|-------------|---------|
| 关键成果 | [名称] | [编号] | [目标编号] | [planDateRange] | 计划期未覆盖本月 / 草稿 |
| 关键举措 | [名称] | [编号] | [目标编号] | [planDateRange] | 计划期未覆盖本月 / 草稿 |
```

### 逐目标循环

**上下文隔离操作指令**：每个目标循环开始时，**只读取以下文件**，不读取其他目标的 goal_section 或 goal_cards 文件：
1. 该目标的数据文件：`/tmp/goal_data_{groupId}_{goalId}.json`
2. 证据台账中**该目标对应的归集段落**（从 `/tmp/evidence_ledger_{groupId}.md` 的"按目标归集"部分定位）
3. 排除状态文件：`/tmp/excluded_goals_{groupId}.md`

对每个**参与自查的目标**，按以下 7 步闭环执行：

**(i) 读取该目标的输入**

- **目标数据文件**：直接读取 `/tmp/goal_data_{groupId}_{goalId}.json`（轻量文件，只含精简后的 goalDetail + reportIndex 索引 + reports 引用列表，不含汇报全文）
- **锚点**（从 Step 3a）：该目标的名称、编号、衡量标准、KR/举措结构
- **证据子集**（从 Step 3b 的"按目标归集"）：每个 KR/举措关联的 R 编号和证据充分性
- **按需精读汇报**：对需要精读的汇报（从 `reportIndex` 中的 `relatedNodes` 定位到当前 KR/举措），先看 `contentPreview`（前 300 字预览）是否足够判断：
  - **预览足够** → 直接使用预览内容
  - **预览不够**（内容较长或需要细节） → 调用 `get_report_text --group_id {groupId} --report_id {reportId}` 获取纯文本全文
  - 对超长汇报（`charCount` > 4000 字）获取全文后，执行 AI 摘要（控制在 500-800 字）。摘要必须保留所有数量/百分比/日期等关键数据点；若原文包含表格或列表，摘要中以精简列表保留

**(ii) 读取排除状态**

直接从 `/tmp/excluded_goals_{groupId}.md` 读取，**不重复执行排除判断逻辑**。

**(iii) 逐 KR 精读分析（不判灯）**

对每个参与自查的关键成果，精读关联汇报正文，对照衡量标准，生成 KR 分析卡片：

```markdown
### KR卡: [关键成果名称] ([编号])

- 衡量标准：[从 measureStandard 提取]
- 计划时间范围：[planDateRange]
- 本月主证据：[R编号列表]
- 本月辅证：[R编号列表]
- 距离衡量标准的差距：[基于证据判断]
- 判断理由：[详细分析]
```

**(iv) 逐举措精读判灯**

对每个参与自查的关键举措，**严格按 traffic-light-rules.md 判灯**，生成举措卡片：

```markdown
### Action卡: [举措名称] ([编号])

- 计划时间范围：[planDateRange]
- 当前状态：[statusDesc]
- 本月推进动作：[从证据提取，引用R编号]
- 对关键成果的支撑情况：[强/中/弱]
- 灯色判断：[🟢/🟡/🔴/⚫]
- 判断依据：
```

**(v) 聚合目标级灯色**

从举措灯色聚合，按优先级命中即停：有红则红 → 有黄则黄 → 有黑则黑 → 全绿则绿。

**(vi) 组装目标报告章节**

**严格按 [report-template-bp-self-check.md](../templates/report-template-bp-self-check.md) 模板输出**，包含 4 个必需子章节：承诺与实际对照、关键成果达成与举措推进、偏差问题与原因分析、目标级综合灯色结论。

**(vii) 写入文件**

- 判断卡片（过程记录）：`/tmp/goal_cards_{groupId}_{goalIndex}.md`
- 报告章节（搬入最终报告）：`/tmp/goal_section_{groupId}_{goalIndex}.md`

---

## Step 3d: 报告拼接与合规性校验

**前置加载**：进入 Step 3d 前，必须先读取 [validation-rules.md](../rules/validation-rules.md)。

### (i) 聚合灯色统计

读取所有 `/tmp/goal_section_{groupId}_{goalIndex}.md`，提取灯色结论，分两部分统计：
1. **参与自查的目标**：统计绿/黄/红/黑灯数量
2. **★ 未启动的目标**：单独统计个数，不计入四色灯

### (ii) 生成全局章节

**严格按 [report-template-bp-self-check.md](../templates/report-template-bp-self-check.md) 逐字段对照组装**：

1. **元数据头**：周期、员工姓名、基线引用（RP 编号超链接，若首月写"首月，无基线"）、证据说明
2. **第 1 章 总体自查结论**：1.1 结论 + 1.2 灯色分布概览 + 1.3 偏差点
3. **第 2 章 目标级自查明细**：2.1 总览表（7 列，含排除目标）+ 2.2 目标明细（从各章节文件拼接）
4. **第 3 章 年度结果预判评分**：仅输出一个链接 `[点击进入本月：年度结果预判评分](https://sg-al-cwork-web.mediportal.com.cn/BP-manager/web/dist/#/monthly-review/self?groupId={groupId}&month={month})`
5. **第 4 章 月度汇报入口**：仅输出一个链接 `[点击进入查看系统月度汇报](https://sg-cwork-web.mediportal.com.cn/BP-manager/web/dist/#/MonthlyReportDashboard?groupId={groupId})`
6. **附录**：从 `/tmp/evidence_ledger_{groupId}.md` 直接读取原样搬入 A.1 + A.2 + A.3

### (iii) 语言清洗

**严格按 [validation-rules.md](../rules/validation-rules.md) 第三章执行。**

### (iv) 写入最终报告

写入 `/tmp/report_selfcheck_{groupId}.md`。

### (v) 合规性校验

**严格按 [validation-rules.md](../rules/validation-rules.md) 第一章执行 16 项校验清单。** 全部通过后方可进入保存草稿流程。
