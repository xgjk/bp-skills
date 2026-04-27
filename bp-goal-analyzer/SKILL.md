---
name: bp-goal-analyzer
description: >-
  BP单目标分析工具。为单个BP目标收集数据、判灯、做KR差距分析，
  生成结构化JSON并保存到远端。每次只处理一个目标，可并行运行。
  当用户需要为单个BP目标生成分析数据时使用。
---

# BP 单目标分析器

为一个 BP 目标完成：数据采集 → AI 判灯与分析 → JSON 拼装 → 校验 → 保存。

> **所有 references/ 下的文件均为强制约束**，读取后必须逐条遵守。

## 目录结构

```
references/
  rules/
    general-rules.md            -- 通用约束（流程启动时加载）
    traffic-light-rules.md      -- 灯色判断规则（Phase 2 加载）
    evidence-rules.md           -- 证据引用规则（Phase 2 加载）
  api-reference.md              -- 脚本 action 速查表与工作目录定义
scripts/
  monthly_report_api.py         -- 工具脚本
```

## 核心概念

- **单目标独立**：每次只处理一个 goalId，不依赖其他目标数据
- **AI 分步产出**：AI 产出 3 个小 JSON 片段，脚本拼装为完整 `goal_complete.json`
- **R 编号自包含**：格式 `R{目标序号}{三位序号}`（如 P3863-3 → R3001, R3002），从 `fullLevelNumber` 自动推导
- **脚本 vs AI 分工**：排除判断、黑灯判断、R 编号、灯色聚合、JSON 拼装/校验由**脚本**完成；红/黄/绿灯判断、KR 分析、目标总结由**AI**完成

## 输入参数

| 参数 | 说明 | 必填 |
|------|------|------|
| `groupId` | 个人节点分组 ID | 是 |
| `goalId` | 目标 ID | 是 |
| `month` | 报告月份（YYYY-MM） | 是 |
| `employeeId` | 员工 ID（用于证据分级） | 是 |

## 环境变量

脚本调用前必须设置：

```bash
export BP_OPEN_API_APP_KEY="{用户提供的密钥}"
export BP_GOAL_STANDALONE=1
```

`BP_GOAL_STANDALONE=1` 使工作目录切换为单目标独立模式：`/Users/openclaw-data/bp/{groupId}_{goalId}_{month}/`。

## 禁止事项

1. 禁止对任何 ID 参数做数值转换（parseInt/Number），保持字符串原样
2. 禁止伪造 R 编号、汇报链接或任何数据
3. 禁止读取其他目标的中间文件
4. 禁止跳过校验直接保存
5. 禁止一次性让 AI 产出完整 `goal_complete.json`，必须按 3 个片段分步产出

## 生成流程

### Phase 1: 脚本数据采集

**前置加载**：读取 [references/rules/general-rules.md](references/rules/general-rules.md) + [references/api-reference.md](references/api-reference.md)

**1a** — 采集目标数据：

```bash
python3 {skill_path}/scripts/monthly_report_api.py collect_goal_progress \
  --group_id {groupId} --goal_id {goalId} --month {month}
```

→ 输出 `progress.json`。**检查返回值**：
- `excluded: true` → **跳到 Phase 3 排除快速路径**
- `excluded: false` → 继续

**1b** — 采集上月数据（用于 KR 环比）：

```bash
python3 {skill_path}/scripts/monthly_report_api.py collect_previous_month_data \
  --group_id {groupId} --goal_id {goalId} --month {上月YYYY-MM} --report_month {month}
```

**1c** — 切割本目标的上月章节：

```bash
python3 {skill_path}/scripts/monthly_report_api.py split_prev_report_by_goal \
  --group_id {groupId} --goal_id {goalId} --month {month}
```

→ 输出 `prev_goal_section.md`

**1d** — 构建证据台账：

```bash
python3 {skill_path}/scripts/monthly_report_api.py build_goal_evidence \
  --group_id {groupId} --goal_id {goalId} --month {month} --employee_id {employeeId}
```

→ 输出 `goal_evidence.md` + `goal_evidence.json`

**1e** — 组装判灯材料 + 预填黑灯：

```bash
python3 {skill_path}/scripts/monthly_report_api.py build_judgment_input \
  --group_id {groupId} --goal_id {goalId} --month {month} --employee_id {employeeId}
```

→ 输出 `judgment_input_*.md` + `black_lamp_prefills.json`（若有黑灯举措）

**输出**：`Phase 1 完成 — {N}个非黑灯举措待AI判灯，{M}个黑灯已预填`

---

### Phase 2: AI 分步产出

**前置加载**：读取 [references/rules/traffic-light-rules.md](references/rules/traffic-light-rules.md) + [references/rules/evidence-rules.md](references/rules/evidence-rules.md)

#### 2a: 举措判灯 → `action_judgments.json`

