## read 模块说明（只读）

### 适用场景

用于 BP 的查询与查看类操作：查看分组 BP Markdown、搜索任务/分组、查看任务关联汇报等。

### CLI 命令清单（只读）

以下命令均通过 `python3 scripts/read/read_cli.py <command> [options]` 执行：

- `view-my`：查看我的 BP（Markdown）
- `view-group`：查看指定分组 BP（Markdown）
- `search-groups`：按名称搜索分组
- `search-tasks`：按名称搜索任务
- `reports`：查看任务关联汇报列表（支持时间过滤）
- `monthly-report`：按分组和月份查询月度汇报
- `list-periods`：列出周期列表（可选按名称模糊搜索）

### 输入最小集（按命令不同而不同）

- 查看分组 BP：`groupId`
- 搜索分组：`periodId` + `name`
- 搜索任务：`groupId` + `name`
- 查看汇报：`taskId`
- 查看汇报（时间过滤，可选）：`businessTimeStart/businessTimeEnd/relationTimeStart/relationTimeEnd`（格式 `yyyy-MM-dd HH:mm:ss`）
- 查询月度汇报：`groupId` + `reportMonth`（格式 `YYYY-MM`）
- 列出周期：可选 `name`（用于按名称模糊搜索）

### 输出

- 统一输出 JSON（命令行）或 Markdown（当返回内容本身为 Markdown）

### 禁止项

- 本模块禁止任何写入更新动作；如用户提出写入需求，应转交 `bp-manager-write`

