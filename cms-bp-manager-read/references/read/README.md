## read 模块说明（只读）

### 适用场景

用于 BP 的查询与查看类操作：查看分组 BP Markdown、搜索任务/分组、查看任务关联汇报等。

### 输入最小集（按命令不同而不同）

- 查看分组 BP：`groupId`
- 搜索分组：`periodId` + `name`
- 搜索任务：`groupId` + `name`
- 查看汇报：`taskId`
- 查看汇报（时间过滤，可选）：`businessTimeStart/businessTimeEnd/relationTimeStart/relationTimeEnd`（格式 `yyyy-MM-dd HH:mm:ss`）
- 查询月度汇报：`groupId` + `reportMonth`（格式 `YYYY-MM`）

### 输出

- 统一输出 JSON（命令行）或 Markdown（当返回内容本身为 Markdown）

### 禁止项

- 本模块禁止任何写入更新动作；如用户提出写入需求，应转交 `bp-manager-write`

