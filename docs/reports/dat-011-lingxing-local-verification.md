# DAT-011 本地验证报告

状态：`in_progress`。2026-09-09 代码复核撤回先前的“本地闭环完成”结论。以下历史验证记录只表示当时测试通过，不代表真实接入能力通过验收。

所有需要业务人员、领星管理员或接口支持核对的条目统一维护在
[DAT-011 领星人工核对与接口权限清单](./dat-011-lingxing-manual-review-and-access-gaps.md)。
该清单不保存凭据、真实响应或客户字段值；未核对项保持停用、未分配或
`schema_pending`，不能据此宣称接入完成。

## 2026-09-12 状态分层回归与本地质量门

复核并修正了一个过期测试：`warehouse_bins` 的共享 `ResourceSpec` 保持
`confirmed`，新建来源登记仍从 `schema_pending` 开始，只有提交当前目录版本才可显式
确认。连接器完整质量门 48 项通过；来源确认、W0-W3 扩展映射和资源目录 API 9 项通过；
API Ruff（161 个源文件）、API mypy（无问题）、workspace check、doctor 和 Web build
均通过。Docker 未安装，仅保留为本地 doctor 的可选提示。

## 2026-09-12 星云项目范围收窄为 Amazon-only

业务范围已明确：星云铁皮柜本期只采集 Amazon，不采集 Wayfair、Temu 或其他多平台。
因此，官方目录中的 72 个 `multiplatform` 资源继续保留用于目录完整性和未来扩展，但本期应标记为
`excluded_by_business_scope`，不建立多平台店铺绑定、不排队、不抓取，也不计入 DAT-011 当前阻断。

此前对 Wayfair/Temu 的直连探测仅作为证据留档，不再要求申请其权限或提供店铺归属确认。当前需要继续处理的
权限/账号错误均来自 Amazon 范围或通用 Amazon 业务链路：历史候选 `-1` × 5、`1` × 9、
`400` × 7、`403` × 2；`2001006` 已依据领星全局错误码定位为签名不一致，修正 GET 数组参数的紧凑 JSON
线材化后，六家 Amazon SID 隔离复测返回 `code=0`。另有 13 个仓库归属、当前 1 个参数口径、9 个上游依赖、14 个
Amazon 请求结构规则；116 个 Amazon/通用操作已自动判定为只读，1 个写入操作已排除。

## 2026-09-11 共享目录与来源台账状态分层复核

复核确认 `ResourceSpec.schema_status=confirmed` 表示共享代码已有严格字段映射契约，
而来源登记的 `SourceResource.schema_status` 仍可在真实 Raw 预检前保持
`schema_pending`。`warehouse_bins` 采用这一双层状态：共享目录允许严格映射测试，
来源台账继续等待真实页预检和显式确认；页面和 Worker 以后者作为运行时门禁。本轮
补充分层回归后，连接器全套 48 项、来源确认/扩展 W0-W3 API 9 项均通过。

## 2026-09-11 字符串数组资源与候选单页验证

依据官方字段说明，目录版本提升到 `lingxing-2026-09-11.35`，计划工作清单为
`lingxing-rollout-2026-09-11.13`，参数策略为
`lingxing-parameter-policy-2026-09-13.5`。两个字符串数组资源采用同范围 Raw 依赖的
单值分区：已有商品信息 `skus` 每次包装一个 `sellerSku/msku`，出单时段分析 `sku` 每次
包装一个 MSKU，并按官方 `sid/profile_id` 二选一只使用已批准 `sid`、按 `hourly/weekly`
穷举 `group_type`。连接器 48 项、Worker 92 项、API 278 项以及 Ruff/mypy 通过；对象数组
资源仍保持运行时阻断。

隔离候选库在 `pre-catalog-35-string-array-partitions` 备份后物化 265 个官方资源，旧的
17 个结构阻断资源按目录收回。`official_a2fa77b89b3172af` 已通过真实只读单页验证并
保持启用；`official_04957300fd9047e6` 使用合法 Amazon 范围请求但返回
`sync.external_business.1`，已停用并进入人工账号/权限核对。该响应只保存错误分类，未
写入报告或仓库。探测编排脚本同时增加命名空间过滤，后续不会再用 Amazon SID 入队多平台
资源。候选 Worker 重启后保持 active，生产发布、业务库和线上四服务未改变。

候选隔离库历史安全汇总（2026-09-11 10:20）为：145 个资源 validated、41 个
needs_attention、96 个未验证；其中错误分类为 `source.read_only_review_blocked` × 17、
`sync.external_business.-1` × 5、`sync.external_business.1` × 9、
`sync.external_business.400` × 7、`sync.external_business.403` × 2；另有 9 个资源等待上游依赖值；汇总只保留数量和错误
分类，不保存响应内容。`2001006` 的历史失败保留作审计，不再计入当前人工阻断。候选迁移头仍为
`0078_backfill_parameter_fanout`。

## 2026-09-11 店铺来源命名空间隔离

官方动态资源现在显式区分 Amazon 店铺来源键 `store:{sid}` 与多平台店铺来源键
`store:multiplatform:{store_id}`。分类同时使用官方请求路径和官方文档目录；三个
`/cepf/warehouse/api/openApi/*` 接口虽然路径不含 multiplatform，但官方文档位于
`MultiPlatform/V2`，因此也按多平台资源处理。目录版本为
`lingxing-2026-09-11.34`，计划工作清单为 `lingxing-rollout-2026-09-11.12`：263 个
可物化资源中 178 个使用 Amazon 店铺范围、72 个使用多平台店铺范围、13 个使用仓库范围。
当前六家人工批准店铺只来自 Amazon 目录，不能用于多平台接口。

修正先通过失败测试复现，再完成连接器 47 项、Worker 53 项、API 8 项回归，Ruff 与
mypy 均通过。隔离候选库分别建立 27,085,510 字节和 27,197,856 字节的 PostgreSQL
自定义格式备份，并通过 `pg_restore --list` 校验。两次受控契约转换共暂停 49 个持续
计划和 24 个回填计划、取消 49 个活动运行、取消 352 个未完成覆盖窗口；1,476 个跨
命名空间 Raw 页标记为 `scope_invalid`，一个由其形成的依赖值标记为 `rejected`。原始
归档和历史运行保留作审计，没有删除 Raw 或写入规范事实。

重启独立候选 Worker 后，72 个多平台资源保持 disabled/unvalidated，49 个持续计划和
24 个回填计划保持 paused，非终态多平台任务为 0，批准的多平台店铺绑定为 0。当前
来源资源状态为 144 个 validated、42 个 needs_attention、96 个 unvalidated；其中仅
23 个非多平台接口错误进入人工权限核对，跨命名空间产生的空结果或错误不再作为权限
证据。生产发布仍为 `/opt/zhixing-releases/zhixing-20260909-dat011-0056`，业务库和 API、
Worker、Web、Nginx 均未切换且保持 active/ready。

## 2026-09-11 NewAd 只读资源与暂停式回填计划

官方 NewAd 契约中 40 个 Amazon 广告资源将 `sid` 与 `profile_id` 描述为二选一，
候选来源按已审核店铺使用 `sid` 分区，不读取或猜测 `profile_id`。目录提升到
`lingxing-2026-09-11.30`，只读审查提升到
`lingxing-readonly-review-2026-09-11.4`；所有请求固定 `X-API-VERSION: 2`，按
offset/length 分页，日期资源按官方单日窗口执行。六个额外枚举字段仅使用官方文档列出的
合法值。该批资源保持 Raw-only，不进入指标、AI、MCP 或集团合并。

连接器 44 项、ruff 和 11 个连接器源文件 mypy 通过；API 组合回归中 31 项通过，唯一
陈旧资源计数断言修正后单项通过。隔离候选库备份为 25,182,147 字节的 PostgreSQL
自定义格式并通过 `pg_restore --list` 校验。40 个资源经真实只读单页探测全部成功，未把
响应或客户字段值输出或下载到仓库。

随后通过管理 API 创建 390 个分店铺持续计划和 276 个全历史回填计划，状态全部为
`paused`，没有触发大规模外部请求。候选库当前官方资源验证状态为 183 个 validated、73
个 needs_attention、26 个 unvalidated；接口或账号条件错误共 52 个，另有 20 个数组结构
资源及 1 个写操作保持运行时阻断。所有人工口径、权限、仓库归属和参数问题统一写入人工核对清单。
候选迁移保持 `0078_backfill_parameter_fanout`，生产发布、业务数据库和四个线上服务未改变。

现有显式运行目录中 36 个官方操作也已回填到同一只读审查台账，解决“运行时已经执行、
人工清单仍显示未审查”的文档冲突；该变更不增加运行时资源或外部请求。人工逐项只读审查
数量由 188 个收敛为 153 个。

