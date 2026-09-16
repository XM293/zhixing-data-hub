# 通用后台 Worker

常驻循环在调度、队列领取或结果提交遇到数据库 OperationalError / InterfaceError 时，以 1、2、4、8、16、30 秒退避重连，成功轮询后重置。等待可被停止信号打断；事件仅记录异常类型与等待秒数，不记录数据库异常正文。单次执行仍失败退出，其他编程异常不被吞掉。任务执行中的失败继续遵守任务重试预算和租约，连接恢复不跳过这些约束。

0067 支持显式 deferred 采集：每页归档后，同事务保存镜像页目录、采集 checkpoint 和独立 Raw 映射任务；映射任务无外部请求，复用租约、当前权限重验、哈希与版本门禁。采集成功不表示规范映射成功，映射失败不回退采集水位。schema_pending 页不创建规范映射任务；未确认字段仍不进入 Core。旧 inline 请求兼容，采集与映射状态通过镜像页 API 分开读取。

Raw 重放使用现有 `data-source.sync` 租约任务的 `raw_replay` 命令分支，只读 `SOURCE_ARCHIVE_PATH` 内经过路径、大小、哈希和行数校验的 JSON 页。无需领星凭据，不调用外部接口；当前资源/权限/映射版本仍须有效。独立 replay 分区不推进外部采集水位，新 manifest 与规范观测时间保留原 fetched_at，防止旧归档覆盖较新事实。失败、取消、幂等与部分失败复用同步台账。

DAT-011 当前要求迁移到 `0066_source_configuration_versions`。来源任务每轮最多 100 页，在 180 秒或期限前 30 秒到达已提交页边界时正常续跑，下一轮从数据库 checkpoint 接续。正常续跑不消耗外部错误重试预算，领取轮次与续跑次数分开审计；失效或过期令牌不能续跑。关闭 Provider 仍会校正已失败/取消 Job 对应的来源台账。新任务和运行保存入队 `source_version`，旧运行不回填当前版本；该值不是秘密版本，也不替代每页的实时授权与停用检查。

目录 `.15` 新增销售出库 `fulfillments` 的 page/page_size 分页和规范表头/明细；店铺、仓库须同时批准到同一项目，坏行或旧页不覆盖有效事实。未知来源时区保留本地字符串、UTC 为空，运费不计为收入。FBA 发货单 `fba_shipments` 仅分页 Raw，状态与多店铺数量语义未确认，不映射 Core。

目录版本 `lingxing-2026-09-09.10` 包括 ERP 用户目录（来源实体，不创建平台账号，支持周期快照）、头程物流商（显式八种筛选组合、嵌套分页、规范实体），以及库存流水/FBA 库存和库位的只读分页 Raw 路径。共享目录可提供严格映射契约，但来源登记在真实 Raw 预检前仍保持 `schema_pending`；库位使用 offset/limit。参数和未确认语义见 `docs/development/12-lingxing-official-schema-review.md`。

Worker 使用 `packages/jobs` 的任务状态机，独立于 API 进程启动和停止。启动前先运行 `pnpm db:upgrade`，然后：

```powershell
pnpm worker:once
pnpm worker:run
```

`pnpm worker:verify` 只允许对名称含 `test` 或 `verify` 的 PostgreSQL 数据库执行，会验证幂等入队、`FOR UPDATE SKIP LOCKED` 和追踪字段持久化。

默认使用 API 的本地 SQLite 数据库；部署环境应设置同一 PostgreSQL `DATABASE_URL`。SQLite 只用于单进程开发和测试，生产领取并发依赖 PostgreSQL `FOR UPDATE SKIP LOCKED`。

当前登记 `system.noop` 验收处理器和 `analysis.daily-store-review` 经营巡店处理器。后者领取任务后调用产品 API 的领域执行入口，由 API 冻结事实、运行模型或确定性降级并生成简报；Worker 不复制经营查询、授权或 AI Prompt。其他同步、知识解析、Agent 和 Action 处理器由各自后续任务注册。

