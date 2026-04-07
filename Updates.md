2026-04-07 19:49 参考 `xgjk/xg-skills` 的 README 结构，完善本仓库 `README.md`：补充核心约定、Skills 索引、结构说明、规范摘要与变更约束。

2026-04-07 18:42 完善 `cms-bp-manager-read`：为任务汇报分页查询新增时间范围过滤参数（businessTime/relationTime），并新增按分组+月份查询月度汇报（2.23 getMonthlyReportByMonth）的只读入口，同时同步更新相关文档与路由表。

2026-04-07 17:35 在 `cms-bp-monthly-report/SKILL.md` 标题下补充 `当前版本` 与 `接口版本` 字段，便于按协议快速定位版本信息。

2026-04-07 17:23 为 `cms-bp-monthly-report/SKILL.md` 补齐/修正协议要求的 YAML 头字段（`name`、`skillcode`、`github`、`dependencies`），并将 `github` 指向本仓库正确目录路径。

2026-04-07 17:05 修正三个 Skill 文件头部的 `github` 地址，统一指向本仓库 `xgjk/bp-skills` 的正确目录路径（替换原错误的 `xgjk/xg-skills`）。

2026-04-07 17:02 移除 `.gitattributes` 中对 `*.pyc` 的 Git LFS 过滤配置，并在 `.gitignore` 中忽略 Python 字节码与缓存目录，修复因缺少 `git-lfs` 导致的提交失败问题。

