# 通用规则

> 本文件为强制约束，补充 SKILL.md 未覆盖的运行时细节。

---

## AI 产出约束（`conclusion_data.json`）

- 使用中文，正式商务风格，句式自然（主谓宾完整）
- 禁止空值直出（如"无数据"），转为有引导意义的自然语句
- 禁止技术字段泄漏（reportId、taskId 等 API 字段名不得出现在文本中）
- `topDeviations` 中的 `goalNumber` 必须与对应 `goal_complete.json` 的 `goalInfo.fullLevelNumber` 一致

---

## 证据引用格式

- 当月证据：`[R编号](huibao://view?id={reportId})`，不附带书名号标题
- 上月参考：`[RP编号](huibao://view?id={reportRecordId})`
- R 和 RP 编号使用不同前缀，**严禁混用**
- AI 在 `conclusion_data.json` 中不需要包含证据引用，正文证据全部由脚本渲染

---

## 保存约束

- **校验通过后直接保存到 BP 系统**，无需等待用户确认
- `save_openclaw_report` 会直接写入线上数据，只有校验全部通过后才能调用
