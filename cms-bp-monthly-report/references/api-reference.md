# 工具脚本参考手册

> Skill B（bp-report-assembler）专用。

---

## 调用方式

```bash
python3 /home/node/.openclaw/skills/bp-report-assembler/scripts/monthly_report_api.py <action> [options]
```

---

## Action 速查表

| action | 说明 | 必填参数 | 可选参数 |
|--------|------|----------|----------|
| `init_work_dir` | 初始化工作目录 | `--group_id`、`--month` | — |
| `collect_monthly_overview` | 采集目标列表 → `overview.json` | `--group_id`、`--month` | `--output` |
| `collect_previous_month_data` | 采集上月汇报+评价 → `prev_month.json` | `--group_id`、`--month`（上月） | `--report_month`（当月）、`--output` |
| `fetch_goal_readings` | 从远端批量读取目标 JSON → `goals/{goalId}/goal_complete.json` | `--group_id`、`--month` | — |
| `render_full_report` | 一站式渲染 + 拼接 → `report_selfcheck.md` | `--group_id`、`--month` | `--employee_name`、`--period_name` |
| `save_openclaw_report` | 保存报告到 BP 系统 | `--group_id`、`--month`、`--content_file` | — |
| `update_report_status` | 更新任务状态（0=RUNNING, 1=SUCCESS, 2=FAILED） | `--group_id`、`--month`、`--status` | `--fail_reason`（status=2 时必填） |

---

## 工作目录结构

```
/Users/openclaw-data/bp/bp_report_{groupId}_{month}/

  ── 数据采集产物 ──
  overview.json                          # collect_monthly_overview
  prev_month.json                        # collect_previous_month_data
  goals/
    {goalId}/
      goal_complete.json                 # fetch_goal_readings

  ── AI 产出 ──
  conclusion_data.json                   # AI Phase 2（全局结论）

  ── 脚本渲染产物（render_full_report 自动生成）──
  report_header.md
  overview_table.md
  conclusion.md
  goals/{goalId}/goal_report.md
  excluded_goals.md
  evidence_ledger.md
  chapter3.md / chapter4.md

  ── 最终输出 ──
  report_selfcheck.md                    # render_full_report → 保存到 BP 系统
```

---

## 环境配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BP_OPEN_API_APP_KEY` | API 密钥（**必填**） | 无 |
| `BP_OPEN_API_BASE_URL` | API 地址 | `https://sg-al-cwork-web.mediportal.com.cn/open-api` |
