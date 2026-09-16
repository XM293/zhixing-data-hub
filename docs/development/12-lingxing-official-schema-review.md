# 领星官方只读字段复核

复核日期：2026-09-09。仅阅读官方站点的公开说明，没有调用 ERP 业务接口，没有使用账号凭据。合成测试自行构造，不复制客户响应。官方导航 `/_sidebar.md` 提供公开文档索引；下列链接直接定位官方说明。

## 已落地的目录扩展

| 资源 | 官方说明 | 处理 |
| --- | --- | --- |
| 亚马逊市场 | [AllMarketplace](https://apidoc.lingxing.com/#/docs/BasicData/AllMarketplace) | GET，无分页；以 marketplace_id 建参考目录，保留 mid、国家和地区关联 |
| 亚马逊概念店铺 | [ConceptSellerLists](https://apidoc.lingxing.com/#/docs/BasicData/ConceptSellerLists) | GET，无分页；以 id 建 concept_store，不等同 sid |
| 国家下地区 | [WorldStateLists](https://apidoc.lingxing.com/#/docs/BasicData/WorldStateLists) | POST，country_code；国家、地区名称和 code 构成来源键 |
| 多平台国家下州省 | [StateList](https://apidoc.lingxing.com/#/docs/BasicData/StateList) | POST，countryCode；data.states 信封，独立来源命名空间 |
| 多平台店铺 | [StoreInfoV2](https://apidoc.lingxing.com/#/docs/MultiPlatform/V2/StoreInfoV2) | POST，offset/length，页长 200；data.list/data.total；store_id 唯一，sid 只作关联属性 |
| 月汇率 | [Currency](https://apidoc.lingxing.com/#/docs/BasicData/Currency) | POST，date 为 YYYY-MM；换算基准与方向缺乏明确证据，schema_pending，仅 Raw |
| 品牌 | [Brand](https://apidoc.lingxing.com/#/docs/Product/Brand) | POST，offset/length；bid、title、brand_code，规范参考目录 |
| 产品分类 | [Category](https://apidoc.lingxing.com/#/docs/Product/Category) | POST，offset/length；cid、parent_cid、title、category_code，保留父级来源键 |
| 供应商 | [Supplier](https://apidoc.lingxing.com/#/docs/Purchase/Supplier) | POST，offset/length；以 supplier_id 为键，忽略已停用的 customer_supplier_id；停用标志保留，Core 不复制银行和联系人字段 |

上述资源已加入共享目录版本 `lingxing-2026-09-09.8`（本版新增库存流水、FBA 库存 Raw 资源）。多平台嵌套信封、同号店铺隔离及真实 Job 队列结合 MockTransport 的整链测试通过。尚未进行真实账号对账。

## 后续实现时必须保留的证据与阻断

### 库存流水和 FBA 共享库存

[WarehouseStatementNew](https://apidoc.lingxing.com/#/docs/Warehouse/WarehouseStatementNew) 的只读路径为 `/erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement`，offset/length，默认页长 20；来源日期左闭右开，未传 types/sub_types 时全部类型。新增 `inventory_statements` 要求显式日期。statement_id 可作为来源身份，但数量正负与各结存量的对账公式、操作时间时区、成本币种尚未确认，当前保持 schema_pending，仅 Raw，不映射净出入库或金额。

[FBAStock_v2](https://apidoc.lingxing.com/#/docs/Warehouse/FBAStock_v2) 的只读路径为 `/basicOpen/openapi/storage/fbaWarehouseDetail`。新增 `fba_inventory` 用页长 200，显式包含零库存、已删除 Listing，不合并父 ASIN，并请求共享仓子店铺数量。共享仓 sid=0，响应没有可直接等同本地 wid 的仓库主键；共享库存归属、跨店重复计数、成本币种未确认。保持 schema_pending，不能自动归属星云项目，不能进入规范库存与集团汇总。

这两项是 W3 尚未完成规范映射的明确阻断，不计作 W0-W3 交付完成。当前可验证的是分页、Raw 归档和禁止投影的通用链路。

### 售后订单

[afterSaleList](https://apidoc.lingxing.com/#/docs/Sale/afterSaleList) 明确为只读 POST `/erp/sc/routing/amzod/order/afterSaleList`；必须提供来源日期 start_date/end_date，左闭右开；date_type=3 表示更新时间。默认分页 1000。请求示例误写 data_type，与参数表冲突，实现须按参数表 date_type 并记录契约测试。

父记录 id 明确不是唯一键；子 item_list 的 item_identifier/md5_v2 才是现行唯一标识。md5/md5_new 已废弃，不能用行序号或父 id 代替。售后事件时间和更新时间应取子项 after_time/data_update_time，而非只取父级。

金额字段包含货币符号（如 $），不能当作 ISO 币种代码；同一符号可能代表不同币种。官方未明确这些本地时间的时区，不能直接标记 UTC。0062 已实现独立售后子项规范事实、来源文本、币种/时区质量标记与只读查询；不输出待确认金额汇总。子项唯一键、迟到数据、整行校验及拒绝后换绑保护已用合成数据验证，仍没有真实账号对账证据。

### 头程物流商

[QueryHeadLogisticsProvider](https://apidoc.lingxing.com/#/docs/Logistics/QueryHeadLogisticsProvider) 为 POST `/basicOpen/logistics/headLogisticsProvider/query/list`，使用嵌套 search.page/search.length，返回 data.providers/data.total。已加入执行目录与规范实体映射，三项筛选必须显式提供：enabled=0/1、isAuth=0/1、payMethod=1/2；完整目录需枚举八种组合。providerId 是来源键，联系人不进入 Core，来源状态保留。逐页提交与从第三页恢复使用 MockTransport 验证；没有真实账号验证。
# 2026-09-09 库位目录校核（目录 .9）

目录 .10 增加 W0 ERP 用户目录。官方 [BasicData/AccoutLists](https://apidoc.lingxing.com/docs/BasicData/AccoutLists.md) 确认 GET `/erp/sc/data/account/lists` 返回全部开启的 ERP 账号，无分页参数。规范映射仅使用 uid、realname、status（0/1）及 is_master（0/1），写入来源实体 source_user，要求来源归属；不创建 UserAccount/Principal、不迁移 ERP 权限、不按 seller 名称列表自动批准店铺、不把电话、邮箱和登录 IP 投影到 Core。来源登录时间时区未确认，不推断 source_updated_at。

官方 [Warehouse/warehouseBin](https://apidoc.lingxing.com/docs/Warehouse/warehouseBin.md) 确认只读 POST `/erp/sc/routing/data/local_inventory/warehouseBin`，采用 offset/limit，默认每页 20，不设置状态过滤以覆盖停用库位。返回字段表的 whb_status、SKU/FNSKU 与同页示例 status、sku/fnsku 不一致，storage_bin 的声明类型与示例也不一致。warehouse_bins 暂按 schema_pending 逐页归档，禁止规范映射及指标使用；等待官方字段契约澄清，不能按示例猜测映射。

# W0–W3 受限规范包络决策（2026-09-10，目录 .21 / 映射 2.4.1）

实施代码与上述早期 `schema_pending` 结论发生冲突后，先按官方字段表重新核对并缩小规范层语义。`0069` 保存每个 Raw 页实际使用的非敏感请求参数；`0070` 增加 `canonical_operational_facts`，只接收已明确的来源身份、状态、数量、原币金额、来源本地时间和已审核店铺/仓库/商品关系。它不是指标事实表，也不参与 AI、MCP、集团汇总或权威来源合并。

本轮允许进入该受限包络的资源为月汇率、FBM 订单、FBA 发货单、入库单、出库单、库存流水和 FBA 库存；产品属性进入参考实体，库位仅继承已审核仓库。未确认语义继续用 `quality_flags` 与映射冲突队列阻断：月汇率保留来源值但标记汇率方向和本位币待确认；金额缺币种、来源时区、库存流水方向和共享仓归属不推断。FBA 共享仓 `sid=0` 不会自动归属，跨店铺或跨仓库记录拒绝映射。

真实 FBM 预检进一步证明列表行不返回 `sid`。映射 2.4.1 因此把 Raw 请求中的单店铺 `sid` 与 `order_number` 共同组成规范身份和冲突身份，防止不同店铺同号记录或同仓库未分配记录合并；请求上下文由 0069 的 manifest 字段提供，重放时保持不变。

库位字段冲突采用严格失败策略：映射只接受官方字段表中的 `whb_status`、`type`、`storage_bin` 和 `wid`，示例中的替代字段不会被猜测兼容。真实页如不满足该契约会进入 Schema 冲突队列，已有事实不被删除。共享代码目录中的 `confirmed` 表示具备可审核的严格映射；每个来源已登记的 `SourceResource.schema_status` 仍保持 `schema_pending`，必须在合成测试和该来源真实 Raw 预检通过后，按精确目录版本显式确认，才能产生离线映射任务。
# Listing 目录补充（2026-09-10）

## 市场与多平台店铺实测修订（目录 .19）

官方 AllMarketplace 将 aws_region 标为必填，但同页成功示例明确给出中国市场 aws_region 为空；真实目录也出现 1 条空值。因此保留市场实体，aws_region 记为 null，不用 region 猜填。官方 StoreInfoV2 将 currency 标为必填，真实目录出现 2 条空值；保留店铺进入归属审核，currency_code 记为 null 并写入 currency_pending 质量标记，不能参与币种汇总。非字符串值仍视为 Schema 漂移并拒绝。映射版本提升至 2.3.0，目录提升至 .19，待失败 Raw 页离线重放验证。

本地目录 .18 / 映射 2.2.0：规范持久化、旧页保护、撤权级联、原项目重新批准及跨项目迁移阻断已具备合成测试，Listing 目录标为 confirmed。真实 Raw 预检发现一条删除记录缺少 item_name；显示名在来源名称非空时使用来源名称，删除记录缺名时回退到其必填 seller_sku，非字符串仍拒绝。已有来源登记的 schema_pending 不随目录升级自动解除：管理员通过版本匹配的资源 PATCH 显式确认，产生单次审计；管理页使用 ConfirmDialog。该状态仅说明映射契约可用，真实 37 条记录仍需候选环境重放和逐项对账，不能据此宣称已进入 Core。

归属生命周期：店铺审核撤销必须在同一事务将同法人、同来源、同店铺派生 Listing 标记 unassigned 并清空 Origin 项目；重新批准到原项目可恢复来源状态。已有派生 Listing 的店铺跨项目迁移沿用历史迁移门禁。映射读取已批准 SourceBinding 时持有行锁，避免审核撤销与新派生写入交错后留下过期授权。

规范目录实施决策：Listing 作为店铺派生的业务实体，身份采用 sid+seller_sku，归属只继承当前已批准店铺，不据 local_sku 自动批准商品或仓库。保存 MSKU、本地 SKU、ASIN/FNSKU 与来源状态；删除记录保留为 deleted。只有 listing_update_date 用官方零时区解释，空更新时间使用 Raw 观测时间防止较旧归档覆盖新记录。Listing 中的库存/价格不作为额外经营事实重复汇总；规范持久化和撤权测试完成前仍保留 schema_pending。

官方 `Sale/Listing.md` 确认只读 POST `/erp/sc/data/mws/listing`，sid 字符串必填，offset/length 最大 1000，唯一键为 sid+seller_sku。本地按单店铺及 is_delete=0/1 显式分区覆盖两种状态。listing_update_date 为零时区，pair_update_time 为北京时间；不混用两者。先以 schema_pending 归档，待建立规范 Listing 关联及覆盖测试后再开放映射，不能把该接口中的库存重复计入库存事实。

# W4–W8 核心只读资源受限映射（2026-09-10，目录 .22 / 映射 2.5.0）

官方采购单、SP 广告活动、费用明细、评论管理和所有订单源报表已逐项复核请求字段、分页信封和返回字段。五类资源进入 `canonical_operational_facts` 的受限包络，仍不直接参与指标、AI、MCP 或集团合并：采购单保存仓库、采购状态、原币总额、数量和脱敏后的子项；广告活动保存单店铺活动身份、状态和每日预算，但币种待确认；费用明细保存单店铺分区、原币费用和不含人员/备注的分摊项；评论仅保存星级、状态、站点和标志位，评论正文、标题、作者、邮箱及媒体链接只留在受控 Raw；所有订单源报表按店铺保存行级订单、SKU、数量、原币商品金额及其余金额分量，不推导订单总额。

`finance` 和 `customer_service` 的官方店铺筛选为可选。项目来源运行时将 `sid` 提升为强制单店铺分区，再转换为官方 `sids` 参数；`advertising` 与 `source_reports` 同样按单店铺运行。Worker 在外部请求前验证该店铺已由当前 Scope 获权，并保存实际请求上下文。返回行不含 sid 的接口以该单店铺请求作为范围证据；所有订单源报表还会再次校验行内 sid。没有已审核店铺时在网络请求前失败，不能退回账号全量。

共享目录的严格映射能力不自动更改已有来源的 Schema 状态。每类资源仍须先在隔离候选库以短窗口或单店铺采集，验证真实信封和字段后，使用精确目录版本显式确认并离线重放。报告导出状态只描述任务进度和下载位置，继续保持 `schema_pending`/Raw-only，不生成业务事实。
