---
name: bp-report-assembler
description: >-
  BP月报整合生成工具。从远端读取各目标的结构化JSON数据，
  AI只做全局结论生成，脚本渲染全部Markdown章节并拼接为完整月报。
  当用户需要生成或预览个人BP月度汇报、月报、自查报告时使用。
  前置条件：所有目标已通过 bp-goal-analyzer 完成分析并保存到远端。
---

# BP 月报整合生成器

从远端读取各目标的 `goal_complete.json`，AI 只做一件事——生成全局结论，其余全部由脚本渲染 + 拼接。

> **前置条件**：所有目标已通过 `bp-goal-analyzer`（Skill A）完成分析并通过 `save_task_monthly_reading` 保存到远端。
> **所有 references/ 下的文件均为强制约束**，读取后必须逐条遵守。

## 目录结构

```
references/
  rules/
    general-rules.md               -- 通用约束（启动时加载）
    validation-rules.md            -- 合规校验、语言清洗（Phase 4 加载）
  templates/
    report-template-bp-self-check.md -- 报告模板（Phase 4 校验参考）
  api-reference.md                 -- 脚本 action 速查表
scripts/
  monthly_report_api.py            -- 工具脚本
```

## 核心概念

- **远端数据驱动**：所有目标级数据从远端 API 读取（`fetch_goal_readings`），不依赖本地文件共享
- **AI 极简参与**：AI 只产出 `conclusion_data.json`（1.1 优势/短板 + 1.3 偏差点），其余全部由脚本完成
- **脚本一站式渲染**：`render_full_report` 从目标 JSON 渲染全部 Markdown 章节并自动拼接为最终报告
- **证据来源**：证据数据全部来自各目标 `goal_complete.json` 的 `evidence.reports` 字段，脚本自动合并、排序、渲染

## 输入参数

| 参数 | 说明 | 必填 |
|------|------|------|
| `groupId` | 个人节点分组 ID | 是 |
| `month` | 报告月份（YYYY-MM） | 是 |
| `employeeId` | 员工 ID | 是 |
| `employeeName` | 员工姓名（报告标题用） | 是 |
| `periodName` | BP 周期名称（报告头部用） | 是 |

## 环境变量

脚本调用前必须设置：

```bash
export BP_OPEN_API_APP_KEY="{用户提供的密钥}"
```

工作目录固定为 `/Users/openclaw-data/bp/bp_report_{groupId}_{month}/`，每次运行自动清空或创建。

## 禁止事项

1. 禁止一步生成整篇报告，必须按分步流程执行
2. 禁止对任何 ID 参数做数值转换（parseInt/Number），保持字符串原样
3. 禁止在校验通过前调用保存接口
4. 禁止跳过或简化校验流程
5. 禁止伪造 R 编号、RP 编号、汇报链接或任何数据
6. 禁止在最终报告中输出内部流程步骤编号或模板括号注释
7. 禁止混用 R 编号和 RP 编号

## 生成流程

### Phase 1: 确认参数 + 数据准备

**前置加载**：读取 [references/rules/general-rules.md](references/rules/general-rules.md) + [references/api-reference.md](references/api-reference.md)

**1a** — 确定目标员工与月份：

获取 `groupId`、`employeeId`、`employeeName`、`periodName`、`month`。`periodName` 由脚本自动从月份推断（格式：`{年份}年BP`）。

**1b** — 标记生成开始：

```bash
python3 /home/node/.openclaw/skills/bp-report-assembler/scripts/monthly_report_api.py update_report_status \
  --group_id {groupId} --month {month} --status 0
```

**1c** — 初始化工作目录：

```bash
python3 /home/node/.openclaw/skills/bp-report-assembler/scripts/monthly_report_api.py init_work_dir \
  --group_id {groupId} --month {month}
```

**1d** — 获取目标列表：

```bash
python3 /home/node/.openclaw/skills/bp-report-assembler/scripts/monthly_report_api.py collect_monthly_overview \
  --group_id {groupId} --month {month}
```

→ 输出 `overview.json`（含目标 ID 列表，供 `fetch_goal_readings` 使用）

**1e** — 从远端批量读取所有目标 JSON：

```bash
python3 /home/node/.openclaw/skills/bp-report-assembler/scripts/monthly_report_api.py fetch_goal_readings \
  --group_id {groupId} --month {month}
```

→ 输出各 `goals/{goalId}/goal_complete.json`。**检查返回值**：
- 若所有目标均被排除 → Phase 2 跳过 AI 部分，直接进入 Phase 3
- 若存在失败目标 → 报告中标注，不阻塞后续流程

**1f** — 获取上月数据（用于附录 A.3 和报告头部基线行）：

