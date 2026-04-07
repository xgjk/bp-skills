---
name: cms-bp-manager-write
description: BP 日常维护（写入更新）Skill：支持目标/成果/举措增删改与对齐承接维护（以 API 支持为准），并强制联动 BP 审计；同时保留“仅审计”独立入口。
skillcode: cms-bp-manager-write
github: https://github.com/xgjk/bp-skills/tree/main/cms-bp-manager-write
dependencies:
  - cms-auth-skills
---

# bp-manager-write — 索引

本文件提供能力边界、路由规则与使用约束。详细说明见 `references/`，实际执行见 `scripts/`。

**当前版本**: 0.1.0  
**接口版本**: v1（BP Open API，`/open-api/bp/*`）

## 能力概览（2 块能力）

- `write`：写入更新（受控确认）+ 对齐承接接入点占位
- `audit`：独立审计入口（复用 `bp-audit`）

## 统一规范

- 鉴权依赖：`cms-auth-skills/SKILL.md`
- 运行时日志/缓存/状态：统一写入工作区根目录 `.cms-log/`
- 危险操作确认：所有写操作必须二次确认
- 不编造接口：未明确 Open API 支持的写操作（编辑/删除/对齐承接修改）禁止伪造调用

## 授权依赖

所有需要鉴权的接口调用统一依赖 `cms-auth-skills`。脚本不实现登录与换 token。

## 输入完整性规则

- 写操作必须携带“定位对象所需最小输入”（如 `goalId`、`keyResultId` 等）
- 写操作必须显式二次确认（CLI：`--confirm yes`）
- 审计入口必须能定位到 `groupId/taskId` 或可搜索定位的名称

## 建议工作流（写入更新）

1. 变更前审计（Pre-Audit）
2. 形成变更方案（Plan）
3. 二次确认（Confirm）
4. 执行写入（Write）
5. 变更后复核（Post-Check）

工作流详情见：`./references/workflow/README.md`

## 脚本使用规则

- 解释器统一使用 `python3`
- 写操作必须 `--confirm yes` 才执行
- 审计默认建议输出 Markdown（节省 token），必要时再输出 JSON

## 路由与加载规则

- 默认只读本 `SKILL.md` 决定模块与脚本入口
- 写入前必须阅读工作流文档 `references/workflow/README.md`
- 审计规则与证据引用要求以复用的 `bp-audit` 能力为准

## 宪章

1. 写入更新必须强制联动审计，防止“改了但不合规/不承接”
2. 未接入接口必须明确提示并给出人工操作建议，禁止编造
3. 不在输出中泄露 `appKey`、`access-token`

## 能做什么

- 新增关键成果（KR）
- 新增关键举措（Action）
- 发送延期提醒（对外有副作用，必须二次确认）
- 仅审计（基础合规/向上对齐/向下承接/GAP）

## 不能做什么（当前阶段，避免编造能力）

- 对齐/承接关系“修改设置”如无明确 Open API 支持，禁止伪造接口；只能给出审计结论与人工操作建议。
- 目标/成果/举措的“编辑/删除”如无明确 Open API 支持，禁止伪造接口；只能给出变更方案与人工操作建议。

## 授权依赖（强制）

所有需要鉴权的接口调用统一依赖 `cms-auth-skills`。脚本不实现登录与换 token。

## 建议工作流（写入更新）

1. 只读拉取目标对象（必要时）
2. 执行审计（变更前）
3. 给出变更方案，并要求二次确认
4. 执行写入
5. 执行审计/复核（变更后）

## 模块路由表

| 用户意图（示例） | 模块 | 能力摘要 | 模块说明 | 脚本 |
|---|---|---|---|---|
| 新增关键成果/新增关键举措/发延期提醒 | `write` | 写入更新与受控确认 | `./references/write/README.md` | `./scripts/write/write_cli.py` |
| 修改对齐/承接关系（占位） | `write` | 对齐承接修改接口接入点（未接入前仅提示与收集契约） | `./references/workflow/README.md` | `./scripts/write/set_alignment.py` |
| 审计BP/检查BP质量/向上对齐/下级承接/GAP分析 | `audit` | 独立审计入口（复用 bp-audit 能力） | `./references/audit/README.md` | `./scripts/audit/audit_cli.py` |

## 能力树

```text
bp-manager-write/
├── SKILL.md
├── references/
│   ├── audit/
│   │   └── README.md
│   ├── workflow/
│   │   └── README.md
│   └── write/
│       └── README.md
└── scripts/
    ├── audit/
    │   ├── README.md
    │   └── audit_cli.py
    └── write/
        ├── README.md
        ├── bp_client.py
        ├── set_alignment.py
        └── write_cli.py
```

