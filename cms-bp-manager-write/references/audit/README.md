## audit 模块说明（已迁移）

### 适用场景（迁移说明）

本模块已迁移至 `cms-bp-manager` 的 `audit` 能力：

- 文档：`cms-bp-manager/references/audit/README.md`
- 脚本：`cms-bp-manager/scripts/audit/audit_cli.py`

`cms-bp-manager-write` 作为“纯写入”技能保留工作流约束：写入前后必须执行审计，但审计入口不再放在本技能内。

### 审计输出要求

- 结论必须精确引用到具体对象（编号+名称）
- 不允许使用“部分/某些/个别”等模糊指代
- 问题必须包含严重等级、原因与建议

