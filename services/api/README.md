# 知行数枢 API

0067 增加 `source_mirror_pages`，显式 `projection_mode=deferred` 的同步/批量导入/周期计划独立登记采集与映射。旧请求默认 inline，旧计划回填 inline，不改变历史事实。`GET /api/v1/data-center/sources/{source_key}/mirror-pages?offset=0&limit=25` 按当前法人来源治理权限分页返回采集页和映射状态；契约见 `contracts/data/source-mirror-pages.schema.json`，不返回 Raw 内容或凭据。采集计数排除离线重放，避免同一页被当作再次外部采集。

`GET /api/v1/data-center/canonical/scope-twin?offset=0&limit=20` 返回获权组织节点及已归属店铺/仓库的来源状态。服务端以 ScopeContext v2 与规范来源血缘求交集，要求 `metric.query.execute`；单页上限 100，不返回凭据、连接地址或全来源运行计数。集团/项目/店铺数字孪生使用该投影及权威订单汇总，旧法人三维场景维持兼容。契约见 `contracts/ui/scope-twin-projection.schema.json`。

`POST /api/v1/data-center/raw-manifests/{id}/replay` 接收 `client_request_key`、`expected_content_hash`、`expected_mapping_version`，返回 202 的运行与任务标识。只重放当前已确认规范映射的 JSON 页；API 不读取归档，也不调用领星。来源运行的 manifest 查询返回 `replay_eligible` 与当前映射版本，页面使用 ConfirmDialog 入队。

Bootstrap v2 可显式声明 `read_only_tools: [query_authoritative_orders]`，逐法人登记已审阅的 R0 工具定义并纳入逐表 dry-run/漂移校验；默认不登记，未知或重复模板拒绝。该工具复用权威订单查询及当前 ScopeContext v2，调用者不能传入法人 ID 扩大范围，MCP allowlist 和权限仍逐次校验。它不会自动赋予其他角色访问权。

`GET /api/v1/data-center/canonical/orders/summary?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` 返回 `canonical-orders-v1`：业务日期闭开区间、当前 ScopeContext v2、权威订单记录数、状态计数、分原币金额、金额缺失数和来源版本血缘。要求 `metric.query.execute`，由服务端展开已获权法人/项目/店铺。包含所有订单状态，不是付款 GMV；汇率未确认时本位币为空，集团统计不执行内部交易抵销。空结果仍标记覆盖未核验，不代表已经完成全量同步。

迁移头为 `0066_source_configuration_versions`：空 PostgreSQL 与 0053 升级路径均已验证，旧组织和已有任务预算保持不变。`GET/PUT /api/v1/data-center/authority-assignments` 管理项目、来源实例与事实族的权威指派；写入要求版本和项目治理权限。规范事实 `orders`、`after_sales`、`inventory`、`fulfillments` 支持 `authoritative_only=true`；这仍不代表旧指标层已完成集团合并。履约列表返回出库明细、原币运费和 Raw 血缘，同时过滤获权店铺与仓库；来源时区未确认时不填 UTC。后台任务 API 分别返回执行轮次、正常续跑次数和已提交进度。

来源读取返回 `version`，编辑/停用 PATCH 必须提供 `expected_version`；版本冲突返回 409，缺少版本返回 422。Web 与 API 应同时升级。运行列表返回入队时的 `source_version`，历史运行为空；它不是秘密版本，Token 刷新和健康状态更新不改变配置版本。`scripts/verify_source_configuration.py --database-url <isolated-loopback-postgresql-url>` 使用固定合成测试主体验证双请求并发冲突，只允许 loopback 的 test/verify 数据库。

来源分批导入：`POST /api/v1/data-center/sources/{source_key}/imports` 接收版本化资源选择与时间窗，返回 202/queued 父运行；单批最多 128 个资源/时间分区，所有任务同事务入队。`GET/POST .../schedules` 和 `PUT .../schedules/{id}?version=...` 管理周期采集；默认暂停，版本冲突返回 409，Worker 独立检查到期计划。订单 UTC 增量只有成功批次才推进水位，其他支持资源按当前快照采集。

首期为 FastAPI 模块化单体。当前提供平台健康状态、模块注册表、可迁移的企业数据接入底座和数据库驱动的数字孪生查询。领星来源台账从迁移 0054 建立，0055 增加范围快照、资源运行和 Raw 追踪元数据。

```powershell
uv sync --project services/api
uv run --directory services/api uvicorn zhixing_api.main:app --app-dir src --reload
uv run --directory services/api pytest
```

数据库生命周期命令：

```powershell
pnpm db:status
pnpm db:upgrade
pnpm db:seed
$env:DATABASE_URL = "sqlite+pysqlite:///var/local_test.db"
pnpm db:rebuild:test
```

`db:rebuild:test` 会删除并重建目标结构，只允许数据库名称或 SQLite 文件名包含 `test` 或 `verify`。种子清单位于 `seeds/`，同一版本的内容校验和发生变化时会拒绝运行。

路由：

- `GET /health/live`
- `GET /health/ready`
- `GET /api/v1/platform/modules`
- `GET /api/v1/data-center/overview`
- `POST /api/v1/data-center/sources/mock-commerce/sync`
- `POST /api/v1/data-center/sources`
- `GET /api/v1/data-center/sources/{source_key}/resources`
- `GET /api/v1/data-center/sources/{source_key}/checkpoints`
- `POST /api/v1/mcp/sessions`
- `GET /api/v1/tools/catalog`
- `POST /api/v1/tools/{tool_key}/invoke`

除健康检查和登录外，产品路由使用 HttpOnly 会话或受信 Bearer 会话解析数据库 `ActorContext`。开发与测试环境可使用 `X-Zhixing-Demo-Actor` 选择种子身份，生产环境不会接受该身份头。数据中心管理接口要求企业范围，指标、经营事实和客户查询按企业或门店范围授权；来源同步要求 `source.manage`，菜单可见性不替代 API 检查。

