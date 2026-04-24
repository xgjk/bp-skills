# 工具脚本参考手册

> 本文件汇总 `monthly_report_api.py` 全部 action 及环境配置，供所有步骤查阅。

---

## 调用方式

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py <action> [options]
```

---

## Action 速查表

| action | 阶段 | 说明 | 必填参数 | 可选参数 |
|--------|------|------|----------|----------|
| `init_work_dir` | 前置 | 初始化工作目录（清理同一 groupId+month 的历史残留） | `--group_id`、`--month` | — |
| `collect_monthly_overview` | 1 | 采集全局概览（任务树+目标列表） | `--group_id`、`--month` | `--output` |
| `collect_goal_progress` | 2-3 | 单目标：排除判断 + 证据 Markdown + 黑灯 + reportId 提取 | `--group_id`、`--goal_id`、`--month` | `--output` |
| `build_goal_evidence` | 3.5 | 构建目标级证据台账 + R 编号分配 | `--group_id`、`--goal_id`、`--month`、`--employee_id`、`--r_start_index` | `--output` |
| `build_judgment_input` | 4 | 组装判灯材料包 Markdown | `--group_id`、`--goal_id`、`--month` | — |
| `aggregate_lamp_colors` | 7 | 举措灯色 → 目标灯色聚合 | `--group_id`、`--goal_id`、`--month` | — |
| `build_evidence_ledger` | 8 | 合并所有目标证据台账为全局台账 | `--group_id`、`--month` | — |
| `assemble_report` | 15 | 拼接最终报告 | `--group_id`、`--month` | `--output` |
| `save_openclaw_report` | 16 | 保存报告内容到 `bp_openclaw_task` 并自动标记成功（调用后无需再调 `update_report_status --status 1`） | `--group_id`、`--month`、`--content_file` | — |
| `save_task_monthly_reading` | 3d+ | 保存目标月报阅读内容到系统（API 2.35 saveTaskMonthlyReading）。参与自查目标传 `--content_file`，排除目标传 `--content`。**失败不阻塞流程** | `--task_id`、`--month` | `--content_file`（二选一）、`--content`（二选一） |
| `collect_previous_month_data` | 2e | 采集上月汇报+评价 | `--group_id`、`--month`（上月） | `--report_month`（当月，用于定位工作目录）、`--output` |
| `update_report_status` | 通用 | 更新 `bp_openclaw_task` 任务状态（0=RUNNING, 1=SUCCESS, 2=FAILED）。保存成功后**无需调用**，仅用于标记开始（status=0）和失败（status=2） | `--group_id`、`--month`、`--status` | `--fail_reason`（status=2 时必填） |

---

## 工作目录结构

所有中间产物统一保存在 `/Users/openclaw-data/bp/bp_report_{groupId}_{month}/` 下（中间产物 vs 最终拼接素材详见 SKILL.md）：

```
/Users/openclaw-data/bp/bp_report_{groupId}_{month}/

  ── 中间产物（仅供后续阶段消费）──
  overview.json                          # collect_monthly_overview
  prev_month.json                        # collect_previous_month_data
  goals/
    {goalId}/
      progress.json                      # collect_goal_progress
      goal_evidence.md                   # build_goal_evidence（供AI引用+合并到全局台账）
      goal_evidence.json                 # build_goal_evidence（供脚本消费）
      judgment_input_{actionId}.md       # build_judgment_input（供AI判灯消费）
      action_judgments.json              # AI Step 3a（供脚本聚合）
      action_judgments.md                # AI Step 3a（供AI生成目标报告）
      kr_analysis.md                     # AI Step 3b（供AI生成目标报告）
      goal_lamp.json                     # aggregate_lamp_colors（供总览表和结论引用）

  ── 最终拼接素材（由 assemble_report 读取并拼入报告）──
  goals/
    {goalId}/
      goal_report.md                     # AI Step 3d → 拼入 2.2 目标明细
  excluded_goals.md                      # AI Step 3e → 拼入 2.2 尾部
  report_header.md                       # AI Step 3h → 拼入报告开头
  overview_table.md                      # AI Step 3f → 拼入 2.1 章
  conclusion.md                          # AI Step 3g → 拼入第1章
  chapter3.md                            # AI Step 3h → 拼入第3章
  chapter4.md                            # AI Step 3h → 拼入第4章
  evidence_ledger.md                     # build_evidence_ledger → 拼入附录

  ── 最终输出 ──
  report_selfcheck.md                    # assemble_report → 保存到BP系统
```

---

## 环境配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BP_OPEN_API_APP_KEY` | 数据查询用 API 密钥（**必填**） | 无（用户提供） |
| `BP_OPEN_API_BASE_URL` | API 地址 | `https://sg-al-cwork-web.mediportal.com.cn/open-api` |

> 报告保存使用 `save_openclaw_report`，通过 `BP_OPEN_API_APP_KEY` 认证，无需额外配置。