检查 Phase 1e 返回的 `count`：
- `count == 0` → 所有举措黑灯，跳到 2b
- `count > 0` → AI 读取各 `judgment_input_*.md` + `traffic-light-rules.md`，逐举措判灯

**AI 写入** `action_judgments.json`：
```json
{
  "举措ID字符串": {
    "lamp": "green|yellow|red",
    "reason": "判断理由",
    "summary": "推进动作摘要 1-3 句",
    "support": "强|中|弱",
    "progress": "完成度一句话",
    "rCodes": ["R3001", "R3002"]
  }
}
```

若 `black_lamp_prefills.json` 存在，**合并**其内容到 `action_judgments.json`（不覆盖 AI 结果）。

#### 2b: KR 差距分析 → `kr_analysis.json`

检查 `progress.json` 中是否有非排除 KR：
- 无 → 写 `kr_analysis.json` 为 `[]`，跳到 2c
- 有 → AI 读取 `progress.json`（KR 部分）+ `prev_goal_section.md` + `goal_evidence.md`

**AI 写入** `kr_analysis.json`：
```json
[
  {
    "krId": "KR的ID字符串",
    "fullLevelNumber": "P12717-2.8",
    "name": "KR全称",
    "measureStandard": "衡量标准",
    "excluded": false,
    "monthlyResult": "本月结果",
    "gapToStandard": "距离衡量标准的差距",
    "momComparison": "环比上月描述",
    "evidence": "[R3001](huibao://view?id=xxx)",
    "judgmentReason": "KR判断理由"
  }
]
```

#### 2c: 灯色聚合（脚本）

```bash
python3 {skill_path}/scripts/monthly_report_api.py aggregate_lamp_colors \
  --group_id {groupId} --goal_id {goalId} --month {month}
```

→ 输出 `goal_lamp.json`

#### 2d: 目标总结 → `goal_summary.json`

AI 读取 `progress.json`（目标信息）+ `action_judgments.json` + `kr_analysis.json` + `goal_lamp.json`

**AI 写入** `goal_summary.json`：
```json
{
  "commitment": {
    "standard": "承诺口径",
    "actual": "本月实际达成",
    "gap": "差异点，无差异写'无'",
    "evidence": "[R3001](huibao://view?id=xxx)"
  },
  "deviations": [
    {
      "point": "偏差点",
      "impact": "影响",
      "hypothesis": "原因假设",
      "correction": "下月纠偏方向",
      "evidence": "[R3001](huibao://view?id=xxx)"
    }
  ],
  "conclusionText": "关键依据+关键短板/优势",
  "goalJudgmentReason": "目标级判断理由"
}
```

**输出**：`Phase 2 完成 — 3 个 AI 片段已产出`

---

### Phase 3: 拼装 + 校验 + 保存

**3a** — 拼装完整 JSON：

```bash
python3 {skill_path}/scripts/monthly_report_api.py assemble_goal_json \
  --group_id {groupId} --goal_id {goalId} --month {month}
```

→ 输出 `goal_complete.json`

**3b** — 校验：

```bash
python3 {skill_path}/scripts/monthly_report_api.py validate_goal_json \
  --group_id {groupId} --goal_id {goalId} --month {month}
```

- `valid: true` → 继续 3c
- `valid: false` → 根据 `errors` 定位问题，AI 修正对应片段 → 重新 3a → 3b（最多 2 次）
- 2 次仍失败 → 生成失败 JSON 并保存

**3c** — 保存到远端：

```bash
python3 {skill_path}/scripts/monthly_report_api.py save_task_monthly_reading \
  --task_id {goalId} --month {month} \
  --content_file {工作目录}/goal_complete.json
```

**输出**：`Phase 3 完成 — goal_complete.json 已校验通过并保存`

---

### 排除目标快速路径

当 Phase 1a 返回 `excluded: true` 时：

1. `assemble_goal_json` 自动生成排除目标的简化 JSON
2. 直接保存：

```bash
python3 {skill_path}/scripts/monthly_report_api.py assemble_goal_json \
  --group_id {groupId} --goal_id {goalId} --month {month}

python3 {skill_path}/scripts/monthly_report_api.py save_task_monthly_reading \
  --task_id {goalId} --month {month} \
  --content_file {工作目录}/goal_complete.json
```

**输出**：`目标被排除（{reason}），排除 JSON 已保存`

## 边界场景

| 场景 | 处理 |
|------|------|
| 目标不参与自查（★ 未启动） | 脚本生成排除 JSON → 直接保存 |
| 所有举措均为黑灯 | 脚本预填完成 → AI 2a 跳过 |
| 所有 KR 被排除 / KR 列表为空 | `kr_analysis.json` 空数组 → 灯色黑灯 |
| 首月无上月数据 | `prev_goal_section.md` 写"首月无基线" |
| 校验失败 | AI 修正片段 → 重新拼装 → 最多重试 2 次 |
