# AGT-010 Skill Runtime 注入验收记录

日期：2026-09-07

## 完成内容

- `runtime_skill_service.select_runtime_skill` 只解析当前企业已发布且当前版本有效的 Skill；
- Skill 版本声明的工具必须仍在企业 Tool Registry 中处于 active；
- Runtime 使用的工具集合是 Skill 工具与当前主体已授权 R0 工具的交集；
- 运行规格的 instructions 由 Skill 指令和角色边界组合生成；
- `AgentRun` 的 Runtime metadata 保存 Skill 键和版本号，便于回放实际使用的能力版本；
- 未发布 Skill、停用工具和无交集工具会在 Runtime 启动前拒绝，不会进入 Codex 子进程。

## 验证

- Runtime Skill 版本解析和工具交集测试通过；
- 未知/不可运行 Skill 拒绝测试通过；
- API Ruff、mypy 通过。

## 边界

本轮只完成 Web 分身 Runtime 的 Skill 选择与注入。数字会议、经营分析、客服和外部渠道尚未迁移到 Skill Runtime；Skill 仍不授予权限，R1/R2/R3 工具继续遵循 Tool Gateway 与 Action 审批边界。
