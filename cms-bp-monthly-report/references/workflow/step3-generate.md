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

## 3d: 生成目标总结报告（阶段 10）

**这是核心章节产出。** 每个参与自查的目标生成一份自包含的目标总结报告。

**输入**（全部在同一目标目录下）：
- `progress.json` — BP 结构和证据 Markdown
- `goal_evidence.md` — 证据台账（R 编号索引）
- `action_judgments.md` — 举措判灯结果
- `kr_analysis.md` — KR 差距分析
- `goal_lamp.json` — 目标级灯色

**输出**：`goals/{goalId}/goal_report.md`

**⚠️ 灯色锚定规则（MANDATORY — 严禁违反）**：
1. 生成"目标级综合灯色结论"前，**必须先读取** `goal_lamp.json` 的 `goalLamp` 和 `goalLampEmoji` 字段
2. "结论一句话"的灯色 span **必须使用** `goalLampEmoji` 的值，严禁 AI 自行判断替代
3. "四灯判断块"的灯色 **必须使用** `goalLamp` 的值来选择对应模板（green→绿灯2行 / yellow→黄灯8行 / red→红灯8行 / black→黑灯8行），**严禁 AI 二次判断覆盖脚本聚合结果**
4. "结论一句话"灯色与"四灯判断块"灯色 **必须完全一致**，均来自 `goal_lamp.json`
5. 若 AI 对脚本聚合结果有异议，可在判断理由中注明"AI 建议为 X 灯，脚本聚合为 Y 灯，以脚本为准"，但最终灯色仍以脚本为准

**严格按模板结构**（见 report-template-bp-self-check.md 2.2 节），包含 4 个必需子章节：

```markdown
##### {fullLevelNumber}｜{目标全称}

**承诺与实际对照**
承诺口径：...
本月实际：...
差异点：...
证据：[R{编号}](huibao://view?id={reportId})

**关键成果达成与举措推进**
（组装 kr_analysis.md 和 action_judgments.md 的内容）

**偏差问题与原因分析**
（若无偏差写"本目标本期无重大偏差"）

**目标级综合灯色结论**
结论一句话：[从 goal_lamp.json 读取灯色] ...
（嵌入四灯判断块，灯色必须与 goal_lamp.json 的 goalLamp 一致）
```

---

## 3d+: 保存目标月报阅读内容

**在 3d 完成后立即执行。** 将该目标的月报阅读内容保存到系统（API 2.35 saveTaskMonthlyReading）。

**保存失败不阻塞后续流程**，仅记录警告日志，继续执行 3e 及后续步骤。

### 参与自查的目标

3d 生成 `goal_report.md` 后，立即读取并保存：

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

## 3f: 生成总览表（阶段 12）

读取所有目标的 `goal_lamp.json` + `goal_report.md` + 排除状态，生成 `overview_table.md`。

**注意：`overview_table.md` 不包含 `#### 2.1 目标清单总览` 标题**（该标题由 `assemble_report` 脚本在拼接时自动插入），直接从表格开始输出。

**必须 7 列**：目标编号 / BP目标 / 本月承诺口径 / 本月实际 / 证据引用 / 目标灯色 / 结论一句话。

**⚠️ 灯色数据源规则（MANDATORY）**：
1. 总览表中每个参与自查目标的"目标灯色"列，**必须从该目标的 `goal_lamp.json` 的 `goalLampEmoji` 字段读取**，不得由 AI 自行判断
2. 被排除目标（★未启动）的灯色列使用 `★` 标记，不读取 `goal_lamp.json`

**目标编号必须使用系统 `fullLevelNumber`**（如 `P1001-7`），**严禁使用自编流水号**（如 001、002）。数据源优先级：先读 `overview.json` 的 `goals[].fullLevelNumber`（Step 2b 执行后已自动回填），若为空则从 `goals/{goalId}/progress.json` 的 `goalDetail.fullLevelNumber` 字段读取。

所有目标均列入（含★未启动的目标）。

