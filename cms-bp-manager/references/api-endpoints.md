# BP API 端点参考

本文档整理了 BP 系统的所有 API 端点，供 Skill 开发参考。

**数据源**: 玄关开放平台 - BP系统API说明.md

**最后更新**: 2026-04-04

---

## 接口清单

### 周期管理

| 接口 | 方法 | 路径 | 说明 |
|-----|------|------|------|
| listPeriods | GET | /bp/period/list | 查询周期列表 |
| getPeriodDetail | GET | /bp/period/{periodId}/detail | 获取周期详情 |

### 分组管理

| 接口 | 方法 | 路径 | 说明 |
|-----|------|------|------|
| listGroups | GET | /bp/group/list | 获取分组树 |
| getPersonalGroupIds | POST | /bp/group/getPersonalGroupIds | 批量查询员工个人类型分组ID |
| searchGroups | GET | /bp/group/searchByName | 按名称搜索分组 |
| getGroupMarkdown | GET | /bp/group/markdown | 获取分组完整BP的Markdown |
| batchGetKeyPositionMarkdown | POST | /bp/group/batchGetKeyPositionMarkdown | 批量获取关键岗位详情Markdown |
| getKeyPositionDetail | GET | /bp/group/getKeyPositionDetail | 获取关键岗位详情（已废弃） |

### 任务管理

| 接口 | 方法 | 路径 | 说明 |
|-----|------|------|------|
| getSimpleTree | GET | /bp/task/v2/getSimpleTree | 查询BP任务树（简要信息） |
| searchTasks | GET | /bp/task/v2/searchByName | 按名称搜索任务 |
| getTaskChildren | GET | /bp/task/children | 获取任务子树骨架 |
| pageAllReports | POST | /bp/task/relation/pageAllReports | 分页查询所有汇报 |

### 目标管理

| 接口 | 方法 | 路径 | 说明 |
|-----|------|------|------|
| listGoals | GET | /bp/goal/list | 获取目标列表 |
| getGoalDetail | GET | /bp/goal/{goalId}/detail | 获取目标详情 |
| addKeyResult | POST | /bp/task/v2/addKeyResult | 根据目标ID新增关键成果 |

### 关键成果管理

| 接口 | 方法 | 路径 | 说明 |
|-----|------|------|------|
| listKeyResults | GET | /bp/keyResult/list | 获取关键成果列表 |
| getKeyResultDetail | GET | /bp/keyResult/{keyResultId}/detail | 获取关键成果详情 |
| addAction | POST | /bp/task/v2/addAction | 根据成果ID新增关键举措 |

### 关键举措管理

| 接口 | 方法 | 路径 | 说明 |
|-----|------|------|------|
| listActions | GET | /bp/action/list | 获取关键举措列表 |
| getActionDetail | GET | /bp/action/{actionId}/detail | 获取关键举措详情 |

### 延期提醒

| 接口 | 方法 | 路径 | 说明 |
|-----|------|------|------|
| sendDelayReport | POST | /bp/delayReport/send | 发送AI延期提醒汇报 |
| listDelayReports | GET | /bp/delayReport/list | 查询AI延期提醒汇报历史 |

---

## 数据模型

### Period（周期）
- id: 周期ID
- name: 周期名称
- status: 状态（1=启用，0=未启用）

### Group（分组）
- id: 分组ID
- name: 分组名称
- type: 类型（org/personal）
- levelNumber: 层级编码
- employeeId: 员工ID（个人分组）
- parentId: 父分组ID
- childCount: 下级分组数量
- children: 子分组列表

### Goal（目标）
- id: 目标ID
- name: 目标名称
- fullLevelNumber: 目标编码
- statusDesc: 状态描述
- reportCycle: 汇报周期
- planDateRange: 计划时间范围
- taskUsers: 参与人列表
- krCount: 关键成果数量
- actionCount: 关键举措数量
- keyResults: 关键成果列表（详情）

### KeyResult（关键成果）
- id: 关键成果ID
- name: 关键成果名称
- fullLevelNumber: 编码
- statusDesc: 状态描述
- measureStandard: 衡量标准
- reportCycle: 汇报周期
- planDateRange: 计划时间范围
- taskUsers: 参与人列表
- actionCount: 关键举措数量
- actions: 关键举措列表（详情）

### Action（关键举措）
- id: 关键举措ID
- name: 关键举措名称
- fullLevelNumber: 编码
- statusDesc: 状态描述
- reportCycle: 汇报周期
- planDateRange: 计划时间范围
- taskUsers: 参与人列表

### TaskUser（任务参与人）
- taskId: 任务ID
- role: 角色（承接人/协办人/抄送人/监督人/观察人）
- empList: 员工列表

### Employee（员工）
- id: 员工ID
- name: 员工姓名

---

## 通用说明

### 认证方式
所有接口需要在请求头中携带 `appKey`：
```
appKey: YOUR_APP_KEY
```

### 响应格式
```json
{
  "resultCode": 1,      // 1表示成功
  "resultMsg": null,    // 错误信息
  "data": {}            // 响应数据
}
```

### 常用字段说明
- `fullLevelNumber`: 完整层级编码，如 A4-1.1.1
- `reportCycle`: 汇报周期，格式为 `{ruleType}+{index}`，如 `week+1`
- `planDateRange`: 计划时间范围，格式为 `yyyy-MM-dd ~ yyyy-MM-dd`

---

## 注意事项

1. **编辑和删除**：当前系统不支持编辑和删除操作，只能通过 Web UI 进行
2. **权限控制**：部分接口有数据权限校验，无权限时返回空列表
3. **周期管理**：建议每次操作前先确认当前周期
4. **性能考虑**：`getGroupMarkdown` 返回完整 BP，Token 消耗较大
