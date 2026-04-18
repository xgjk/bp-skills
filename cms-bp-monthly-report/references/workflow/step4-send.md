# Step 4: 保存草稿 → 保存

> 本文件为强制约束。AI 执行 Step 4 时必须严格遵守。

---

## 保存汇报草稿

**校验通过后直接保存草稿**，无需等待用户确认。

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py save_draft \
  --receiver_emp_id "{employeeId}" \
  --title "{员工姓名} {YYYY年M月} BP自查报告" \
  --content_file "/tmp/report_selfcheck_{groupId}.md"
```

> `--employeeId` 用户提供。

> `--sender_id` 无需手动指定。脚本自动通过接收人的 empId 查询组织架构获取 corpId，匹配对应企业的 AI 助理。

> `save_draft` 仅将汇报保存为草稿状态，不会正式发出。如需正式发出，需后续调用草稿提交接口（`POST /work-report/draftBox/submit/{id}`）。

记录返回的 `data.id` → 记为 `report_record_id`，生成报告链接：`huibao://view?id={report_record_id}`

---

## 保存到 BP 系统

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py save_monthly_report \
  --group_id "{groupId}" \
  --month "{YYYY-MM}" \
  --content_file "/tmp/report_selfcheck_{groupId}.md" \
  --report_record_id "{report_record_id}"
```

`save_monthly_report` 默认将 `generateStatus` 设为 `1=成功`，保存成功即代表流程完成，**无需再单独调用 `update_report_status --status 1`**。

---

## 批量生成

1. `get_all_periods` → 获取启用周期
2. `get_group_tree --only_personal` → 获取所有个人分组
3. 遍历每个个人分组，对每人执行完整生成流程

**注意**：批量生成前必须征得用户明确同意，并告知预计耗时。
