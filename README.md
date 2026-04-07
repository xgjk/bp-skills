# bp-skills

本仓库用于存放 BP 相关的 Skills（以 `SKILL.md` + `references/` + `scripts/` 为最小结构），覆盖只读查询、写入维护、报告生成与月报生成等能力。

## 目录结构约定（最小骨架）

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

## 重要约束

- 鉴权统一依赖 `cms-auth-skills`，业务 Skill 不实现登录与换 token。
- 运行时日志/缓存/状态统一写入工作区根目录 `.cms-log/`，不写回 Skill 包目录。
- 对用户有副作用的动作（新增/修改/删除/发送/同步等）执行前必须二次确认。

## 快速开始

1. 进入目标 Skill 目录，先阅读其 `SKILL.md` 了解能力边界与入口脚本。
2. 按 `SKILL.md` 的路由表进入对应 `references/<module>/README.md` 补齐输入。
3. 运行 `scripts/<module>/<action>.py`（通常使用 `python3`）。

## 协议规范

创建与检查 Skill 的协议规范见：`001_CREATE_SKILLS_PROTOCOLS.md`。

