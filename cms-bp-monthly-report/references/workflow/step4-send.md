# Step 4: 保存草稿 → 保存

> 本文件为强制约束。AI 执行 Step 4 时必须严格遵守。

---

> **⚠️ 两个接口返回的 ID 含义不同，严禁混淆：**
>
> | 接口 | 返回的 `data` | 含义 | 用途 |
> |------|---------------|------|------|
> | `save_draft` | 工作汇报草稿 ID | 工作协同系统中的草稿记录 ID | **用于生成 `huibao://view?id=` 链接、传给 `save_monthly_report --report_record_id`** |
> | `save_monthly_report` | BP 月报 ID | BP 系统中的月报记录 ID | 仅供 BP 系统内部使用，**不可用于生成汇报链接** |
>
> `report_record_id` **只能**从 `save_draft` 的返回结果中获取，**严禁**使用 `save_monthly_report` 返回的 ID。

---

## 保存汇报草稿

**校验通过后直接保存草稿**，无需等待用户确认。

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py save_draft \
  --receiver_emp_id "{employeeId}" \
  --title "{员工姓名} {YYYY年M月} BP自查报告" \
  --content_file "/tmp/report_selfcheck_{groupId}.md"
```

> `--receiver_emp_id` 即目标员工的 employeeId，由用户提供。

> `--sender_id` 无需手动指定。脚本自动通过接收人的 empId 查询组织架构获取 corpId，匹配对应企业的 AI 助理。

> `save_draft` 仅将汇报保存为草稿状态，不会正式发出。如需正式发出，需后续调用草稿提交接口（`POST /work-report/draftBox/submit/{id}`）。

**立即记录**返回 JSON 中的 `report_record_id` 字段 → 记为 `report_record_id`。API 返回的 `data` 直接就是该 ID 字符串（如 `"2045377196335587329"`），脚本已自动提取到顶层 `report_record_id` 字段。

生成报告链接：`huibao://view?id={report_record_id}`

---

## 保存到 BP 系统

将 `save_draft` 获得的 `report_record_id` 传入 `--report_record_id`：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py save_monthly_report \
  --group_id "{groupId}" \
  --month "{YYYY-MM}" \
  --content_file "/tmp/report_selfcheck_{groupId}.md" \
  --report_record_id "{report_record_id}"
```

`save_monthly_report` 默认将 `generateStatus` 设为 `1=成功`，保存成功即代表流程完成，**无需再单独调用 `update_report_status --status 1`**。

> **再次提醒**：`save_monthly_report` 返回的 `data` 是 BP 月报 ID，与 `report_record_id` 无关。Step 4 完成后向用户输出的 `report_record_id` 必须是前面从 `save_draft` 获取的值。

---


