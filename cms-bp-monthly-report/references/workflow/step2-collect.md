# Step 2: 采集 BP 数据

> 本文件为强制约束。AI 执行 Step 2 的所有子步骤时必须严格遵守。

---

## Step 2a-i: 采集全局概览

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py collect_monthly_overview \
  --group_id "{groupId}" \
  --month "{YYYY-MM}" \
  --output "/tmp/monthly_overview_{groupId}.json"
```

**输出 JSON 结构**：

| 字段 | 说明 |
|------|------|
| `taskTree` | 精简后的任务树（目标 → 关键成果 → 关键举措） |
| `goals` | 目标摘要列表，每条含 `goalId`、`name`、`fullLevelNumber`、`planDateRange`、`statusDesc` |
| `stats` | 统计信息：`totalGoals`（目标数）、`totalNodes`（总节点数） |

执行完成后，**Read** 此文件获取目标列表，确定有多少个目标需要逐个采集。

**容错**：若调用失败，重试一次。仍失败则调用 `update_report_status --status 2`，终止流程。

---

## Step 2a-ii: 逐目标采集数据

读取 Step 2a-i 的 `goals` 列表，对每个目标独立采集：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py collect_goal_data \
  --group_id "{groupId}" \
  --goal_id "{goalId}" \
  --month "{YYYY-MM}" \
  --output "/tmp/goal_data_{groupId}_{goalId}.json"
```

脚本内部自动完成：
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

**产出文件一览**：

```
/tmp/monthly_overview_{groupId}.json         -- 全局概览
/tmp/goal_data_{groupId}_{goalId_1}.json     -- 目标1 数据
/tmp/goal_data_{groupId}_{goalId_2}.json     -- 目标2 数据
...
```

**容错**：每个目标采集完成后，检查输出的 `errors` 数组。若 `errors` 非空但 `goalDetail` 和 `uniqueReportMap` 已获取 → 记录警告，继续下一个目标。若 `goalDetail` 缺失 → 重试一次该目标。仍失败则跳过该目标并在最终报告中注明。

---

## Step 2b: 采集上月汇报与评价

**`--month` 参数为当前汇报月份的上一个月**，由 AI 根据 `report_month` 自行计算。计算规则：
- `report_month=2026-03` → 传 `2026-02`
- `report_month=2026-01` → 传 `2025-12`（跨年递减）

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py collect_previous_month_data \
  --group_id "{groupId}" \
  --month "{上月YYYY-MM}" \
  --output "/tmp/prev_month_data_{groupId}.json"
```

脚本内部自动完成：
1. 调用 `listMonthlyReports` 获取上月所有月报的 `reportTypeDesc` + `reportRecordId`
2. 对每个 `reportRecordId`，通过工作协同接口拉取汇报正文
3. 调用 `getMonthlyEvaluation` 获取上月评价的翻译后 Markdown（自评 + 上级评价）
4. 将全部数据写入一个聚合 JSON 文件

**输出 JSON 结构**：

| 字段 | 说明 |
|------|------|
| `reports` | 上月各类型月报列表，每条含 `reportTypeDesc`、`reportRecordId`、`title`、`content` |
| `evaluations` | 上月评价 Markdown 列表，每条含 `evaluationTypeDesc`（自评/上级评价）和 `evaluationMarkdown` |
| `stats` | 统计信息：报告数、评价数 |
| `errors` | 采集过程中的错误记录（如有） |

**使用方式**：
- 上月报告正文作为本月汇报的纵向对比基线
- 上月评价 Markdown 中的评分和评语可用于本月灯色判断的辅助参考
- 若上月数据为空（首月汇报），跳过此步骤，不影响后续流程
