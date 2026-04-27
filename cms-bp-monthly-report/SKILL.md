---
name: bp-report-assembler
description: >-
  BP月报整合生成工具。从远端读取各目标的结构化JSON数据，
  AI只做全局结论生成，脚本渲染全部Markdown章节并拼接为完整月报。
  当用户需要生成或预览个人BP月度汇报、月报、自查报告时使用。
  前置条件：所有目标已通过 bp-goal-analyzer 完成分析并保存到远端。
---

# BP 月报整合生成器（Skill B）

从远端读取各目标的 `goal_complete.json`，AI 只做一件事——生成全局结论，其余全部由脚本渲染 + 拼接。

> **前置条件**：所有目标已通过 `bp-goal-analyzer`（Skill A）完成分析并通过 `save_task_monthly_reading` 保存到远端。
> **渐进式加载**：启动时只需阅读本文件。各步骤的详细操作按需加载对应文件。
> **所有 references/ 下的文件均为强制约束**，读取后必须逐条遵守。

## 目录结构

```
references/
  workflow/                        -- 分步操作手册
    step1-identify.md              -- Step 1 详细操作
    step4-send.md                  -- Step 4 详细操作（拼接+校验+保存）
  rules/
    general-rules.md               -- 通用约束
    validation-rules.md            -- 合规校验、语言清洗
  templates/
    report-template-bp-self-check.md -- 报告模板与输出格式定义
  api-reference.md                 -- 工具脚本速查表
scripts/
  monthly_report_api.py            -- API 工具脚本
```

## 核心概念

- **数据来源**：所有目标级数据从远端 API 读取（`fetch_goal_readings`），不依赖本地文件共享
- **AI 极简参与**：AI 只产出 `conclusion_data.json`（1.1 优势/短板 + 1.3 偏差点），其余全部由脚本完成
- **脚本一站式渲染**：`render_full_report` 脚本从目标 JSON 渲染全部 Markdown 章节并自动调用 `assemble_report` 拼接
- **A.3 上月参考**：Skill B 自己调用 `collect_previous_month_data` 获取上月报告索引 + 评价，脚本渲染到附录

## 输入参数

| 参数 | 说明 | 必填 |
|------|------|------|
| `groupId` | 个人节点分组 ID | 是 |
| `month` | 报告月份（YYYY-MM） | 是 |
| `employeeId` | 员工 ID | 是 |

## 禁止事项

1. 禁止一步生成整篇报告，必须按分步流程执行
2. 禁止对任何 ID 参数做数值转换（parseInt/Number），保持字符串原样
3. **禁止在校验通过前调用保存接口**
4. **禁止跳过或简化校验流程**
5. 禁止伪造 R 编号、RP 编号、汇报链接或任何数据
6. 禁止在最终报告中输出内部流程步骤编号或模板括号注释
7. 禁止混用 R 编号和 RP 编号

## 输出风格

- 语言：中文，正式商务风格，句式自然（主谓宾完整）
- 禁止空值直出（如"无数据"），必须转为有引导意义的自然语句
- 禁止技术字段泄漏（reportId、taskId 等 API 字段名不得出现在报告正文）
- 所有灯色使用 HTML span 标签渲染（详见 templates/report-template-bp-self-check.md）
- 正文证据引用只带编号：`[R编号](huibao://view?id={reportId})`

## 全局容错规则

- **远端读取失败**：`fetch_goal_readings` 会为失败目标生成 `failed` JSON，报告中标注"数据生成失败"
- **所有目标均被排除**：AI 结论步骤跳过，脚本用模板填充
- **校验失败回退**：定位失败项，修正后重新渲染。最多重试 2 次
- **最大重试**：任何单步最多重试 2 次，超过则标记失败并终止

## 生成流程

### Step 1: 确定目标员工与月份

**前置加载**：读取 [references/workflow/step1-identify.md](references/workflow/step1-identify.md)

