# Step 3: 生成月报内容（阶段 5-14）

> 本文件为强制约束。AI 执行 Step 3 的所有子步骤时必须严格遵守。

**前置加载**（必须在 3a 之前完成）：
- [traffic-light-rules.md](../rules/traffic-light-rules.md)
- [evidence-rules.md](../rules/evidence-rules.md)
- [report-template-bp-self-check.md](../templates/report-template-bp-self-check.md)

---

## 3a: 举措级并行判灯（阶段 5）

**对每个参与自查的目标**，读取该目标下的判灯材料包，逐举措判灯。

**输入**：`goals/{goalId}/judgment_input_{actionId}.md`（Phase 4 脚本产出）

**被排除的举措（`excluded: true`）**：不写入 `action_judgments.json` / `.md`，不判灯、不展开、不记录。被排除举措仅在 3d `goal_report.md` 的"关键成果达成与举措推进"小节末尾用一行汇总说明（如"另有 N 个举措计划期未覆盖本月，不纳入自查。"），**严禁为其生成四灯判断块或任何灯色**。

**对黑灯举措（`isBlackLamp: true`）**：无需 AI 判断，脚本已标记。AI 只需在 `action_judgments.json` / `.md` 中记录 `"lamp": "black"`。黑灯的含义是**参与自查但本月无有效汇报证据**，与"被排除"是完全不同的概念。

**对非黑灯且非排除举措**：读取判灯材料包，严格按 traffic-light-rules.md 判灯。

> ⚠️ **核心区分**：
> - **排除** = 不参与自查（计划期未覆盖本月 / 草稿状态等），**不出现在 judgments 文件中**
> - **黑灯** = 参与自查但无有效证据，**必须出现在 judgments 文件中并标记 `"lamp": "black"`**

**输出**：每个目标生成两个文件到 `goals/{goalId}/`（仅包含参与自查的举措）：

1. `action_judgments.json`（结构化，供 Phase 7 聚合脚本消费）：
```json
{
  "{actionId}": {
    "lamp": "green",
    "reason": "...",
    "summary": "推进动作摘要 1-3 句",
    "support": "强",
    "progress": "完成度或里程碑",
    "rCodes": ["R0401", "R0402"]
  }
}
```
其中 `lamp` 取值：`green` / `yellow` / `red` / `black`

2. `action_judgments.md`（Markdown，供 AI 后续引用）

**上下文隔离**：每个目标只读自己目录下的文件，不读其他目标的判灯结果。

---

## 3b: 成果层分析（阶段 6）

对每个参与自查的 KR，精读其 `progressMarkdown`（来自 `progress.json`），对照衡量标准，生成 KR 差距分析。**KR 不判灯色。**

**输出**：`goals/{goalId}/kr_analysis.md`

每个 KR 包含 6 个必需子字段：
- 衡量标准
- 本月结果
- 距离衡量标准
- 环比上月（若有 `prev_month.json` 则对比，否则"首月无基线"）
- 证据（R 编号引用）
- 判断理由

---

## 3c: 目标层聚合（阶段 7）

**脚本执行**，AI 无需介入。输出：`goals/{goalId}/goal_lamp.json`

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py aggregate_lamp_colors \
  --group_id "{groupId}" \
  --goal_id "{goalId}" \
  --month "{YYYY-MM}"
