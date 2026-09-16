# ADR-002：首期技术栈与本地开发方式

- 状态：Accepted
- 日期：2026-08-24
- 决策任务：FND-002
- 适用范围：M0-M2 默认实现

## 背景

知行数枢首期需要同时开发管理台、模块化 API、后台同步与解析任务、数据契约和本地基础设施。团队计划主要使用 Codex 研发，因此技术栈需要满足：常见、可测试、契约清晰、跨 Windows/Linux 可重复运行，并允许知识、记忆、指标和智能体运行时按适配器替换。

当前开发机已有 Node.js 22、pnpm 9、uv 和 Python 3.11。Docker 尚未安装，因此基础设施编排文件需要先做静态验证，待 Docker 可用后完成启动验收。

## 决策

### 1. 运行时与工作区

| 范围 | 首期选择 | 版本政策 | 选择原因 |
|---|---|---|---|
| JavaScript 运行时 | Node.js 22 LTS | `>=22 <25`，CI 固定 Node 22 | 当前开发机可用，生态成熟，支持原生测试与脚本 |
| JavaScript 包管理 | pnpm 9 | 根 `packageManager` 锁定具体版本 | Workspace 快、磁盘占用低、依赖边界清楚 |
| Python 运行时 | CPython 3.11 | `>=3.11,<3.14`，首期 CI 固定 3.11 | AI/数据生态兼容性好，当前开发机已有 64 位版本 |
| Python 包与虚拟环境 | uv | 锁文件进入仓库，禁止共用系统 site-packages | 解析和安装快，适合 Codex 重建环境 |
| 仓库组织 | pnpm workspace + uv project | 根命令统一编排，不使用嵌套 Git 仓库 | 同时管理 Web、Python 和契约资产 |

`pnpm` 是用户和 CI 的统一入口；Node 脚本负责跨平台编排，`Makefile` 只提供兼容别名，不能成为 Windows 开发的唯一入口。

### 2. Web 管理台

- 框架：Next.js App Router、React、TypeScript 严格模式。
- UI：可访问的基础组件与设计 Token；是否采用具体组件库由 FND-004 决定并锁入 ADR。
- 数据访问：浏览器只调用企业 API，不直接访问数据库、知识产品或 MCP 服务。
- 状态：服务端数据优先；只有交互状态进入客户端 Store，首期不引入全局状态框架。
- 测试：组件/逻辑使用 Vitest；主流程使用 Playwright。

替代条件：若管理台变成嵌入既有门户的纯前端模块，可改为 Vite/React；若出现大量实时协同界面，再评估专门状态和实时数据方案。替换 UI 框架不得改变领域 API。

### 3. API 与后台 Worker

- API：FastAPI、Pydantic v2、SQLAlchemy 2、Alembic。
- 结构：单一部署单元内按 ADR-001 组织模块；路由、应用用例、领域对象和适配器分层。
- Worker：与 API 共用应用与领域包，但使用独立进程运行。
- 首期任务队列：PostgreSQL 任务表，使用事务、幂等键和 `FOR UPDATE SKIP LOCKED` 领取任务。
- 定时任务：Worker 内部轻量调度器，只登记任务，不直接执行业务写操作。
- 接口：OpenAPI 3、JSON Schema 2020-12、版本化事件 Envelope。
- 测试：pytest、pytest-asyncio；Ruff 负责格式和静态规则，mypy 负责边界类型检查。

选择 PostgreSQL 任务表是为了让首期同步、解析和评测任务与领域审计使用同一事务边界，同时保持 Redis 可选。以下任一情况出现时评估 Temporal：

- 工作流跨小时或跨天并需要可靠计时器；
- 多步骤外部写入需要补偿或人工中断后恢复；
- 普通重试无法清楚表达状态，或任务恢复成为持续故障来源；
- 不同 Worker 需要长期编排而不只是一次性后台任务。

若仅出现高吞吐、短耗时队列需求，可先引入 Redis/RabbitMQ Broker，而不直接升级为工作流平台。

### 4. 数据库与分析存储

- 主数据库：PostgreSQL 16。
- 向量：首期允许 pgvector 或知识产品内置向量索引；领域数据只保存稳定引用。
- 经营事实：首条数据链路仍进入 PostgreSQL 的 Raw/Staging/Core/Mart 逻辑分层。
- 时间：所有技术时间使用带时区时间戳；经营日期显式携带公司业务时区。
- 迁移：Alembic 迁移必须可重复部署；已发布迁移不回写修改，以前向修复为主。

