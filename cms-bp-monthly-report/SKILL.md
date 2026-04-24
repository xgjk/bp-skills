---
name: bp-monthly-report
description: >-
  BP个人月度汇报生成工具。基于 BP 目标结构、衡量标准和当月汇报证据，
  按分步流程生成结构固定、证据可追溯的月报并保存到 BP 系统。
  当用户需要生成或预览个人BP月度汇报、月报、自查报告、BP汇报、灯色判断时使用。
---

# BP 个人月度汇报

为 BP 系统中的个人节点生成月度汇报。核心逻辑是**脚本预处理 → AI 逐目标分析 → 脚本拼接报告**。

> **渐进式加载**：启动时只需阅读本文件。各步骤的详细操作说明按需加载对应文件。
> **所有 references/ 下的文件均为强制约束**，读取后必须逐条遵守。

## 目录结构

```
references/
  workflow/                        -- 分步操作手册（执行对应步骤时加载）
    step1-identify.md              -- Step 1 & 1.5 详细操作
    step2-collect.md               -- Step 2 详细操作（阶段 1-4: 数据采集+证据台账+判灯材料）
    step3-generate.md              -- Step 3 详细操作（阶段 5-14: AI 判灯+分析+报告生成）
    step4-send.md                  -- Step 4 详细操作（阶段 15-16: 拼接+保存）
  rules/                           -- 判断规则与校验约束
    general-rules.md               -- 通用约束（流程启动时加载）
    traffic-light-rules.md         -- 灯色判断规则与排除规则
    evidence-rules.md              -- 证据去重、分级、归集与链接规则
    validation-rules.md            -- 合规校验、语言清洗与附录搬运
  templates/                       -- 报告模板（Step 3 加载）
    report-template-bp-self-check.md -- 报告模板与输出格式定义
  api-reference.md                 -- 工具脚本速查表与环境配置
  changelog.md                     -- 变更记录（仅维护参考，无需加载）
scripts/
  monthly_report_api.py            -- API 工具脚本
```

## 核心概念

- **报告定位**：以"每个 BP 目标"为主线底座的自查报告，串起承诺对照→结果→举措→偏差
- **层次化分析**：举措级判灯 → KR 级差距分析 → 目标级总结报告 → 全目标拉通总结 → 拼接月报
- **脚本 vs AI 分工**：排除判断、黑灯判断、R 编号分配、灯色聚合、报告拼接由**脚本**完成；红/黄/绿灯判断、KR 差距分析、目标总结、总体结论由**AI**完成
- **灯色层级**：目标级排除判断（★未启动 / 参与）→ 举措级独立判灯 → 目标级从举措聚合（红→黄→黑→绿）→ KR 级不判灯
- **证据编号**：当月 `R{MM}{序号}`（如 `R0301`），上月 `RP{序号}`（如 `RP01`），严禁混用
- **报告是拼接的**：最终月报由脚本按固定模板从各中间产物文件拼接而成，不是一次性 AI 生成

## 工作目录

每次运行的中间产物统一保存在 `/tmp/bp/bp_report_{groupId}_{month}/` 目录下，按 groupId + month 隔离。初始化时清理同一维度的历史残留，不影响其他分组或月份。各步骤的具体产出文件见对应的 workflow 文档。

## 禁止事项

1. 禁止一步生成整篇报告，必须走 Step 1 → 1.5 → 2 → 3 → 4 的分步流程
2. 禁止对任何 ID 参数做数值转换（parseInt/Number），保持字符串原样
3. **禁止在校验通过前调用保存接口** — 4b 校验为最高优先级，必须逐条执行并输出校验报告
4. **禁止跳过或简化校验流程** — 不得用"已大致检查"替代逐条校验，必须 17 项全部给出明确结论
5. 禁止伪造 R 编号、RP 编号、汇报链接或任何数据
6. 禁止跳过参考文档加载直接执行 Step 3
7. 禁止在最终报告中输出内部流程步骤编号（Step 3a/3b 等）或模板括号注释
8. 禁止混用 R 编号和 RP 编号
9. 禁止读取其他目标的 goal_report 或中间文件（上下文隔离）

## 输出风格

- 语言：中文，正式商务风格，句式自然（主谓宾完整）
- 禁止空值直出（如"无数据"），必须转为有引导意义的自然语句
- 禁止技术字段泄漏（reportId、taskId 等 API 字段名不得出现在报告正文）
- 所有灯色使用 HTML span 标签渲染（详见 templates/report-template-bp-self-check.md）
- 正文证据引用只带编号：`[R编号](huibao://view?id={reportId})`，不附带书名号标题

## 全局容错规则

- **数据采集失败**（Step 2）：检查脚本输出的 `errors` 数组。若核心数据已获取 → 记录警告，继续。若核心数据缺失 → 重试一次。仍失败则调用 `update_report_status --status 2`
- **文件不存在**：执行每个步骤前，先确认上一步的产出文件存在且非空。若不存在，回退重新执行上一步
- **校验失败回退**：以目标为粒度定位失败项，仅回退修正该目标对应章节。同一目标最多重试 2 次
- **最大重试**：任何单步最多重试 2 次，超过则标记失败并终止

## 边界场景速查表