```

---

## 3d: 生成目标总结数据（阶段 10）

**这是核心章节产出。** 每个参与自查的目标生成一份**结构化 JSON 数据文件**，由渲染脚本转换为 Markdown。

> **⚠️ 架构变更**：AI 只负责产出内容数据（JSON），不再直接写 Markdown。
> 所有标题、灯色 HTML span、四灯判断块格式、people-suggest 区域均由 `render_goal_report` 脚本自动渲染。
> **AI 严禁在 JSON 值中包含任何 HTML 标签或 Markdown 标题。**

**输入**（全部在同一目标目录下）：
- `progress.json` — BP 结构和证据 Markdown
- `goal_evidence.md` — 证据台账（R 编号索引）
- `action_judgments.json` — 举措判灯结果（含每个举措的 lamp 颜色）
- `kr_analysis.md` — KR 差距分析
- `goal_lamp.json` — 目标级灯色（脚本聚合产出）

**AI 输出**：`goals/{goalId}/goal_report_data.json`

```json
{
  "fullLevelNumber": "P12717-2",
  "goalName": "目标全称（纯文本）",
  "commitment": {
    "standard": "承诺口径文本",
    "actual": "本月实际达成情况文本",
    "gap": "差异点描述，若无差异写'无'",
    "evidence": "[R0201](huibao://view?id=xxx)"
  },
  "keyResults": [
    {
      "fullLevelNumber": "P12717-2.8",
      "name": "KR全称（纯文本）",
      "measureStandard": "衡量标准文本",
      "monthlyResult": "本月结果文本",
      "gapToStandard": "距离衡量标准的差距描述",
      "momComparison": "环比上月描述",
      "evidence": "[R0201](huibao://view?id=xxx)",
      "judgmentReason": "对该KR的判断理由文本",
      "actions": [
        {
          "fullLevelNumber": "P12717-2.8.5",
          "name": "举措全称（纯文本）",
          "excluded": false,
          "lamp": "green",
          "summary": "推进动作摘要 1-3 句",
          "support": "强",
          "progress": "完成度或里程碑阶段 — 一句话说明",
          "evidence": "[R0201](huibao://view?id=xxx)",
          "reason": "判断理由文本（纯文本，不含HTML）"
        }
      ]
    }
  ],
  "excludedKrCount": 0,
  "excludedActionCount": 0,
  "deviations": [
    {
      "point": "偏差点描述",
      "impact": "影响描述",
      "hypothesis": "原因假设",
      "correction": "下月纠偏方向",
      "evidence": "[R0301](huibao://view?id=xxx)"
    }
  ],
  "conclusionText": "关键依据+关键短板/优势（纯文本，不含灯色emoji/HTML）",
  "goalJudgmentReason": "目标级判断理由文本（纯文本，不含HTML）"
}
```

**字段规则**：
1. `lamp` 字段取值：`green` / `yellow` / `red` / `black`，**必须与 `action_judgments.json` 中的对应举措灯色一致**
2. `deviations` 数组：若无偏差则为空数组 `[]`
3. 所有文本字段为**纯文本**，仅 `evidence` 字段允许 Markdown 链接格式 `[R编号](huibao://view?id=xxx)`
4. `excluded` 为 `true` 的举措不需要填写 lamp/summary/support/progress/evidence/reason 字段

**脚本渲染**：AI 写完 JSON 后，立即执行渲染脚本：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py render_goal_report \
  --goal_id "{goalId}" \
  --group_id "{groupId}" \
  --month "{YYYY-MM}"
```

脚本会读取 `goal_report_data.json` + `goal_lamp.json`，自动渲染：
- 所有 Markdown 标题（`#####`）
- 四灯判断块 HTML（灯色从 `goal_lamp.json` 读取）
- `people-suggest` 人工确认区域（非绿灯自动添加，绿灯不添加）
- 结论一句话的灯色 span HTML

**输出**：`goals/{goalId}/goal_report.md`（由脚本生成，AI 不直接写此文件）

---

## 3d+: 保存目标月报阅读内容

**在 3d 的 `render_goal_report` 脚本执行完成后立即执行。** 将该目标的月报阅读内容保存到系统（API 2.35 saveTaskMonthlyReading）。

**保存失败不阻塞后续流程**，仅记录警告日志，继续执行 3e 及后续步骤。

### 参与自查的目标

`render_goal_report` 生成 `goal_report.md` 后，立即读取并保存：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py save_task_monthly_reading \
  --task_id "{goalId}" \
  --month "{YYYY-MM}" \
  --content_file "/Users/openclaw-data/bp/bp_report_{groupId}_{month}/goals/{goalId}/goal_report.md"
```

### 未参与自查的目标

在 **3e 完成后**，遍历所有被排除的目标（`progress.json` 中 `excluded: true` 的目标），为每个目标保存一行说明：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py save_task_monthly_reading \
  --task_id "{goalId}" \
  --month "{YYYY-MM}" \
  --content "本月该目标不参与自查（原因：{excludeReason}），未生成目标明细。"
```

其中 `{excludeReason}` 从该目标 `progress.json` 的 `excludeReason` 字段读取。

---

## 3e: 生成未参与目标说明（阶段 11）

读取所有目标的 `progress.json`，汇总被排除的目标，生成 `excluded_goals.md`。

**注意：`excluded_goals.md` 不包含任何 `#` / `##` / `###` 级别标题**（它被拼接在 `#### 2.2 目标明细` 之后）。若需标题，使用 `# 未参与自查目标说明`（一级标题，渲染效果等同于普通加粗文本段），或直接以加粗段落开头。**目标编号必须使用系统 `fullLevelNumber`**（如 `P1001-7`），从 `progress.json` 的 `goalDetail.fullLevelNumber` 字段读取，**严禁使用自编流水号**。

这些目标在 2.1 总览表中以 ★ 标记，不展开明细。

---

## 3f: 生成总览表数据（阶段 12）

> **⚠️ 架构变更**：AI 只负责产出结构化 JSON 数据，由 `render_overview_table` 脚本渲染为 Markdown 表格。
> 灯色 HTML span、★ 标记等格式均由脚本自动生成，AI 不写任何 HTML。

读取所有目标的 `goal_report_data.json` + `progress.json`，生成 `overview_data.json`。

**AI 输出**：`overview_data.json`（写入工作目录根）

```json
{
  "goals": [
    {
      "goalId": "2030893444855308290",
      "fullLevelNumber": "P12717-2",
      "name": "目标全称（纯文本）",
      "excluded": false,
      "standard": "本月承诺口径（纯文本）",
      "actual": "本月实际达成情况（纯文本）",
      "evidence": "[R0201](huibao://view?id=xxx)-[R0208](huibao://view?id=xxx)",
      "conclusion": "结论一句话（纯文本，不含灯色）"
    },
    {
      "goalId": "2030893444855308295",
      "fullLevelNumber": "P12717-18",
      "name": "投前弹性窗口管理",
      "excluded": true,
      "excludeReason": "计划2026-07-01起"
    }
  ]
}
```

**字段规则**：
1. 参与自查的目标必须包含：`standard`、`actual`、`evidence`、`conclusion`
2. 被排除目标只需：`goalId`、`fullLevelNumber`、`name`、`excluded: true`、`excludeReason`
3. 所有文本字段为**纯文本**，仅 `evidence` 字段允许 Markdown 链接格式
4. **目标编号必须使用系统 `fullLevelNumber`**（如 `P1001-7`），**严禁使用自编流水号**

**脚本渲染**：AI 写完 JSON 后，立即执行：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py render_overview_table \
  --group_id "{groupId}" \
  --month "{YYYY-MM}"
```

脚本会读取 `overview_data.json` + 各目标的 `goal_lamp.json`，自动渲染 7 列表格，灯色从 `goal_lamp.json` 精确读取。

**输出**：`overview_table.md`（由脚本生成）

---

## 3g: 生成总体结论数据（阶段 13）

> **⚠️ 架构变更**：AI 只负责产出内容数据（JSON），由 `render_conclusion` 脚本渲染为 Markdown。
> 灯色分布统计由脚本自动从 `goal_lamp.json` 文件精确计算，AI 不手动统计灯色数量。

读取所有目标的 `goal_report_data.json`，从全局视角生成 `conclusion_data.json`。

**AI 输出**：`conclusion_data.json`（写入工作目录根）

```json
{
  "strength": "关键目标兑现率高且无明显短板（纯文本）",
  "weakness": "个别关键目标存在偏差，需在下月通过 X 纠偏（纯文本）",
  "topDeviations": [
    {
      "point": "偏差点一句话描述",
      "goalNumber": "P12717-15",
      "impact": "对 BP/KR/节点的影响",
      "hypothesis": "最可能原因 1-2 条",
      "correction": "下月纠偏方向一句话"
    }
  ]
}
```

**字段规则**：
1. `strength` 和 `weakness` 为**纯文本**，分别对应"一句话优势"和"一句话短板"
2. `topDeviations` 最多 3 条；若无偏差则为空数组 `[]`
3. 所有文本字段为**纯文本**，不含 HTML 或 Markdown 标题
4. **灯色分布统计不由 AI 填写**，脚本会自动遍历所有 `goal_lamp.json` 精确计算

**脚本渲染**：AI 写完 JSON 后，立即执行：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py render_conclusion \
  --group_id "{groupId}" \
  --month "{YYYY-MM}"
```

脚本会渲染完整的 `conclusion.md`，包含：
- `#### 1.1 结论`（从 JSON 读取 strength/weakness）
- `#### 1.2 灯色分布概览`（从 `goal_lamp.json` 文件精确统计，code block 格式）
- `#### 1.3 本月最关键偏差点`（从 JSON 读取 topDeviations）

**输出**：`conclusion.md`（由脚本生成）

---

## 3h: 生成报告头部 + 链接章节 + 评分附录（阶段 9/14）

> **⚠️ 报告头部也改为脚本渲染**，AI 只需产出 `header_data.json`。

**AI 输出**：`header_data.json`（写入工作目录根）

```json
{
  "employeeName": "姜葳",
  "periodName": "2026年BP全年目标",
  "baseline": "已参考上月 [RP01](huibao://view?id=xxx), [RP02](huibao://view?id=xxx) 及上月评价（详见附录 A.3）"
}
```

**字段规则**：
1. `baseline`：若有上月数据，格式为 `已参考上月 [RP01](...), [RP02](...) 及上月评价（详见附录 A.3）`；若首月则写 `首月，无基线`
2. `employeeName` 和 `periodName` 从 `overview.json` 或上下文获取

**脚本渲染**：AI 写完 JSON 后，立即执行：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py render_report_header \
  --group_id "{groupId}" \
  --month "{YYYY-MM}"
```

脚本会生成精确格式的 `report_header.md`（标题行 + 引用块，不含任何章节标题）。

**第 3 章** `chapter3.md`：**不包含 `### 3. 年度结果预判评分` 标题**（该标题由 `assemble_report` 脚本在拼接时自动插入），仅输出链接内容。

**第 4 章** `chapter4.md`：**不包含 `### 4. 月度汇报入口` 标题**（该标题由 `assemble_report` 脚本在拼接时自动插入），仅输出链接内容。

---

## 3i: 全局证据台账合并（阶段 8）

**脚本执行**，AI 无需介入。输出：`evidence_ledger.md`

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py build_evidence_ledger \
  --group_id "{groupId}" \
  --month "{YYYY-MM}"
```

---

## 3j: 语言清洗与校验

**前置加载**：读取 [validation-rules.md](../rules/validation-rules.md)

在各个中间产物生成完毕后、拼接报告前，对所有 AI 产出的 Markdown 文件执行语言清洗 5 条规则。

---

## 完成后产出一览

```
goals/{goalId}/
  action_judgments.json      ← 3a (AI)
  action_judgments.md        ← 3a (AI)
  kr_analysis.md             ← 3b (AI)
  goal_lamp.json             ← 3c (脚本)
  goal_report_data.json      ← 3d (AI 产出 JSON)
  goal_report.md             ← 3d (render_goal_report 脚本渲染)
  (→ 远端已保存月报阅读)     ← 3d+ save_task_monthly_reading
excluded_goals.md            ← 3e (AI)
(→ 排除目标远端已保存说明)    ← 3d+ save_task_monthly_reading（3e 后执行）
overview_data.json           ← 3f (AI 产出 JSON)
overview_table.md            ← 3f (render_overview_table 脚本渲染)
conclusion_data.json         ← 3g (AI 产出 JSON)
conclusion.md                ← 3g (render_conclusion 脚本渲染)
header_data.json             ← 3h (AI 产出 JSON)
report_header.md             ← 3h (render_report_header 脚本渲染)
chapter3.md                  ← 3h (AI)
chapter4.md                  ← 3h (AI)
evidence_ledger.md           ← 3i (脚本)
```

**完成后输出**：`Step 3 完成 — 报告各章节已生成，待拼接`
