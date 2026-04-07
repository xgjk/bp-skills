2026-04-07 17:23 为 `cms-bp-monthly-report/SKILL.md` 补齐/修正协议要求的 YAML 头字段（`name`、`skillcode`、`github`、`dependencies`），并将 `github` 指向本仓库正确目录路径。

2026-04-07 17:05 修正三个 Skill 文件头部的 `github` 地址，统一指向本仓库 `xgjk/bp-skills` 的正确目录路径（替换原错误的 `xgjk/xg-skills`）。

2026-04-07 17:02 移除 `.gitattributes` 中对 `*.pyc` 的 Git LFS 过滤配置，并在 `.gitignore` 中忽略 Python 字节码与缓存目录，修复因缺少 `git-lfs` 导致的提交失败问题。

