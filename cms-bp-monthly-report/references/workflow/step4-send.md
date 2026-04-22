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

脚本按固定顺序拼接以下文件：

| 顺序 | 来源文件 | 章节 |
|------|---------|------|
| 1 | `report_header.md` | 报告头部 |
| 2 | `conclusion.md` | 1. 总体自查结论 |
| 3 | `overview_table.md` | 2.1 目标清单总览 |
| 4 | 各 `goals/{goalId}/goal_report.md` | 2.2 目标明细（按目标顺序） |
| 5 | `excluded_goals.md` | 未参与目标说明 |
| 6 | `chapter3.md` | 3. 年度结果预判评分 |
| 7 | `chapter4.md` | 4. 月度汇报入口 |
| 8 | `evidence_ledger.md` | 附录：证据索引 |

输出：`/tmp/bp_report_{groupId}_{month}/report_selfcheck.md`

---

## 4b: 合规性校验

**前置加载**（若尚未加载）：读取 [validation-rules.md](../rules/validation-rules.md)

对 `report_selfcheck.md` 执行 16 项合规校验清单。**全部通过后方可保存。**

**校验失败回退**：以目标为粒度定位失败项，仅回退修正该目标的 `goal_report.md`，
然后重新执行 `assemble_report`。同一目标最多重试 2 次。

---

## 4c: 保存到 BP 系统（阶段 16）

**不再通过 save_draft 发送草稿**，直接保存到 BP 系统：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py save_openclaw_report \
  --group_id "{groupId}" \
  --month "{YYYY-MM}" \
  --content_file "/tmp/bp_report_{groupId}_{month}/report_selfcheck.md"
```

保存成功后，调用 `update_report_status --status 1` 标记成功（若 API 未自动标记）。

**完成后输出**：`Step 4 完成 — 报告已保存到 BP 系统`

---

## 失败处理

若保存失败：
1. 保留 `report_selfcheck.md` 文件
2. 调用 `update_report_status --status 2 --fail_reason "保存失败: {错误信息}"`
3. 提示用户可手动重试