自动巡店内部执行入口不接受用户会话或客户端 ActorContext。它只接受当前 Worker 领取任务时得到的一次性执行令牌，并与数据库中的 Worker、任务追踪、发起人快照、权限声明和目标范围匹配；实际分析和行动提议仍按发起人的当前数据库权限重新授权。

MCP 会话由已登录主体签发，固定客户端、工具白名单、可选范围和可选 AgentRun；令牌只返回一次且数据库只保存哈希。工具目录和调用入口使用 `X-Zhixing-MCP-Session` 与 `X-Zhixing-MCP-Client-ID` 解析当前数据库 ActorContext，不接受开发身份头替代 MCP 会话。每次调用重新计算权限与范围，并将会话、运行和权限版本写入工具调用台账。

再授权使用签发时的账号 ID 和法人 ID，保留当前显式拒绝。项目/店铺/仓库选择在签发和调用时重新验证并限制企业级授权；会话与 Runtime 保存 ScopeContext v2 快照供追溯，不能据此绕过当前权限检查。

未设置 `DATABASE_URL` 时使用 `var/zhixing.db`。第三方测试数据必须通过 `connectors/` 映射，不得在标准模型中直接使用供应商字段。
# 领星数据接入

根 `.env.example` 仅列出变量名且值全部留空；请按目标环境显式配置。它不是可直接启动的生产配置，不包含账号、数据库凭据或预设演示运行值。实际运行环境文件不属于版本库。

共享资源目录 `.15` 包含 38 个资源，产品标签、SPU、头程物流渠道和销售出库单等可规范映射；15 个资源保持 `schema_pending`，包括产品属性、入库单、出库单、FBM 订单和 FBA 发货单列表，仅支持 Raw。FBM 使用单店铺 sid、来源本地时间区间和 page/length 分页，不与 Amazon 订单合并。销售出库使用 page/page_size、显式来源日期区间和稳定明细 ID，不计为收入。目录覆盖不等于全部领星数据已接入。`POST /sources/{source_key}/imports` 支持多个资源和订单时间分区；页面使用统一 Dialog 入队并展示父子运行和 Raw 血缘。单资源 sync 响应只返回 run，不附带经营 overview。

领星连接器仅允许官方 HTTPS Host 与只读资源。凭据通过运行环境注入，不写入仓库；`SOURCE_ARCHIVE_PATH` 用于本地 Raw gzip 内容寻址归档。W4-W8 未确认 Schema 的资源保持 `schema_pending`。

数据库生命周期工具的 `production-bootstrap` 与 `demo-retire` 当前仅接受名称包含 `test` 或 `verify` 的隔离数据库，默认 dry-run。执行必须同时提供 `--execute --confirm-test-database --backup-id <备份标识> --plan-hash <预检哈希>`；领域入口也校验相同门禁。预检输出逐表实际影响与计划哈希，计数/身份变化要求重新预检，不自动覆盖已有账号或授权。

初始化 manifest v1 仅建组织；v2 通过严格 Schema 定义集团、法人、业务单元、角色权限模板及至少两个管理员。结构示例见 `tests/fixtures/bootstrap-formal-synthetic.json`，仅为合成测试数据。管理员密码只使用 `password_env` 引用运行环境中以 `BOOTSTRAP_` 开头、`_PASSWORD` 结尾的变量；dry-run 不读取密码，重复执行不读取或重置已有密码。未知字段（包括内联 password/secret）会被拒绝。不会调用演示种子创建正式账号。

`scripts/verify_formal_bootstrap.py --database-url <显式本地 PostgreSQL 隔离库>` 验证合成集团、两个法人、三个业务单元和两个管理员的真实密码登录及跨法人授权；它拒绝非 loopback 数据库，不读取默认数据库 URL，不调用任何外部业务接口。数据库需已备份或为空的专用验证库。
# DAT-011 范围与来源治理接口

`GET /api/v1/data-center/source-operations` 是独立来源运维读模型，要求当前法人 source.manage 授权，显式返回治理法人和 ScopeContext 快照；仅包含来源、资源质量数量、Raw 接收计数和父运行，不携带经营指标、客户或孪生场景。契约见 `contracts/data/source-operations.schema.json`。来源页面用此接口替代旧 overview，并统一从资源台账入队。

`GET /api/v1/governance` 返回主体获权的组织目录；集团、法人、业务单元、成员关系、合并口径通过对应治理接口修改。集团变更另查集团授权，业务单元编辑要求 expected_version，停用/撤销使用确认操作。成员关系不会自动复制角色权限。

`POST /api/v1/context/switch` 校验并保存 ScopeContext v2 选择。`GET /api/v1/data-center/canonical/orders` 与 `inventory` 按受信法人、项目、店铺、仓库选择分页查询，金额以原币 Decimal 表示；缺少汇率证据时本位币金额为空。来源绑定审核同步更新目录归属；已经关联事实的对象不能直接跨项目重新分配。

旧指标、经营事实、客户查询和分析请求同时校验当前选择，项目/店铺选择不能调用全法人查询。单店铺 AI 指标上下文默认采用选中的店铺；尚未实现的集团合并查询不能降级成当前法人数据。ERP 用户目录仅作为来源实体，经归属审核使用，不会创建平台账号或转换 ERP 权限。

`POST /api/v1/data-center/sources/{source_key}/sync` 仅入队。来源运行支持取消、资源状态、checkpoint 和 Raw manifest 查询；Raw 内容不通过这些元数据接口返回。API 包作为 workspace 领域依赖供 Worker 复用，禁止通过临时 PYTHONPATH 导入。
