2026-04-09 16:51 发布 `v2.1.1`：仅升级 `cms-bp-manager-write` 写入 Skill 文档版本与发布信息，补齐 updateTask + 版本历史/回退链路说明。

2026-04-09 16:51 完善 `cms-bp-manager-write/SKILL.md`：按最新 BP Open API 补齐“通用修改 updateTask”“版本历史/快照详情”“版本回退 rollback”三类基础操作的场景说明与强制安全约束（写前差异确认单、二次确认、写后复核、Long ID 字符串化、中文 URL 编码）。

2026-04-08 21:34 新增组织月报模板：新增 `cms-bp-monthly-report/references/report-template-org-bp-self-check.md`（组织BP自查，含下级BP汇总）与 `cms-bp-monthly-report/references/report-template-org-manager-bp-evaluation.md`（组织管理人评价组织月报，要求同时参考组织月报与管理人月报）。

2026-04-08 21:07 更新 `cms-bp-monthly-report/references/report-template-personal-summary.md`：在 1.1 的目标明细表新增“目标状态灯（来自报告一）”列；在第 3/4 章增加“是否需要补充完善”的提示语，提醒员工补齐遗漏信息。

2026-04-08 20:56 更新 `cms-bp-monthly-report/references/manager-review-sheet.html`：内置“员工自评示例分数”预置（无可导入 JSON 时默认展示），并新增“载入示例自评”按钮；仍支持导入/清空自评分数。

2026-04-08 20:50 更新 `cms-bp-monthly-report/references/manager-review-sheet.html`：支持导入员工自评（来自 `goal-score-sheet.html` 导出的 JSON），并在管理者为每个目标的四维滑块旁展示“员工自评”分数用于对照；支持一键清空自评分数。

2026-04-08 20:42 新增静态页面 `cms-bp-monthly-report/references/manager-review-sheet.html`：管理者对下级的“第 5/6 章”填写页，复用 `goal-score-sheet.html` 口径（四维 1~5 分、固定权重、护栏、0~100、五档评价、目标权重汇总），并提供“管理者要求文本”输入与模板复制、LocalStorage 保存、JSON 导出/清空。

2026-04-08 20:27 更新 `cms-bp-monthly-report/references/report-template-personal-summary.md`：删除第 5 章“评分元信息”小节；将第 6 章从表格填写改为管理者按固定结构输出一段文本（Top3 要求/Stop Doing/支持与节奏），并对文本内容字段提出硬性要求。

2026-04-08 20:20 简化 `cms-bp-monthly-report/references/report-template-personal-summary.md` 第 5/6 章：管理者评分改为参考 `goal-score-sheet.html` 的“四维 1~5 分 + 固定权重 + 护栏 + 0~100 + 五档评价”，管理者要求收敛为 Top3 要求 + 1 条 Stop Doing + 支持与对齐节奏。

2026-04-08 20:13 更新 `cms-bp-monthly-report/references/report-template-personal-summary.md`：新增第 5 章“管理者评分”和第 6 章“管理者要求”，以结构化表格字段输出管理者打分、目标级差异、下月硬性要求、Stop Doing、能力行为对齐与跟踪机制。

2026-04-08 20:08 更新 `cms-bp-monthly-report/references/report-template-personal-summary.md`：将“1.1 本月总体判断”改为直接展示来自报告一（BP自查）的自评得分汇总（总分/加权分）与按目标的得分×权重明细，作为本报告该段落的依据入口。

2026-04-08 20:03 更新 `cms-bp-monthly-report/references/traffic-light-rules.md`：补充黑灯规则——命中黑灯时除整改/补证据外，需同步询问用户是否需要调整 BP（目标/KR/举措/时间范围等），并在报告中记录选择与原因。

2026-04-08 19:52 优化报告一模板：在 `report-template-bp-self-check.md` 的 `2.2 目标明细` 中，将每个目标标题改为“先展示目标灯色，再展示目标名称”。

2026-04-08 19:45 重新生成“报告一/报告二”模板章节映射：报告一承接原模板第 2/3/4/5 章并按 BP目标主线组织（目标内串起承诺对照/结果/举措/偏差问题）；报告二承接原模板第 1/6/7/8 章，并将风险与资源需求按目标落点呈现；同步更新 `cms-bp-monthly-report/references/report-template.md` 索引说明。

2026-04-08 19:49 调整 `cms-bp-monthly-report/references/goal-score-sheet.html` 的目标权重口径：权重改为百分比（0~100），要求所有目标权重合计=100% 才计算本月最终得分，并在页面底部增加合计校验提示。

2026-04-08 19:41 增强 `cms-bp-monthly-report/references/goal-score-sheet.html`：为每个目标增加“目标权重”输入，并在页面底部输出按权重汇总的“本月最终得分”（加权平均 0~100）。

2026-04-08 19:28 调整 `cms-bp-monthly-report/references/goal-score-sheet.html`：目标清单改为只读（不允许新增/删除/改名，支持 URL 参数 `goals=` 传入目标列表），补充四维度 1~5 分详细解释说明，并将页面改为浅色调。

