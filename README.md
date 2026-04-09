# bp-skills 仓库（统一管理）

本仓库用于统一管理 BP 相关 Skills（技能包）源码：**每个 Skill 作为一个独立文件夹**，在内部遵循同一套 Skill 包协议规范，便于索引、校验与复用。

## 核心约定

1. **每个 Skill = 一个目录**  
   仓库根下的一级目录名即为 `skill-name`，例如：`cms-bp-manager/`、`cms-bp-manager-write/`。
2. **Skill 包内部结构固定**  
   每个 Skill 文件夹内部目录与文件结构遵循本仓库的创建与检查规范（见下文“协议规范”）。
3. **业务逻辑与界面代码分离**  
   业务脚本放在 `scripts/`，说明文档放在 `references/`，索引入口为 `SKILL.md`。

## Skills 索引（当前仓库）

以下为当前已收录的 Skills（以仓库实际目录为准）：

- `cms-bp-manager/`：**BP 管理（读 + 审计，主入口）** — 基于原版 bp-manager 重建，包含完整场景/API/数据模型/康哲规则
- `cms-bp-manager-write/`：BP 写入（纯写入，受控确认）— 新增 KR/举措/延期提醒、承接/对齐、通用修改、版本历史与回退
- `cms-bp-reporting/`：BP 报告相关（填写规范、模板管理）
- `cms-bp-monthly-report/`：个人月度汇报生成（流程化生成与工具脚本）

> 说明：新增/删除 Skill 时，请同步更新本索引。

## 仓库结构说明（简版）

```text
bp-skills/
├── README.md
├── Updates.md
└── <skill-name>/
    ├── SKILL.md
    ├── references/
    └── scripts/
```

## Skill 规范（精简版）

README 只保留最低必要规则，详细协议以 `001_CREATE_SKILLS_PROTOCOLS.md` 为准。

### 最小要求（必须）

- 每个 Skill 为独立目录，且包含 `SKILL.md`
- `SKILL.md` 只做索引与约束声明，不堆实现细节
- 模块说明写在 `references/<module>/README.md`
- 可执行脚本写在 `scripts/<module>/*.py`，并可在命令行独立运行
- 不允许残留占位符（如 `<module>` / `<action>`）

### 最小目录骨架（推荐）

```text
<skill-name>/
├── SKILL.md
├── references/
│   └── <module>/
│       └── README.md
└── scripts/
    └── <module>/
        ├── README.md
        └── <action>.py
```

## 重要约束（强制）

1. **鉴权统一依赖 `cms-auth-skills`**  
   业务 Skill 不实现登录与换 token，不硬编码敏感鉴权值。
2. **运行时文件统一落盘到工作区根目录 `.cms-log/`**  
   日志/缓存/状态不写回 Skill 包目录。
3. **对用户有副作用的动作必须二次确认**  
   新增/修改/删除/发送/同步等写操作默认拦截，只有在明确确认后才允许执行。

## 快速开始

1. 进入目标 Skill 目录，先阅读其 `SKILL.md` 了解能力边界与入口脚本。
2. 按 `SKILL.md` 的路由表进入 `references/<module>/README.md` 补齐输入。
3. 运行 `scripts/<module>/<action>.py`（通常使用 `python3`）。

## 协议规范

创建与检查 Skill 的协议规范见：`001_CREATE_SKILLS_PROTOCOLS.md`。

## 变更操作约束（强制）

为避免误改、错改、跨目录污染，所有对 Skill 的新增/更新/删除操作必须遵循：

1. **作用域强约束：必须指定目标 Skill 目录**  
   禁止未指定目录的模糊更新；涉及多 Skill 时需逐个确认范围。
2. **变更类型确认：先确认新增/更新/删除**  
   用户描述不清时不得自行猜测。
3. **删除操作高风险：必须二次确认**  
   未完成二次确认，禁止删除任何文件/目录。

## Issue 提报与协作规范（推荐）

建议统一通过 Issue 管理需求与问题，并在标题与内容中明确：

- 期望行为（Expected）与实际行为（Actual）
- 最小复现步骤（Bug 类）
- 影响范围与验收标准（DoD）

