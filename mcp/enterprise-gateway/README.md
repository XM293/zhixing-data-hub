# 知行数枢企业 MCP 网关

该进程使用官方 MCP Python SDK，把企业 API 中已登记且当前会话允许的 R0 能力暴露给 Codex 和其他 MCP Host。它不连接业务数据库，也不接受 `principal_id`、访问角色、权限或企业参数。身份来自 API 签发的短期受限会话，数据库只保存令牌哈希。

当前工具：

- `read_policy`：读取带版本与原文定位的当前制度证据；
- `search_knowledge`：检索企业知识切片；
- `get_metric`：按授权范围读取指标口径和最新快照。
- `query_commerce_facts`：读取授权范围内的规范经营事实。
- `query_customer_360`：读取授权范围内的客户汇总或单客详情。

运行约束：

- 先由已登录主体调用 `POST /api/v1/mcp/sessions` 签发工具白名单、范围和有效期；
- 将响应中的令牌与相同 `client_id` 通过 `ZHIXING_MCP_SESSION_TOKEN` 和 `ZHIXING_MCP_CLIENT_ID` 注入进程；
- 网关启动时按会话目录投影实际工具，不发布会话未允许的工具；
- 每次调用由 API 按当前数据库权限重新授权，签发时快照只用于审计；
- `ZHIXING_MCP_RUN_ID` 可绑定上游运行，不设置时网关进程生成稳定运行 ID。
- 连通性验证启动 STDIO 子进程时只显式传递 API 地址、会话令牌、客户端 ID 和可选运行 ID；SDK 负责合并操作系统所需的受控基础环境，不继承父进程中的其他变量。

Codex 等 Host 使用 stdio 启动 `pnpm mcp:run`，完整连通性使用 `pnpm mcp:verify`。不要把会话令牌、API Key、密码或 OAuth Token 写进仓库配置、文档或日志；Host 通过本机环境或密钥管理注入。