## 2026-09-11 参数依赖与候选迁移

迁移 `0075_source_dependency_values` 建立范围感知的来源参数值台账，保存首末 Raw
manifest 血缘、来源资源、项目范围、观测次数和提取器版本；Worker 仅从已确认 Schema
的 Raw 页提取白名单字段。隔离候选库离线重放 6,663 个已校验 Raw manifest，无网络
请求，形成 353 个唯一依赖值。迁移 `0076_source_dependency_tuples` 进一步保存同一 Raw
对象中的 `inboundPlanId + shipmentId` 关系，禁止把两个独立 ID 集合做笛卡尔积。

两项迁移均通过空 PostgreSQL、0053 升级库及现有隔离候选库升级；0076 前候选备份为
18,924,115 字节的 PostgreSQL 自定义格式，并通过 `pg_restore --list` 校验。升级前后
281 个来源资源、343 个持续计划、183 个历史计划、7,122 个覆盖窗口、9,212 个 Raw
manifest、15,070 个同步运行和 353 个依赖值计数保持。候选 Worker 恢复 active，生产
四服务及 `/opt/zhixing-releases/zhixing-20260909-dat011-0056` 未改变。

参数策略 `lingxing-parameter-policy-2026-09-11.1` 覆盖 69 个额外必填参数资源：65 个可由
Raw 依赖值、官方枚举或日/月周期生成，4 个因国家 ID、商品类型或店铺区域语义保持人工
确认。分页规划每批最多 64 个参数分区，支持配对维度和复合键，缺少依赖值时返回等待状态，
不生成空参数成功任务。相关迁移生命周期 11 项、参数策略/依赖值 5 项及 mypy/ruff 已通过；
完整工作区质量门仍须在余项完成后重跑。

## 2026-09-10 云库副本恢复、升级与真实 W0

参数化持续计划：新增 0068，为来源计划保存已校验 resource_parameters，并纳入计划不可变身份；后端可调度 Listing、国家地区、多平台地区、产品属性、头程物流商、库位、FBA 库存和广告等参数化快照，Web Dialog 按资源契约录入必填参数。SQLite 的 0067 旧行回填、0053→head 与定向调度共 10 项通过；独立 PostgreSQL 16 的空库和 0053 升级均到 0068、153 表、保留哨兵行。隔离库在 6,732,814 字节自定义格式备份校验后升级，10,660 个实体、553 个 Raw 页、522 个运行、12 个旧计划计数保持且旧参数均为空。

Listing 持续采集：使用 0068 经管理 API 建立 6 家已审核店铺 × is_delete 两态的 12 个小时级计划，全部 active 且首轮成功，分区身份 12 个互不重复；首轮结束仍为 37 个 Listing 且全部归属项目。计划执行期间订单计划也正常推进，故总 Raw 页增量不能单独作为 Listing 页数；独立对账以计划终态和 Listing 规范实体为准。

参数化参考目录首轮：23 个 Amazon 国家代码的地区目录读取 641 条/23 页、规范写入 641；相同代码的多平台地区目录读取 641 条/23 页、规范写入 641，均无映射失败。头程物流商 8 个官方筛选组合均在写 Raw 前返回永久业务错误；当前错误分类只保留通用码，尚不能区分权限、协议或账号数据状态。已增加只保留受限机器码且彻底丢弃响应消息的错误契约，待回归和候选复测，不能宣称头程物流商已接入。

Listing 候选闭环：目录 .18 / 映射 2.2.0 更新独立候选服务后，先以 12 页、37 条真实 Raw 做无输出内容预检，再通过管理 API 显式确认契约。12 个离线重放运行全部 succeeded，形成 37 个唯一 Listing（25 active、9 deleted、3 inactive），37 条均归属已审核项目、Raw 血缘全部校验、待处理冲突 0、外部请求 0。候选与现有四服务均 active，实际业务发布仍为 0056。

随后真实采集 ERP 用户、市场、概念店铺、多平台店铺与物流渠道：813 条、13 页 Raw 全部成功，810 条规范写入；聚合预检定位 1 条市场 aws_region 为空、2 条多平台店铺 currency 为空。两种空值均与官方文档/示例或实际只读响应矛盾有关，未打印实际对象。新增失败测试后按 null/quality_pending 语义修订为目录 .19 / 映射 2.3.0，17 项定向测试通过；失败页尚待离线重放和对账。

目录 .17 回归结果：连接器全量、Listing/契约 API 和 Worker 全量组合 95 项通过（128.82 秒）。追加“原始页为 schema_pending、资源批准后离线重放”用例后，重放定向 2 项通过（27.46 秒），覆盖无网络、哈希/版本校验、旧观测保护、checkpoint 不变和再次降级拒绝。Web 34 项测试与变更 ruff 通过；这些不是浏览器交互验收或服务器发布证据。下一步为受控候选更新及 37 条真实 Listing 对账。

Listing 后续本地进展：店铺撤权级联、原项目重新批准和已有 Listing 跨项目迁移阻断已实现；资源契约确认 API 具备目录版本校验、不可映射资源拒绝和幂等审计，Web 增加服务端控制的确认入口。相关 API 8 项测试通过（14.03 秒），Web tsc 通过。候选预检证明 .17 的 37 条真实 Raw 中有一条删除记录缺少 item_name，且在批准前被拦截；目录修订为 .18、映射 2.2.0，以必填 seller_sku 作为缺名删除记录的显示名回退，非字符串仍拒绝。来源仍为 pending，未创建重放任务，待新版本回归与部署。

Listing 规范目录本地推进：新增 sid+seller_sku 稳定身份、删除/停售状态、MSKU/本地 SKU/ASIN/FNSKU 关联和官方 UTC 更新时间；持久化继承已审核店铺项目范围。7 项 mapper/真实迁移 SQLite 测试通过（13.91 秒），覆盖重复页、旧页、跨项目和撤销授权后拒绝新写入，ruff 通过。尚需完成店铺审核变更对已派生 Listing 的范围级联与读取验证，目录继续 schema_pending，未部署该规范映射，未将 37 条真实 Listing 转入 Core。

库存与 Listing 最终结果：库存采集 38,713 条、49 页成功，独立映射 49 次 partial_failed、规范写入 0；冲突逐类统计全部为 mapping.unassigned（38,713 条），未伪装为库存就绪。Listing 按 6 家已审核店铺 × 删除/未删除两种状态执行 12 分区，读取 37 条、12 页，schema_pending、无规范映射任务。订单水位随后推进，积压队列已清空。原库存观察 SSH 在远端脚本结束后仍未退出；以同请求键重新读取持久化终态，再仅关闭已核验的本地观察连接，没有重启采集。仓库/商品归属规则仍待用户确认。

公平续跑修复：失败测试证明旧批次会在续跑后再次抢占等待中的任务；改为优先级、available_at、created_at、id 顺序，令牌重新签发及续跑计数保持。队列包 18 项、Worker 全量 64 项通过（158.99 秒），mypy 18 文件与变更 ruff 通过。候选备份后更新队列、目录 .16 和 Worker，五服务 active；尚待真实积压消退与 Listing 采集验证。

Listing 本地扩展：目录 .16 新增只读 listings，显式单店铺 sid 与 is_delete=0/1 分区；保持 schema_pending。范围与分页/资源目录定向 33 项通过，尚未部署候选或采集真实 Listing。库存采集中已观察到 17,600 条确认读取，批次仍运行，不能宣称完成。复核队列按 priority/created_at 领取，而续跑仅更新 available_at，老大批次可能持续抢先；需补公平续跑回归再扩展长期并行采集。

售后真实字段复核：仅在服务器读取并校验 Raw SHA-256，将 49 条父记录展开的 73 条子项与规范事实逐条比较外部键、SKU、数量、来源金额原文、来源时间、订单关联、店铺及项目归属；73 条全部匹配，字段差异 0、缺失 Raw 匹配 0。金额/币种/UTC 均为 NULL；timezone_pending 73 条，currency_pending 与 amount_format_pending 各 30 条。此结果证明原文和归属一致，不证明退款金额或 UTC 财务口径已就绪；未猜测时区、币种或将空金额置零。

售后范围闭环追加：Worker 全量 61 项通过（165.44 秒），候选 main.py 备份后更新，现有业务发布不变。after_sales 使用官方 sid 字符串筛选已批准 6 家店铺，归档前响应范围检查通过。2026-09-01 至 2026-09-10（官方来源日期，未推断 UTC）读取 49 条父记录、1 页，独立映射写入 73 条子明细，映射失败 0。数量差异来自 map_after_sales 展开子项，不能用父记录数直接替代售后事件数；真实金额、重复重放与时间对账仍待验收。

