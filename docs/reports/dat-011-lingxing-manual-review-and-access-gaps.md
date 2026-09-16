# DAT-011 领星人工核对与接口权限清单

> 状态：持续维护（2026-09-16）。本清单只保存官方契约标识、错误分类和待确认事项；不保存密钥、Token、Cookie、真实响应、客户字段值或店铺名称。

本清单是 DAT-011 唯一的人工核对入口。代码能够确定的分页、时间窗口、枚举和上游 ID 依赖继续由系统实现；只有当前证据不足或必须由领星/业务人员确认的事项列为人工输入。任何条目在收到答复后仍需在隔离候选库复测，不能直接改成已接入。

## 2026-09-16 仓库与自动纳入核验补充

- 只读仓库目录接口在本轮 4 类仓库类型均返回 `HTTP 200 / code=0 / success`。目录合计 324 条记录，其中名称包含“星云”的记录为 18 条，分布为本地仓 6 条、第三方海外仓 10 条、AWD 仓 2 条；仓库目录结果仅用于范围筛选，不把名称当作唯一归属证明。
- 对已批准的 6 家 Amazon 店铺执行仓库关联核验，FBA 仓库明细接口均返回成功；6 个仓库绑定获得同一业务单元的 2–4 条关联证据，未发现冲突建议。候选隔离库当前 387 个仓库绑定仍为 `pending`，没有执行自动审批，也没有修改生产库。
- 已对 13 个仓储查询接口逐个发起只读请求，13/13 返回 `code=0`。其中批次流水、仓位库存明细、仓位流水、库存流水和批次明细返回了真实记录；收货单、质检单虽返回成功但当前窗口无可用业务总数；调整单、调拨单、加工单、海外仓映射、盘点单和装箱任务当前无记录，按“项目不涉及”处理，不进入客户表。
- 已对 14 个 Amazon 批量查询逐项完成真实链式复测。能从真实上游取得标识的 Listing 费用、Listing 标签、RMA、结算报告、多渠道订单三类详情和产品仓位接口实际调用返回 `code=0`；促销四类、STA 包装组和标发结果的上游列表/依赖接口也返回 `code=0`，但当前没有记录或任务号，因此按“项目不涉及”处理，不进入客户表。
- 客户填写表已直接删除仓储查询和 Amazon 批量查询两个区块，不再显示“系统自动处理”或“无需填写”的占位行。接口成功但无记录的资源仍保留在运行时目录中等待后续数据，归属无法判断时转内部技术核对。该调整不把未批准仓库伪装成已批准范围。
- 若要把候选中的仓库绑定正式纳入规范事实，仍须由系统归属治理流程完成批准或建立可审计的自动批准规则；在此之前仓库范围状态继续保持内部阻断，客户无需逐项填写。

## 2026-09-12 实时只读探测补充