引入 ClickHouse 或专用分析仓库前必须提供基准数据。触发评估的信号包括：

- 经营事实存储和索引成本已明显影响主业务数据库；
- 典型聚合查询经过索引、分区和预计算优化后仍无法达到已约定 SLO；
- 数据量、并发或保留周期要求独立扩缩容；
- 数据团队需要与在线配置、知识和行动记录独立发布和恢复。

OpenMetadata 和 MetricFlow 仍作为设计参考，只有资产和指标数量达到人工维护瓶颈后才成为正式运行依赖。

### 5. 对象存储

- 接口：S3 兼容对象存储抽象。
- 本地/私有化默认：MinIO。
- 内容：制度原件、聊天导出、附件、解析中间件和证据数据快照。
- PostgreSQL 只保存对象键、内容哈希、版本和元数据，不保存大文件正文。

当客户已有合规对象存储、需要跨机房容灾或 MinIO 运维成本高于复用现有平台时，通过 S3 适配器替换；领域对象键和内容哈希规则保持不变。

### 6. 缓存与消息组件

Redis 首期不是必需组件，只在以下场景启用：

- 可丢失的短期缓存可以显著降低外部 API 或模型调用；
- Web/Worker 需要短期进度广播；
- 已选择的短任务 Broker 明确依赖 Redis。

Redis 不保存制度版本、记忆审核状态、Action 审批或唯一运行记录。

### 7. 契约与代码生成

- `contracts/` 保存平台自有 JSON Schema，Schema ID 和版本不可变。
- Python 模型以契约兼容为验收目标；TypeScript 类型从 Schema 生成或通过契约测试验证。
- MCP 工具 Schema 从内部应用服务契约派生，工具实现不得包含核心业务规则。
- 数据库模型不是外部 API，不从 ORM 自动泄漏响应结构。

### 8. 本地开发命令契约

FND-003 实现以下根命令：

| 命令 | 作用 |
|---|---|
| `pnpm bootstrap` | 检查运行时并安装/同步 JavaScript 与 Python 依赖 |
| `pnpm dev` | 启动当前已实现的 Web、API 和 Worker |
| `pnpm infra:up` | Docker 可用时启动 PostgreSQL、MinIO 和可选 Redis |
| `pnpm check` | 运行格式、静态检查、契约检查和快速测试 |
| `pnpm test` | 运行全部单元与集成测试 |
| `pnpm run doctor` | 只读检查本机工具、配置和端口条件；使用 `run` 避免与 pnpm 内置命令重名 |

命令必须在 PowerShell 和 Linux shell 中使用相同名称；内部不得依赖全局 Python、`make` 或用户特定绝对路径。

### 9. 部署形态

M0-M1 默认部署单元：

```text
web
api
worker
postgresql
minio
optional knowledge provider
```

API 和 Worker 共用代码镜像但使用不同启动命令。领域模块只有在出现独立扩容、独立发布、故障隔离或明确团队所有权需求后才拆成服务。

## 未选择的方案

- 全 TypeScript 后端：对文档解析、数据处理和 AI 生态不如 Python 直接；保留作为高并发边缘服务候选。
- 首期微服务：增加部署、契约和调试成本，尚无独立扩容证据。
- Celery + Redis 作为默认队列：会让 Redis 从可选变为关键依赖，首期任务规模不足以证明必要性。
- 首期完整湖仓：无法在管理者分身试点前证明投入价值。
- 直接采用某个开源项目的数据模型：会把平台领域边界绑定到供应商内部实现。

## 影响与风险

- 两套语言带来构建和类型同步成本，因此根命令和 JSON Schema 契约是强制项。
- PostgreSQL 同时承担配置、任务和首期经营事实，需要从第一条数据链路开始记录容量与查询 SLO。
- 当前机器没有 Docker，FND-005 的动态启动验收需要在安装 Docker Desktop/Engine 后补做；这不改变编排文件和静态验证工作。
- Python 依赖必须由 uv 环境提供，禁止误用当前系统路径中的 32 位 Python 3.7。

## 验收对应

- 已选择前端、API、Worker、任务队列、数据库、对象存储、缓存、测试和工作区方案。
- 每个关键组件均给出替代或升级条件。
- 已定义跨 Windows/Linux 的统一开发命令和运行时范围。