目录周期首轮最终复核：所有采集及独立映射任务成功，无排队/运行中的重放、无新失败。商品 8,692、仓库 384、供应商 355、分类 104、品牌 9 均保持稳定；6 家店铺仍 active、260 家仍未分配。重复采集未新增重复实体，人工审核归属未被来源快照覆盖。Worker mypy 11 文件通过。

周期快照追加：11 类目录计划已由真实管理 API 启用，每 86400 秒快照，deferred 模式。首轮采集通过，独立映射进行中；中途复核稳定实体数量未增加、6 家审核店铺仍 active、260 家未分配。售后范围代码发现未传官方 sid 筛选，新增 2 个失败用例后修复，11 项范围定向测试及 ruff 通过；Worker 全量回归进行中，尚未更新服务器候选代码或实际采集售后。

主数据批次最终结果：products 8,692、product_categories 104、suppliers 355、brands 9、product_styles 0、product_tags 0，共读取 9,160 条、14 个 Raw 页；独立映射写入 9,160，映射失败 0。Raw 和实际名称均仅留服务器。商品等目录的周期快照、重复同步归属保持，以及商品/仓库到项目的审核尚未验收，不能把主数据映射成功等同于库存和履约可用。

仓库目录真实验证：通过 API 创建四资源 deferred 批次，由常驻候选 Worker 独立执行。本地仓 100、海外仓 67、平台仓 185、AWD 仓 32，共 384 条、4 页，采集成功且规范映射写入 384，映射失败 0。数据库复核全部为 unassigned，没有套用“星云”店铺名称规则。首次验证脚本错误读取 SyncRun.resource_key；修正为任务载荷的资源键后使用同一请求键复查，未重复入队。商品等六类目录批次随后开始独立映射，最终结果尚待核验。

常驻候选部署：独立 systemd Worker 已启动并启用开机启动，固定隔离验证库，原业务四服务与 0056 发布不变。订单计划每 300 秒运行，首轮采集/独立映射成功；手动重启候选 Worker 后调度恢复并确认水位 `2026-09-10T04:59:22.92482Z`，active、无活动批次或新错误。未进行整机重启、长期稳定性或全资源持续同步验收。候选入口与回滚文件只保存在服务器受限目录；源文件 runner 更新前备份为 runner-before-persistent.py。

常驻可靠性修复：先复现队列轮询数据库 OperationalError / InterfaceError 导致退出（2 个失败测试），再加入可停止、最高 30 秒的指数退避，恢复后重置；非连接类错误仍上抛，日志不含 SQL/凭据异常正文。队列包 17 项通过，Worker 全量 59 项通过（163.20 秒），ruff 与 jobs mypy 7 文件通过。该修复尚未部署候选或现有业务服务；服务器复核四服务 active，隔离计划 paused、无活动批次，新错误为 0，历史范围解析失败 2 条仍保留。

2024 年全年覆盖扫描成功：53 个分区、53 个空 Raw 页、53 次独立映射成功，读取与写入均为 0，累计订单仍为 2,434 条。这只能证明此次平台更新时间窗口返回为空，不能证明 2024 年以前没有历史订单。本轮 doctor 和 workspace check 再次通过；未改业务实现，未重复完整 check/build。当前周期计划暂停，没有遗留运行中的本轮回填任务。

2025 年全年追加回填成功：53 个分区、读取 125 条、Raw 53 页、独立映射 53 次成功且 0 失败，规范订单累计 2,434 条。官方订单文档仅确认单次查询跨度不超过一年，未给出账号最早可用历史边界；不得将此限制误读为仅保留一年数据。

历史与增量衔接追加验证：周期计划连续两轮采集成功，水位从 2026-09-01 推进至 2026-09-10T04:14:04.837636Z，规范订单累计 74 条，无调度错误。受控验证结束后计划暂停，不代表已部署持续增量服务。API 调度定向测试 1 项通过（16.44 秒）。随后 2026-01-01 至 2026-09-01 UTC 历史批次完成 35 个分区，读取 2,235 条、Raw 35 页、独立映射 35 次成功且 0 失败，规范订单累计 2,309 条。覆盖按平台更新时间计；用户要求的全部可用历史仍在向早期扩展，尚未确认最早边界。证明文件仅保存于服务器候选目录，未下载原始响应。

本轮最终验证：Worker 全量 59 项通过（146.47 秒，`.tmp/dat011-store-scoped-worker.log`），范围定向 9 项通过；mypy、ruff、doctor、workspace check 通过。真实订单范围复核为 3 条、范围外 0、缺失 Raw 血缘 0。线上四服务仍 active，发布仍为 0056。本轮只改 Worker 和其测试/文档，未重新执行约 38 分钟的 API 全套和未改动 Web 构建；上一轮完整 check/build 结果保留作基线。扫描覆盖 697 文件、19 个候选，新增候选为本轮合成凭据字面量，实际客户数据没有写入仓库。

后续店铺归属与订单试运行：用户确认名称包含“星云”的店铺归属于星云铁皮柜。通过现有审核 API 批准 6 家，剩余 260 家保持未分配，服务器保存审核 manifest 和审计事件。未按名称设置店铺时区，也没有推断仓库归属。

首个订单窗口为 2026-09-08 00:00 至 2026-09-09 00:00 UTC（平台更新时间，date_type=3）。当前 Worker 新增项目/店铺范围的官方 sid_list（最多 20 个），SID 从法人+来源+已审核 Origin 映射解析，不能从内部 canonical_key 拆取。归档前检查响应 SID，范围外数据拒绝写 Raw/checkpoint。首次范围解析和任务 source_id 字段适配失败均在外部采集前终止、读取 0；修复后的真实运行读取 3、Raw 1 页、独立映射写入 3 条规范订单。同一请求键重试仍为 3 条、1 页，无新增采集和重复订单。失败记录保留，没有伪造成功。候选 Worker 源文件在独立 workspace 更新，原发布未变。

定向范围测试 8 项通过后追加数据库来源隔离测试；Worker 全量回归结果待下文补记。Worker mypy 11 文件及变更 lint 通过。超过 20 店铺的范围暂时明确拒绝，后续需要按店铺分区；全法人采集保持现有账号范围语义。当前仅完成单个 UTC 窗口，不代表历史全量、持续增量、库存、金额汇率对账或生产页面验收完成。

用户补充管理员身份并授权继续，真实认证及 CREATEDB 权限通过；管理员配置仅保存在服务器 root-only 文件，未改变应用身份。创建同实例 `zhixing_dat011_verify`，从 `pre-dat011-mirror-20260909T153727Z` 备份单事务恢复成功：0056、141 表。PostgreSQL 17 客户端导出的 `SET transaction_timeout = 0` 不适用于 PostgreSQL 11，恢复 SQL 仅移除此会话设置，不改业务数据。恢复材料保留服务器受限目录。

候选 uv workspace 位于独立验证目录，源码包 SHA-256 为 `a9b2dc39b3ac5f65f41f4028fb4525a866028314d809ddf57fa01f714f4baf06`；锁定安装后离线复检 47 个包通过。候选代码在真实 PostgreSQL 11.22 副本上升级 0056→0067 成功，153 表；原有 140 张业务表计数均不变。此结果不是业务数据逐字段校验或完整回滚演练。

隔离副本建立领航集团、星云项目主体（暂定）、星云铁皮柜和两个随机密码验证管理员。两个账号均通过真实登录 API；来源通过管理 API 注册，sync API 返回 queued，Worker 使用实际只读领星连接器执行。两次目录采集各 266 条、采集规范写入均为 0，两个独立映射运行各写入 266 条；数据库最终仅 266 个店铺实体及 266 条来源追溯，没有重复实体，全部未分配、来源追溯 business_unit_id 为空。真实 Raw 两页仅存服务器隔离目录，响应未下载到本地或写入仓库。全部试运行管理员会话已撤销，管理员凭据留服务器受限文件。

试运行脚本首次将同步 Worker 放入 API 验证事件循环导致协程调用错误，之后改为独立线程；原任务经重试最终成功。最终断言又误读 BusinessEntity 不存在的 business_unit_id 字段；已改用实体 unassigned 状态及 CanonicalEntityOrigin 范围列复核，单独对账通过。未删除这些运行记录。读取时间列时出现服务器 `PRC` 时区别名识别警告，客户端回退 UTC；经营时间窗口扩展前须明确会话及来源时区，不据此推断店铺时区。

现有 `zhixing` 业务库、0056 发布及四个线上服务未切换，health/ready 为 staging/ready。未执行 demo-retire、生产清库或订单库存全量导入。W0 成功仅代表店铺目录链路，38 个资源规格中 15 个 schema_pending 仍保留。下一放行条件为店铺/项目归属确认、正式管理员交接、候选 Web 受控验收及订单短窗口对账。工作区检查通过；696 个可提交文本文件扫描的 18 个候选均为既有合成测试/示例，未出现新凭据。