获取 `groupId`、`employeeId`、`report_month`。若用户只给姓名，通过 `bp-data-viewer` 定位。

**完成后输出**：`Step 1 完成 — groupId={值}, employeeId={值}, month={值}`

### Step 1.5: 标记生成开始

调用 `update_report_status --status 0` 标记"生成中"。

### Step 2: 准备数据

1. **2-0**: `init_work_dir --group_id {groupId} --month {month}` 初始化工作目录
2. **2a**: `collect_monthly_overview --group_id {groupId} --month {month}` → 获取目标列表（生成 overview.json，供 fetch_goal_readings 使用）
3. **2b**: `fetch_goal_readings --group_id {groupId} --month {month}` → 从远端批量读取所有目标的 JSON

**完成后输出**：`Step 2 完成 — 已读取 {N} 个目标 JSON（{M} 参与，{K} 排除，{F} 失败）`

**分支判断**：
- 若所有目标均被排除 → 跳过 Step 3 的 AI 部分，直接进入 Step 3b
- 若存在失败目标 → 报告中标注，不阻塞后续流程

4. **2c**: `collect_previous_month_data --group_id {groupId} --month {上月YYYY-MM} --report_month {month}` → 获取上月报告索引 + 评价（用于附录 A.3）

### Step 3: AI 全局结论 + 脚本渲染

#### 3a: AI 生成全局结论 → `conclusion_data.json`

AI 读取每个参与目标的 `conclusionText`、`deviations`、`lamp` 字段（数据量极小），生成：

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

`topDeviations` 最多 3 条，从各目标偏差中筛选最关键的。

将结果写入工作目录下的 `conclusion_data.json`。

**若所有目标均被排除**：跳过此步骤，`render_full_report` 会自动使用默认模板文案。

#### 3b: 脚本一站式渲染 + 拼接

`render_full_report --group_id {groupId} --month {month}`

该脚本自动完成：
- 从各目标 JSON 渲染 `overview_table.md`（2.1 总览表）
- 从 `conclusion_data.json` + 灯色统计渲染 `conclusion.md`（1.1/1.2/1.3）
- 从各目标 JSON 渲染每个 `goal_report.md`（2.2 目标明细）
- 生成 `excluded_goals.md`（未参与目标说明）
- 从各目标 JSON 的 evidence 字段合并渲染 `evidence_ledger.md`（附录 A.1/A.2 + A.3）
- 生成 `chapter3.md` / `chapter4.md`（固定链接模板）
- 渲染 `report_header.md`
- 调用 `assemble_report` 拼接最终 `report_selfcheck.md`

**完成后输出**：`Step 3 完成 — 报告已渲染并拼接`

### Step 4: 校验 + 保存

**前置加载**：读取 [references/workflow/step4-send.md](references/workflow/step4-send.md) + [references/rules/validation-rules.md](references/rules/validation-rules.md) + [references/templates/report-template-bp-self-check.md](references/templates/report-template-bp-self-check.md)

1. **4a**: 读取完整 `report_selfcheck.md`，对照 `validation-rules.md` 逐条校验

   **校验未全部通过时，严禁进入保存流程**。根据失败项修正后重新执行 Step 3b。

2. **4b**: `save_openclaw_report --group_id {groupId} --month {month} --content_file {report_selfcheck.md路径}` 保存到 BP 系统
3. **4c**: `update_report_status --status 1` 标记成功

**完成后输出**：`Step 4 完成 — 报告已保存到 BP 系统`

## 边界场景

| 场景 | 处理方式 |
|------|---------|
| 所有目标均被排除 | 2.1 总览表全部 ★，2.2 不展开，1.1/1.3 用模板文案，灯色分布全 0 |
| 某目标 Skill A 失败 | `fetch_goal_readings` 生成 failed JSON，总览表标 ❌，不展开明细 |
| 上月数据为空（首月） | A.3 写"首月汇报，无上月参考基线" |
| 远端读取 API 不可用 | 重试一次，仍失败则 `update_report_status --status 2` |
