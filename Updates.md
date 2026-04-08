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