复核初始阻断（已修复）：官方签名 AES 密钥/URL 编码/POST 体签名、API/Worker 协议重复、逐页 checkpoint 和 Raw 计数混淆。初始复核时未导入真实领星数据；后续隔离 W0 导入见上文。未执行清库。

## 2026-09-09 继续实施记录

### 0067 镜像采集与独立映射；受控服务器探测

最终完整 `pnpm check` 返回 0（`.tmp/dat011-0067-check.log`）：Web 34、Connector 22、API 237（38 分 29 秒）、Agent Runtime 4、Codex 适配器 3、Jobs 13、Worker 50（155.19 秒）、Mock Commerce 6、Mock Memory 2、Mock Knowledge 3、MCP 4 项通过。API 收集后的来源计数/计划/重放修改另有下述定向补验。镜像页“映射血缘”浏览器点击已读取对应运行、资源和原 Raw 页，显示成功及 1/1；使用合成数据。最终可提交文本扫描覆盖 696 个文件、18 个候选行，新增候选来自 deferred 合成测试；未输出匹配值，未读取实际 `.env`。

依据 ADR-023，新增 SourceMirrorPage 页目录和 deferred 入队模式。Raw manifest、采集 checkpoint 与独立映射任务在同一事务提交；映射失败不撤销已完成的采集，schema_pending 只归档、不创建规范映射任务。现有 inline 模式保持兼容，新建 Web 批量导入和计划默认 deferred。镜像页 API 按法人授权分页，提供采集与映射运行血缘；单页重放更新最新映射指针，保留历史运行。离线映射不再重复累加外部采集行数。

迁移 `0067_source_mirror_pages` 在本地 PostgreSQL 16.14 空库和 0053 升级库均通过（153 表），保留合成存量法人、来源、运行和任务预算。定向 Worker 4 项、API 4 项通过；后续重放指针 1 项、来源计数/计划/队列 4 项、只读探测 1 项补验通过。API/Worker 类型与 lint、Web 类型检查、最新 build、doctor 和 workspace check 已通过。本轮完整 check 仍在运行，最终结果待追加，不能用之前的完整检查代替。

本地 PostgreSQL/API/Worker 浏览器流程已完成 deferred 店铺采集及独立映射，Raw 1 条、规范写入 1 条；ERP HTTP 使用合成 MockTransport。桌面和 390×844 镜像页面已查看。当前实现是可追溯的页镜像目录，尚不是全部领星数据的记录级 ODS，也未完成独立 PostgreSQL Schema/角色隔离或批量重映射。

用户后续授权受控服务器测试并指示使用此前提供的凭据。本轮已核验目标 IP/hostname/SSH 指纹，现有四个服务 active，发布仍为 `zhixing-20260909-dat011-0056`、环境 staging。凭据仅安装在服务器 root-only `/etc/zhixing/lingxing-xingyun.env`，未修改现有服务配置；不宣称凭据已经轮换。隔离连接器环境使用同一连接器实现，真实 Token 与只读店铺目录探测成功，共读取 266 条目录记录；响应仅在服务器内存处理，没有写入业务库、Raw 归档或本地仓库，也没有自动分配到星云铁皮柜项目。

已创建服务器备份 `pre-dat011-mirror-20260909T153727Z`，包含数据库 dump 和受限环境文件，留在服务器受保护备份目录；dump 目录可读取，恢复尚未验证。云数据库实际版本为 PostgreSQL 11.22，现有应用账号没有 CREATEDB 权限，等待隔离数据库 `zhixing_dat011_verify` 或服务器上的建库配置路径。未执行数据库迁移、清理、真实业务导入、正式组织初始化或现有发布切换。组织名称已获用户确认：领航集团、星云项目主体（暂定）、星云铁皮柜。

生产交接前仍须完成同版本恢复与迁移验证、正式身份和来源归属、受控 Raw 采集/映射对账及回滚验证。目录仍为 38 个规格、15 个 schema_pending，不等于全量 ERP 覆盖；增量计划不等于实时变更监听。

最新完整 `pnpm check` 已返回 0（`.tmp/dat011-0065-check.log`）：Node 23、Web 34、Connector 22、API 233（39 分 53 秒）、Agent Runtime 4、Codex 适配器 3、Jobs 13、Worker 46（91.37 秒）、Mock Commerce 6、Mock Memory 2、Mock Knowledge 3、MCP 4 项。API 收集后的 0066 来源版本改动另按下述定向 6 项及补验 3 项验证；API 155/Worker 11 源文件 mypy 与各自 ruff 再次通过。最新 `pnpm build`（`.tmp/dat011-0066-build.log`）、Web 34 项、doctor 与 workspace check 均通过。静默期间用仅栈帧诊断定位为 SQLite 生命周期索引迁移，进程继续推进，没有中断后宣称通过。

最新迁移为 `0066_source_configuration_versions`：来源配置版本回填 1，新建来源记录创建时间，旧创建时间与旧运行版本保持未知；单资源、批量和 Raw 重放运行保存入队版本。PATCH 必须携带 expected_version，过期编辑/停用返回 409。两条本地 PostgreSQL 迁移路径均通过（152 表），0053 来源与运行、法人及任务预算保留。独立 PostgreSQL 两线程验证一个编辑成功、一个 409、仅一条审计事件。来源版本/队列/批量/真实管理 API/Raw 重放 6 项通过（153.18 秒），追加运行列表和 Job 版本追溯 3 项通过（40.92 秒）。浏览器编辑合成来源使版本由 1 变为 2，新 shops 同步成功且父子运行入队版本均为 2；历史运行仍显示未知。该验证不涉及生产数据或真实账号。

最终浏览器刷新后的截图 `output/playwright/.playwright-cli/page-2026-09-09T14-35-47-204Z.png` 已人工查看：新运行显示 succeeded、入队配置版本 2、Raw 读取 1、规范写入 1，历史运行版本未知。最新可提交文本扫描覆盖 687 文件、17 个候选行，均为既有合成测试或示例字面量；没有输出匹配值，实际 `.env` 未读取。可提交输出仍仅含用户原有截图，本轮截图、日志与隔离数据库均在忽略目录。此次启动的浏览器、API/Worker 验证服务和 Web 服务已关闭，本地隔离 PostgreSQL 与合成数据保留。

