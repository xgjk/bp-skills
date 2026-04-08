2026-04-08 11:15

基于原版 bp-manager（路径：`BP-guanfang/agent-factory/05_products/bp-manager/`）完整重建 `cms-bp-manager` 后，需注意：

1. 原版的审计能力是"获取 Markdown → 让 AI 基于康哲规则做检查"，审计规则正文在 `references/kangzhe-rules.md`（200 行，含三层结构定义、边界规则、承接规则、质量检查清单、常见违规模式等），已完整迁移。
2. `scripts/commands.py` 的 `check-bp` 命令当前只负责拉取 BP Markdown 并返回，**深度审计逻辑依赖 AI 运行时读取 kangzhe-rules.md 后推理输出**——这不是 bug，是设计如此。
3. 原版 `bp-audit/scripts/bp-audit/bp_api.py` 的依赖问题：`cms-bp-manager-write/scripts/audit/audit_cli.py` 仍保留迁移提示脚本；如后续需要对接真正的 bp-audit 脚本，需确认该外部仓库路径。
4. 写入技能 `cms-bp-manager-write` 的 `bp_client.py` 只有写入方法（addKeyResult/addAction/sendDelayReport），与 `cms-bp-manager/scripts/bp_client.py` 的只读客户端**不共享代码**——这是有意为之，保持两个技能解耦。

---

2026-04-08 10:54

本次对 `bp-manager` 做能力重组（读/写解耦、审计回归到统一入口）时发现：

1. `cms-bp-manager-write/scripts/audit/audit_cli.py` 依赖仓库根目录下的 `bp-audit/scripts/bp-audit/bp_api.py`。
2. 当前工作区内未发现 `bp-audit/` 目录（可能是外部技能包/子模块/另一个仓库）。

解决方案：

- 新增 `cms-bp-manager` 作为"读 + 审计"统一入口，把审计 CLI 迁移到该技能内。
- `cms-bp-manager-write` 保持"纯写入"定位，但在工作流中仍要求写入前后执行审计；审计入口统一指向 `cms-bp-manager`。
- 后续如果要做到"非常完整详尽的审计报告（规则正文 + 证据口径）"，需要补齐 `bp-audit` 真实位置或将其规则文件纳入仓库（以实际情况为准），避免运行时找不到依赖脚本。
