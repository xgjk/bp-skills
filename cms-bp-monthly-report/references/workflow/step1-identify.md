# Step 1 & 1.5: 确定目标员工与月份 + 标记生成开始

> 本文件为强制约束。AI 执行 Step 1 和 Step 1.5 时必须严格遵守。

---

## Step 1: 确定目标员工与月份

用户需提供：
- **目标员工**：员工姓名、employeeId 或 groupId（个人分组 ID）
- **汇报月份**：格式 `YYYY-MM`，如 `2026-03`

推荐输入协议：

```yaml
groupId: 2029384010718834690
report_month: 2026-03
```

若用户只给了姓名，通过 `bp-data-viewer` 的 `search_group_by_name` 在个人分组中按名称匹配定位。

若没有 `period_id`，通过 `bp-data-viewer` 的 `get_all_periods` 取 `status=1` 的启用周期。**注意**：`get_all_periods` 属于 `bp-data-viewer` 工具，不是本 Skill 的 `monthly_report_api.py` 脚本。

---

## Step 1.5: 标记生成开始

确定 `groupId` 和月份后，**立即**调用：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py update_report_status \
  --group_id "{groupId}" \
  --month "{YYYY-MM}" \
  --status 0
```

状态 `0=生成中`。后续任何步骤失败，都必须调用 `update_report_status --status 2 --fail_reason "失败原因"` 记录失败。
