# 工具脚本参考手册

> Skill A（bp-goal-analyzer）专用。仅列出本 skill 使用的 action。

---

## 调用方式

```bash
python3 {skill_path}/scripts/monthly_report_api.py <action> [options]
```

---

## Action 速查表

| action | 说明 | 必填参数 | 可选参数 |
|--------|------|----------|----------|
| `collect_goal_progress` | 单目标数据采集：排除判断 + 证据 Markdown + 黑灯标记 + reportId 提取 | `--group_id`、`--goal_id`、`--month` | `--output` |
| `collect_previous_month_data` | 采集上月完整报告 + 评价 | `--group_id`、`--month`（上月） | `--report_month`（当月）、`--output` |
| `split_prev_report_by_goal` | 从上月完整报告切割出本目标章节 | `--group_id`、`--goal_id`、`--month` | — |
| `build_goal_evidence` | 构建证据台账 + R 编号分配（`R{目标序号}{三位序号}`） | `--group_id`、`--goal_id`、`--month`、`--employee_id` | — |
| `build_judgment_input` | 组装判灯材料包 + 预填黑灯举措 | `--group_id`、`--goal_id`、`--month`、`--employee_id` | — |
| `aggregate_lamp_colors` | 举措灯色 → 目标灯色聚合 | `--group_id`、`--goal_id`、`--month` | — |
| `assemble_goal_json` | 从 3 个 AI 片段 + 脚本数据拼装 `goal_complete.json` | `--group_id`、`--goal_id`、`--month` | — |
| `validate_goal_json` | 校验 `goal_complete.json`（13 项规则） | `--group_id`、`--goal_id`、`--month` | — |
| `save_task_monthly_reading` | 保存 JSON 到远端 | `--task_id`、`--month` | `--content_file`（二选一）、`--content`（二选一） |

---

## 工作目录

```
/Users/openclaw-data/bp/{groupId}_{goalId}_{month}/
  progress.json                    # collect_goal_progress
  prev_goal_section.md             # split_prev_report_by_goal
  goal_evidence.md                 # build_goal_evidence
  goal_evidence.json               # build_goal_evidence
  judgment_input_{actionId}.md     # build_judgment_input
  black_lamp_prefills.json         # build_judgment_input（黑灯预填）
  action_judgments.json            # AI Phase 2a
  kr_analysis.json                 # AI Phase 2b
  goal_lamp.json                   # aggregate_lamp_colors
  goal_summary.json                # AI Phase 2d
  goal_complete.json               # assemble_goal_json（最终输出）
```

每次运行前：目录不存在则创建，已存在则清空目录下所有文件。

---

## 环境配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BP_OPEN_API_APP_KEY` | API 密钥（**必填**） | 无（用户提供） |
| `BP_OPEN_API_BASE_URL` | API 地址 | `https://sg-al-cwork-web.mediportal.com.cn/open-api` |
