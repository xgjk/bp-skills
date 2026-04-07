---
name: cms-bp-reporting
description: BP 报告相关 Skill：当前阶段先生成月报/季报/半年报/年报的“填写规范”（含审查输出），后续再接入“成稿报告生成”。
skillcode: cms-bp-reporting
github: https://github.com/xgjk/xg-skills/tree/main/cms-bp-reporting
dependencies:
  - cms-auth-skills
---

# bp-reporting — 索引

本文件提供能力边界、路由规则与使用约束。详细说明见 `references/`，实际执行见 `scripts/`。

**当前版本**: 0.1.0  
**接口版本**: v1（BP Open API，`/open-api/bp/*`）

## 能力概览（2 块能力）

- `reporting`：生成月报/季报/半年报/年报的“填写规范”（含审查输出）
- `templates`：空白母版模板的版本管理与查询（复用 `bp-prototype/versions/`）

## 统一规范

- 鉴权依赖：`cms-auth-skills/SKILL.md`
- 运行时日志/缓存/状态：统一写入工作区根目录 `.cms-log/`（本 Skill 不写回包内目录）
- 危险操作确认：涉及写入（如生成新模板版本目录）前必须再次确认

## 授权依赖

- 所有需要鉴权的接口调用统一依赖 `cms-auth-skills`
- 本 Skill 的脚本不实现登录与换 token，不硬编码鉴权值

## 输入完整性规则

- **ID 处理**：任何 `periodId/groupId/taskId` 必须按字符串原样传递，禁止转数字
- **生成填写规范**：必须提供 `periodId` +（`orgName` 或 `groupId`）+ `templateTypes`
- **模板查询**：必须提供 `versionDir` 才能读取指定模板文件；未指定时只能列出版本清单

## 建议工作流（简版）

1. 先读取 `SKILL.md`，确认能力边界和限制
2. 根据用户意图定位模块（`reporting` 或 `templates`）
3. 读取对应模块说明（`references/<module>/README.md`）
4. 补齐必要输入
5. 执行对应脚本

## 脚本使用规则

- 解释器统一使用 `python3`
- 任何需要鉴权的动作，鉴权值只允许由 `cms-auth-skills` 提供（或由运行时注入到 `BP_APP_KEY`）
- 输出以脚本自身 stdout 为准，不在脚本内打印敏感鉴权信息

## 路由与加载规则

- 默认只读本 `SKILL.md` 判断模块与脚本入口
- 需要理解输入/输出与约束时，再读对应模块说明 `references/<module>/README.md`
- 执行前先读对应脚本索引 `scripts/<module>/README.md`

## 宪章

1. 不承诺未接入的“成稿报告生成”（第 3 步为独立 Skill）
2. 不在输出中泄露 `appKey`、`access-token` 等敏感信息
3. 不删除任何历史模板版本目录与文件
4. 不把实现细节（完整请求字段表等）堆在 `SKILL.md`，实现细节仅在脚本中体现

## 定位

- 面向：员工、部门负责人、中心负责人、集团管理层
- 目标（当前阶段）：将“节点 BP”输出为可交付的“填写规范（Markdown）”，并提供审查结论与缺口清单
- 边界：不直接修改 BP 数据；如需补数据，仅输出补数建议与路径

## 授权依赖（强制）

所有需要鉴权的接口调用统一依赖 `cms-auth-skills`。本 Skill 的脚本不实现登录与换 token，不硬编码鉴权值。

## 建议工作流（简版）

1. 列出并选择周期
2. 列出并选择报告类型（月报/季报/半年报/年报/四套）
3. 指定组织节点（名称或 `groupId`）
4. 执行生成，输出到指定目录

## 模块路由表

| 用户意图（示例） | 模块 | 能力摘要 | 模块说明 | 脚本 |
|---|---|---|---|---|
| 列出可选周期 | `reporting` | 查询 BP 周期供选择 | `./references/reporting/README.md` | `./scripts/reporting/list_periods.py` |
| 生成月报/季报/半年报/年报填写规范 | `reporting` | 按周期+节点生成填写规范并落盘 | `./references/reporting/README.md` | `./scripts/reporting/generate_filling_guides.py` |
| 查询模板版本/列出可用模板 | `templates` | 列出 bp-prototype 版本目录下的模板清单 | `./references/templates/README.md` | `./scripts/templates/list_template_versions.py` |
| 获取指定模板文件 | `templates` | 读取并输出某版本下的模板文件内容 | `./references/templates/README.md` | `./scripts/templates/get_template_file.py` |
| 更新 BP 规范（拉取最新业务说明） | `templates` | 更新 bp-prototype 所依赖的 BP 规范文件 | `./references/templates/README.md` | `./scripts/templates/update_bp_spec.py` |
| 创建新一版空白母版模板（版本化） | `templates` | 创建新版本目录并生成四套空白母版模板（内容由 AI 推理填充） | `./references/templates/README.md` | `./scripts/templates/generate_blank_templates.py` |

## 能力树（实际目录结构）

```text
bp-reporting/
├── SKILL.md
├── references/
│   ├── reporting/
│   │   └── README.md
│   └── templates/
│       └── README.md
└── scripts/
    ├── reporting/
    │   ├── README.md
    │   ├── generate_filling_guides.py
    │   └── list_periods.py
    └── templates/
        ├── README.md
        ├── generate_blank_templates.py
        ├── get_template_file.py
        ├── list_template_versions.py
        └── update_bp_spec.py
```

