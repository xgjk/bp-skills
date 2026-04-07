---
name: cms-bp-manager-read
description: BP 日常维护（只读）Skill：查看周期/分组/任务树/详情/Markdown/汇报与搜索，禁止任何写入更新。
skillcode: cms-bp-manager-read
github: https://github.com/xgjk/bp-skills/tree/main/cms-bp-manager-read
dependencies:
  - cms-auth-skills
---

# bp-manager-read — 索引

本文件提供能力边界、路由规则与使用约束。详细说明见 `references/`，实际执行见 `scripts/`。

**当前版本**: 1.0.0  
**接口版本**: v1（BP Open API，`/open-api/bp/*`）

## 能力概览（1 块能力）

- `read`：查看/搜索/汇报查询等只读能力收口

## 统一规范

- 鉴权依赖：`cms-auth-skills/SKILL.md`
- 运行时日志/缓存/状态：统一写入工作区根目录 `.cms-log/`
- 本 Skill 禁止任何写入更新（含新增/修改/删除/发送提醒/修改对齐承接）

## 能做什么

- 查看我的 BP（Markdown）
- 查看指定分组 BP（Markdown）
- 按名称搜索分组/任务
- 查看任务关联汇报列表（支持按业务时间/关联时间过滤）
- 查询月度汇报（按分组+月份）
- 列出周期列表（供选择）

## 不能做什么

- 不新增/修改/删除目标/成果/举措
- 不修改对齐/承接关系
- 不发送延期提醒（属于写入副作用，归入写入 Skill）

## 授权依赖（强制）

所有需要鉴权的接口调用统一依赖 `cms-auth-skills`。脚本不实现登录与换 token。

## 输入完整性规则

- 查看我的 BP：必须提供 `employeeId`（参数或环境变量 `BP_EMPLOYEE_ID/EMPLOYEE_ID`）
- 查看分组 BP：必须提供 `groupId`
- 搜索分组：必须提供 `periodId` + `name`
- 搜索任务：必须提供 `groupId` + `name`
- 查看汇报：必须提供 `taskId`
- 查询月度汇报：必须提供 `groupId` + `reportMonth`（`YYYY-MM`）

## 建议工作流（简版）

1. 先读取 `SKILL.md`，确认只读边界
2. 根据用户意图定位模块 `read`
3. 读取模块说明 `references/read/README.md`
4. 补齐必要输入
5. 执行 `scripts/read/read_cli.py`

## CLI 命令清单（只读）

脚本：`./scripts/read/read_cli.py`

- `view-my`：查看我的 BP（Markdown）
- `view-group`：查看指定分组 BP（Markdown）
- `search-groups`：按名称搜索分组
- `search-tasks`：按名称搜索任务
- `reports`：查看任务关联汇报列表（支持时间过滤）
- `monthly-report`：按分组和月份查询月度汇报
- `list-periods`：列出周期列表（可选按名称模糊搜索）

## 脚本使用规则

- 解释器统一使用 `python3`
- 输出统一为结构化 JSON（Markdown 内容作为字段返回）
- 不在输出中泄露 `appKey`、`access-token`

## 路由与加载规则

- 默认只读本 `SKILL.md` 决定入口脚本
- 需要理解输入/输出与约束时，再读 `references/read/README.md`

## 宪章

1. 只读能力不做写入变更，避免越权与误操作
2. 对写入诉求必须转交 `bp-manager-write`
3. 不编造任何未接入的接口与字段

## 模块路由表

| 用户意图（示例） | 模块 | 能力摘要 | 模块说明 | 脚本 |
|---|---|---|---|---|
| 查看我的 BP / 查看分组 BP | `read` | 获取分组 Markdown 并输出 | `./references/read/README.md` | `./scripts/read/read_cli.py` |
| 搜索分组/任务 | `read` | 按名称模糊搜索并输出结果 | `./references/read/README.md` | `./scripts/read/read_cli.py` |
| 查看任务汇报历史（支持时间过滤） | `read` | 查询任务关联汇报分页列表并支持时间范围过滤 | `./references/read/README.md` | `./scripts/read/read_cli.py` |
| 查询月度汇报（按分组+月份） | `read` | 查询指定月份的月度汇报内容 | `./references/read/README.md` | `./scripts/read/read_cli.py` |

## 能力树

```text
bp-manager-read/
├── SKILL.md
├── references/
│   └── read/
│       └── README.md
└── scripts/
    └── read/
        ├── README.md
        ├── bp_client.py
        └── read_cli.py
```