巡店 Worker 调用内部执行入口时携带任务的 `request_id`、`run_id`、当前 Worker ID 和一次性领取令牌。API 只从数据库任务记录解析发起主体、声明权限和目标范围，并在运行前重新加载当前访问角色和范围；请求头不能覆盖 ActorContext。其他任务类型接入时必须复用同一任务 v2 和领取令牌模式。
# 领星 Worker

Worker 负责分页请求、Raw manifest、checkpoint、租约和父子运行汇总。API 只负责创建任务并返回 `queued` 运行；外部网络请求不得在 API 请求生命周期执行。Worker 按法人和资源范围隔离查找台账，逐页内容寻址归档，失败时保留上一批有效事实，并将未知 Schema 资源标记为 `schema_pending`。
# DAT-011 来源任务执行

迁移 0061 建立 `source_sync_schedules`。`LINGXING_ENABLED` 启用时 Worker 每 30 秒检查到期计划；计划默认暂停，启用后按数据库行锁防重入队，随后走同一租约执行器。API/Worker 均使用该开关；环境值为空时关闭。

历史导入父批次按资源与 UTC 窗口拆子任务，最多 128 个分区，订单每分区最多 7 天。只有全部子运行成功才推进计划水位；失败、部分失败、取消停在原水位并转待处理。定期订单更新时间拉取带重叠、安全延迟和每日历史回看；目录及当前库存定期快照不代表事件实时推送。未确认增量字段的其他资源不能创建增量计划。

页提交及完成资源运行时在数据库事务内锁定当前 Job，校验执行令牌、状态和租约；同 Worker ID 的新领取也不会接受旧执行器结果。取消使用相同锁顺序，已确认页面不删除。

领星任务直接使用 `zhixing-connectors` 与 `zhixing-api` 领域包；逐页检查任务租约、取消、来源资源状态和发起人当前账号/权限/范围。缺少可信账号快照时失败关闭。每页压缩内容归档后，在同一事务写 manifest、Staging 结果、规范数据和 checkpoint；失败保留已确认页面与旧的有效事实。

目录由 `zhixing-connectors.catalog` 唯一定义，API 与 Worker 使用相同的只读 method/path allowlist。确认仓库列表按本地/海外/平台/AWD 分资源执行，店铺、产品、仓库归属审核通过后才能写关联规范订单与库存。未实现规范映射的资源不得把 Raw 行数作为 records_written。

页提交事务锁定来源和资源，再核对当前启停与 Schema 状态。目录或数据库 Schema 待确认时仅存 Raw，manifest 标为 schema_pending，规范写入为 0；已停用来源/资源不推进 checkpoint。重新确认后可重放原始页，保留原采集时间，不访问外部网络。

产品标签执行单次 GET，SPU/物流渠道执行 offset 分页并映射来源隔离的规范实体；产品属性执行 data.list 嵌套分页。入/出库单用显式日期与 increment_time 筛选分页归档；属性和出入库资源仍为 schema_pending，不能进入指标或自动时间水位计划。

从迁移 0060 起，Worker 通过共享请求预算按 AppID/资源原子预留时隙；数据库仅存不可逆组合标识和时刻，不保存 Token。等待期间持续检查租约/取消，超出最大等待的预留回滚。默认各资源每秒一次；不同来源若共用 AppID，仍共享该资源的预算。

认证 Provider 在单个 Worker 进程中有界复用 Token，提前刷新；凭据轮换选择新的缓存项。Token 不写入任务、日志、Raw 或数据库，进程重启后重新认证。Worker 本身与共享 API/Connector 均为可安装 workspace 包，执行前使用 `uv sync --all-packages`，不需要 PYTHONPATH。

W8 `report_export_status` 只查询已存在的导出任务，参数为 seller_id / task_id / region；不会创建导出任务。等待状态每 30 秒重查，最多 120 次。状态 Raw 去除短期下载链接；下载报告按原始二进制字节归档，大小最多 64 MiB，保持 schema_pending、规范写入为 0。`SOURCE_REPORT_DOWNLOAD_HOSTS` 默认空；官方文档没有明确下载域名，正式配置须先核实。空白名单时运行以 download_host_pending 失败，不能把外部 DONE 视作本地已下载。