上一包 `0065_canonical_fulfillments` 新增销售出库单和稳定明细键，两条 PostgreSQL 验证路径均通过（152 表），0053 存量法人和 Job 预算保留，日志 `.tmp/dat011-0065-migrations.log`。按官方 [销售出库单](https://apidoc.lingxing.com/#/docs/Warehouse/WmsOrderList) 实现 page/page_size 分页、双维度归属校验、幂等更新、迟到保护及明细整行校验；运费保留原币精度，不重复计为销售收入。来源时区未确认，UTC 列为空且明确质量标记。新增映射/持久化/目录 13 项与扩展 Worker 整链 1 项通过。

目录 `.15` 共 38 个规格、15 个 schema_pending；新增 [FBA 发货单](https://apidoc.lingxing.com/#/docs/FBA/GetInboundShipmentList) 的 data.list/data.total 分页 Raw 契约，因请求/结果状态枚举不同、多店铺关联和数量维度未澄清，禁止进入规范事实与指标。目录数不表示全量 API 覆盖率。

履约追加验证：超长单号先以失败测试复现，再在映射阶段拒绝；持久化回归覆盖已有关联事实时禁止店铺/仓库迁移项目、权威来源指派和 Schema 降级过滤。最新契约/映射/目录/持久化 15 项通过；FBA 两页 Raw 等补验 29 项通过。PostgreSQL 浏览器库的单据与明细 dry-run 验证逐表计数、父单据删除被明细外键阻断、完整计划明细优先，未执行删除。

本地浏览器完成销售出库主流程：审批仓库归属 project-a、启用 fulfillments、填写显式来源日期并入队；父子运行均成功，Raw 与规范写入各 1 条，保存 1 条明细。页面显示原币 KWD 1.125、已出库和来源时区待确认；血缘 Dialog 的 Raw、仓库和明细截图已查看。发现范围外项目仍出现在审核选项的问题，服务端正确拒绝，前端已按当前 ScopeContext 收窄选项。最新 API 155 源文件 mypy、API/Worker ruff 与 Web tsc 通过。可提交文本扫描 682 文件、17 个既有合成/示例候选，无新增真实凭据；实际 `.env` 未读取。

ScopeTwin 范围投影已接入集团/项目/店铺数字孪生和驾驶舱，返回当前获权组织、已归属店铺与仓库及来源真实状态。跨法人、单店铺、项目缩窄、未归属隔离和禁用来源状态测试 2 项通过。旧驾驶舱固定 4 来源/10 万记录验收目标已移除，改为来源实际连接及同步状态；生产入口静态保护 4 项通过。Web 34 项通过，桌面浅色范围页面截图检查通过；这不代表财务合并或集团三维经营模拟已完成。

最新完整 `pnpm check` 已返回 0（`.tmp/dat011-final-resource-check.log`）：Node 23、Web 33、Connector 22、API 211（37 分 44 秒）、Agent Runtime 4、Codex 适配器 3、Jobs 13、Worker 45、Mock Commerce 6、Mock Memory 2、Mock Knowledge 3、MCP 4 项通过。测试收集之后新增的来源治理、Schema 门禁、同步响应/会议范围等变更分别定向补验，见下文。后续电商页面范围兼容与十进制展示改动已通过 Web 34 测试、tsc 和最新 `pnpm build`（`.tmp/dat011-final-commerce-build.log`）；生产路径静态回归 3 项通过。doctor 与 workspace check 再次通过，Docker 仍为未安装的可选项。

追加正向页面验收：真实本地 PostgreSQL/API/Worker、仅 ERP HTTP 使用合成 MockTransport。浏览器批准 store:991 归属 project-a 并显式设置 UTC，提交订单时间窗口后得到 2 条规范订单；通过 ConfirmDialog 设置项目订单权威来源，页面汇总显示 JPY 100、KWD 1.125，订单下钻为 2 条，金额没有浮点截断。项目页面不再请求旧全法人付款事实查询，保留覆盖/汇率未确认质量状态；桌面截图已检查，未使用真实客户响应。

本次完整 `pnpm check` 已返回 0（`.tmp/dat011-summary-check.log`）：Node 23、Web 33、Connector 19、API 205（44 分 38 秒）、Agent Runtime 4、Codex 适配器 3、Jobs 13、Worker 39、Mock Commerce 6、Mock Memory 2、Mock Knowledge 3、MCP 4 项。测试收集后的追加改动另行定向验证：工作台 4 项、旧概览范围守卫与正常法人概览 3 项、同页采集时间与 Raw 重放 2 项。最新 Web 类型检查和 `pnpm build` 通过；doctor、workspace check 通过，可选 Docker 未安装。

浏览器本地 PostgreSQL + 真实 API/Worker + MockTransport 验收：批量导入 shops/warehouses_local 返回 2 个分区；父运行成功、两子运行各读取/写入 1 条，两个 Raw manifest 可追溯。Raw 重放经 ConfirmDialog 入队执行；集团工作台显示规范订单汇总，旧全法人指标和动态不混入集团结果。数字孪生/驾驶舱在 scope_version 改变时重建视图，旧 overview 不能越过集团/项目/店铺选择读取全法人。场景的真正多范围读模型仍未完成。截图位于忽略的 `output/playwright/.playwright-cli`，没有真实客户数据。

目录升级为 `.11`，新增产品标签与头程物流渠道，合计 31 个规格、10 个 schema_pending。官方来源为 [产品标签](https://apidoc.lingxing.com/#/docs/Product/GetProductTag) 与 [头程物流渠道](https://apidoc.lingxing.com/#/docs/Logistics/ChannelList)。只映射已确认身份与状态，标签未知启停状态记 unknown；创建时间单位、渠道更新时间时区及运价币种不猜测。两法人来源隔离、幂等更新、坏行保留有效实体、GET Raw 与资源回归共 34 项通过（17.59 秒）。新增目录支持暂停状态的周期快照计划，不声称删除检测或实时推送。

新增权威订单聚合与页面：`canonical-orders-v1` 按业务日期闭开区间执行单条数据库分组查询，返回按原币的金额、状态和来源版本血缘；所有状态均计入订单记录数，不复用旧付款 GMV。新汇总及已有权威/范围定向测试 4 项通过，覆盖两法人三项目、非权威重复、未获权法人、源/规则停用、Schema 待确认、KWD 三位小数及日期上界排除。汇率、内部抵销、全量覆盖仍未核验。新增页面类型检查和构建通过；本地 PostgreSQL 空库升级至 0064 后浏览器读取真实 API 空状态，未访问远程系统。移动布局在截图检查后继续调整。

会议创建与 Action 确认/审批/工作事件补完整 ScopeContext v2 快照；先用旧实现运行新增审批断言，得到缺少 scope_context 的失败，再实现同次审批复用相同快照。相关集成回归 6 项通过（113.55 秒）。

权威汇总补来源/项目/Schema/映射版本/业务日期下钻到规范订单，回归逐组核对总数与 Raw manifest。新增 R0 `query_authoritative_orders` 和 Bootstrap v2 显式只读工具模板；工具输入拒绝额外法人参数，保留权限/MCP allowlist/调用审计。Bootstrap、工具及汇总定向 13 项通过（226.22 秒，`.tmp/dat011-summary-tool-tests.log`）。152 个 API 文件及 11 个 Worker 文件 mypy、相应 ruff 已通过；这不代表全部余项已验收。

Raw 单页重放已加入队列、Worker 和 ConfirmDialog。合成队列执行测试通过：无凭据和网络请求，原外部 checkpoint 不变，保留 2020 年原采集时间；旧页不覆盖 2026 年的新事实，跨法人拒绝，非法归档路径及 Schema 降级失败且保留有效事实。普通采集与规范写入共用同一 observed_at，避免毫秒差让同页重放被误判为旧页。重放与写入/调度回归 3 项通过；随后新增同页时间断言的调度与重放 2 项通过。

本轮后续补验：旧指标、经营事实、客户和分析读入口加入所选范围校验，单店铺 AI 上下文使用当前选中的店铺；全法人查询不能绕过项目/店铺选择。真实 ScopeContext + 路由授权及 AI 查询范围测试 2 项通过，工具/指标/分析/分身集成 8 项通过。工具管理审计也修复集团主体跨法人名称查找，仍只返回当前法人的调用事件。149 个 API 源文件 mypy 和全 API ruff 通过。

配置检查发现示例文件和部署模板含非空初始凭据，已仅将凭据字段改为空，实际 `.env` 未改动。新增模板静态回归 2 项通过，失败信息只包含变量名；Node 工作区测试 23 项通过。该检查覆盖可提交模板，不读取服务器环境文件。历史截图与验证库保留在原位置或忽略目录，没有删除用户原有文件。

随后目录升级 `.12`：增加 [SPU](https://apidoc.lingxing.com/#/docs/Product/spuList) 规范款式实体及 [产品属性](https://apidoc.lingxing.com/#/docs/Product/attributeList) 嵌套分页 Raw。SPU 四种在售状态保留，采购成本币种/创建时区不猜测；属性 ID 官方释义冲突登记 pending。资源、映射、协议和 Raw 定向 36 项通过（18.57 秒）；追加两法人 SPU 持久化后映射测试 3 项通过。最新 API 152 文件 mypy、API/Worker/Connector ruff、Web 33 测试和凭据模板 2 测试通过。

目录 `.13` 继续加入官方 [入库单列表](https://apidoc.lingxing.com/#/docs/Warehouse/inboundgetOrders) 和 [出库单列表](https://apidoc.lingxing.com/#/docs/Warehouse/outboundgetOrders) 的更新时间筛选分页 Raw。明细稳定键、成本币种、来源时区和数量维度未确认，保持 pending，不写库存流水事实。最新 Connector/资源/映射/Worker Raw 定向 40 项通过（20.57 秒）。桌面父子运行血缘与 390×844 批量导入 Dialog 截图均已检查。

当前目录 .14 共有 36 个资源规格，其中 14 个仅 Raw、未放行规范事实；目录数量不等于领星全部 API 覆盖率。新增官方 [FBM 订单列表](https://apidoc.lingxing.com/#/docs/Sale/FBMOrderList)，实现 page/length 分页、单 sid 和来源本地时间校验；缺少金额、明细且与 Amazon 订单重叠，保持 pending。最新目录/映射/Raw 定向 42 项通过（21.66 秒）。前次可提交文本秘密特征扫描覆盖 667 个文件、无命中；后续变更须补扫。这是模式检查而非所有秘密的数学保证，未读取实际 `.env`。输出目录唯一可提交截图仍为用户原有的 `output/browser/cockpit-2515x1199.png`，本轮截图及测试日志均在忽略目录。

追加来源治理闭环：SourceOperations 独立契约/API 只返回当前法人获权的运维元数据，来源页不再查询旧经营 overview。资源 enabled 与 schema_status 独立，目录与持久化状态任一 pending 都禁止规范映射；Worker 页事务锁定资源/来源重查，Schema 降级只写 Raw，停用不推进 checkpoint，旧有效事实保留。规范写入/重放/调度/Store 4 项通过（97.80 秒），追加来源停用快速回归 2 项通过；来源 API 集成 1 项通过（35.23 秒），来源治理 2 项、权威目录降级及范围汇总 4 项通过。

浏览器追加三资源批量导入：product_styles、product_tags、logistics_channels 的父运行成功，三子运行各读/写 1 条，3 个 Raw manifest 和未分配实体可追溯。仅合成 MockTransport。同步响应已移除经营 overview；会议动作选中范围守卫在变更之前执行，范围/入队/原会议兼容回归 6 项通过（81.14 秒）。`.env.example` 所有变量值现均留空，新增静态保护，配置模板 3 项通过；实际 `.env` 未读取或修改。

| 波次 | schema_pending 资源 | 当前阻断 |
|---|---|---|
| W0 | monthly_exchange_rates | 汇率方向、本位币及版本证据不足 |
| W1 | warehouse_bins、product_attributes | 官方字段表与示例存在冲突，属性/属性值 ID 释义未确认 |
| W2 | fbm_orders | 列表无金额/明细，系统单号与 Amazon 订单键不同且覆盖重叠，不能直接合并 |
| W3 | inventory_statements、fba_inventory、inbound_orders、outbound_orders、fba_shipments | 流水方向、共享仓归属、单据行稳定键、金额币种及来源时区未确认；FBA 发货单状态/多店铺/数量口径待确认 |
| W4 | purchases | 采购规范契约、日期时区及事实映射未完成 |
| W5 | advertising | 广告指标与事实口径映射未完成 |
| W6 | finance | 财务记账口径及金额映射未完成 |
| W7 | customer_service | 客服资源规范映射未完成 |
| W8 | source_reports、report_export_status | 源报表与异步报告仅完成 Raw 执行状态，未放行指标 |

尚未满足完成定义：W0-W3 子资源规范覆盖、权威来源到指标/集团合并的链路、部分旧业务查询范围兼容及业务模板审查仍有缺口。生产全量导入、增量调度与实际功能验收尚未放行；DAT-011 维持 in_progress。

本次继续补齐 MCP：以签发的账号 ID/法人 ID 重新解析身份，保留显式 deny；项目、店铺、仓库选择在签发与调用时重新验证，不能回退到全法人。新增回归 6 项通过，已有 MCP 签发/撤销及权限变更集成 2 项通过。Runtime 新增兼容性范围快照契约，拒绝跨法人快照；Runtime 契约 4 项、分身执行/取消集成 2 项及同范围续问集成 1 项通过。范围变更或缺少 v2 快照禁止复用旧线程的回归通过。以上快照不能代替指标或集团汇总授权。

后台任务人工重试新增连续 4 次正常续跑后的失败恢复验证：API 保留 4 条 continued 与 1 条 failed，人工重试不把续跑次数加进故障预算，幂等重放通过。API ruff、148 源文件 mypy，以及 Worker/Jobs/Connector/Runtime 共 27 源文件 mypy 通过。本次启动的浏览器、API 和 Web 验证进程已关闭；本地隔离 PostgreSQL 保留供后续测试。

目录 .9 新增 warehouse_bins 的 offset/limit 分页。官方字段表与示例的状态、SKU 键名和库位类型存在冲突，因此仅 Raw，保持 schema_pending；Connector 与资源 Raw 定向 29 项通过。

目录 .10 新增 ERP 用户目录 erp_users：官方只读 GET 单次取数，规范来源实体仅保存必要目录字段，不创建登录账号/主体或继承 ERP 权限，必须人工批准归属。双法人同 uid、重复导入、字段最小化和较早观察页保护的 2 项测试通过；来源目录与冲突回归共 7 项通过；连接器加只读请求定向 20 项通过；规范写入和批次调度集成 2 项通过。周期目录快照默认暂停，未连接真实 ERP。

本轮完整 `pnpm check` 返回 0：Node 23、Web 33、Connector 18、API 190（47 分 51 秒）、Agent Runtime 4、Codex 适配器 3、Jobs 13、Worker 37、Mock Commerce 6、Mock Memory 2、Mock Knowledge 3、MCP 4 项通过。API 套件收集后新增的身份审计/MCP/Runtime 8 项、之后新增的 ERP 用户映射 2 项另行通过；修改过的登录、范围、Runtime、重试预算与写入/调度测试已定向补跑。`doctor`、workspace check、最终 `pnpm build` 均返回 0；Docker 仍为可选缺失提示。质量门通过不代表上文剩余完成条件已满足。

当前迁移头为 `0064_job_continuations`。本地空 PostgreSQL 与 0053 升级库各 150 表通过；升级验证额外保留一条旧合成 Job，确认续跑计数回填为 0、原 attempt=1/max_attempts=3 保持不变。Job 正常续跑与故障重试预算分离，过期/替换令牌与重复进度不能续跑；真实队列 + MockTransport 证明首轮提交 checkpoint 后 queued、父批次保持 running，次轮从下一页完成。独立 Job 提前失败的台账状态校正、已有成功状态保护与重复校正通过定向测试。

共享目录升级到 `lingxing-2026-09-09.8`：头程物流商显式校验 enabled/isAuth/payMethod，使用 search.page/search.length，规范实体不包含联系人；库存流水与 FBA 共享库存加入 Raw 链路，但因数量/时区/币种及共享仓归属语义未确认保持 schema_pending，不能计作 W3 规范映射完成。缺少来源 ID 的坏行以 Raw manifest 与页内序号隔离冲突；不同库存维度和物流商不会互相关闭冲突。

前一批 Connector/资源 Raw 定向 28 项通过；Jobs 13 项通过；独立运行状态校正 1 项通过。完整回归结果见上文。浏览器发现的移动端表单布局问题已修复并完成下述复验。上述记录不表示 DAT-011 已完成，状态继续 in_progress。

浏览器补验已完成：权威规则创建与 ConfirmDialog 停用分别返回版本 1/2；390×844 表单纵向布局截图已检查。集团管理员切换法人 B 后组织页面暴露审计主体 KeyError，已用失败测试复现并限定为当前法人事件引用主体的名称补查。修复后组织页面正常，保存项目版本 2 后顶部仍选中原项目和店铺，没有扩大范围。对应身份审计与后台任务人工重试 API 定向 2 项通过；1440×1000 组织页面截图已检查。

可提交文本扫描覆盖 648 个文件，4 个命中均位于测试或本地基础设施验证字面量，没有输出匹配值。发现的 8 个历史相对路径 SQLite 验证库已添加精确忽略规则，未删除或覆盖；浏览器截图继续保存在忽略目录。没有连接服务器或真实领星账号。

范围修正定向 7 项通过：单店铺授权从有效来源血缘派生所属项目，不授予同项目其他店铺；业务单元显式拒绝同时隐藏该店铺。项目级权威修改额外要求项目或完整法人治理授权，不能由这种派生项目范围扩大权限。售后事实也纳入归属换绑保护，先拒绝再换绑不能绕过历史迁移要求。

上一阶段迁移 `0063_source_authority_assignments`：项目级指派绑定来源实例、资源及事实族，唯一约束为法人/业务单元/事实族，旧配置保留而不推断迁移。空 PostgreSQL 与 0053 升级库均通过（150 表，存量合成法人保留）。项目权限、版本冲突、Schema 待确认阻断、来源停用退出权威查询及跨法人隔离已定向通过。新增 `/authority-assignments` API、来源台账权威规则 Dialog/ConfirmDialog、规范事实“仅权威来源”过滤；旧无项目 PUT 接口返回 410，历史 GET 保留审计用途。管理 API 定向测试通过，mypy/ruff 与 Web 类型检查通过。新的权威过滤尚未替代旧指标层，汇率和集团合并统计仍未完成。

本轮完整 `pnpm check` 返回 0：Node 23、Web 33、Connector 16、API 183（22 分 41 秒）、Agent Runtime 3、Codex 适配器 3、Jobs 11、Worker 32、Mock Commerce 6、Mock Memory 2、Mock Knowledge 3、MCP 4 项通过。运行期间新增的冲突和登录契约等 6 项定向补跑通过，API 147 源文件 mypy 与全 API ruff 通过。`doctor` 和 workspace check 通过（Docker 未安装，仅提示）；`pnpm build` 通过。该质量门证明已覆盖实现通过验证，不等于下方剩余功能自动完成。

浏览器进一步验证：切换到法人 A 后，法人 B 创建的来源与店铺从列表和范围选项中消失；切回 B 能读取真实台账计数。桌面 1440×1000 与移动 390×844 截图均已查看。本地浏览器验收服务已停止，合成验证数据库保留供复核。

本地浏览器验收使用 `services/worker/scripts/verify_browser_server.py`，真实 API/Worker/PostgreSQL，仅 ERP HTTP 边界为 MockTransport 合成响应。已验证邮箱形式管理员登录、集团/双法人切换、来源创建、W0 入队到父子运行成功、Raw 页血缘、店铺归属 Dialog 与 ConfirmDialog 批准，以及 390×844 移动布局。截图仅含合成组织和店铺，保存在忽略目录 `output/playwright/.playwright-cli/`。这不代表真实账号探测或全量导入已执行。

浏览器发现并修复 bootstrap 与登录接口的登录名格式不一致，统一初始化/创建/登录契约，6 项登录与 bootstrap 测试通过。发现来源首页漏计 Raw manifest 并重复统计父子批次，已补归档行数与父运行统计，真实 Worker 批次定向测试通过；最新来源由运行外键关联，连接健康采用独立连接状态。新增变更仍需最终验证。

冲突审核新增有效重新映射证据门禁、并发版本检查和审计事件；缺少修复 manifest 不允许批准，新失败重新打开冲突并清除旧修复证据。来源台账新增真实 API 驱动的冲突列表和批准/退回 ConfirmDialog。冲突与售后定向 4 项通过，相关 mypy 和 Web 类型检查通过；完整检查仍在运行，新增冲突测试另行执行，不计入已启动的 183 项 API 全量集合。

最新迁移头为 `0062_canonical_after_sales`。本机隔离 PostgreSQL 16.14 的 `dat011_0062_empty_verify` 空库、`dat011_0062_upgrade_verify` 从 0053 升级均通过，149 张表，升级库保留 1 条存量合成法人记录。没有执行远程迁移。

目录版本 `.6` 新增 W2 售后列表，使用官方子项 `item_identifier` 保留独立退款、退货和换货事实，父记录 ID 不作为唯一键。逐行先验证全部子项，较旧来源更新时间不覆盖有效事实；Raw 行数与子项写入数独立计算。币种符号不推断 ISO 币种，未确认时区不推断 UTC，质量状态保留在事实和人工队列中，查询不生成金额汇总。售后、规范查询和 Worker 批次定向 5 项通过，Web 类型检查通过。

组织治理范围回归发现业务单元授权曾被错误地当作整个法人治理授权，失败测试复现后修正：组织治理独立要求显式法人或集团范围，概览仅列举可治理法人。治理、售后及规范查询 5 项通过，治理模块 mypy/ruff 通过。来源归属批准/拒绝改用统一 ConfirmDialog，浏览器验收仍待执行。以上新增证据不代表最终全量质量门已通过。

0061 新增周期采集台账和批次请求指纹：历史订单每 7 天分区（可缩小到 1 天），单批上限 128 分区，父/子运行与 Job 同事务入队；后台按独立子任务执行，父批次合并计数、失败及取消。API 返回 queued；Web 时间窗口同步走分批 API，来源台账新增采集计划的创建、编辑、启用/暂停、成功水位和错误状态。

订单基于官方 UTC 更新时间定期拉取，保留重叠和安全延迟、每天重新检查配置的历史窗口；目录和当前库存只声明快照采集。计划默认暂停，Worker 每 30 秒检查到期计划；全部子运行成功才推进水位，失败/部分失败/取消保留水位并要求处理，权限与范围每轮重查。尚不能将这些周期轮询称为来源事件推送或全部资源的实时同步。

0061 空 PostgreSQL 和 0053 升级库均通过，148 表，存量合成法人保留。`verify_source_schedules.py` 在 loopback 隔离库验证 4 个并发调度器、2 个计划只入队 2 个 Job，取消后水位不前进，外部请求 0。Worker/Jobs/规划/队列/调度定向 47 项通过，后续旧执行令牌隔离回归及端到端队列测试 13 项通过；Web tsc、API 144 文件 mypy 通过。后续修改仍需最终全套回归。

执行隔离补充：页落库和运行结束在事务中锁定并校验当前 Job 的执行令牌；旧 Worker 即使复用相同 worker_id 也不能完成或失败新领取的任务。租约丢失不再由旧 Worker 把资源运行改为取消；取消入口与页落库统一按 Job → 运行的顺序加锁。

异步报告补齐：官方既有导出任务查询已进入 W8 目录（版本 .3），Worker 保存移除下载凭据的状态页，排队/生成中按 30 秒退避重查，状态/文件使用不同页号；下载只允许显式受信域名，禁止重定向和向下载端转发 ERP 凭据。二进制报告按原字节内容寻址压缩归档，不猜测报表行结构，规范写入为 0。官方文档未确认下载域名，`SOURCE_REPORT_DOWNLOAD_HOSTS` 默认空，此时 DONE 只表示外部生成完成，本地运行报 download_host_pending，不宣称文件已接入。HTTP INFO/DEBUG 日志在 handler 接收前屏蔽签名 URL，HTML 等非 JSON 429/5xx 也按可重试错误处理。Worker/Connector/Jobs/API 入队定向 54 项通过；补充非 JSON 错误与二进制流测试后相关 26 项通过，ruff / mypy 通过。

本次完整 `pnpm check` 在 API 阶段结束：166 通过、3 失败（均为测试仍断言 0057 迁移头）；修正为与实际 Alembic head 比较后的相关 8 项通过。完整检查仍需在所有剩余变更完成后重新运行，不能将定向复测视为整体通过。本次 `pnpm build` 已通过，日志仅保存在忽略目录 `.tmp/dat011-build-verification.log`。

0060 新增不含凭据/Token 的共享请求预算表：多个 Worker 按 AppID/官方路径散列原子预留时隙，等待期间检查租约与取消，超过最大等待的预留回滚。Token 在 Worker 进程内有界缓存，跨资源任务与顺序事件循环复用；凭据变更创建新 Provider。协议/限流/Raw/规范整链定向 18 项通过，补充等待中取消与预算上限后协议/限流 13 项通过。PostgreSQL 两连接池、8 个并发预留获得唯一的 0..7 秒时隙，连接均释放。0060 的空库与 0053 升级路径通过，147 表、存量合成行保留。

正式组织初始化补齐：严格 bootstrap v2 契约、逐表预检及计划哈希，在领域入口强制隔离测试库、执行确认、备份 ID 与哈希复核。v2 显式建立管理员、角色权限、法人成员与范围授权，不复用演示账号；凭据仅从指定环境变量读取且不输出。循环/跨法人上级、未知权限、内联密码、身份漂移被拒绝，凭据失败整笔回滚，重复执行不重置密码。

SQLite bootstrap / retirement / CLI 共 10 项通过，包括退役后重新登录与权限保持、旧会话撤销。独立本地 PostgreSQL 16.14（0059）验证创建 1 集团、2 法人、3 业务单元、2 管理员、2 角色、4 成员关系、4 角色分配、4 范围授权；两名管理员实际密码认证、切换法人、集团范围和重复执行均通过。此证据仅涉及合成数据，不代表服务器组织或领星真实数据已经初始化。

最新目录进展：W4 采购单、W5 SP 广告活动、W6 费用明细、W7 新版 Review、W8 所有订单源报表已分别从官方文档核实只读路径和分页信封，接入通用 Raw 页执行。采购/财务/客服等日期作为用户显式填写的来源日期，不擅自转换为 UTC。W5 固定发送 X-API-VERSION:2，W6 使用 data.records/data.total；查询字段白名单拒绝注入认证参数。W4-W8 的上述资源仍是 schema_pending，仅写 Raw；并不表示各波次全部接口已覆盖。分页与参数/协议定向测试 14 项通过。

本轮补充（仍未完成最终验收）：0059 将受信 ScopeContext v2 选择写入 AuthSession。集团范围与显式拒绝、跨法人父子关系/循环/版本冲突、规范事实范围查询均有合成测试。新增集团/法人/业务单元/成员/合并口径治理 API 与统一 Dialog 页面；成员关系不隐式授予角色权限，主法人账号保留账号停用流程。来源台账页面接入资源启停、时间窗口入队、归属审核、checkpoint、父子运行取消和 Raw manifest 血缘。规范事实页面读取新查询契约，不将订单总额冒充收入。

本机隔离 PostgreSQL `dat011_0059_empty_verify` 空库与 `dat011_0059_upgrade_verify` 的 0053 升级路径均到达 `0059_trusted_scope_selection`，146 表，存量合成法人行保留。旧的 0058 验证仍是历史记录。新增目录共用 `zhixing-connectors.catalog`，已确认本地仓、海外仓、平台仓和 AWD 仓的官方只读列表，映射仓库并保留来源停用状态。Worker 每页重查发起人账号/权限/范围，缺少可信账号的任务失败关闭；合成整链现覆盖真实认证模拟、双法人同键店铺、归属审核、订单、产品、仓库、库存数量、迟到更新、坏行保留与店铺时区。

本轮定向结果：治理/规范查询测试 2 项通过；归属审核/范围测试 2 项通过；来源与范围 API 定向 5 项通过；Worker/Jobs 在目录扩展前 27 项通过；扩展后的整链测试 1 项通过。Web 类型检查和 33 项单测通过；API/Worker/共享 Connector 共 153 源文件 mypy 通过，ruff 通过。上述单测不替代尚未完成的浏览器端到端和最终全量检查。

尚未关闭：W0-W3 各波次全部子资源与映射、W4-W8 全部可确认目录及报告下载域名、权威来源/汇率合并口径、部分旧经营/工作台查询范围兼容、业务模板逐类审查、最终安全检查与浏览器验收。采购单已进入 Raw 执行目录，来源日期时区仍没有证据，不能猜为 UTC。共享限流、Token 复用、批次编排和已确认资源的周期采集已补齐；组织及身份模板初始化已补齐，知识、技能和指标模板不从演示租户自动迁移。

新增验证（当前工作树）：本机 PostgreSQL 16.14 独立集群只监听 `127.0.0.1:55438`；`dat011_empty_verify` 空库和 `dat011_upgrade_verify` 的 0053 存量合成法人升级到 `0058_canonical_source_facts` 均通过，146 张表，存量合成行保留。验证入口为 `services/api/scripts/verify_lingxing_migrations.py`，拒绝非 loopback 主机和非 test/verify 库名。旧报告中的 `alembic -x database_url=...` 没有被 env.py 消费，不能证明其指定库升级；以上显式 Database URL 验证替代该项证据。

0058 新增规范销售订单、订单行、实际库存平衡、主数据来源血缘和 Staging 页结果。官方订单总额不再冒充已付款金额；金额使用 Decimal/NUMERIC(38,12)，汇率未确认时本位币金额保持空。店铺先进入未分配目录，批准店铺归属后才映射订单；坏行、未归属及迟到版本分别统计。真实 Worker + MockTransport 的集团双法人同键店铺、项目隔离、坏行与迟到更新保留有效订单的整链测试已通过；映射单测 4 项、Raw 哈希/路径测试 6 项通过。W0–W3 尚未覆盖各波次所有子资源，不能据此宣称这些波次全部完成。

API 与 Worker 现在显式共享可安装 `zhixing-api` 领域包；每页 manifest、规范数据、冲突、Staging 结果和 checkpoint 共用事务。来源命令及后台任务也改为同一事务，已验证相同请求幂等、不同请求各有任务、入队失败不会留下孤立运行。JobContext 每次检查租约和取消状态；取消后下一页不会执行（Jobs 9 项通过）。正式法人没有演示场景/会议时 overview 返回空值，Web 显示业务空态，不再依赖 seed 中的场景 ID。新增变更尚待本轮最终全量质量门验证，以下历史全量通过记录不覆盖它们。

已修复并验证：共享 `zhixing-connectors` workspace 包统一 API/Worker 协议；AES 使用原始 AppID 字节、官方 SDK 的 ASCII 排序/嵌套 JSON/空值规则，sign 由 HTTP 层只编码一次；Token 获取与刷新支持注入 MockTransport、并发锁和业务错误分类；客户端覆盖 GET、JSON POST、只读 multipart，Host 与只读路径强制白名单，GET/POST 均有有界退避和资源级请求间隔；官方 W0–W3 路径已经从文档核实，W4–W8 保持 `schema_pending`；来源可绑定法人下业务单元并保存 credential_ref 引用；探测和同步均由 Worker 排队执行；Worker 按资源/分区恢复 checkpoint，manifest 幂等范围为运行+页，重复内容哈希可以复用；Raw 接收数与规范写入数分离；新增 0057 来源项目归属和 manifest 身份迁移。

定向结果：Connector/API `10 passed`，Worker `11 passed`，数据中心隔离 SQLite `10 passed`，数据库生命周期 `7 passed`，ruff 与 `uv lock --check` 通过。曾有一次未隔离测试继承远程 DATABASE_URL，在应用导入时 132 秒连接超时；未对远程数据库写入，随后使用隔离 SQLite 重跑。

本轮进一步完成：`demo-retire` 现在按显式租户 manifest 反射真实表结构，输出逐表匹配数、外键阻断、会话撤销数、计划哈希和依赖顺序；执行模式要求 test/verify 数据库、backup ID、计划哈希和显式确认，并在串行化事务中失败关闭。`production-bootstrap` 已支持版本化集团/法人/业务单元 manifest 的真实 dry-run、幂等执行和身份漂移阻断，仍只允许 test/verify 数据库。来源归属新增按来源列举接口；Worker job 只携带 credential_ref，按 env:<prefix> 从进程环境解析凭据，API 侧拒绝 Lingxing 同步直执行。未在任何生产或远程环境执行。

仍未完成：W0–W3 全部子资源的规范映射与对账、店铺/仓库归属人工审核页面闭环、bootstrap 正式管理员和权限模板迁移、完整集团范围选择与运行详情、W4–W8 官方资源目录及异步报告补全、增量调度与全套最终验证。真实来源凭据和生产配置属于后续受限注入与交接，本轮不访问。DAT-011 继续保持 `in_progress`，不能宣称真实领星数据已接入。

已完成：ScopeContext v2 字段快照扩展；新增服务端当前主体可选范围 API（集团关联法人、业务单元、店铺、仓库）；同步服务在省略范围时从持久化企业目录解析，不再回退演示企业；0054 来源资源基础迁移、0055 运行/范围元数据和 0056 币种/来源时间增量迁移；领星官方 Host/只读路径约束、签名、凭据 Provider 与 MockTransport 可测试客户端；来源注册自动建立 W0-W8 资源台账、编辑、停用、只读探测、资源启停、映射冲突审核、权威资源规则、父运行资源明细和 Raw manifest 查询 API；资源目录与 checkpoint 查询 API；bootstrap/retire 安全 CLI dry-run 门禁与 backup ID 校验；任务索引状态更新。

`schema_pending`：W4-W8 未确认官方 Schema 的资源必须保持该状态，不进入指标、AI 或集团汇总。

本地验证：领星、Raw、资源目录、脱敏、Token 生命周期和演示企业静态回归测试均已通过；Worker 分页、租约和父子状态聚合测试均已通过；单集团双法人三业务单元合成隔离测试通过。`node tools/workspace.mjs check` 与 Alembic head/history 检查通过。空 SQLite 库升级、0053→0057 回放及 0057→0056→0057 回滚往返已实测通过；生产候选环境此前仅迁移至 0056，本轮未执行远程迁移。

最新质量门（2026-09-09）：`pnpm run doctor`、`node tools/workspace.mjs check`、`pnpm build`、Web 测试（10 文件/33 测试）和 API/Jobs/Worker 静态检查已通过；数据库空库升级和 0053→0057 回放已通过；在隔离 SQLite、本地文件对象存储和关闭 Agent Runtime 探针的测试环境中，`pnpm check` 全量通过：API `157 passed`，Agent Runtime `3 passed`，Codex Runtime `3 passed`，Jobs `8 passed`，Worker `11 passed`，Mock Commerce `6 passed`，Mock Memory `2 passed`，Mock Knowledge `3 passed`，MCP Gateway `4 passed`。

DAT-011 相关定向回归全集通过：API 领星、Raw、资源目录、脱敏、Token、范围、数据中心、Commerce、Customer360、Decision、Knowledge 回归均通过；Worker `10 passed`。

本次全量质量门使用隔离 SQLite 完成；生产候选环境此前在备份后执行过 PostgreSQL 0054/0055/0056 增量迁移并复核关键表结构，本轮未执行远程迁移，未访问领星账号或写入真实领星数据。

可复现命令：`pnpm check`；`uv run --directory services/api alembic heads`；`$env:PYTHONPATH='services/api/src'; pytest services/api/tests/test_lingxing_contract.py services/api/tests/test_raw_archive.py services/api/tests/test_resource_catalog.py services/api/tests/test_redaction.py services/api/tests/test_token_provider.py -q`；`$env:PYTHONPATH='services/worker/src'; pytest services/worker/tests/test_lingxing_sync.py services/worker/tests/test_lease.py services/worker/tests/test_aggregation.py -q`。

生产交接条件：客户确认集团/法人/业务单元、只读凭据通过受限注入、生产副本迁移 dry-run、W0 店铺归属人工批准；本任务未访问真实账号或远程环境。

补充证据：bootstrap 与 credential_ref 链路补齐后的本地全量 API pytest `158 passed in 1304.12s`；Worker 当前定向套件 `11 passed`，Jobs `8 passed`；生产候选发布 `/opt/zhixing-releases/zhixing-20260909-dat011-0056` 已通过本机和公网健康检查，服务错误计数为 0。未声明真实领星数据已接入。

远程只读验收（2026-09-09）：`https://zhixing.maysu.com/health/ready`、`https://api.zhixing.maysu.com/health/ready`、`https://hook.zhixing.maysu.com/health/ready` 均返回 `200` 且状态为 `ready`；`/console` 返回 `200`。本次未使用服务器密码、领星凭据或任何真实 Token，也未执行远程发布、迁移、重启或数据变更。
