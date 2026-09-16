# 生产运行依赖与切换边界

状态：implemented-slice  
对应任务：`OPS-006`

## 1. 目标

生产运行时使用 PostgreSQL、S3 兼容对象存储、Redis、Responses Provider 与 Codex Runtime。SQLite、本地文件目录和 `mock-memory`、`mock-knowledge` 只保留为开发与契约测试依赖，不进入正式运行拓扑。

## 2. 运行依赖

| 能力 | 开发兼容 | 正式运行 |
| --- | --- | --- |
| 业务数据库 | SQLite | 托管 PostgreSQL |
| 文件资产 | 本地目录 | S3 兼容对象存储 |
| 调度协调 | 单实例无锁 | Redis 短租约互斥 |
| 模型调用 | 禁用或测试端点 | 服务端 Responses Provider |
| 智能体运行 | FakeRuntime / Codex 探针 | Codex App Server + 受限 MCP 会话 |
| 业务来源 | 第三方契约沙箱 | 客户连接器 |
| 知识与记忆 Provider | 契约沙箱 | 真实端点评测后启用，否则禁用 |

PostgreSQL 继续保存经营事实、知识治理状态、角色记忆真值、权限和运行台账。文件正文、导入附件与导出物写入对象存储。Redis 只负责短时协调，不成为业务真值。

## 3. 配置和密钥

- `AI_*` 为产品配置前缀；未设置时兼容 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `OPENAI_MODEL`。
- API Key 只从进程环境或部署密钥管理器读取，不进入数据库、浏览器响应、仓库和运行文档。
- `FILE_ASSET_STORAGE_PROVIDER=s3` 时，新文件写入 `s3-object-storage`；注册表继续允许按元数据读取旧的 `local-object-storage` 资产，便于迁移窗口内回读。
- S3 可以使用显式访问密钥，也可以在云环境中使用工作负载身份；正式环境禁止由应用自动创建存储桶。
- API 与 Worker 分别配置连接池，Worker 会读取仓库根目录的本地 `.env`，避免 API 已切换而 Worker 仍连接 SQLite。

正式配置模板位于 `deploy/production/.env.example`，其中不保存真实凭据。

## 4. 数据库发布流程

正式 API 不自动执行迁移，也不装载开发种子。发布顺序固定为：

1. 在受控发布任务中注入 `DATABASE_URL`；
2. 执行 `pnpm db:status`；
3. 执行一次 `pnpm db:upgrade`；
4. 执行 `pnpm runtime:verify`；
5. 启动或滚动更新 API、Worker；
6. 检查 `/health/ready`。

若数据库版本不是 Alembic 当前 head，`/health/ready` 返回 `503 database-migrations`，负载均衡不得向该实例分发请求。

开发库从 SQLite 切换 PostgreSQL 时，先执行 `pnpm db:migrate-sqlite:dry-run`。实际替换目标库必须显式运行：

```powershell
pnpm db:migrate-sqlite -- --replace-target --confirm-target
```

迁移命令保留 SQLite 源文件不动，目标必须是非系统 PostgreSQL 数据库。目标表在单一事务中替换；失败时整体回滚。

## 5. 就绪和多实例协调

`/health/ready` 同时验证：

- PostgreSQL 可连接；
- 数据库修订等于 Alembic head；
- 当前对象存储桶可访问；
- Redis 在启用时可执行 `PING`。

会议状态调度器与自动巡店分发器使用 Redis 短租约。多 API 实例可以同时运行，但同一轮只有一个实例执行扫描；业务幂等和 PostgreSQL 约束仍是最终保护。

`pnpm runtime:verify:ai` 额外发起一次不含企业数据的结构化模型探针，检查 Responses、严格 JSON Schema 和 Token usage。

## 6. 迁移验证记录

2026-09-04 完成开发运行时切换：

- 项目独立 PostgreSQL 16 迁移到 `0049_skill_registry`；
- 旧 SQLite 的 129 张业务表、104,146 行数据迁入 PostgreSQL，源文件保留；
- 新文件资产经 API 写入并从 MinIO/S3 回读，持久化 Provider 为 `s3-object-storage`；
- Redis `PING`、调度租约和 API 就绪检查通过；
- Codex App Server 握手通过；
- 外置凭据通过进程环境注入，`gpt-5.4-mini` 严格结构化输出探针通过。

真实 PostgreSQL 同时暴露并修正了 SQLite 未执行的外键顺序、`VARCHAR(64)` 关联 ID 和失败原因长度约束。对应规则已进入种子、身份写入和迁移脚本。

2026-09-08 完成客户服务器的云数据库过渡切换：

- 应用服务器通过云联网访问腾讯云 PostgreSQL 新内网地址，TCP 和账号认证均通过；
- 创建独立 `zhixing` 业务库与无超级用户、建库、建角色、复制权限的应用角色；
- 线上稳定发布版升级到 `0049_skill_registry`，原 SQLite 的 132 张业务表、543 行数据逐表迁移，行数差异为 0；
- API 与 Worker 同时指向云库，启动自动迁移与开发种子均已关闭；
- 完成就绪检查、真实登录/会话/注销写入回归、三个 HTTP 域名入口及 API/Worker 无告警启动验收；
- SQLite 和运行配置在切换前完成受限权限备份，原数据文件保留为回滚资产。

该腾讯云实例当前为 PostgreSQL 11.22，已验证兼容服务器稳定发布版 `0049`，但不替代 PostgreSQL 16 正式基线的升级与全量回归。服务器当前仍是 `staging`，文件资产暂存本地，不因本次数据库切换宣称整体生产就绪。

## 7. 未宣称完成的外部依赖

- 客户吉客云、CRM、广告和客服数据结构尚未取得，继续使用独立测试来源验证连接器，不把它描述为真实客户接入。
- TencentDB Agent Memory、Mem0、WeKnora、RAGFlow 和 OpenViking 没有正式端点与凭据时保持禁用；契约适配器已存在，但不能把沙箱评测当成生产效果。
- 飞书消息收发、SSO 和外部系统写入仍需要客户应用凭据、回调地址和现场数据契约。