```bash
python3 /home/node/.openclaw/skills/bp-report-assembler/scripts/monthly_report_api.py collect_previous_month_data \
  --group_id {groupId} --month {上月YYYY-MM} --report_month {month}
```

→ 输出 `prev_month.json`

**输出**：`Phase 1 完成 — 已读取 {N} 个目标 JSON（{M} 参与，{K} 排除，{F} 失败）`

---

### Phase 2: AI 全局结论

AI 读取每个参与目标的 `goal_complete.json`，只需关注以下字段：
- `goalInfo.fullLevelNumber` — 目标编号
- `lamp.goalLamp` — 目标灯色
- `conclusionText` — 目标结论
- `deviations` — 偏差列表

从中综合判断生成 `conclusion_data.json`：

```json
{
  "strength": "一句话优势",
  "weakness": "一句话短板",
  "topDeviations": [
    {
      "point": "偏差点",
      "goalNumber": "P12717-2",
      "impact": "影响",
      "hypothesis": "原因假设",
      "correction": "下月纠偏方向"
    }
  ]
}
```

`topDeviations` 最多 3 条，从各目标偏差中筛选最关键的。将结果写入工作目录下的 `conclusion_data.json`。

**若所有目标均被排除**：跳过本阶段，`render_full_report` 会自动使用默认模板文案。

**输出**：`Phase 2 完成 — conclusion_data.json 已生成`

---

### Phase 3: 脚本渲染 + 拼接

```bash
python3 /home/node/.openclaw/skills/bp-report-assembler/scripts/monthly_report_api.py render_full_report \
  --group_id {groupId} --month {month} --employee_name "{employeeName}"
```

该脚本自动完成：
- 渲染 `report_header.md`（含员工姓名、周期、基线 RP 引用、证据说明、解释口径）
- 从 `conclusion_data.json` + 灯色统计渲染 `conclusion.md`（1.1/1.2/1.3）
- 从各目标 JSON 渲染 `overview_table.md`（2.1 总览表，按 fullLevelNumber 排序）
- 从各目标 JSON 渲染每个 `goal_report.md`（2.2 目标明细，含灯色判断块）
- 生成 `excluded_goals.md`（未参与目标说明）
- 从各目标 JSON 的 `evidence` 字段合并渲染 `evidence_ledger.md`（附录 A.1/A.2 按 R 编号排序 + A.3 从 `prev_month.json` 渲染）
- 生成 `chapter3.md` / `chapter4.md`（带 groupId 和 month 参数的固定链接）
- 拼接最终 `report_selfcheck.md`

**输出**：`Phase 3 完成 — report_selfcheck.md 已生成`

---

### Phase 4: 校验 + 保存

**前置加载**：读取 [references/rules/validation-rules.md](references/rules/validation-rules.md)

**4a** — 读取完整 `report_selfcheck.md`，对照 `validation-rules.md` 执行 4 项 AI 校验 + 5 条语言清洗。每条必须给出 `✅ 通过` 或 `❌ 未通过` 结论。报告的结构、格式、灯色等由脚本保证，AI 只校验自己产出的内容（1.1 结论、1.3 偏差点）和数据完整性。

**校验未全部通过时，严禁进入保存流程**。

校验失败回退：
- **全局结论问题**（1.1/1.3 内容）：修正 `conclusion_data.json`，重新执行 Phase 3
- **格式/灯色问题**：重新执行 Phase 3（脚本保证格式正确性）
- 同一问题最多重试 **2 次**，仍不通过则调用 `update_report_status --status 2`

**4b** — 全部通过后保存：

```bash
python3 /home/node/.openclaw/skills/bp-report-assembler/scripts/monthly_report_api.py save_openclaw_report \
  --group_id {groupId} --month {month} \
  --content_file {工作目录}/report_selfcheck.md
```

保存接口会自动将任务标记为成功，**无需再调用 `update_report_status --status 1`**。

**输出**：`Phase 4 完成 — 报告已保存到 BP 系统`

---

### 失败处理

任何步骤失败，必须立即标记：

```bash
python3 /home/node/.openclaw/skills/bp-report-assembler/scripts/monthly_report_api.py update_report_status \
  --group_id {groupId} --month {month} --status 2 --fail_reason "具体失败原因"
```

## 边界场景

| 场景 | 处理 |
|------|------|
| 所有目标均被排除 | 2.1 总览表全部 ★，2.2 不展开，1.1/1.3 用模板文案，灯色分布全 0 |
| 某目标 Skill A 失败 | `fetch_goal_readings` 生成 failed JSON，总览表标 ❌，不展开明细 |
| 上月数据为空（首月） | A.3 写"首月汇报，无上月参考基线"；报告头部基线行写"首月，无基线" |
| 远端读取 API 不可用 | 重试一次，仍失败则 `update_report_status --status 2` |
