# Step 2: 采集 BP 数据（阶段 1-3.5）

> 本文件为强制约束。AI 执行 Step 2 的所有子步骤时必须严格遵守。

---

## 2-0: 初始化工作目录

**每次运行前必须执行。** 清理同一 groupId + month 的历史残留，不影响其他分组或月份的数据。

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py init_work_dir \
  --group_id "{groupId}" \
  --month "{YYYY-MM}"
```

工作目录结构：
```
/tmp/bp_report_{groupId}_{month}/
  overview.json
  prev_month.json
  goals/
    {goalId}/
      progress.json
      goal_evidence.md
      goal_evidence.json
      judgment_input_{actionId}.md
      action_judgments.json     (AI Phase 5 产出)
      action_judgments.md       (AI Phase 5 产出)
      kr_analysis.md            (AI Phase 6 产出)
      goal_lamp.json            (Phase 7 产出)
      goal_report.md            (AI Phase 10 产出)
  excluded_goals.md
  evidence_ledger.md
  report_header.md              (AI Phase 9 产出)
  overview_table.md             (AI Phase 12 产出)
  conclusion.md                 (AI Phase 13 产出)
  chapter3.md                   (AI Phase 14 产出)
  chapter4.md                   (AI Phase 14 产出)
  report_selfcheck.md           (Phase 15 产出)
```

---

## 2a: 采集全局概览（阶段 1）

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py collect_monthly_overview \
  --group_id "{groupId}" \
  --month "{YYYY-MM}"
```

输出文件：`/tmp/bp_report_{groupId}_{month}/overview.json`

| 字段 | 说明 |
|------|------|
| `taskTree` | 精简后的任务树（目标 → KR → 举措） |
| `goals` | 目标摘要列表，含 `goalId`、`name`、`fullLevelNumber`、`planDateRange`、`statusDesc` |
| `stats` | `totalGoals`、`totalNodes` |

---

## 2b: 逐目标采集进展（阶段 2-3）

读取 `overview.json` 的 `goals` 列表，对每个目标调用 `collect_goal_progress`：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py collect_goal_progress \
  --group_id "{groupId}" \
  --goal_id "{goalId}" \
  --month "{YYYY-MM}"
```

脚本内部自动完成：
1. 获取目标详情（`getGoalAndKeyResult`），精简为判灯必要字段
2. **目标级排除判断**（按 traffic-light-rules.md 规则）
3. 若目标参与自查 → 逐 KR/举措执行排除判断
4. 对未排除的 KR/举措调用 `getReportProgressMarkdown`(2.34) 获取聚合证据 Markdown
5. **黑灯判断**：举措无有效汇报 → 标记 `isBlackLamp: true`
6. **reportId 提取**：从 Markdown 正则提取所有 `汇报ID：{reportId}`

输出文件：`/tmp/bp_report_{groupId}_{month}/goals/{goalId}/progress.json`

| 字段 | 说明 |
|------|------|
| `goalDetail` | 精简的目标详情（含 KR、举措结构） |
| `excluded` | 目标是否被排除 |
| `excludeReason` | 排除原因 |
| `krData` | `{krId: {name, excluded, progressMarkdown, reportIds, reports}}` |
| `actionData` | `{actionId: {name, parentKrId, excluded, isBlackLamp, progressMarkdown, reportIds, reports}}` |
| `allReportIds` | 该目标下所有去重后的 reportId |
| `stats` | KR/举措数、排除数、黑灯数 |

**容错**：若 `getReportProgressMarkdown` 调用失败，记录到 `errors` 数组，该举措标记黑灯。goalDetail 获取失败则重试一次，仍失败则跳过该目标。

---

## 2c: 构建目标级证据台账（阶段 3.5）

**在 AI 判灯之前执行。** 为每个参与自查的目标构建证据台账，分配 R 编号。

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py build_goal_evidence \
  --group_id "{groupId}" \
  --goal_id "{goalId}" \
  --month "{YYYY-MM}" \
  --employee_id "{employeeId}" \
  --r_start_index "{起始序号}"
```

- `--employee_id`：用于判断证据级别（本人=主证据，他人=辅证）
- `--r_start_index`：R 编号起始序号，跨目标连续递增。第 1 个目标传 `1`，后续目标传前一个目标返回的 `nextRIndex`

脚本内部自动完成：
1. 读取 `progress.json`，汇总该目标下所有 reportId（去重）
2. 分配 R 编号（`R{MM}{序号}`，全局连续）
3. 判断证据级别：`authorId == employeeId` → 主证据，否则 → 辅证
4. 按节点归集：每个 KR/举措关联了哪些 R 编号
5. 评估证据充分性

输出文件：
- `goal_evidence.md`：Markdown 格式的目标级证据台账（AI 分析时引用）
- `goal_evidence.json`：结构化数据（含 rCodeMap，后续阶段使用）

返回值中 `nextRIndex` 用于下一个目标的起始编号。

---

## 2d: 组装判灯材料包（阶段 4）

为每个参与自查的举措生成判灯材料包 Markdown，供 AI 在 Phase 5 中消费。

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py build_judgment_input \
  --group_id "{groupId}" \
  --goal_id "{goalId}" \
  --month "{YYYY-MM}"
```

脚本内部自动完成：
1. 读取 `progress.json` + `goal_evidence.json`
2. 对每个非排除、非黑灯的举措，生成判灯材料包，包含：
   - BP 锚点（目标/KR/举措名称编号、KR 衡量标准）
   - 关联证据 R 编号
   - 汇报推进情况原文（`progressMarkdown`）

输出文件：每个举措一个 `judgment_input_{actionId}.md`

---

## 2e: 采集上月汇报与评价

`--month` 参数为当前汇报月份的上一个月，`--report_month` 传当前月份以定位工作目录。

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py collect_previous_month_data \
  --group_id "{groupId}" \
  --month "{上月YYYY-MM}" \
  --report_month "{当月YYYY-MM}"
```

输出文件：`/tmp/bp_report_{groupId}_{month}/prev_month.json`

若首月无上月数据，跳过此步骤。

---

## 完成后产出一览

```
/tmp/bp_report_{groupId}_{month}/
  overview.json                          ← 2a
  prev_month.json                        ← 2e (可选)
  goals/
    {goalId_1}/
      progress.json                      ← 2b
      goal_evidence.md                   ← 2c
      goal_evidence.json                 ← 2c
      judgment_input_{actionId_1}.md     ← 2d
      judgment_input_{actionId_2}.md     ← 2d
    {goalId_2}/
      progress.json                      ← 2b
      ...
```

**完成后输出**：`Step 2 完成 — {N} 个目标数据已采集，{M} 个参与自查，{K} 份证据已编号`
