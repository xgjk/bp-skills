# Step 2: 采集 BP 数据（阶段 1-3.5）

> 本文件为强制约束。AI 执行 Step 2 的所有子步骤时必须严格遵守。

---

## 2-0: 初始化工作目录

**每次运行前必须执行。**

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py init_work_dir \
  --group_id "{groupId}" \
  --month "{YYYY-MM}"
```

工作目录结构（中间产物 vs 最终拼接素材详见 SKILL.md）：
```
/tmp/bp/bp_report_{groupId}_{month}/
  overview.json                          # Step 2a 产出
  prev_month.json                        # Step 2e 产出
  goals/
    {goalId}/
      progress.json                      # Step 2b 产出
      goal_evidence.md                   # Step 2c 产出
      goal_evidence.json                 # Step 2c 产出
      judgment_input_{actionId}.md       # Step 2d 产出
      action_judgments.json              # Step 3a AI 产出
      action_judgments.md                # Step 3a AI 产出
      kr_analysis.md                     # Step 3b AI 产出
      goal_lamp.json                     # Step 3c 脚本产出
      goal_report.md                     # Step 3d AI 产出 → 拼入最终报告
  excluded_goals.md                      # Step 3e AI 产出 → 拼入最终报告
  evidence_ledger.md                     # Step 3i 脚本产出 → 拼入最终报告
  report_header.md                       # Step 3h AI 产出 → 拼入最终报告
  overview_table.md                      # Step 3f AI 产出 → 拼入最终报告
  conclusion.md                          # Step 3g AI 产出 → 拼入最终报告
  chapter3.md                            # Step 3h AI 产出 → 拼入最终报告
  chapter4.md                            # Step 3h AI 产出 → 拼入最终报告
  report_selfcheck.md                    # Step 4a 脚本拼接 → 最终输出
```

---

## 2a: 采集全局概览

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py collect_monthly_overview \
  --group_id "{groupId}" \
  --month "{YYYY-MM}"
```

输出：`overview.json`（含 `goals` 目标摘要列表、`taskTree` 精简任务树、`stats` 统计）

---

## 2b: 逐目标采集进展

读取 `overview.json` 的 `goals` 列表，对每个目标调用：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py collect_goal_progress \
  --group_id "{groupId}" \
  --goal_id "{goalId}" \
  --month "{YYYY-MM}"
```

输出：`goals/{goalId}/progress.json`

| 关键字段 | 说明 |
|----------|------|
| `excluded` / `excludeReason` | 目标是否被排除及原因 |
| `krData` | 各 KR 的排除状态、`progressMarkdown`、`reportIds` |
| `actionData` | 各举措的排除状态、`isBlackLamp`、`progressMarkdown`、`reportIds` |
| `allReportIds` | 该目标下所有去重后的 reportId |
| `errors` | 采集过程中的错误（若有） |

**容错**：若 API 调用失败，记录到 `errors` 数组，该举措标记黑灯。goalDetail 获取失败则重试一次，仍失败则跳过该目标。

---

## 2c: 构建目标级证据台账

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

输出：`goal_evidence.md`（AI 分析时引用）+ `goal_evidence.json`（供后续脚本消费）

---

## 2d: 组装判灯材料包

为每个参与自查的非黑灯举措生成判灯材料包，供 AI 在 Step 3a 中消费。

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py build_judgment_input \
  --group_id "{groupId}" \
  --goal_id "{goalId}" \
  --month "{YYYY-MM}"
```

输出：每个举措一个 `judgment_input_{actionId}.md`

---

## 2e: 采集上月汇报与评价

`--month` 参数为上一个月，`--report_month` 传当前月份以定位工作目录。

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py collect_previous_month_data \
  --group_id "{groupId}" \
  --month "{上月YYYY-MM}" \
  --report_month "{当月YYYY-MM}"
```

输出：`prev_month.json`。若首月无上月数据，跳过此步骤。

---

## 完成后产出一览

```
/tmp/bp/bp_report_{groupId}_{month}/
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
