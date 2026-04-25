# Step 4: 拼接报告 → 保存（阶段 15-16）

> 本文件为强制约束。AI 执行 Step 4 时必须严格遵守。

---

## 4a: 拼接最终报告（阶段 15）

**脚本执行**：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py assemble_report \
  --group_id "{groupId}" \
  --month "{YYYY-MM}"
```

脚本按固定顺序拼接以下文件（均由 render 脚本预生成，格式已锁定）：

| 顺序 | 来源文件 | 章节 | 生成方式 |
|------|---------|------|---------|
| 1 | `report_header.md` | 报告头部 | `render_report_header` 脚本 |
| 2 | `conclusion.md` | 1. 总体自查结论 | `render_conclusion` 脚本 |
| 3 | `overview_table.md` | 2.1 目标清单总览 | `render_overview_table` 脚本 |
| 4 | 各 `goals/{goalId}/goal_report.md` | 2.2 目标明细 | `render_goal_report` 脚本 |
| 5 | `excluded_goals.md` | 未参与目标说明 | AI 直接输出 |
| 6 | `chapter3.md` | 3. 年度结果预判评分 | AI 直接输出 |
| 7 | `chapter4.md` | 4. 月度汇报入口 | AI 直接输出 |
| 8 | `evidence_ledger.md` | 附录：证据索引 | `build_evidence_ledger` 脚本 |

输出：`/Users/openclaw-data/bp/bp_report_{groupId}_{month}/report_selfcheck.md`

---

## 4b: 合规性校验（最高优先级 — 不可跳过、不可简化）

> **这是保存前的最后一道关卡。校验不通过，报告不保存。**

**前置加载**（若尚未加载）：读取 [validation-rules.md](../rules/validation-rules.md) + [report-template-bp-self-check.md](../templates/report-template-bp-self-check.md)

### 执行流程

1. **读取** `report_selfcheck.md` 的完整内容
2. **逐条执行** validation-rules.md 中的 **19 项校验清单**（含新增的灯色一致性、灯色分布准确性、异常灯人工确认区完整性 3 项），每条必须给出明确的 `✅ 通过` 或 `❌ 未通过` 结论
3. **执行** 5 条语言清洗规则扫描（技术字段泄漏、句式自然化、空值直出、模板括号注释、系统流程说明）
4. **输出校验报告摘要**：

```
校验结果：{通过数}/19 | 语言清洗：{通过/未通过}
❌ 未通过项：
  - 第 X 项（校验项名称）：具体问题描述
  - 第 Y 项（校验项名称）：具体问题描述
```

5. **全部通过** → 进入 4c 保存
6. **任何一项未通过** → 按下方回退规则修正

### 校验失败回退

- **目标级问题**（某个目标的子字段缺失等）：修正该目标的 `goal_report_data.json`，重新执行 `render_goal_report` + `assemble_report` + 重新校验
- **全局性问题**（总体结论内容问题、总览表内容问题等）：修正对应的 `*_data.json` 文件，重新执行对应 render 脚本 + `assemble_report` + 重新校验
- 灯色/格式问题由 render 脚本保证，通常不需要回退修正
- 同一问题最多重试 **2 次**，仍不通过则调用 `update_report_status --status 2`

---

## 4c: 保存到 BP 系统（阶段 16）

直接保存到 BP 系统：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py save_openclaw_report \
  --group_id "{groupId}" \
  --month "{YYYY-MM}" \
  --content_file "/Users/openclaw-data/bp/bp_report_{groupId}_{month}/report_selfcheck.md"
```

保存接口会自动将任务标记为成功，**无需再调用 `update_report_status --status 1`**。

**完成后输出**：`Step 4 完成 — 报告已保存到 BP 系统`

---

## 失败处理

若保存失败：
1. 保留 `report_selfcheck.md` 文件
2. 调用 `update_report_status --status 2 --fail_reason "保存失败: {错误信息}"`
3. 提示用户可手动重试
