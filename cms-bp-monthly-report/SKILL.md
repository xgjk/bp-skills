---
name: bp-monthly-report
description: >-
  BP个人月度汇报生成与发送工具。基于 BP 目标结构、衡量标准和当月汇报证据，
  按分步流程生成结构固定、证据可追溯的月报初稿。
  当用户需要生成、发送或预览个人BP月度汇报、月报、自查报告、BP汇报、灯色判断时使用。
---

# BP 个人月度汇报

为 BP 系统中的个人节点生成月度汇报。核心逻辑是**先拆证据、再做判断、最后组装报告**。

> **渐进式加载**：启动时只需阅读本文件。各步骤的详细操作说明按需加载对应文件。
> **所有 references/ 下的文件均为强制约束**，读取后必须逐条遵守。

## 目录结构

```
references/
  workflow/                        -- 分步操作手册（执行对应步骤时加载）
    step1-identify.md              -- Step 1 & 1.5 详细操作
    step2-collect.md               -- Step 2 详细操作
    step3-generate.md              -- Step 3 详细操作
    step4-send.md                  -- Step 4 详细操作 + 工具速查表
  rules/                           -- 判断规则与校验约束
    general-rules.md               -- 通用约束（流程启动时加载）
    traffic-light-rules.md         -- 灯色判断规则与排除规则
    evidence-rules.md              -- 证据去重、分级、归集与链接规则
    validation-rules.md            -- 合规校验、语言清洗与附录搬运
  templates/                       -- 报告模板（Step 3 加载）
    report-template-bp-self-check.md -- 报告模板与输出格式定义
  api-reference.md                 -- 工具脚本速查表与环境配置
  workflow-details.md              -- 流程索引页（指向 workflow/ 下各文件）
  changelog.md                     -- 变更记录（仅维护参考，无需加载）
scripts/
  monthly_report_api.py            -- API 工具脚本
```

## 核心概念

- **报告定位**：以"每个 BP 目标"为主线底座的自查报告，串起承诺对照→结果→举措→偏差
- **判断主轴**：先以目标维度判断是否参与自查（计划时间范围与汇报月份有无交集），目标不在范围内直接标★未启动；参与自查的目标再对其下关键举措逐个判灯，KR 只做差距分析不判灯
- **灯色层级**：目标级排除判断（★未启动 / 参与）→ 举措级独立判灯 → 目标级从举措聚合（红→黄→黑→绿）→ KR 级不判灯
- **证据编号**：当月 `R{MM}{序号}`（如 `R0301`），上月 `RP{序号}`（如 `RP01`），严禁混用

## 禁止事项

1. 禁止一步生成整篇报告，必须走 Step 1 → 1.5 → 2 → 3 → 4 的分步流程
2. 禁止对任何 ID 参数做数值转换（parseInt/Number），保持字符串原样
3. 禁止在校验通过前调用 `send_report`
4. 禁止伪造 R 编号、RP 编号、汇报链接或任何数据
5. 禁止跳过参考文档加载直接执行 Step 3
6. 禁止在最终报告中输出内部流程步骤编号（Step 3a/3b 等）或模板括号注释
7. 禁止混用 R 编号和 RP 编号
8. 禁止读取其他目标的 goal_section 或 goal_cards 文件（上下文隔离）

## 输出风格

- 语言：中文，正式商务风格，句式自然（主谓宾完整）
- 禁止空值直出（如"无数据"），必须转为有引导意义的自然语句
- 禁止技术字段泄漏（reportId、taskId 等 API 字段名不得出现在报告正文）
- 所有灯色使用 HTML span 标签渲染（详见 templates/report-template-bp-self-check.md）
- 证据引用统一使用 `[R编号](huibao://view?id={reportId})《汇报标题》` 格式

## 全局容错规则

- **数据采集失败**（Step 2）：检查脚本输出的 `errors` 数组。若核心数据（`goalDetail`、`uniqueReportMap`）已获取 → 记录警告，继续。若核心数据缺失 → 重试一次该步骤。仍失败则调用 `update_report_status --status 2`
- **文件不存在**：执行每个步骤前，先确认上一步的产出文件存在且非空。若不存在，回退重新执行上一步
- **校验失败回退**：以目标为粒度定位失败项，仅回退修正该目标对应章节。同一目标最多重试 2 次
- **最大重试**：任何单步最多重试 2 次，超过则标记失败并终止