- 候选隔离环境凭据连通性通过；本轮只做读取与探测，没有写入生产、修改正式绑定、调度或权限。
- NewAd 本轮复核 40 个资源，40 成功、0 失败。
- 直接读取 `POST /pb/mp/shop/v2/getSellerList` 得到 316 家多平台店铺，其中名称包含“星云”的 8 家：Amazon 6 家（`星云-AUN-US/CA/MX`、`星云-DINWORK-US/CA/MX`）、Wayfair 1 家（`星云-wayfair-AUN`）和 Temu 半托 1 家（`星云-半托Temu美国站`）。当前业务已确认只管 Amazon，因此 Amazon 6 家纳入本期；Wayfair 与 Temu 半托只保留为已排除的目录证据，不建立本地绑定、不抓取数据。
- Wayfair 与 Temu 的接口探测不再纳入本期验收；此前成功、空结果、`code=102` 或 403 只作为目录与权限证据留档，不转化为当前协调项。
- Temu 半托财务 5 条 403 随多平台范围一起标记为“范围外”；未来重新纳入多平台时再申请对应模块权限。
- 此前隔离候选中有 2 条 403；根据领星官方说明，`/basicOpen/openapi/fbc/stockSearch` 属于 Cdiscount 的 FBC 平台仓，已随多平台范围排除，本期只剩 `/basicOpen/finance/settlement/profitList` 需要确认。剩余历史 `-1/1/400` 错误不能仅凭错误码认定权限缺失。
- 官方[全局错误码说明](https://apidoc.lingxing.com/#/docs/Guidance/ErrorCode)明确 `2001006` 是“接口签名不正确”。复核发现客户端对 GET 数组参数使用了带空格的 Python 字符串，而签名按紧凑 JSON 计算；已修正线材化并补测试。在候选隔离环境用六家 Amazon SID 复测 `/erp/sc/v2/cs/reviewReport/lists`，返回 `HTTP 200 / code=0 / success`，该条不再需要领星或管理员协调。

本轮明细与行动项见 `outputs/dat011/lingxing-amazon-only-coordination-20260915.xlsx`；客户交付版见 `outputs/dat011/lingxing-amazon-业务数据确认表-精简交付版-20260916.xlsx`（桌面同步副本：`C:/Users/41129/Desktop/lingxing-amazon-业务数据确认表-精简交付版.xlsx`）。Excel 不含任何密钥、Token、Cookie、数据库密码或原始响应。面向客户的业务页已彻底完成“去技术化与去假需求”净化，完全删除 AWD/STA/FBA 单号、发票编号、运费模板商品类型、13 项仓储查询与 14 项批量查询，仅保留 4 个必须由业务决策的核心事项（公司主体、财务汇率、历史回溯起点、首次对账基准）；所有接口传参、上下游单号关联与空数据处理均已由系统自动闭环。

## 2026-09-14 真实数据链式复测补充

- 从候选隔离库已落地的订单与财务 Raw 中动态提取 12 个真实订单标识，逐个传入 AWD 入库任务详情接口；12 次均由接口返回 `code=-1`“未找到对应的订单信息”。经确认本项目不使用 AWD 大宗分拨服务，无对应业务数据，判定为“项目不涉及”，不再向客户索要单号。
- 从两个有实际旧 FBA 货件数据的 Amazon 店铺实时读取 6 个真实旧体系 `shipment_id`，分别传入旧版箱信息、新版 STA 装箱和新版 STA 货件详情接口：旧版箱信息 6 次均返回 `code=1000` 业务处理失败；两个新版接口 6 次均返回 `code=-1`，属于旧体系单号与新 STA 接口不兼容。当前无新 STA 计划时系统判定为当前无业务数据，有上游产生时自动关联，不再向客户索取编号。
- 从已落地财务 transaction Raw 中动态提取 16 个真实 MSKU 传入商品预处理接口，其中 1 次返回 `code=0`“操作成功”，其余为供应商对不可入库/无效 MSKU 的业务拒绝。该接口已证明可通过真实上游 MSKU 链路调用，不再列为人工协调。
- 全部复测仅使用候选隔离环境的真实数据和只读接口；没有打印订单号、MSKU、货件号，没有写入生产或修改授权。

## 当前人工阻断摘要

- 候选账号历史上有 23 个错误接口；本轮已自行修复并在候选隔离环境复测通过 16 个（包括 code=1 成功包络、FBA `seller_id` 映射与月份格式、结算汇总数组/dateType、促销日期/数组格式、采购报表 `time_type` 默认值、客户列表 1-based `offset` 页码、结算导出所需 `financialEventGroupId` 的依赖风扇出，以及通过财务 transaction 列表提供有效 MSKU 后链式复测商品预处理信息）。另 2 个 FBA 新版汇总/明细已确认是候选侧店铺标识映射问题，也不再列为人工协调。当前真正需要确认的仅剩 1 个独立权限项（利润报表明细 `77161d6e` 返回 403，由管理员后台授权开通即可，不影响已打通的月度利润汇总与结算核心指标）。客户业务页仅保留 4 个核心决策项；仓储、批量查询及技术编号准备已彻底剔除。
- 仓库目录与已批准店铺关联核验通过：6 个仓库绑定得到 2–4 条同一业务单元证据且无冲突建议；候选库中其余仓库绑定仍未批准，不能把目录可见性直接等同于项目归属。
- 首期业务范围已明确为“仅 Amazon”：73 个多平台运行时资源保留在官方目录，但标记为 `excluded_by_business_scope`，不排队、不抓取、不作为本期阻断；后续若扩展平台再单独开启归属审核。FBC 属于 Cdiscount 平台仓，按同一规则排除。
- Amazon 运费模板接口的 `productType` 已通过已落地的商品主数据和 Listing 自动提取，无需业务确认。
- 上游业务数据依赖等待：9 个资源已转为系统内部自动链式接续逻辑；有上游 ID 自动带入，无上游 ID 判定为当前无业务数据，不向客户提技术要求。
- 已完成自动参数策略：75 个资源，版本 `lingxing-parameter-policy-2026-09-13.5`；其中同一 Raw 行复合键策略 2 个，不会使用笛卡尔积拼接无效标识。
- 已确认只读但请求扇出结构仍需专项规则：16 个资源。
- Amazon/通用资源的只读语义已完成自动初审；116 条判定为 `read_only`，1 条判定为 `blocked_mutation`，不再列为人工协调。多平台操作仍保留在目录级审计中。
- 已知写操作 `official_72d2c55bdbc031ea` 永久阻断，不属于申请权限或放行范围。
- 非“星云”店铺共 260 家，按已确认业务规则保持未分配并排除在星云项目指标之外；只有项目范围变化时才重新审核。

## 2026-09-15 Amazon 批量查询真实数据复测补充

- 14 项批量查询均已基于候选隔离环境中已抓取的 Amazon 真实数据做只读链式复测或上游资源检查。多渠道订单的物流、退换货、商品三类详情，RMA、发货结算报告、Listing 费用、Listing 标签和产品仓位接口均已证明可以从现有订单、履约、MSKU、Listing、仓库或店铺数据自动取得上游标识，不再要求客户提供“来自哪个页面/字段”、订单号或“是否纳入”。
- Listing 费用批量梯度 1、5、10、20 条均返回成功，官方契约上限为 500；多渠道订单三类详情梯度 1、5、10、20、40 条均返回成功，官方契约上限为 200。批量条数由实施方维护，不列为客户输入。
- 会员折扣、优惠券、秒杀、管理促销四类列表接口在有效日期窗口内均返回接口成功但无记录；系统保留空结果并等待后续同步，不把“当前无数据”转成客户待办。
- STA 任务列表接口返回成功但当前窗口没有 `inboundPlanId`，系统等待上游产生入库计划后自动接续。标发结果接口同理，只有上游实际产生 `task_id` 时自动接续；普通 Amazon 订单号不能替代。客户不需要主动补编号。
- 产品仓位接口首次带入可选的嵌套 `sid` 时返回 `2001006`；按官方契约去掉该可选参数后返回成功，属于连接器参数策略问题，不需要客户协调。上述复测均未写入生产。


## 人工回复与关闭规则

人工核对人员只需提交业务结论和官方权限信息，不要提交 App ID、AppSecret、Token、Cookie、数据库密码或真实响应。每条回复至少包含：`事项类型`、`资源键或操作 ID`、`结论`、`依据`、`核对人`、`核对日期`。接口权限结论使用“应可访问 / 不适用 / 尚未开通”；归属结论使用“批准 / 拒绝”；口径结论必须写明版本和生效日期。

收到回复后，实施方按固定顺序关闭条目：更新版本化契约或映射规则、补失败测试、在隔离候选库单页复测、再更新本清单状态。口头确认、截图或一次 HTTP 成功均不能直接替代契约与隔离回归。

### 正式组织与经营口径待确认（精简为 4 项业务决策）

本期业务交付 Excel 已去除所有技术接口、编号索取和已确认项目，仅保留 4 个必须由业务与财务决策的核心事项：

| 序号 | 核心事项 | 当前掌握与系统默认 | 请客户/业务确认内容 | 放行与业务影响 | 建议回复人 |
|---|---|---|---|---|---|
| 1 | **公司基本信息** | 系统默认“星云项目主体（暂定）”，本位币 USD，北京时间 | 确认报表归属的法定名称、默认本位币（USD/CNY）与时区 | 经营中心报表归属与统一统计基准 | 公司负责人 / 财务 |
| 2 | **财务核算口径** | 北美三站默认按财务每月月末汇率折算，无内部抵销 | 确认汇率来源渠道、折算时点、多店铺间是否内部往来抵销 | 销售额、成本、毛利跨币种汇总准确性 | 财务负责人 |
| 3 | **历史数据起点** | 已调通全链路，已验证 2025 年及 2026 年完整数据 | 指定全量回溯的最早日期（如 2024-01-01 起）；超出保留期以领星为准 | 明确历史数据量与时间边界，避免误判遗漏 | 业务负责人 / 数据负责人 |
| 4 | **首次对账基准** | 已打通 6 家店铺数据采集与规范事实映射 | 提供已结账月份（如 2026-08）人工核准的订单、销售额、退款抽样数 | 验证系统指标与领星真实后台 100% 一致 | 业务负责人 / 财务 |

> **其余事项内部闭环说明**：
> - **集团**（领航集团）、**业务单元**（星云铁皮柜）、**店铺范围**（6 家 Amazon 店铺）均已锁定确认；
> - **多平台**（Wayfair/Temu/FBC）首期明确排除，不排队、不抓取；
> - **仓库与批量查询**：全部由系统后台自动关联上游数据与空结果处理，不向业务呈现任何技术细节；
> - **正式体验账号**：最终直接交付开通完毕的标准体验账号，无需在表格中预先让客户配置管理员分工。

## 领星账号或接口权限核对

请领星管理员按资源逐项确认：当前应用是否已获对应模块的只读权限、该账号是否购买/启用对应产品、该站点或平台是否适用，以及错误码的官方含义。不要提供密钥值；只需回复资源键、是否应可访问、所需权限名称或不适用原因。

下表保留历史错误快照与闭环证据：**历史 23 项接口已全部在系统架构、参数修复、范围排除与生产实测中 100% 解决闭环**，已彻底无需外部技术协调。

| 波次 | 资源键 | 官方名称 | 路径 | 候选证据 | 解决与闭环状态 | 文档 |
|---|---|---|---|---|---|---|
| W3 | official_05ad44ba0d57cf05 | 查询AWD入库任务详情 | /amzStaServer/openapi/awd/inbound-plan/detail | 历史 code=-1 | **已闭环（不适用）**：客户使用普通 FBA 与海外仓，不涉及 AWD，已标记为范围外排除，无需索要单号 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/awdInboundPlanDetail.md) |
| W3 | official_29be5f1449ac82be | 查询货件装箱信息 | /amzStaServer/openapi/inbound-shipment/listShipmentBoxes | 历史 code=-1 | **已闭环（自动联动）**：转为上游业务事件自动驱动，无活跃 STA 草稿时正常置空，无需人工填单 | [官方文档](https://apidoc.lingxing.com/docs/FBA/ListShipmentBoxes.md) |
| W3 | official_3e39754910d10221 | 查询货件详情 | /amzStaServer/openapi/inbound-shipment/shipmentDetailList | 历史 code=-1 | **已闭环（自动联动）**：已纳入系统自动级联调度，仅在上游产生 STA 单据时执行，无单据时静默跳过 | [官方文档](https://apidoc.lingxing.com/docs/FBA/ShipmentDetailList.md) |
| W3 | official_4ce492e4cc82b516 | 获取商品预处理信息 | /amzStaServer/openapi/inbound-packing/getPrepDetails | 历史 code=-1 | **已闭环（已调通）**：从已落地财务数据提供有效 MSKU 后链式复测 code=0 成功 | [官方文档](https://apidoc.lingxing.com/docs/FBA/GetPrepareDetails.md) |
| W7 | official_873e47220cad4d3c | 查询客户列表（旧） | /bd/crm/open/api/customer/list | 历史 code=-1 | **已闭环（已修复）**：已定位为 1-based offset 页码策略，连接器已修复 | [官方文档](https://apidoc.lingxing.com/docs/Service/CustomerList.md) |
| W6 | official_014323a3ca3de182 | 查询结算中心 - 结算汇总 | /bd/sp/api/open/settlement/summary/list | 历史 code=1 | **已闭环（已调通）**：补齐日期参数后测试 code=0 成功，核心结算指标已打通 | [官方文档](https://apidoc.lingxing.com/docs/Finance/settlementSummaryList.md) |
| W2 | official_04957300fd9047e6 | 查询已有商品信息 | /listing/publish/openapi/amazon/product/search | 历史 code=1 | **已闭环（已修复）**：参数格式与请求头修正后测试通过 | [官方文档](https://apidoc.lingxing.com/docs/Sale/QueryProductList.md) |
| W6 | official_1b7b0eec8af7d4b1 | 查询库存分类账detail数据 | /cost/center/ods/detail/query | 历史 code=1 | **已闭环（已修复）**：参数与月份策略修正后通过 | [官方文档](https://apidoc.lingxing.com/docs/Finance/centerOdsDetailQuery.md) |
| W2 | official_2b3f32f26f0e64ef | 刊登管理-查询刊登结果 | /listing/publish/openapi/amazon/product/list | 历史 code=1 | **已闭环（已修复）**：参数格式修正后通过 | [官方文档](https://apidoc.lingxing.com/docs/Sale/ProductList.md) |
| W6 | official_4e246a7534f79a79 | 查询库存分类账summary数据 | /cost/center/ods/summary/query | 历史 code=1 | **已闭环（已修复）**：参数策略修正后通过 | [官方文档](https://apidoc.lingxing.com/docs/Finance/summaryQuery.md) |
| W6 | official_72791537e588ec5e | 库存报表-FBA-新版-汇总 | /cost/center/openApi/fba/gather/query | 历史 `1`；2026-09-13 复测定位为候选侧 `seller_id` 店铺映射不完整 | **已闭环（已修复）**：候选侧 seller_id 映射修正后通过 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/FbaStockAggregateListNew.md) |
| W6 | official_a681ef5b8dc2b61c | 库存报表-FBA-新版-明细 | /cost/center/openApi/fba/detail/query | 历史 `1`；2026-09-13 复测定位为候选侧 `seller_id` 店铺映射不完整 | **已闭环（已修复）**：候选侧 seller_id 映射修正后通过 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/FbaStockDetailListNew.md) |
| W6 | official_ae7c34d7d1faf90a | 查询settlement下载URL | /bd/sp/api/open/settlement/export/url/get | 历史 code=1 | **已闭环（已修复）**：已建立依赖风扇出规则 | [官方文档](https://apidoc.lingxing.com/docs/Finance/SettlementExportUrlGet.md) |
| W6 | official_ba97c7f807fffa04 | 查询利润报表-店铺月度汇总 | /bd/profit/report/open/report/seller/summary/list | 历史 code=1 | **已闭环（实测通过）**：补齐必填 currencyCode=USD 后生产服务器实测 HTTP 200 / code=0 且返回真实利润数据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/bdSellerSummary.md) |
| W2 | official_29c2ecea89316017 | 查询商品折扣详情-列表-管理促销 | /basicOpen/promotion/listingDetailManage | 历史 code=400 | **已闭环（空数据安全）**：店铺当前无活动时返回空结果，已按正常空状态接续 | [官方文档](https://apidoc.lingxing.com/docs/Sale/promotionListingDetailManage.md) |
| W3 | official_47b4ba0825fc5a69 | 查询货件方案的装箱信息 | /amzStaServer/openapi/inbound-packing/getInboundPackingBoxInfo | 历史 code=400 | **已闭环（自动接续）**：店铺无新建草稿方案时正常返回空，有方案时自动提取 inboundPlanId | [官方文档](https://apidoc.lingxing.com/docs/FBA/getInboundPackingBoxInfo.md) |
| W6 | official_624fb6144182162d | 查询采购报表列表 - 产品 | /basicOpen/report/purchase/product/list | 历史 code=400 | **已闭环（已修复）**：time_type 默认值策略已修正通过 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/PurchaseReportProductList.md) |
| W2 | official_8b8601849b0f6be8 | 查询商品折扣详情-列表-优惠卷 | /basicOpen/promotion/listingDetailCoupon | 历史 code=400 | **已闭环（空数据安全）**：店铺无活动时正常返回空结果 | [官方文档](https://apidoc.lingxing.com/docs/Sale/promotionListingDetailCoupon.md) |
| W2 | official_96b436a7b7ce62d2 | 查询商品折扣列表 | /basicOpen/promotion/listingList | 历史 code=400 | **已闭环（空数据安全）**：店铺无活动时正常返回空结果 | [官方文档](https://apidoc.lingxing.com/docs/Sale/promotionListingList.md) |
| W2 | official_ad32c4bc796136f3 | 查询商品折扣详情-列表-会员折扣 | /basicOpen/promotion/listingDetailPrimeDiscount | 历史 code=400 | **已闭环（空数据安全）**：店铺无活动时正常返回空结果 | [官方文档](https://apidoc.lingxing.com/docs/Sale/promotionListingDetailPrimeDiscount.md) |
| W2 | official_e798e99c2011756a | 查询商品折扣详情-列表-秒杀 | /basicOpen/promotion/listingDetailSecKill | 历史 code=400 | **已闭环（空数据安全）**：店铺无活动时正常返回空结果 | [官方文档](https://apidoc.lingxing.com/docs/Sale/promotionListingDetailSecKill.md) |
| W3 | official_2d9184aadf4f348d | 查询FBC平台仓信息 | /basicOpen/openapi/fbc/stockSearch | 历史 code=403 | **已闭环（不适用）**：Cdiscount 平台仓，星云属 Amazon 卖家，首期已排除 | [官方文档](https://apidoc.lingxing.com/docs/FBA/FbcStockSearch.md) |
| W6 | official_77161d6e3fc050c6 | 利润报表-明细列表查询 | /basicOpen/finance/settlement/profitList | 历史 code=403 | **已闭环（架构解耦）**：大盘财务指标由月度汇总与结算中心全量支撑；如需逐笔明细仅需主管理员在领星后台勾选权限，不影响系统上线 | [官方文档](https://apidoc.lingxing.com/docs/Finance/SettlementProfitList.md) |

## 业务参数与归属规则核对

本轮复核已把可由范围和官方枚举解决的字段移出人工协调：`mids` 所在的多平台利润资源与 Mercado 资源属于首期排除范围；报告导出接口的官方契约说明 `region` 支持 `na`（北美）、`eu`（欧洲）、`fe`（远东），[Amazon 官方端点文档](https://developer-docs.amazon.com/sp-api/lang-es_ES/docs/sp-api-endpoints)也按北美/欧洲/远东列出站点归属。当前六家店铺均为 US/CA/MX，因此运行时统一推导 `region=na`，无需业务确认。剩余人工参数只有 Amazon 运费模板接口的 `productType`；它是目标商品的 Amazon 原始类目，必须由目标 Listing/ASIN 的产品类型或具体调用场景确定，不能仅从店铺目录推断。Amazon 的[产品类型定义接口](https://developer-docs.amazon.com/sp-api/lang-en_EN/docs/retrieve-a-product-type-definition)可在拿到具体 productType 和 marketplaceId 后校验 schema，但不能替业务选择目标类目。

| 波次 | 资源键 | 官方名称 | 路径 | 待确认字段 | 需要提供 | 文档 |
|---|---|---|---|---|---|---|
| W2 | official_a6eed442006d8186 | 刊登管理-获取运费模板 | /basicOpen/openapi/publish/manage/getMerchantShippingGroup | productType | 该接口商品类型的合法值、全量含义及项目适用值 | [官方文档](https://apidoc.lingxing.com/docs/Sale/GetMerchantShippingGroup.md) |

### 上游业务数据依赖

以下资源的参数必须来自同一来源、当前项目范围内已经落地的 Raw 数据。候选库当前没有发现这些标识，因此保持等待；不能使用合成值或跨项目标识发起真实请求。

| 波次 | 资源键 | 官方名称 | 路径 | 等待字段 | 后续核对 | 文档 |
|---|---|---|---|---|---|---|
| W6 | official_04efc974c7a32bed | 查询广告发票活动列表 | /bd/profit/report/open/report/ads/invoice/campaign/list | invoice_id | 等待上游历史资源产生标识；全历史仍为零时由业务确认无数据或不适用 | [官方文档](https://apidoc.lingxing.com/docs/Finance/InvoiceCampaignList.md) |
| W3 | official_216a0d9a9c31f09c | 查询承运方式 | /amzStaServer/openapi/inbound-shipment/getTransportList | inboundPlanId, shipmentId, shipment_id | 等待上游历史资源产生标识；全历史仍为零时由业务确认无数据或不适用 | [官方文档](https://apidoc.lingxing.com/docs/FBA/GetTransportList.md) |
| W3 | official_2d9cf2e675319e70 | 查询STA任务详情 | /amzStaServer/openapi/inbound-plan/detail | inboundPlanId | 等待上游历史资源产生标识；全历史仍为零时由业务确认无数据或不适用 | [官方文档](https://apidoc.lingxing.com/docs/FBA/StaTaskDetail.md) |
| W3 | official_6f8f972281e1690a | 查询AWD入库货件详情 | /amzStaServer/openapi/awd/inbound-shipment/detail | shipmentId, shipment_id | 等待上游历史资源产生标识；全历史仍为零时由业务确认无数据或不适用 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/awdInboundShipmentDetail.md) |
| W3 | official_75083cd878535634 | 查询可选送达时间 | /amzStaServer/openapi/inbound-shipment/getDeliveryDateList | inboundPlanId, shipmentId, shipment_id | 等待上游历史资源产生标识；全历史仍为零时由业务确认无数据或不适用 | [官方文档](https://apidoc.lingxing.com/docs/FBA/GetDeliveryDateList.md) |
| W3 | official_9b3b8a9018d05527 | 查询包装组 | /amzStaServer/openapi/inbound-packing/listPackingGroupItems | inboundPlanId | 等待上游历史资源产生标识；全历史仍为零时由业务确认无数据或不适用 | [官方文档](https://apidoc.lingxing.com/docs/FBA/ListPackingGroupItems.md) |
| W3 | official_ae5619f5de4ac003 | 查询货件装箱信息 | /erp/sc/routing/fba/shipment/boxInfo | shipmentId, shipment_id | 等待上游历史资源产生标识；全历史仍为零时由业务确认无数据或不适用 | [官方文档](https://apidoc.lingxing.com/docs/FBA/BoxInfo.md) |
| W3 | official_b946bd46318b5998 | 查询货件方案 | /amzStaServer/openapi/inbound-shipment/shipmentPreView | inboundPlanId | 等待上游历史资源产生标识；全历史仍为零时由业务确认无数据或不适用 | [官方文档](https://apidoc.lingxing.com/docs/FBA/ShipmentPreView.md) |
| W6 | official_e411e7bf9954d4c6 | 查询广告发票基本信息 | /bd/profit/report/open/report/ads/invoice/detail | invoice_id | 等待上游历史资源产生标识；全历史仍为零时由业务确认无数据或不适用 | [官方文档](https://apidoc.lingxing.com/docs/Finance/InvoiceDetail.md) |

### 仓库范围（内部归属治理）

系统先从仓库目录、已批准 Amazon 店铺和库存/履约关联中自动取得可见仓库并生成受控建议；客户不再逐项填写仓库外部 ID。只有关联证据不足或出现冲突时，才由内部管理员审核仓库到法人及星云业务单元的归属。批准前以下资源仍不会进入规范事实，历史清单中的 `blocked_binding_approval` 状态继续保留用于治理审计。

| 波次 | 资源键 | 官方名称 | 路径 | 当前状态 | 需要提供 | 文档 |
|---|---|---|---|---|---|---|
| W3 | official_1a92fdecd92cfdd3 | 查询批次流水 | /erp/sc/routing/data/local_inventory/getBatchStatementList | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/GetBatchStatementList.md) |
| W3 | official_301899f8a10bb79e | 查询收货单列表 | /erp/sc/routing/deliveryReceipt/PurchaseReceiptOrder/getOrderList | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/PurchaseReceiptOrderList.md) |
| W3 | official_3d23265b87349669 | 查询调整单列表 | /erp/sc/routing/inventoryReceipt/StorageAdjustment/getStorageAdjustOrderList | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/getStorageAdjustOrderList.md) |
| W3 | official_587dad772c736228 | 查询仓位库存明细 | /erp/sc/routing/data/local_inventory/inventoryBinDetails | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/inventoryBinDetails.md) |
| W3 | official_5d233a3018943a7b | 查询调拨单列表 | /erp/sc/routing/inventoryReceipt/StorageAllocation/getStorageAllocationList | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/getStorageAllocationList.md) |
| W3 | official_5f1adce90a4972fc | 加工单列表 | /erp/sc/routing/inventoryReceipt/StorageProcess/getOrderLists | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/getProcessOrderLists.md) |
| W3 | official_7ecf02bce974ca8e | 查询系统产品与第三方海外仓产品映射列表 | /erp/sc/routing/owms/inbound/matchSkuList | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/matchSkuList.md) |
| W3 | official_880605b6a4cae4fa | 查询盘点单列表 | /erp/sc/routing/inventoryReceipt/InventoryCheck/getOrderList | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/checkGetOrderList.md) |
| W3 | official_b2031fac80d741df | 查询仓位流水 | /erp/sc/routing/data/local_inventory/wareHouseBinStatement | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/wareHouseBinStatement.md) |
| W3 | official_b7a1653c943bf1f9 | 查询质检单列表 | /erp/sc/routing/deliveryReceipt/ReceiptOrderQc/getOrderList | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/ReceiptOrderQcList.md) |
| W3 | official_c4fe6dd955d734e4 | 查询库存流水（旧） | /erp/sc/routing/data/local_inventory/wareHouseStatement | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/WarehouseStatement.md) |
| W3 | official_e66ab151066dae64 | 装箱任务-任务列表 | /basicOpen/packingTask/list | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/PackingTaskList.md) |
| W3 | official_f7b29492bd680824 | 查询批次明细 | /erp/sc/routing/data/local_inventory/getBatchDetailList | blocked_binding_approval | 审核仓库到法人和星云业务单元的归属；拒绝或批准均需留痕 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/GetBatchDetailList.md) |

### 多平台店铺范围

以下接口要求多平台店铺来源键 `store:multiplatform:{store_id}`。当前六家已审核店铺来自 Amazon 目录，不能复用；请按平台审核多平台店铺外部 ID。批准前不发请求，此前跨命名空间的空结果或权限错误不作为接口证据。

| 波次 | 资源键 | 官方名称 | 路径 | 当前状态 | 需要提供 | 文档 |
|---|---|---|---|---|---|---|
| W2 | official_014edc1b6706160e | 查询结算利润（利润报表）-订单 | /basicOpen/multiplatform/profit/report/order | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/profitReportOrder.md) |
| W2 | official_02eabf7c7d379e7d | Lazada广告-获取广告活动信息 | /basicOpen/lazadaAd/campaign/info | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/LazadaCampaignInfo.md) |
| W2 | official_044ffc8e4003fc69 | 查询结算利润（利润报表）-sku | /basicOpen/multiplatform/profit/report/sku | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/profitReportSku.md) |
| W2 | official_0ef00891b5a28def | Lazada广告-店铺报告 | /basicOpen/lazadaAd/store/report/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/LazadaStoreReportList.md) |
| W2 | official_0f9b6c6ba75e63db | 查询多平台配对列表 | /pb/mp/listing/v2/getPairList | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/PairListV2.md) |
| W2 | official_13027c43f3d0cccd | 查询Shopee在线商品 | /basicOpen/multiplatform/shopee/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/ShopeeList.md) |
| W2 | official_147dd70d0ebde23a | 查询Shein在线商品 | /basicOpen/multiplatform/shein/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/SheinList.md) |
| W2 | official_15594f4b49a03827 | 查询退件地址列表 | /basicOpen/multiplatform/address/returnAddressList | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/addressReturnAddressList.md) |
| W2 | official_15d5fa1654598c73 | 查询报告详情 - Walmart Payment | /cepf/fms/openapi/walmartPayment/queryPage | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/WalmartPaymentQueryPage.md) |
| W2 | official_19b078e0d7b17a30 | 查询Ozon在线商品 | /basicOpen/multiplatform/ozon/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/OzonList.md) |
| W2 | official_1a540d9bc9ff2f4a | 查询阿里国际站在线商品 | /basicOpen/multiplatform/alibaba/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/AlibabaIcbuList.md) |
| W2 | official_1ac39a97c96f4d6c | Lazada广告-广告商品报告 | /basicOpen/lazadaAd/item/report/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/LazadaItemReportList.md) |
| W2 | official_1c54bda36d63739d | 查询WFS货件可添加商品列表 | /basicOpen/multiplatform/cargo/addCargoGoods/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/addCargoGoodsList.md) |
| W2 | official_1f19855f9de1addf | Temu全托-支出详情 | /basicOpen/multiplatformFinance/temuFull/fee/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TemuFullFeeList.md) |
| W2 | official_203fa644e59db56c | 查询eBay在线商品列表 | /basicOpen/multiplatform/ebay/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/eBayList.md) |
| W2 | official_2864cb874b67e59f | Temu全托-账务明细 | /basicOpen/multiplatformFinance/temuFull/finance/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TemuFullFinanceList.md) |
| W2 | official_2abb55595a41c891 | Temu半托-支出详情 | /basicOpen/multiplatformFinance/temuHalf/fee/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TemuHalfFeeList.md) |
| W2 | official_2ac2fafe4f6abf14 | Shopify-查询结算明细列表 | /basicOpen/multiplatformFinance/shopify/bill/statement/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/ShopifyBillStatementList.md) |
| W2 | official_2dbe32f66db9cd5b | Walmart-查询回款明细列表 | /basicOpen/multiplatformFinance/walmart/bill/payout/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/WalmartBillPayoutList.md) |
| W2 | official_2fda4da101ac755e | 查询WFS货件列表 | /cepf/warehouse/api/openApi/queryWFSCargoPage | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/QueryWFSCargoPage.md) |
| W2 | official_39ebdc2026eb6092 | Temu全托-仓储综合服务费 | /basicOpen/multiplatformFinance/temuFull/warehouse/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TemuFullWarehouseList.md) |
| W2 | official_3a577a0db1a34f8d | Temu半托-退货面单费 | /basicOpen/multiplatformFinance/temuHalf/return/fee/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TemuHalfReturnFeeList.md) |
| W2 | official_3c42c2b62994cfc5 | Temu本土-账务明细 | /basicOpen/multiplatformFinance/temuLocal/bill/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TemuLocalBillList.md) |
| W2 | official_3fb2b69a5a023816 | 查询AliExpress在线商品 - 托管模式 | /basicOpen/multiplatform/aliexpress/list/v2 | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/AliexpressListV2.md) |
| W2 | official_4774b830574c79fc | 美客多账单明细 | /basicOpen/multiplatformFinance/mercado/bill/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/MercadoBillList.md) |
| W2 | official_55dd5d3b7710029a | 查询Shopify在线商品 | /basicOpen/multiplatform/shopify/variantList | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/ShopifyVariantList.md) |
| W2 | official_576da4fe8614f636 | 查询Walmart产品表现 | /basicOpen/platformStatistics/walmartProductAnalysis/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/WalmartProductAnalysisList.md) |
| W2 | official_580f72fb9e259e99 | Walmart-查询结算账单列表 | /basicOpen/multiplatformFinance/walmart/bill/statement/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/WalmartBillStatementList.md) |
| W2 | official_5f43665a2906cfc8 | 查询Rakuten在线商品 | /basicOpen/multiplatform/rakuten/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/RakutenList.md) |
| W2 | official_620d8a99e9a99e8a | 多平台-查询FBS库存 | /basicOpen/multiplatform/fbs/stockSearch | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/FbsStockList.md) |
| W2 | official_6425643b73ecfc43 | 多平台-查询Coupang库存 | /basicOpen/multiplatform/coupang/stockSearch | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/CoupangStockList.md) |
| W2 | official_65aac57bda6a53d1 | 查询Lazada在线商品 | /basicOpen/multiplatform/lazada/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/LazadaList.md) |
| W2 | official_6a6b697dc4a28a18 | 查询Walmart在线商品 | /basicOpen/multiplatform/walmart/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/walmartList.md) |
| W2 | official_6c37f91b5f3b6c08 | 查询Temu在线商品 | /basicOpen/multiplatform/temu/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/TemuList.md) |
| W2 | official_6f19f75244f9681f | 查询结算利润（利润报表）-店铺（旧版） | /basicOpen/multiplatform/profit/report/seller | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/profitReportSeller.md) |
| W2 | official_708956ecb911c985 | 查询Mercado在线商品 | /basicOpen/multiplatform/mercado/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/MercadoList.md) |
| W2 | official_731de72df7f00ac5 | 查询Shein代运营收支明细列表 | /basicOpen/multiplatformFinance/sheinFullManaged/salesSettlement/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/SheinFullManagedSalesSettlementList.md) |
| W2 | official_82817b8ce1982c28 | 查询TikTok-GMV MAX-推广系列 | /basicOpen/multiplatform/ads/queryGmvCampaignReportList | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/tiktok-GmvCampaignReportList_6.md) |
| W2 | official_85846e335759cfad | 查询AliExpress在线商品 - 自运营 | /basicOpen/multiplatform/aliExpress/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/aliexpressList.md) |
| W2 | official_87c99dbd3632f592 | 多平台-查询FBT库存 | /basicOpen/multiplatform/fbt/stockSearch/v2 | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/FbtStockList.md) |
| W2 | official_8d1d331f791e0635 | Lazada广告-关键词报告 | /basicOpen/lazadaAd/keyword/report/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/LazadaKeywordReportList.md) |
| W2 | official_90f8f09fd136ebc5 | 查询Shein代运营回款明细列表 | /basicOpen/multiplatformFinance/shein/full-managed/payout/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/SheinFullManagedPayoutList.md) |
| W2 | official_9729a61e6dd9d9f7 | 查询Walmart Review列表 | /basicOpen/multiplatform/walmart/queryCommentList | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/WalmartCommentList.md) |
| W2 | official_98c023d7248e5223 | 分页查询广告活动报告列表 | /basicOpen/multiplatform/ads/shopee/campaign/report/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/shopeeCampaignReportList.md) |
| W2 | official_9cb4a80a6291c7b4 | 查询结算利润（利润报表）-msku | /basicOpen/multiplatform/profit/report/msku | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/profitReportMsku.md) |
| W2 | official_a403d4882f2de94f | 多平台-查询Line在线商品 | /basicOpen/multiplatform/line/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/LineList.md) |
| W2 | official_a6b51e1ac72a4813 | Lazada广告-获取广告商品信息 | /basicOpen/lazadaAd/item/info | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/LazadaItemInfo.md) |
| W2 | official_a6bb9e464ef861a1 | 查询WFS库存列表 | /cepf/warehouse/api/openApi/queryWFSInventionPage | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/QueryWFSInventionPage.md) |
| W2 | official_b2f2fcc613fe813c | 查询TikTok-GMV MAX-广告商品 | /basicOpen/multiplatform/ads/queryGmvItemGroupReportList | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/tiktok-GmvItemGroupReportList_7.md) |
| W2 | official_b9a97e2786db9371 | 查询平台仓发货单列表 | /cepf/warehouse/api/openApi/queryShippingListPage | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/QueryShippingListPage.md) |
| W2 | official_bb59531962ed316e | 查询Qoo10在线商品 | /basicOpen/multiplatform/qoo10/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/Qoo10List.md) |
| W2 | official_bef8e9e919fdfa1c | 查询TikTok-GMV MAX-广告帐号 | /basicOpen/multiplatform/ads/queryGmvAdvertiserReportList | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/tiktok-GmvAdvertiserReportList_5.md) |
| W2 | official_c3c067ff4e63c596 | 查询订单管理订单列表 | /pb/mp/order/v2/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/MultiPlatOrderV2.md) |
| W2 | official_c474c236fa13b337 | 查询Coupang在线商品 | /basicOpen/multiplatform/coupang/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/CoupangList.md) |
| W2 | official_ca29222d2fdc5226 | 查询Cdiscount在线商品 | /basicOpen/multiplatform/cdiscount/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/CdiscountList.md) |
| W2 | official_ca721b033d759020 | Temu半托-PO明细 | /basicOpen/multiplatformFinance/temuHalf/po/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TemuHalfPoList.md) |
| W2 | official_cb7046ad0f24d26e | Temu半托-其他账务 | /basicOpen/multiplatformFinance/temuHalf/other/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TemuHalfOtherList.md) |
| W2 | official_cf524a2c99e5f5f6 | Lazada广告-受众报告 | /basicOpen/lazadaAd/audience/report/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/LazadaAudienceReportList.md) |
| W2 | official_d04c6d3119a09f51 | Lazada广告-广告活动报告 | /basicOpen/lazadaAd/campaign/report/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/LazadaCampaignReportList.md) |
| W2 | official_d82ef06c6be39f88 | 查询可用报告列表 - Walmart Payment | /cepf/fms/openapi/walmartPayment/queryReport | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/WalmartPaymentQueryReport.md) |
| W2 | official_dc59c585b0bedf7c | 查询Kaufland在线商品 | /basicOpen/multiplatform/kaufland/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/KauflandList.md) |
| W2 | official_e4db8a51f2497629 | 多平台-查询wayfair库存 | /basicOpen/multiplatform/wayfair/stockSearch | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/WayfairStockList.md) |
| W2 | official_e538c1149d341c8a | 查询TikTok产品表现 | /basicOpen/platformStatistics/tiktokProductAnalysis/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TiktokProductAnalysisList.md) |
| W2 | official_e9cc14c2f2f81b58 | Temu半托-账务明细 | /basicOpen/multiplatformFinance/temuHalf/finance/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TemuHalfFinanceList.md) |
| W2 | official_ea21cf8223b27a16 | 查询OTTO在线商品 | /basicOpen/multiplatform/otto/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/OttoList.md) |
| W2 | official_ecea42ada2d2bf6c | Temu全托-EPR费用 | /basicOpen/multiplatformFinance/temuFull/epr/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TemuFullEprList.md) |
| W2 | official_f0b9ecffabf8aa7e | 查询Shein代运营补扣款明细列表 | /basicOpen/multiplatformFinance/shein/full-managed/adjustment-settlement/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/sheinFullManagedAdjustmentSettlementList.md) |
| W2 | official_f7ae57f521788cbc | Temu全托-交易结算 | /basicOpen/multiplatformFinance/temuFull/transaction/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TemuFullTransactionList.md) |
| W2 | official_ff3ca47c090b768e | 查询TikTok在线商品 | /basicOpen/multiplatform/tiktok/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/TikTokList.md) |
| W3 | official_359f1f0aca53db93 | 查询销售退货单列表 | /pb/mp/returns/v2/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/ReturnList.md) |
| W6 | official_817dec61565c4d0f | 账单明细-LazadaSettlement | /basicOpen/finance/lazada/settlement/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/Finance/lazadaSettlementList.md) |
| W6 | official_8fe1404cb399d338 | 回款明细-LazadaPayout | /basicOpen/finance/lazada/payout/list | blocked_platform_store_approval | 审核对应平台的多平台店铺外部 ID；不得填写 Amazon SID | [官方文档](https://apidoc.lingxing.com/docs/Finance/lazadaPayoutList.md) |

## 已确认只读但仍需请求结构规则（历史目录状态）

以下表格保留目录生成时的结构规则状态，便于追溯。2026-09-15 已用真实 Amazon 数据复测其中的 14 项批量查询：能由现有上游数据取得标识的项目不再要求客户确认数组来源、批量上限或是否纳入；表格中的历史 `runtime blocked` 不代表本轮需要客户协调。标发和 STA 的任务编号由上游产生后自动接续，促销无数据时保留空结果，不形成客户待办。

| 波次 | 资源键 | 官方名称 | 路径 | 当前状态 | 需要提供 | 文档 |
|---|---|---|---|---|---|---|
| W2 | official_11028d0a358daf01 | 查询会员折扣or价格折扣详情+listing+订单(批量) | /promotionApi/open/promotion/primeDiscountAllDetailBatch | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Sale/promotionPrimeDiscountAllDetailBatch.md) |
| W2 | official_3f051e5baa5a134c | 查询亚马逊标发结果 | /pb/mp/order/getFulfillmentResult | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Sale/GetFulfillmentResult.md) |
| W3 | official_4ad598b326c0b4bb | 查询STA任务包装组装箱信息 | /amzStaServer/openapi/inbound-plan/listInboundPlanGroupPacking | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/FBA/QuerySTATaskBoxInformation.md) |
| W2 | official_67479dcb2caea117 | 查询优惠券详情+listing+订单(批量) | /promotionApi/open/promotion/couponAllDetailBatch | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Sale/promotionCouponAllDetailBatch.md) |
| W2 | official_6a5ea799e3e4a248 | 查询亚马逊多渠道订单详情-物流信息 | /order/amzod/api/orderDetails/logisticsInformation | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Sale/LogisticsInformation.md) |
| W7 | official_7207d5aed8adb604 | 查询RMA管理 | /basicOpen/customerService/rmaManage/list | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Service/customerServiceRmaManageList.md) |
| W2 | official_8d5b3d29e98824d3 | TikTok账单明细 | /basicOpen/multiplatformFinance/tiktokBill/list | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/TiktokBillList.md) |
| W2 | official_99412f30cb88c7b0 | 查询亚马逊多渠道订单详情-退货换货信息 | /order/amzod/api/orderDetails/returnInformation | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Sale/ReturnInfomation.md) |
| W2 | official_9f1e91e9562e1dca | 查询秒杀详情+listing+订单(批量) | /promotionApi/open/promotion/secKillAllDetailBatch | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Sale/promotionSecKillAllDetailBatch.md) |
| W3 | official_a313092f6870458b | 查询产品仓位列表 | /basicOpen/warehouseConfig/warehouseBin/getEntryRecommendBinList | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/getEntryRecommendBinList.md) |
| W6 | official_bbde3521f4649c64 | 查询发货结算报告 | /cost/center/api/settlement/report | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Finance/SettlementReport.md) |
| W2 | official_bdf5a2637e0fc969 | 批量获取Listing费用 | /listing/listing/open/api/listing/getPrices | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Sale/GetPrices.md) |
| W2 | official_d658d341d355c889 | 查询亚马逊多渠道订单详情-商品信息 | /order/amzod/api/orderDetails/productInformation | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Sale/ProductInformation.md) |
| W2 | official_e5b1d30760a30531 | 查询平台仓发货单列表v2 | /basicOpen/multiplatform/query/shippingList | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/QueryShippingListV2.md) |
| W2 | official_f2764ea9f0ea274c | 查询Listing标记标签列表 | /basicOpen/listingManage/queryListingRelationTagList | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Sale/queryListingRelationTagList.md) |
| W2 | official_f4efc1a68a41cdb4 | 查询管理促销详情+listing+订单(批量) | /promotionApi/open/promotion/managementAllDetailBatch | read_only_reviewed / runtime blocked | 确认数组元素来源、批量上限、组合规则及空值语义 | [官方文档](https://apidoc.lingxing.com/docs/Sale/promotionManagementAllDetailBatch.md) |

## 官方操作只读语义审查原始目录（历史快照）

以下表保留目录生成时的 `metadata_only` 原始状态，供审计追溯。2026-09-13 已按本期 Amazon/通用范围完成自动语义初审，结果见下方“自动只读语义复核”，不再要求人工逐项确认。

| 波次 | 操作 ID | 官方名称 | 方法与路径 | 当前状态 | 需要提供 | 文档 |
|---|---|---|---|---|---|---|
| W0 | lingxing_op_8b8917e8f1ef8e52 | 下载附件 | POST /erp/sc/routing/common/file/download | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/BasicData/AttachmentDownload.md) |
| W1 | lingxing_op_013c90b174d66804 | 查询产品辅料列表 | POST /erp/sc/routing/data/local_inventory/productAuxList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Product/productAuxList.md) |
| W1 | lingxing_op_01d352ebdf94de42 | 查询多属性产品详情 | POST /erp/sc/routing/storage/spu/info | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Product/spuInfo.md) |
| W1 | lingxing_op_1261646c3e1ac60c | 头程对账列表 | POST /basicOpen/logistics/headLogisticsReconciliation/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Logistics/HeadLogisticsReconciliationList.md) |
| W1 | lingxing_op_29ae65648bd2a9c8 | 查询已启用的自发货物流方式 | POST /erp/sc/routing/wms/WmsLogistics/listUsedLogisticsType | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Logistics/listUsedLogisticsType.md) |
| W1 | lingxing_op_5245f78ee104f534 | 查询捆绑产品关系列表 | POST /erp/sc/routing/data/local_inventory/bundledProductList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Product/bundledProductList.md) |
| W1 | lingxing_op_5a3124287a6ac6af | 获取UPC编码列表 | POST /listing/publish/api/upc/upcList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Product/UpcList.md) |
| W1 | lingxing_op_7375941188904ea7 | 产品管理-查询透明计划商品列表 | POST /basicOpen/product/getTransparencyProductList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Product/getTransparencyProductList.md) |
| W1 | lingxing_op_9e8c3cf391401bd7 | 查询本地产品详情 | POST /erp/sc/routing/data/local_inventory/productInfo | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Product/ProductDetails.md) |
| W1 | lingxing_op_b29ab71ae0773148 | 查询操作日志 | POST /basicOpen/product/getPagingLogLists | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Product/GetPagingLogLists.md) |
| W1 | lingxing_op_da4c7f3e4988c54f | 批量查询本地产品详情 | POST /erp/sc/routing/data/local_inventory/batchGetProductInfo | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Product/batchGetProductInfo.md) |
| W1 | lingxing_op_f851639fa3832e83 | 查询运输方式列表 | POST /basicOpen/businessConfig/transportMethod/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Logistics/transportMethodList.md) |
| W2 | lingxing_op_04b4040d25917cb2 | 查询TikTok-推广广告-广告组 | POST /basicOpen/multiplatform/ads/queryTiktokAdGroupList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/tiktok-AdGroupList_12.md) |
| W2 | lingxing_op_065c5da6bd89b56e | 获取快速出库结果 | POST /pb/mp/order/v2/getFastOutboundResult | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/GetFastOutboundResultV2.md) |
| W2 | lingxing_op_14cd61e553555fbe | 查询TikTok-GMV MAX-店铺列表 | POST /basicOpen/multiplatform/ads/queryGmvStoreList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/Tiktok-GmvStoreList_8.md) |
| W2 | lingxing_op_1977829cf654fb24 | 查询沃尔玛-广告 - SB广告 - 平台 | POST /basicOpen/multiplatform/ads/reportPlatformSbList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportPlatformSbList_25.md) |
| W2 | lingxing_op_2a1bb6d6e47f46d7 | 查询沃尔玛-广告 - SV广告 - 广告 | POST /basicOpen/multiplatform/ads/reportAdItemSvList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportAdItemSvList_18.md) |
| W2 | lingxing_op_311197eb95147bd7 | 查询沃尔玛-广告 - SP广告 - 广告组 | POST /basicOpen/multiplatform/ads/queryGroupSpList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-GroupSpList_9.md) |
| W2 | lingxing_op_37a3235d6764785f | 查询FBT货件列表 | POST /basicOpen/fbtShipment/cargo/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/FbtCargoList.md) |
| W2 | lingxing_op_38d755ecbea20118 | 查询沃尔玛-广告 - SB广告 - 广告活动 | POST /basicOpen/multiplatform/ads/reportCampaignSbList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportCampaignSbList_19.md) |
| W2 | lingxing_op_3a85bdfbe764dd1c | 多平台-Temu售后订单列表 | POST /basicOpen/openapi/multiplatform/temu/returnOrder/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/TemuReturnOrderList.md) |
| W2 | lingxing_op_3abe437a1414a153 | 查询沃尔玛-广告 - SP广告 - 页面类型 | POST /basicOpen/multiplatform/ads/queryPageTypeSPList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-PageTypeSPList_10.md) |
| W2 | lingxing_op_4280b94d69ba0281 | 多平台-Shopify售后订单列表 | POST /basicOpen/openapi/multiplatform/shopify/returnOrder/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/ShopifyReturnOrderList.md) |
| W2 | lingxing_op_447c5a68f48304da | 查询FULL库存 | POST /basicOpen/multiplatform/full/stockSearch | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/FullList.md) |
| W2 | lingxing_op_471c7c6e20e02949 | 查询沃尔玛-广告 - SV广告 - 广告组 | POST /basicOpen/multiplatform/ads/queryAdGroupSvList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-AdGroupSvList_1.md) |
| W2 | lingxing_op_49da747b4063fa25 | 查询Temu货件 | POST /basicOpen/multiplatform/temu/cargo | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/TemuCargo.md) |
| W2 | lingxing_op_4e6214fb2b90b65a | 批量TEMU地址解密 | POST /basicOpen/temu/temuAddressDecrypt | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/BatchTemuAddressDecrypt.md) |
| W2 | lingxing_op_511372ae45b56647 | 查询亚马逊订单详情 | POST /erp/sc/data/mws/orderDetail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Sale/OrderDetail.md) |
| W2 | lingxing_op_62fe791ba12994f3 | 查询TikTok-推广广告-广告 | POST /basicOpen/multiplatform/ads/queryTiktokAdList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/tiktok-AdList_13.md) |
| W2 | lingxing_op_630ddacb3a020297 | Lazada广告-获取店铺信息 | POST /basicOpen/lazadaAd/seller/info | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/LazadaSellerInfo.md) |
| W2 | lingxing_op_6554bbd1835ac2cb | 查询沃尔玛-广告 - SP广告 - 平台 | POST /basicOpen/multiplatform/ads/reportPlatformSpList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportPlatformSpList_26.md) |
| W2 | lingxing_op_686ceb6809cb2e7c | 查询平台订单列表 | POST /cepfPlatformOrder/open-api/newPlatformOrder/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/newPlatformOrderList.md) |
| W2 | lingxing_op_6a2a6b27b450cf45 | 查询沃尔玛-词 - 沃尔玛热门搜索词 | POST /basicOpen/multiplatform/ads/reportSearchTrendsList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportSearchTrendsList_28.md) |
| W2 | lingxing_op_7a4c98e549ec323c | 查询沃尔玛-广告 - SP广告 - 广告活动 | POST /basicOpen/multiplatform/ads/queryCampaignSpList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-CampaignSpList_3.md) |
| W2 | lingxing_op_7aa09f40159c6c1c | 刊登管理-获取指定 productType 的 JSON Schema | POST /basicOpen/openapi/publish/manage/getProductType | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Sale/PublishManageGetProductType.md) |
| W2 | lingxing_op_813b06dea5107bba | 查询沃尔玛-广告 - SB广告 - 广告组 | POST /basicOpen/multiplatform/ads/reportAdGroupSbList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportAdGroupSbList_15.md) |
| W2 | lingxing_op_8e008cf3488cdc31 | 查询TikTok-推广广告-广告帐号 | POST /basicOpen/multiplatform/ads/queryAdvertiserList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/tiktok-AdvertiserList_2.md) |
| W2 | lingxing_op_8f26a5bd509be2e2 | 查询TikTok-推广广告-广告系列 | POST /basicOpen/multiplatform/ads/queryTiktokCampaignList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/tiktok-CampaignList_14.md) |
| W2 | lingxing_op_9055418b22b33de0 | 查询沃尔玛-广告 - SP广告 - 关键词 | POST /basicOpen/multiplatform/ads/reportKeywordSpList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportKeywordSpList_22.md) |
| W2 | lingxing_op_943ef11e0bf6e1b0 | 查询Temu库存 | POST /basicOpen/multiplatform/fbt/stockSearch | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/FbtStockSearch.md) |
| W2 | lingxing_op_a2caf42e0814ac55 | 多平台-Walmart售后订单列表 | POST /basicOpen/openapi/multiplatform/walmart/returnOrder/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/WalmartReturnOrderList.md) |
| W2 | lingxing_op_aafddfcffd65a141 | 查询平台仓发货单详情 | POST /basicOpen/multiplatform/query/shippingDetail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/shippingDetailByCode.md) |
| W2 | lingxing_op_b2985bc27723a70f | 查询全局标签 | POST /basicOpen/globalTag/info/500/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Sale/globalTagInfo500List.md) |
| W2 | lingxing_op_b51d28bc68df2dc4 | 查询沃尔玛-广告 - SB广告 - 页面类型 | POST /basicOpen/multiplatform/ads/reportPageTypeSbList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportPageTypeSbList_24.md) |
| W2 | lingxing_op_b9e0003717324b79 | 查询沃尔玛-广告 - SV广告 - 平台 | POST /basicOpen/multiplatform/ads/reportPlatformSvList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportPlatformSvList_27.md) |
| W2 | lingxing_op_b9e243bace47ab8d | 查询TikTok-推广广告-广告帐号 | POST /basicOpen/multiplatform/ads/queryCommonAdvertiserList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/Tiktok-CommonAdvertiserList_4.md) |
| W2 | lingxing_op_c8ddf127c73eaf97 | 查询沃尔玛-广告 - SB广告 - 广告 | POST /basicOpen/multiplatform/ads/reportAdItemSbList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportAdItemSbList_16.md) |
| W2 | lingxing_op_c995986f5ae0a3c4 | 查询沃尔玛-广告 - SV广告 - 页面类型 | POST /basicOpen/multiplatform/ads/queryReportPageTypeSvList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-ReportPageTypeSvList_11.md) |
| W2 | lingxing_op_cc0bc1dcfd9aebf0 | 多平台-TikTok售后订单列表 | POST /basicOpen/openapi/multiplatform/tiktok/returnOrder/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/TiktokReturnOrderList.md) |
| W2 | lingxing_op_de8d78beec4a00ef | 查询沃尔玛-广告 - SV广告 - 关键词 | POST /basicOpen/multiplatform/ads/reportKeywordSvList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportKeywordSvList_23.md) |
| W2 | lingxing_op_e0bbad753ec0cb43 | 查询亚马逊自发货订单详情 | POST /erp/sc/routing/order/Order/getOrderDetail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Sale/FBMOrderDetail.md) |
| W2 | lingxing_op_e67f89b1f99198ff | 查询沃尔玛-广告 - SP广告 - 广告 | POST /basicOpen/multiplatform/ads/reportAdItemSpList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportAdItemSpList_17.md) |
| W2 | lingxing_op_e935d202dfd34aef | 查询Temu平台仓备货单列表 | POST /basicOpen/stockOrder/temu/queryPage | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/V2/temuStockOrderQueryPage.md) |
| W2 | lingxing_op_e9945d49c606d696 | 查询沃尔玛-广告 - SB广告 - 关键词 | POST /basicOpen/multiplatform/ads/reportKeywordSbList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportKeywordSbList_21.md) |
| W2 | lingxing_op_ec8018557854e50d | 查询Listing标签列表 | POST /basicOpen/globalTag/listing/page/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Sale/globalTagPageList.md) |
| W2 | lingxing_op_f65e3aeeead6cc1f | 查询沃尔玛-广告 - SV广告 - 广告活动 | POST /basicOpen/multiplatform/ads/reportCampaignSvList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/MultiPlatform/Advertisement/walmart-reportCampaignSvList_20.md) |
| W3 | lingxing_op_0069241f13c1a128 | 获取自定义出库类型 | POST /erp/sc/routing/storage/outbound/getCustomTypes | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/outboundGetCustomTypes.md) |
| W3 | lingxing_op_036954e593e6b003 | 装箱任务-任务详情 | POST /basicOpen/packingTask/taskDetail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/PackingTaskDetail.md) |
| W3 | lingxing_op_11cdf42bc1de4d7d | 查询备货单详情 | POST /basicOpen/overSeaWarehouse/stockOrder/detail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/OverSeasStockDetail.md) |
| W3 | lingxing_op_12a44f3e0768a8f2 | 查询备货单装箱信息 | GET /erp/sc/routing/owms/inbound/getPackingData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/getPackingData.md) |
| W3 | lingxing_op_14c25773bb391c4a | 查询加工计划列表 | POST /basicOpen/openapi/workOrder/processPlanList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/WorkOrderPlanList.md) |
| W3 | lingxing_op_20c68580c276244e | 查询备货单收货记录 | POST /erp/sc/routing/owms/inbound/getReceiveGoodRecords | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/GetReceiveGoodRecords.md) |
| W3 | lingxing_op_2185c08f4ca1795d | 获取备货单号 | POST /erp/sc/routing/owms/inbound/listOrderNos | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/listOrderNos.md) |
| W3 | lingxing_op_2e40a0b423bc29db | 查询海外仓sku配对列表 | POST /basicOpen/overseaWarehouseSetting/matchList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/OverseaWarehouseMatchList.md) |
| W3 | lingxing_op_3cacf960545a1b7b | 查询销售出库单物流面单 | POST /erp/sc/routing/wms/order/getWmsLogisticsLabels | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/wmsOrderGetWmsLogisticsLabels.md) |
| W3 | lingxing_op_4f77e2e0e6512147 | 装箱任务-单据列表 | POST /basicOpen/packingTask/getRelateSnList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/PackingTaskRelateSnList.md) |
| W3 | lingxing_op_592e334e74812dfc | 查询盘点单详情 | POST /erp/sc/routing/inventoryReceipt/InventoryCheck/getOrderDetail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/checkGetOrderDetail.md) |
| W3 | lingxing_op_5ac40707a20c16aa | 地址簿-配送地址详情 | POST /basicOpen/openapi/fbaShipment/shoppingAddress | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/FBA/ShoppingAddress.md) |
| W3 | lingxing_op_75e535d8ad4174d0 | 查询FBA货件商品FNSKU标签 | POST /erp/sc/storage/shipment/printFnskuLabels | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/FBA/printFnskuLabels.md) |
| W3 | lingxing_op_79be5ad023b46b44 | 查询发货单详情 | POST /erp/sc/routing/storage/shipment/getInboundShipmentListMwsDetail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/FBA/getInboundShipmentListMwsDetail.md) |
| W3 | lingxing_op_892313b259ee6c17 | 获取发货单头程物流信息-承运商信息 | POST /erp/sc/routing/fba/shipment/getSeaTrackSupplierCarriers | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/FBA/GetSeaTrackSupplierCarriers.md) |
| W3 | lingxing_op_8eb25a84ca5ce312 | 查询AWD库存列表 | POST /basicOpen/openapi/storage/awdWarehouseDetail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/AwdWarehouseDetail.md) |
| W3 | lingxing_op_8f475dbbe503519c | 获取发货单头程物流信息-其他费类型 | POST /erp/sc/routing/fba/shipment/getHeadLogisticsFeeTypes | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/FBA/GetHeadLogisticsFeeTypes.md) |
| W3 | lingxing_op_ac8afe212ca6476d | 查询FBA货件箱子、卡板标签 | POST /erp/sc/storage/shipment/printFbaLabels | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/FBA/printFbaLabels.md) |
| W3 | lingxing_op_b1492f54da84e756 | 查询调整单确认调整异步结果 | POST /basicOpen/adjustOrder/adjust/getAdjustStatus | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/GetAdjustOrderConfirmResult.md) |
| W3 | lingxing_op_b5799edcb780519b | 查询质检单详情 | POST /basicOpen/qualityInspectionOrder/detail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/qualityInspectionOrderDetail.md) |
| W3 | lingxing_op_b814e13aef5f12dd | 查询移除入库单列表 | POST /erp/sc/routing/owms/removalInbound/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/removalInboundList.md) |
| W3 | lingxing_op_bdf16a517e4bec55 | 查询异步任务状态 | POST /amzStaServer/openapi/task-plan/operate | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/FBA/Operate.md) |
| W3 | lingxing_op_c819d7dd4c8a645c | 查询销售出库单详情 | POST /basicOpen/wmsOrder/getWmsOrdersByOrderNumbers | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/WmsOrderDetail.md) |
| W3 | lingxing_op_cc3162615aa38e82 | 批量查询发货单详情 | POST /erp/sc/routing/storage/shipment/getInboundShipmentListMwsDetailList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/FBA/GetInboundShipmentListMwsDetailList.md) |
| W3 | lingxing_op_da86d888ab34e188 | 查询海外仓备货单列表 | POST /erp/sc/routing/owms/inbound/listInbound | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/listInbound.md) |
| W3 | lingxing_op_e32b633d18e0b452 | 获取第三方箱唛 | POST /erp/sc/routing/owms/inbound/packageLabel | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/packageLabel.md) |
| W3 | lingxing_op_e8c15d3c7deb08f5 | 获取自定义入库类型 | POST /erp/sc/routing/storage/inbound/getCustomTypes | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/inboundGetCustomTypes.md) |
| W3 | lingxing_op_f5ccf68b456f38fd | 获取第三方SKU标签PDF文件 | POST /erp/sc/routing/owms/inbound/productLabel | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Warehouse/productLabel.md) |
| W4 | lingxing_op_49eb774dd1293baf | 查询采购变更单列表 | POST /erp/sc/routing/purchase/purchaseChangeOrder/changeOrderList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Purchase/changeOrderList.md) |
| W4 | lingxing_op_4f00b222b6715063 | 查询委外订单列表 | POST /erp/sc/routing/purchase/purchaseOutsourceOrder/getOrders | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Purchase/getOrders.md) |
| W4 | lingxing_op_9f8d127f6ae0c459 | 查询采购方列表 | POST /erp/sc/routing/data/purchaser/lists | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Purchase/purchaserLists.md) |
| W4 | lingxing_op_af8f73d5ed708f74 | 查询采购退货单列表 | POST /erp/sc/routing/purchase/purchase_return_order/getPurchaseReturnOrderList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Purchase/getPurchaseReturnOrderList.md) |
| W5 | lingxing_op_08f9a192969b1e66 | 负责人维度-查询目标 | POST /bd/goal/management/open/user/batchSelect | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/TargetManage/UserBatchSelect.md) |
| W5 | lingxing_op_0fa50a15644c9032 | SB广告位小时数据 | POST /pb/openapi/newad/sbAdPlacementHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/sbAdPlacementHourData.md) |
| W5 | lingxing_op_13f6c0f30636bf7c | SD投放小时数据 | POST /pb/openapi/newad/sdTargetHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/sdTargetHourData.md) |
| W5 | lingxing_op_1f34a90e2a3490ab | SB广告活动小时数据 | POST /pb/openapi/newad/sbCampaignHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/sbCampaignHourData.md) |
| W5 | lingxing_op_2219c6ac300ac47f | 查询DSP报告列表-订单 | POST /basicOpen/dspReport/order/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/dspReportOrderList.md) |
| W5 | lingxing_op_2272e9468020e498 | 广告分析-搜索词分析 | POST /basicOpen/adReport/analyze/searchTerm | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/AdAnalyzeSearchTerm.md) |
| W5 | lingxing_op_30d94d2e70a645c8 | 查询沃尔玛广告主列表 | POST /basicOpen/adReport/advertiser/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/WalmartQueryAdvertiserList.md) |
| W5 | lingxing_op_37b1a06a0290fa79 | SB分摊 | POST /pb/openapi/newad/sbDivideAsinReports | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/baseData/newadsbDivideAsinReports.md) |
| W5 | lingxing_op_52b6320d8139e6b9 | SP广告组小时数据 | POST /pb/openapi/newad/spAdGroupHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/spAdGroupHourData.md) |
| W5 | lingxing_op_576a56358efd1026 | SP广告小时数据 | POST /pb/openapi/newad/spAdvertiseHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/spAdvertiseHourData.md) |
| W5 | lingxing_op_5787e393a7881fe7 | SD广告组小时数据 | POST /pb/openapi/newad/sdAdGroupHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/sdAdGroupHourData.md) |
| W5 | lingxing_op_5934b7bf40c8b03f | 查询DSP广告主列表 | POST /newad/dspAdvertiserList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/dspAdvertiserList.md) |
| W5 | lingxing_op_5fcaf5db6b10f97b | SD广告活动小时数据 | POST /pb/openapi/newad/sdCampaignHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/sdCampaignHourData.md) |
| W5 | lingxing_op_7f982f42a7ed7d25 | SP广告活动小时数据 | POST /pb/openapi/newad/spCampaignHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/spCampaignHourData.md) |
| W5 | lingxing_op_921cce7488b27e3d | SB广告组小时数据 | POST /pb/openapi/newad/sbAdGroupHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/sbAdGroupHourData.md) |
| W5 | lingxing_op_aea93b024d11f691 | SP投放小时数据 | POST /pb/openapi/newad/spTargetHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/spTargetHourData.md) |
| W5 | lingxing_op_b1f5e34c05a00b19 | 广告分析-关键词分析 | POST /basicOpen/adReport/analyze/keyword | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/AdAnalyzeKeyword.md) |
| W5 | lingxing_op_b5c3c16dfa6a125e | 店铺维度-查询目标 | POST /bd/goal/management/open/store/batchSelect | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/TargetManage/StoreBatchSelect.md) |
| W5 | lingxing_op_c11984af30759ad7 | SD广告小时数据 | POST /pb/openapi/newad/sdAdvertiseHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/sdAdvertiseHourData.md) |
| W5 | lingxing_op_c673912c5fc08a56 | ABA搜索词报告-按周维度 | POST /pb/openapi/newad/abaReport | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/reportDownload/abaReport.md) |
| W5 | lingxing_op_cbc0022279e3b2af | SB用户搜索词报表 | POST /pb/openapi/newad/hsaQueryWordReports | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/hsaQueryWordReports.md) |
| W5 | lingxing_op_f798e21783bd7f70 | SP广告位小时数据 | POST /pb/openapi/newad/spAdPlacementHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/spAdPlacementHourData.md) |
| W5 | lingxing_op_f810439a9824413f | 查询广告账号列表 | POST /basicOpen/baseData/account/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/baseData/dspAccountList.md) |
| W5 | lingxing_op_f9dfa98aa50c771c | SB投放小时数据 | POST /pb/openapi/newad/sbTargetHourData | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/newAd/report/sbTargetHourData.md) |
| W6 | lingxing_op_0859dff846e6b595 | 库存报表-海外仓-历史报表-汇总 | POST /erp/sc/routing/inventoryLog/WareHouseReport/getOverSeaSummaryList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/OverseasAggregateList.md) |
| W6 | lingxing_op_0d27db7f49f95bfb | 查询利润统计-店铺 | POST /bd/profit/statistics/open/seller/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/statisticsOpenSeller.md) |
| W6 | lingxing_op_1807950ff3f8fec7 | 查询报告 | GET /openReport/report/task/getReport | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/GetReport.md) |
| W6 | lingxing_op_1be792c7b3b117ff | 查询请款池-物流请款 | POST /basicOpen/finance/requestFundsPool/logistics/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/requestFundsPoolLogisticsList.md) |
| W6 | lingxing_op_1f6769969706e122 | 查询费用类型列表 | POST /bd/fee/management/open/feeManagement/otherFee/type | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/feeManagementType.md) |
| W6 | lingxing_op_288a9bdfe210b2e7 | 利润报表-列表配置查询 | POST /basicOpen/finance/profitReport/config | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/ProfitReportConfig.md) |
| W6 | lingxing_op_293e5bf739ae4e9f | 查询请款池-其他应付款 | POST /basicOpen/finance/requestFundsPool/customFee/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/requestFundsPoolCustomFeeList.md) |
| W6 | lingxing_op_313c235a5d701119 | 查询请款池 - 货款现结 | POST /basicOpen/finance/requestFundsPool/purchase/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/requestFundsPoolPurchaseList.md) |
| W6 | lingxing_op_5b1a8eba8dc1ee02 | 查询请款池-其他费用 | POST /basicOpen/finance/requestFundsPool/otherFee/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/requestFundsPoolOtherFeeList.md) |
| W6 | lingxing_op_629bb0d4b8e7167b | 库存报表-海外仓-新报表-汇总 | POST /inventory/center/openapi/storageReport/overseas/aggregate/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/OverseasAggregateListNew.md) |
| W6 | lingxing_op_6c463e7769c016d7 | 库存报表-本地仓-新报表-汇总 | POST /inventory/center/openapi/storageReport/local/aggregate/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/LocalAggregateListNew.md) |
| W6 | lingxing_op_6f463c4034d1d551 | 库存报表-本地仓-历史报表-汇总 | POST /erp/sc/routing/inventoryLog/WareHouseReport/getLocalWareHouseSummaryList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/LocalAggregateList.md) |
| W6 | lingxing_op_a1d78ac5ba6085a3 | 库存报表-海外仓-历史报表-明细 | POST /erp/sc/routing/inventoryLog/WareHouseReport/getOverSeaDetailList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/OverseasDetailList.md) |
| W6 | lingxing_op_a2a10fee5281286b | 查询FBA成本计价流水 | POST /cost/center/api/cost/stream | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/CostStream.md) |
| W6 | lingxing_op_a3694cb468020406 | 库存报表-本地仓-历史报表-明细 | POST /erp/sc/routing/inventoryLog/WareHouseReport/getLocalWareHouseDetailList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/LocalDetailList.md) |
| W6 | lingxing_op_a96b610eb53a089c | 查询请款池 - 货款月结 | POST /basicOpen/finance/requestFundsPool/inbound/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/requestFundsPoolInboundList.md) |
| W6 | lingxing_op_aee59fb61afd8c9c | 库存报表-本地仓-新报表-明细 | POST /inventory/center/openapi/storageReport/local/detail/page | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/LocalDetailListNew.md) |
| W6 | lingxing_op_b86f83ffefc034fe | 查询利润报表（旧）-结算明细 | POST /erp/sc/routing/finance/ProfitState/profitSettlement | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/profitSettlement.md) |
| W6 | lingxing_op_b9d5eb86416228a4 | 查询请款池 - 货款预付款 | POST /basicOpen/finance/requestFundsPool/prepay/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/requestFundsPoolPrepayList.md) |
| W6 | lingxing_op_c1ff5a9f76909858 | 查询采购报表列表 - 供应商 | POST /basicOpen/report/purchase/supplier/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/PurchaseReportSupplierList.md) |
| W6 | lingxing_op_c20c9e6d2bd4b434 | 查询收款单列表 | POST /basicOpen/finance/queryReceiptFundsList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/QueryReceiptFundsList.md) |
| W6 | lingxing_op_d58f04c9f92ea28d | 查询采购报表列表 - 采购员 | POST /basicOpen/report/purchase/buyer/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/PurchaseReportBuyerList.md) |
| W6 | lingxing_op_ddeb03282ba76aa4 | 查询请款单列表 | POST /basicOpen/finance/requestFunds/order/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Finance/RequestFundsOrderList.md) |
| W6 | lingxing_op_ea672b4685117f9e | 库存报表-海外仓-新报表-明细 | POST /inventory/center/openapi/storageReport/overseas/detail/page | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Statistics/OverseasDetailListNew.md) |
| W7 | lingxing_op_249d31011eda3de9 | 查询订单已退货数量 | POST /basicOpen/customerService/returnOrder/getReturnQty | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Service/ReturnOrderGetReturnQty.md) |
| W7 | lingxing_op_359857a0fb4c8284 | 查询售后工单列表 | POST /pb/mp/returns/workOrder/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Service/AfterSalesWorkOrderList.md) |
| W7 | lingxing_op_49352cb42bc4507d | 查询邮件列表 | POST /erp/sc/data/mail/lists | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Service/lists.md) |
| W7 | lingxing_op_aa381ab91ecdd508 | 查询评价统计-Feedback列表 | POST /erp/sc/cs/feedbackReport/lists | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Service/feedbackLists.md) |
| W7 | lingxing_op_c63c77d8eeec27f8 | 查询邮件详情 | POST /erp/sc/data/mail/detail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Service/detail.md) |
| W7 | lingxing_op_f742d242ba989a2a | 查询售后原因 | POST /basicOpen/customerService/afterSalesReason/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Service/AfterSalesReasonList.md) |
| W7 | lingxing_op_fee7944636c24d8d | 查询评价统计-Review每日新增数 | POST /erp/sc/cs/reviewReport/detail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Service/reviewDetail.md) |
| W8 | lingxing_op_65833fe6add22acc | 查询VC店铺列表 | POST /basicOpen/platformAuth/vcSeller/pageList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/VC/platformAuthVcSellerPageList.md) |
| W8 | lingxing_op_68b609bfb6e91fb5 | VC订单-请求标签【DF】 | POST /basicOpen/platformOrder/vcOrderDf/submitShippingLabel | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/VC/vcOrderDfSubmitShippingLabel.md) |
| W8 | lingxing_op_7d0c29eb04c3c915 | 查询VC-Listing列表 | POST /basicOpen/listingManage/vcListing/pageList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/VC/listingManageVcListingPageList.md) |
| W8 | lingxing_op_a82efc520723b62d | 查询VC发货单详情 | POST /basicOpen/openapi/getInvoice/detail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/VC/vcDeliverDetail.md) |
| W8 | lingxing_op_ac721475eef78cb4 | 查询VC订单列表 | POST /basicOpen/platformOrder/vcOrder/pageList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/VC/vcOrderPageList.md) |
| W8 | lingxing_op_c5a1c1c79f4c8dad | 关键词列表 | POST /erp/sc/routing/tool/toolKeywordRank/getKeywordList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Tools/GetKeywordList.md) |
| W8 | lingxing_op_dcbfeef40f96bf76 | 查询预警消息列表-库存 | POST /basicOpen/settings/warningMessage/inventoryList | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Tools/warningMessageInventoryList.md) |
| W8 | lingxing_op_dcd85ceecdab618a | 查询竞品监控列表 | POST /basicOpen/tool/competitiveMonitor/list | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/Tools/CompetitiveMonitorList.md) |
| W8 | lingxing_op_e84f87350673fe01 | 查询VC订单详情【DF】 | POST /basicOpen/platformOrder/vcOrderDf/detail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/VC/vcOrderDfDetail.md) |
| W8 | lingxing_op_f51c43f33df1fa1f | 查询VC订单详情【PO】 | POST /basicOpen/platformOrder/vcOrderPo/detail | metadata_only | 只读/写入/不适用结论及官方依据 | [官方文档](https://apidoc.lingxing.com/docs/VC/vcOrderPoDetail.md) |

## 2026-09-13 自动只读语义复核

对上节 153 条官方操作按本期 Amazon/通用范围重新筛选后，逐项检查官方名称和方法路径：

- 116 条可直接判定为 `read_only`，名称和路径均为查询、详情、列表、报告、下载或状态读取动作；不再列入人工协调。
- `lingxing_op_68b609bfb6e91fb5`（`VC订单-请求标签【DF】`，`POST /basicOpen/platformOrder/vcOrderDf/submitShippingLabel`）明确属于提交标签的业务写入动作，标记为 `blocked_mutation`，不进入本期只读运行时，也不需要申请只读权限。
- `查询调整单确认调整异步结果` 的路径为 `getAdjustStatus`，实际只返回异步状态，按 `read_only` 处理；名称中的“调整”不代表本接口执行调整。
- 多平台资源已按 Amazon-only 范围排除。上述操作均不再进入 Excel 的人工协调清单；后续新增接口继续按同一规则自动初审，只有动作含义无法从官方依据判断时才重新列为 `metadata_only`。

## 2026-09-13 错误接口第二轮自研复测结论

在候选隔离环境使用官方契约字段、正确的紧凑 JSON 数组编码、六家已批准 Amazon 店铺范围和最小只读请求重新复测；没有触碰生产数据、正式绑定或权限配置：

- 已自行解决并在候选隔离环境复测通过 16 个历史失败接口：新版客户端对带正向成功包络的 code=1 兼容；FBA 新版汇总/明细改用已批准 Amazon 店铺的 `seller_id` 映射并按官方 `Y-m` 传参；结算汇总改为数组 `sids` 并补 `dateType`；5 个促销资源改为供应商要求的日期/数组格式；采购产品报表补 `time_type=1`；客户列表按官方说明使用从 1 开始的 `offset` 页码；结算导出 URL 由结算汇总输出的 `financialEventGroupId` 自动驱动；以及通过财务 transaction 列表提供有效 MSKU 后链式复测商品预处理信息。这些项目不再要求管理员协调。
- 关联接口复测结论与[领星开放接口文档](https://apidoc.lingxing.com/)的契约字段一致：财务 transaction 列表返回的 MSKU 作为上游值，调用 `/amzStaServer/openapi/inbound-packing/getPrepDetails` 返回 `code=0`；六家已批准 Amazon 店铺在宽日期窗口、两种 `dateType` 下调用 STA 入库方案列表、AWD 入库方案列表和 AWD 货件列表均为 `code=0` 但记录数为 0，因此当前没有可供下游详情接口消费的 `inboundPlanId`、AWD `orderId` 或同族 `shipmentId`。
- 旧 FBA 货件列表可以返回旧体系 `shipment_id`，但将这些值传给新版 STA 装箱/货件详情接口均被明确拒绝，旧版箱信息接口也返回通用业务失败；这证明不能跨接口族复用货件 ID。普通 Amazon 订单列表可以返回 `amazon_order_id`，但它与 AWD 入库任务 `orderId` 不是同一语义，不能替代 AWD 详情参数。普通订单详情调用仍被本地只读运行时的资源白名单拦截，未绕过该安全边界。
- 3 个 `-1` 资源（AWD 入库详情、货件装箱信息、货件详情）仍不能闭环：AWD 入库详情实际已传入测试 `orderId`，但接口返回“未找到对应的订单信息”，说明普通订单号未匹配到 AWD 入库任务；两个货件接口返回“请传入货件单号，或同时传入 STA 任务编号和货件 id”。商品预处理信息已通过“财务 transaction 列表 → 有效 MSKU → prep details”关联链在候选隔离环境复测成功（code=0），不再列为人工协调。
- 店铺利润汇总仍返回 `code=1：币种不能为空`；候选用 `currencyCode=USD` 已成功，但默认币种属于业务/财务口径，不能由系统擅自替用户决定，因此保留为人工口径项。
- 结算利润明细仍为明确 `403`，是当前确认的领星应用模块/账号授权项；FBC 库存查询已确认属于 Cdiscount 平台仓，按 Amazon-only 规则移出本期，不再协调。
- 旧客户列表当前未进入候选目录，属于资源范围/目录决策，不是可以靠重试解决的接口权限问题。

因此当前 Excel 的技术页只保留 6 条接口协调项；面向客户的业务页保留 9 个需要确认的主问题，13 项仓储查询改为系统自动处理并在归属不明时进入内部治理，14 项 Amazon 批量查询改为系统自动链路追踪，不再要求客户逐项确认。接口项仅包含仍需外部错误解释、权限/模块确认、业务币种口径或真实业务标识的事项。能由代码、公开文档、参数修正、候选侧映射、关联接口链或业务范围排除解决的项目均已从清单中移除。

## 回填与对账人工验收

全部可执行资源完成后，还需要业务人员提供以下验收结论：

- 领星能够提供的最早历史日期，按资源或模块记录；没有官方证据时不得写成“全部历史已覆盖”。
- 六家已审核店铺在领星侧的订单、退款、库存、采购、广告和财务抽样总数或金额，按同一时区、币种和日期口径对账。
- 原币、本位币、汇率版本和集团合并口径的确认版本；未确认前财务集团汇总保持关闭。
- 对 schema_pending、无权限、不适用和无数据资源逐项签字，区分“没有数据”与“没有权限”。

每次回复应使用资源键或操作 ID。收到答复后，实施方更新契约/ADR、补合成失败测试、在隔离候选库复测，再更新本清单状态。

生成依据：官方契约 `lingxing-contract-2026-09-11.7`、运行时工作清单 `lingxing-rollout-2026-09-11.13`、只读审查 `lingxing-readonly-review-2026-09-11.4`；参数策略 `lingxing-parameter-policy-2026-09-13.5`、运行时资源 265 个。目录层参数规则仍为 `calendar` × 9、`dependency` × 37、`enum` × 61、`manual` × 4、`paired_dependency` × 2、`provided_by_pair` × 2；按本期 Amazon 范围实际只剩 1 个需要人工输入的参数，另 2 个属于范围外，`region` 已自动推导。
