# 工具脚本参考手册

> 本文件汇总 `monthly_report_api.py` 全部 action 及环境配置，供所有步骤查阅。

---

## 调用方式

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py <action> [options]
```

---

## Action 速查表

| action | 说明 | 必填参数 | 可选参数 |
|--------|------|----------|----------|
| `collect_monthly_overview` | 采集全局概览（Step 2a-i） | `--group_id`、`--month` | `--output` |
| `collect_goal_data` | 按目标采集精简结构+汇报索引（Step 2a-ii）。输出轻量 JSON（含 `goalDetail`、`reportIndex`、`reports` 引用），汇报全文写入 `/tmp/reports_{groupId}/` | `--group_id`、`--goal_id`、`--month` | `--output` |
| `collect_monthly_data` | [旧版] 一次性采集全量数据到单个 JSON。**仅作历史兼容保留，新流程禁止调用** | `--group_id`、`--month` | `--output` |
| `collect_previous_month_data` | 采集上月汇报+评价作为参考基线。汇报内容只保留前 500 字预览，全文写入 `/tmp/reports_{groupId}/prev_{id}.json` | `--group_id`、`--month`（上月YYYY-MM） | `--output` |
| `get_report_content` | 获取单条汇报原始内容（直接调 API） | `--report_id` | 无 |
| `get_report_text` | 从本地汇报池读取单条汇报纯文本全文（Step 3c 按需精读时使用）。优先读本地缓存，未命中则回退调 API | `--group_id`、`--report_id` | 无 |
| `save_draft` | 保存汇报草稿（工作协同） | `--receiver_emp_id`、`--title`、`--content_file` | `--sender_id`（一般无需指定，脚本自动通过接收人 empId 匹配对应企业的 AI 助理） |
| `save_monthly_report` | 保存月报到 BP 系统 | `--group_id`、`--month`、`--content_file`、`--report_record_id` | 无 |
| `update_report_status` | 更新月报生成状态（0=生成中, 1=成功, 2=失败） | `--group_id`、`--month`、`--status` | `--fail_reason`（status=2 时必填） |

---

## 环境配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BP_OPEN_API_APP_KEY` | 数据查询用 API 密钥（**必填**） | 无（用户提供） |
| `BP_OPEN_API_BASE_URL` | API 地址 | `https://sg-al-cwork-web.mediportal.com.cn/open-api` |

> 发送汇报的机器人 appKey 已按 sender（400001/400002/400003）内置在脚本中，根据接收人企业自动匹配，无需配置。