| 场景 | 处理方式 |
|------|---------|
| 某目标无任何汇报 | 正常进入判灯流程，所有举措判黑灯 |
| 所有目标均被排除（★ 未启动） | 报告保留 2.1 总览表（所有目标均以 ★ 未启动列入），2.2 明细为空不展开，其余章节正常输出 |
| 目标有 KR 但 KR 下无举措节点 | 目标灯色标黑灯，理由注明"无关键举措" |
| 目标参与自查但其下所有 KR/举措均被排除 | 目标仍参与自查，灯色标黑灯，理由注明"该目标下所有成果与举措计划期均未覆盖本月" |
| 上月数据采集为空（首月） | Step 2e 跳过，基线行写"首月，无基线"，RP 不分配 |
| goalDetail 中 KR 列表为空 | 该目标下无成果可分析，目标灯色判黑灯 |
| 内容聚合无法判断是否同一事项 | 默认不合并（宁可多不可少） |

## 生成流程

**禁止一步生成整篇报告。** 必须按以下步骤顺序执行，每步完成后输出进度确认。

**全局前置加载**：读取 [references/rules/general-rules.md](references/rules/general-rules.md)，贯穿 Step 1 – Step 4 的通用约束。

### Step 1: 确定目标员工与月份

**前置加载**：读取 [references/workflow/step1-identify.md](references/workflow/step1-identify.md)

获取 `groupId`、`employeeId`、`report_month`。若用户只给姓名，通过 `bp-data-viewer` 定位。

**完成后输出**：`Step 1 完成 — groupId={值}, employeeId={值}, month={值}`

### Step 1.5: 标记生成开始

调用 `update_report_status --status 0` 标记"生成中"。

**完成后输出**：`Step 1.5 完成 — 状态已标记为"生成中"`

### Step 2: 采集 BP 数据 + 构建证据台账 + 组装判灯材料

**前置加载**：读取 [references/workflow/step2-collect.md](references/workflow/step2-collect.md)

执行顺序：
1. **2-0**: `init_work_dir` 初始化工作目录
2. **2a**: `collect_monthly_overview` → 获取目标列表
3. **2b**: 对每个目标 `collect_goal_progress` → 排除判断 + 证据 Markdown + 黑灯标记
4. **2c**: 对每个参与自查的目标 `build_goal_evidence` → 证据台账 + R 编号分配
5. **2d**: 对每个参与自查的目标 `build_judgment_input` → 判灯材料包
6. **2e**: `collect_previous_month_data` → 上月参考数据

**完成后输出**：`Step 2 完成 — {N} 个目标数据已采集，{M} 个参与自查，{K} 份证据已编号`

### Step 3: 生成月报内容

**前置加载**：读取以下文件：
- [references/workflow/step3-generate.md](references/workflow/step3-generate.md)
- [references/rules/traffic-light-rules.md](references/rules/traffic-light-rules.md)
- [references/rules/evidence-rules.md](references/rules/evidence-rules.md)
- [references/templates/report-template-bp-self-check.md](references/templates/report-template-bp-self-check.md)

执行顺序（对每个目标循环 3a-3d，然后 3e-3i 全局）：
1. **3a**: 举措级判灯（AI 判红/黄/绿，脚本已标黑灯）→ `action_judgments.json/md`
2. **3b**: KR 级差距分析（AI）→ `kr_analysis.md`
3. **3c**: 目标级灯色聚合（`aggregate_lamp_colors` 脚本）→ `goal_lamp.json`
4. **3d**: 生成目标总结报告（AI）→ `goal_report.md`
5. **3d+**: 保存目标月报阅读内容（`save_task_monthly_reading` 脚本）→ 参与自查目标保存 `goal_report.md` 内容，未参与目标在 3e 后保存说明（失败不阻塞）
6. **3e**: 生成未参与目标说明 → `excluded_goals.md`
7. **3f**: 生成总览表 → `overview_table.md`
8. **3g**: 生成总体结论 → `conclusion.md`
9. **3h**: 生成报告头部 + 链接章节 → `report_header.md` + `chapter3.md` + `chapter4.md`
10. **3i**: 全局证据台账合并（`build_evidence_ledger` 脚本）→ `evidence_ledger.md`

**完成后输出**：`Step 3 完成 — 报告各章节已生成，待拼接`

### Step 4: 拼接报告 → 校验 → 保存

**前置加载**：读取 [references/workflow/step4-send.md](references/workflow/step4-send.md) + [references/rules/validation-rules.md](references/rules/validation-rules.md) + [references/templates/report-template-bp-self-check.md](references/templates/report-template-bp-self-check.md)

执行顺序：
1. **4a**: `assemble_report` 脚本拼接最终报告 → `report_selfcheck.md`
2. **4b**: **⚠️ 17 项合规性校验 + 5 条语言清洗（高优先级，不可跳过）**
   - 必须读取完整 `report_selfcheck.md`，逐条对照校验清单
   - 必须同时对照 `report-template-bp-self-check.md` 核查报告结构
   - 每项输出明确的通过/未通过结论，最终输出校验报告摘要
   - **校验未全部通过时，严禁进入保存流程**
3. **4c**: `save_openclaw_report` 保存到 BP 系统

**完成后输出**：`Step 4 完成 — 报告已保存到 BP 系统`