---

## 3g: 生成总体结论（阶段 13）

读取所有目标的 `goal_report.md` + `goal_lamp.json`，从全局视角生成 `conclusion.md`。

**注意：`conclusion.md` 不包含 `### 1. 总体自查结论` 标题**（该标题由 `assemble_report` 脚本在拼接时自动插入），直接从 `#### 1.1` 开始输出。

**⚠️ 灯色统计数据源规则（MANDATORY）**：
1. 1.2 灯色分布概览中的统计数字，**必须遍历所有参与自查目标的 `goal_lamp.json` 文件**，读取 `goalLamp` 字段逐个计数，**不得凭记忆、推断或 AI 自行判断填写**
2. 具体操作：逐个读取 `goals/{goalId}/goal_lamp.json`，统计 `goalLamp` 为 `green`/`yellow`/`red`/`black` 的数量，被排除目标不计入四色灯统计，仅计入"★未启动"

**输出结构必须严格遵守以下格式：**

```markdown
#### 1.1 结论

一句话优势：[例如"关键目标兑现率高且无明显短板"]  
一句话短板：[例如"个别关键目标存在偏差，需在下月通过 X 纠偏"]

#### 1.2 灯色分布概览

```text
参与自查目标 [M] 个：
  🟢 目标数：[N]
  🟡 目标数：[N]
  🔴 目标数：[N]
  ⚫ 目标数：[N]
未参与自查：
  ★ 未启动：[N] 个目标
```

#### 1.3 本月最关键偏差点

1) 偏差点：[一句话描述]（对应目标：[fullLevelNumber]）  
影响：[对 BP/KR/节点的影响]  
原因假设：[最可能原因 1-2 条]  
下月纠偏方向：[一句话]
```

**强制规则：**

1. **1.1 必须输出两个带标签的独立行**：`一句话优势：` 和 `一句话短板：`，不可合并为一段话。
2. **1.2 必须使用 fenced code block**（` ```text ``` `），分行展示四色灯和未启动统计。
3. **1.3 若无偏差**，仍需输出本节，内容为"本月无重大偏差点。"；**若有偏差**（最多 3 条），每条必须包含：偏差点、影响、原因假设、下月纠偏方向 四个字段，并标注对应目标编号。

---

## 3h: 生成报告头部 + 链接章节 + 评分附录（阶段 9/14）

**报告头部** `report_header.md`：
```markdown
# {员工姓名} {YYYY年M月} BP自查报告

> 周期：`{BP周期名称}`
> 节点：`{员工姓名}`
> 基线：已参考上月 [RP01](...), [RP02](...) 及上月评价（详见附录 A.3）
> 证据说明：...
> 解释口径：...
```

**⚠️ report_header.md 内容边界规则（MANDATORY）**：
- `report_header.md` **仅包含**上方代码块中的内容（报告标题 `#` 行 + 引用块 `>` 行），**禁止包含任何其他章节标题行**
- 禁止在 header 中写入 `## 目标明细`、`### 1. 总体自查结论`、`### 2. 目标级自查明细` 等章节标题
- 拼接脚本不会对 `report_header.md` 执行标题去重，AI 多写的任何标题都会原样出现在最终报告中导致结构重复

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
  action_judgments.json   ← 3a
  action_judgments.md     ← 3a
  kr_analysis.md          ← 3b
  goal_lamp.json          ← 3c
  goal_report.md          ← 3d
  (→ 远端已保存月报阅读)  ← 3d+ save_task_monthly_reading
excluded_goals.md         ← 3e
(→ 排除目标远端已保存说明) ← 3d+ save_task_monthly_reading（3e 后执行）
overview_table.md         ← 3f
conclusion.md             ← 3g
report_header.md          ← 3h
chapter3.md               ← 3h
chapter4.md               ← 3h
evidence_ledger.md        ← 3i
```

**完成后输出**：`Step 3 完成 — 报告各章节已生成，待拼接`
