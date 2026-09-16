# AGT-009 企业 Skill 注册与版本治理验收

日期：2026-09-04

## 交付范围

- PostgreSQL 迁移 `0049_skill_registry`：`agent_skills`、`agent_skill_versions`、`agent_skill_events`。
- API：`GET /api/v1/skills/studio`、`POST /api/v1/skills`、版本创建和发布接口。
- Web：`/console/twins/skills` Skill Studio，支持草稿、工具选择、Schema 编辑、发布和版本台账。
- 权限：`skill.registry.manage`，仅企业经营负责人和平台管理员默认拥有；Skill 不授予工具权限。

## 验证结果

- 本地 PostgreSQL 已升级至 `0049_skill_registry`，种子版本 `1.30.0` 重复执行成功。
- `services/api/tests/test_skills.py` 通过：员工拒绝、管理员读取、创建、工具引用校验、版本发布、旧版本退役和发布幂等均覆盖。
- 真实 API 验证通过：管理员创建草稿并发布 v1 返回 HTTP 200；验证数据已从本地数据库清理。
- Web TypeScript 检查和 Next.js 生产构建通过。
- Skill 发布前固定校验工具登记状态；版本事件保存企业、主体、请求 ID 和运行 ID。

## 边界

Skill Registry 是能力编排控制面，不是权限系统、知识库或数据库。当前只提供企业内部注册与版本治理；飞书/微信渠道、会议/分析/客服迁移和 R1/R2 外部写操作仍按对应任务推进。
