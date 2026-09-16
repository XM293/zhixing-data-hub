# 第三方电商测试沙箱

该服务模拟客户现场的吉客云、CRM、广告和库存聚合接口。返回字段刻意使用第三方命名，产品 API 必须通过连接器完成字段隔离和版本化映射。

支持 `normal`、`delayed`、`partial`、`failure` 四种场景。服务默认监听 `127.0.0.1:8100`。

## 经营事实接口

测试沙箱把客户现场常见领域拆为独立资源，避免用一个聚合 JSON 假装真实系统：

- `/api/v1/orders`：订单头、店铺、渠道、金额、状态和业务时间；
- `/api/v1/orders/lines`：订单行、SKU、数量、单价和成本；
- `/api/v1/refunds`：退款单、原订单、SKU、金额、原因和状态；
- `/api/v1/inventory/snapshots`：仓库/SKU 日快照、可用量、锁定量和成本；
- `/api/v1/ads/performance`：店铺/计划/SKU 日粒度的消耗、曝光、点击、归因订单和收入。

`small`、`standard`、`large` 控制体量，数据由稳定业务键和固定业务日确定，可重复同步并验证幂等。沙箱字段保持第三方风格；只有 `services/api/src/zhixing_api/connectors/` 可以把它们转换为 `contracts/data/commerce-fact-batch.schema.json` 定义的规范事实。上层页面、分析和 MCP 不得直接依赖这些测试字段。

连接器还会从 `/api/v1/shops` 生成版本化范围映射，把平台权限范围键映射到沙箱 `shop_code`。客户进场后这一映射可以由实际店铺目录、主数据配置或实施审核结果替换；上层 `query_commerce_facts`、经营分析和角色权限不硬编码沙箱店铺编码。
