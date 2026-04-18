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
1. 获取该目标的完整详情，并精简为只保留判灯必要字段（measureStandard 去 HTML）
2. 提取该目标下所有节点 ID（目标自身 + KR + 举措）
3. 对每个节点查询当月关联汇报列表
4. 拉取所有去重 reportId 的汇报原文
5. 构建 `reportIndex`（轻量索引：标题/作者/时间/字数/前 300 字预览 + `relatedNodes` 标注关联的具体 KR/举措名称和编号）
6. 汇报全文写入全局汇报池 `/tmp/reports_{groupId}/{reportId}.json`（跨目标自动去重）
7. 输出轻量 JSON 文件（不含汇报全文）

**输出 JSON 结构**：

| 字段 | 说明 |
|------|------|
| `goalId` | 目标 ID |
| `goalDetail` | 该目标的精简详情（含 KR 列表、举措列表、衡量标准纯文本，去掉 API 冗余字段） |
| `reportIndex` | reportId → 轻量汇报索引，每条含标题、作者、时间、`charCount`、`contentPreview`（前 300 字）、`relatedNodes`（关联的 KR/举措名称和编号） |
| `reports` | 按 taskId 分组的 reportId 引用列表（仅含 reportId + type + businessTime，不含全文） |
| `reportsDir` | 汇报全文所在目录路径 `/tmp/reports_{groupId}/` |
| `stats` | 统计信息：`nodeCount`、`uniqueReportCount`、`fetchedReportContents` |
| `errors` | 采集过程中的错误记录（如有） |

**产出文件一览**：

```
/tmp/monthly_overview_{groupId}.json         -- 全局概览
/tmp/goal_data_{groupId}_{goalId_1}.json     -- 目标1 数据
/tmp/goal_data_{groupId}_{goalId_2}.json     -- 目标2 轻量索引
...
/tmp/reports_{groupId}/                       -- 全局汇报池（所有目标共享，按 reportId 去重）
  {reportId_1}.json                           -- 单条汇报纯文本 + HTML 全文
  {reportId_2}.json
  ...
```

**容错**：每个目标采集完成后，检查输出的 `errors` 数组。若 `errors` 非空但 `goalDetail` 和 `reportIndex` 已获取 → 记录警告，继续下一个目标。若 `goalDetail` 缺失 → 重试一次该目标。仍失败则跳过该目标并在最终报告中注明。

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
| `reports` | 上月各类型月报列表，每条含 `reportTypeDesc`、`reportRecordId`、`title`、`charCount`、`contentPreview`（前 500 字纯文本预览）。全文存入 `/tmp/reports_{groupId}/prev_{reportRecordId}.json` |
| `evaluations` | 上月评价 Markdown 列表，每条含 `evaluationTypeDesc`（自评/上级评价）和 `evaluationMarkdown` |
| `stats` | 统计信息：报告数、评价数 |
| `errors` | 采集过程中的错误记录（如有） |

**使用方式**：
- 上月报告正文作为本月汇报的纵向对比基线
- 上月评价 Markdown 中的评分和评语可用于本月灯色判断的辅助参考
- 若上月数据为空（首月汇报），跳过此步骤，不影响后续流程