2026-04-08 19:12 新增静态页面 `cms-bp-monthly-report/references/goal-score-sheet.html`：支持按目标填写四维得分（目标达成度/推进质量/协同与影响力/风险与确定性），自动计算加权总分（0~100）与五档评价（优秀/良好/合格/不足/失控），并提供本地保存与 JSON 导出。

2026-04-08 19:00 将 `cms-bp-monthly-report/references/report-template.md` 按会议决议拆分为“三份独立报告模板”：新增 `report-template-bp-self-check.md`（报告一 BP自查）、`report-template-personal-summary.md`（报告二 个人总结）、`report-template-personal-evaluation.md`（报告三 个人评价），并将原 `report-template.md` 调整为索引入口与共用灯色规范。

2026-04-08 18:30 扩展 `cms-bp-monthly-report/references/report-template.md` 第 1 章综述段落：为“总体判断/关键进展/关注问题/下月判断”新增主观评级（优秀/良好/合格/不足）与可对照的判断标准，并将下月判断强化为可验证的客观口径（里程碑/指标/依赖与反证信号）。

2026-04-08 17:06 升级 `cms-bp-manager-write` 到 v2.1.0：补齐 2.25~2.30（addGoal/alignTask/updateTask/getHistoryPage/getHistoryDetail/rollback）并在 `update-task` 落地“字段白名单 + 差异确认单 + 写后复核”；同步更新 `SKILL.md` 说明与接口清单。

2026-04-08 16:40 更新 `cms-bp-monthly-report`：版本升级到 1.0.1；`save_monthly_report` 强制要求 `report_record_id`（与 `send_report` 返回 id 闭环）；`send_report` 增加抄送参数与“汇报人ID有误/401 限流”自动等待重试；采集汇报作者字段兼容 `writeEmpId/writeEmpName`。

2026-04-08 15:23 为 `cms-bp-manager` 增加“运行时更新检查/提示/自动更新”机制（默认检查，支持提示或自动执行 `npx clawhub@latest install cms-bp-manager --force`），并升级版本号到 v2.1.0。

2026-04-08 14:42 升级 `cms-bp-manager` 版本号到 v2.0.1（移除 BP_APP_KEY 直接依赖后的补充版本发布）。

2026-04-08 14:14 移除 `cms-bp-manager/SKILL.md` 中对 `BP_APP_KEY` 的直接依赖声明，统一通过 `cms-auth-skills` 注入鉴权信息。

2026-04-08 11:57 从仓库移除已废弃的 `cms-bp-manager-read/` 目录（只读能力已由 `cms-bp-manager` 承接），并同步更新 README 索引。

2026-04-08 11:15 基于原版 bp-manager（BP-guanfang/agent-factory/05_products/bp-manager/）完整重建 `cms-bp-manager`：迁移全部 references（api-endpoints/kangzhe-rules/maintenance/api-request）、design/design.md、setup.md、README.md；重建 scripts/bp_client.py（只读+审计，合并 UTF-8/时间过滤/月度汇报增强）与 scripts/commands.py（读+审计命令）；同步丰富 `cms-bp-manager-write` 的场景描述并升级到 v2.0.0。

2026-04-08 10:54 重组 BP manager 能力：新增 `cms-bp-manager`（读+审计统一入口）；将 `cms-bp-manager-write` 收敛为纯写入并迁移审计入口；将 `cms-bp-manager-read` 标记为废弃并指引迁移。

2026-04-07 23:24 将 `cms-bp-manager-read/SKILL.md` 的 `当前版本` 从 0.1.0 升级为 1.0.0（与本次已合入的读能力增强/修复同步）。

2026-04-07 23:04 修复并完善 `cms-bp-manager-read`：兼容非 UTF-8 终端避免中文 help 输出崩溃；显式使用 UTF-8 编码构造查询参数；修复 view-my 对 `getPersonalGroupIds` 响应 key 类型的兼容；新增 `list-periods` CLI 入口并补齐文档命令清单。

2026-04-07 19:49 参考 `xgjk/xg-skills` 的 README 结构，完善本仓库 `README.md`：补充核心约定、Skills 索引、结构说明、规范摘要与变更约束。

2026-04-07 18:42 完善 `cms-bp-manager-read`：为任务汇报分页查询新增时间范围过滤参数（businessTime/relationTime），并新增按分组+月份查询月度汇报（2.23 getMonthlyReportByMonth）的只读入口，同时同步更新相关文档与路由表。

2026-04-07 17:35 在 `cms-bp-monthly-report/SKILL.md` 标题下补充 `当前版本` 与 `接口版本` 字段，便于按协议快速定位版本信息。

2026-04-07 17:23 为 `cms-bp-monthly-report/SKILL.md` 补齐/修正协议要求的 YAML 头字段（`name`、`skillcode`、`github`、`dependencies`），并将 `github` 指向本仓库正确目录路径。

2026-04-07 17:05 修正三个 Skill 文件头部的 `github` 地址，统一指向本仓库 `xgjk/bp-skills` 的正确目录路径（替换原错误的 `xgjk/xg-skills`）。

2026-04-07 17:02 移除 `.gitattributes` 中对 `*.pyc` 的 Git LFS 过滤配置，并在 `.gitignore` 中忽略 Python 字节码与缓存目录，修复因缺少 `git-lfs` 导致的提交失败问题。