## 边界场景速查表

| 场景 | 处理方式 |
|------|---------|
| 某目标无任何汇报 | 正常进入判灯流程，所有举措判黑灯 |
| 所有目标均被排除（★ 未启动） | 报告只有 1.2 灯色概览（全部★未启动）+ 附录，无第 2 章明细 |
| 目标有 KR 但无举措 | 目标灯色标黑灯，理由注明"无关键举措" |
| 上月数据采集为空（首月） | Step 2b 跳过，基线行写"首月，无基线"，RP 不分配 |
| goalDetail 中 KR 列表为空 | 该目标下无成果可分析，目标灯色判黑灯 |
| 内容聚合无法判断是否同一事项 | 默认不合并（宁可多不可少） |

## 生成流程

**禁止一步生成整篇报告。** 必须按以下步骤顺序执行，每步完成后输出进度确认。

**全局前置加载**：读取 [references/rules/general-rules.md](references/rules/general-rules.md)，贯穿 Step 1 – Step 4 的通用约束。

### Step 1: 确定目标员工与月份

**前置加载**：读取 [references/workflow/step1-identify.md](references/workflow/step1-identify.md)

获取 `groupId`、`employeeId`、`report_month`。若用户只给姓名，通过 `bp-data-viewer` 定位。

**完成后输出**：`✅ Step 1 完成 — groupId={值}, employeeId={值}, month={值}`

### Step 1.5: 标记生成开始

调用 `update_report_status --status 0` 标记"生成中"。

**完成后输出**：`✅ Step 1.5 完成 — 状态已标记为"生成中"`

### Step 2: 采集 BP 数据

**前置加载**：读取 [references/workflow/step2-collect.md](references/workflow/step2-collect.md)

1. **2a-i**: 执行 `collect_monthly_overview` → 产出 `/tmp/monthly_overview_{groupId}.json`，读取该文件获取目标列表
2. **2a-ii**: 对 goals 列表中的每个目标，执行 `collect_goal_data` → 产出 `/tmp/goal_data_{groupId}_{goalId}.json`
3. **2b**: 执行 `collect_previous_month_data`（**`--month` 传上月**，如当月 2026-03 则传 2026-02） → 产出 `/tmp/prev_month_data_{groupId}.json`。首月可跳过

**完成后输出**：`✅ Step 2 完成 — {N} 个目标数据已采集，上月数据已采集（或首月跳过）`

### Step 3: 生成月报内容

**Step 3-预备（必须在 3a 之前完成）**：读取以下四个文件：
- [references/workflow/step3-generate.md](references/workflow/step3-generate.md)
- [references/rules/traffic-light-rules.md](references/rules/traffic-light-rules.md)
- [references/rules/evidence-rules.md](references/rules/evidence-rules.md)
- [references/templates/report-template-bp-self-check.md](references/templates/report-template-bp-self-check.md)

**确认已读取后**，按 3a → 3b → 3c → 3d 顺序执行，不可跳步：

1. **3a**: 构建 BP 锚点图 → 产出 `/tmp/bp_anchor_{groupId}.md`
2. **3b**: 构建证据台账 + R/RP 编号分配（严格按 evidence-rules.md） → 产出 `/tmp/evidence_ledger_{groupId}.md`
3. **3c**: 目标级排除判断 + 逐目标循环（精读→判灯→组装） → 产出 `/tmp/excluded_goals_{groupId}.md` + `/tmp/goal_cards_{groupId}_{N}.md` + `/tmp/goal_section_{groupId}_{N}.md`
4. **3d**: 读取 [references/rules/validation-rules.md](references/rules/validation-rules.md)，拼接全局报告（含第 1–4 章 + 附录） + 语言清洗 + 16 项合规校验 → 产出 `/tmp/report_selfcheck_{groupId}.md`

**完成后输出**：`✅ Step 3 完成 — 报告已生成并通过合规校验`

### Step 4: 发送 → 保存

**前置加载**：读取 [references/workflow/step4-send.md](references/workflow/step4-send.md)

校验通过后直接发送（`send_report`），记录 `report_record_id`，再保存到 BP 系统（`save_monthly_report`）。失败时调用 `update_report_status --status 2`。

**完成后输出**：`✅ Step 4 完成 — 报告已发送并保存，report_record_id={值}`
