# 知行数枢 · 企业数据智能运营中枢

当前项目现状、文档冲突处理和后续路线以 [`docs/PROJECT-STATE-AND-ROADMAP.md`](docs/PROJECT-STATE-AND-ROADMAP.md) 为准；分阶段开发和生产接入边界见 [`docs/development/09-next-phase-development-plan.md`](docs/development/09-next-phase-development-plan.md)。首个领星 ERP 真实来源与集团架构的生产展开以 [`docs/development/10-lingxing-erp-real-data-and-group-rollout-plan.md`](docs/development/10-lingxing-erp-real-data-and-group-rollout-plan.md) 为准，本地一次性工程改造执行 [`DAT-011`](docs/development/11-lingxing-local-one-pass-implementation-plan.md)，新 Codex 会话提示词位于 [`tasks/DAT-011-CODEX-PROMPT.md`](tasks/DAT-011-CODEX-PROMPT.md)。本文保留产品背景、启动方式和纵向切片摘要；下方按迁移顺序保留历史实现记录，历史阶段报告不代表当前生产就绪度。

本仓库是“知行数枢”的产品、架构、研发任务与后续代码工作区。项目目标不是只做一个 CEO 聊天机器人，而是逐步建设企业私有化的数据智能运营中枢：统一接入企业经营数据、制度知识、组织经验和业务工具，再为管理者分身、数字会议、经营分析、运营助手、智能客服和受控执行提供底座。

## 当前阶段

经营驾驶舱已经读取企业与门店范围的 90 天持久化指标序列，指标 API 与 `get_metric` MCP 共享同一查询契约，不再由前端生成趋势。第三方测试沙箱已在平台内部拆成吉客云 ERP/OMS、CRM、广告与客服四个独立可替换来源；当前开发库四源均已完成大型档同步，形成 50,131 条原始记录、18,761 条规范经营事实、600 个客户主档、3,600 条客户触点、5,424 个统一实体和 21 个指标口径。

当前处于 `M0：数据驱动产品全景重做` 阶段。纯静态全景 v0.1 未通过产品负责人验收；当前已进入企业经营数字孪生纵向切片评审：使用可迁移数据库、灵活连接器、电商模拟连接器、可下钻经营空间、数据图层、受约束自由镜头、数字分身路线和持久化会议状态验证整体效果。仓储和数字会议室已经成为按需装载的独立业务空间，镜头读取数据库预设；会议到场期限持久化并由 API 调度器推进，浏览器只订阅状态且不会因会议运行劫持用户导航。数据库数字会议已经支持三角色独立分析、两轮交叉质询、反方风险审查、主持汇总、证据新颖性校验和单阶段受控降级，并已延伸到人工确认、数据库行动提案、分权审批和零外部写入的内部执行台账。迁移 `0014_identity_access_foundation` 已加入数据库账号、组织岗位、访问角色、权限范围和授权决策审计，管理台菜单和业务按钮由 `/api/v1/identity/me` 的数据库投影驱动。迁移 `0015_enterprise_tool_gateway` 进一步加入数据库工具定义和调用审计，官方 MCP Python SDK 网关已通过企业 API 向 Codex 发布五个只读工具。迁移 `0016_knowledge_ingestion_lifecycle` 已打通管理员资料导入、内容哈希去重、章节切片、冲突提示、不可变草稿、CEO 发布/退役和指定时点有效版本读取。迁移 `0017_memory_governance` 与 `0018_agent_memory_context` 进一步打通聊天原件、消息/话题切分、记忆候选、审核/激活/退役、制度冲突隔离，以及回答实际使用记忆版本的运行追踪。迁移 `0019_role_twin_versioning` 已正式分离岗位模板、分身实例和不可变配置版本，管理台可创建/发布新版本，`AgentRun` 保存实际使用的分身版本。迁移 `0020_role_twin_test_studio` 又加入版本化试跑用例、真实运行和追加式人工审核，角色本人可检查样例回答的证据、边界、表达和业务实用性。SSO、生产级外部对象存储、后台大文件解析、真实飞书渠道适配器、其他 Worker 任务类型的统一守卫和真实业务系统写入仍按任务依赖推进；本地密码登录、服务端会话、渠道身份绑定中心、本地文件资产和自动巡店 Worker 重授权已可用。后续门店和客服作战室按同一场景契约增量实现。验收后仍采用“全局架构、纵向切片”，优先用管理者分身打通知识、结构化数据、角色记忆、飞书问答与评测闭环。

迁移 `0021_agent_feedback_and_handoff` 已加入可归属到提问人的回答反馈、人工接管工单、负责人认领/解决/重开事件与员工处理结果回看；反馈不会直接修改制度、记忆、Prompt 或外部系统。迁移 `0022_evaluation_runner` 加入版本化评测套件、可信数据库案例身份、逐项检查、幂等批量运行和基线对比；迁移 `0023_feedback_evaluation_candidates` 将人工纠错转成待审核评测候选，只有具备治理权限的负责人接纳后才会进入固定回归集。迁移 `0024_business_analysis_and_briefs` 已把店铺诊断和经营简报替换为数据库纵向切片。迁移 `0025_customer_service_copilot` 加入数据库客服会话、订单上下文、证据冻结、AI 回复草稿、确定性风险门禁、人工接管与零外部写入的沙箱发送台账。迁移 `0026_ai_provider_operations` 进一步加入不保存密钥、Prompt 或企业上下文的 Provider 探针，并将分身、会议、经营分析、客服和评测运行汇总到平台管理员可见的 AI 运行控制台。

最新迁移 `0027_scoped_meeting_creation` 将数字会议推进到受治理创建纵向切片：CEO 或具备会议发起权限的管理者可以从三个固定模板选择企业或授权门店范围、编排 3–6 位已发布角色分身，并以幂等请求创建会议。系统保存可信发起人、当时的 Actor 快照、范围、模板、席位和分身版本；运行时只冻结该范围的指标与所选分身的已审核记忆。会议列表、详情、运行和确认均使用同一数据库权限投影，开发身份接口仅为自动化测试兼容，不作为产品入口。

最新迁移 `0028_memory_provider_evaluations` 新增可审计长期记忆供应商双跑：TencentDB-Agent-Memory 与 Mem0 通过自有适配器接收同一批已生效记忆和固定问题集，平台保存执行人、幂等键、基准快照、逐题命中、Recall@3、延迟和脱敏端点指纹。开发环境由独立 `mock-memory` 服务验证两类公共 HTTP 契约并明确标注 `contract-sandbox`；客户部署可替换真实端点，角色记忆审核与版本真值不随供应商变化。

最新迁移 `0029_knowledge_provider_evaluations` 的评测台账现已承载 WeKnora、RAGFlow 与 OpenViking 三路适配：评测只读取数据库当前生效且已索引的文档/切片，固定题集同时记录 Recall@3、MRR、延迟、返回证据键和失败原因。OpenViking 通过公开 `/content/batch-write` 与 `/search/find` HTTP 契约接收运行隔离的 `viking://resources` 副本，平台不复制其 AGPL 代码，也不把 OpenViking 的资源、记忆或 Skill 对象当成企业知识真值。独立 `mock-knowledge` 服务在 `8300` 端口模拟三类公开契约；知识中心的“引用与证据”页面可以在 CEO/运营负责人权限下发起多路评测，所有运行和端点指纹落入数据库。该纵向切片用于验证连接器替换和检索对照，不代表正式 `KNO-004`、`KNO-005` 或 `KNO-008` 已完成。

最新迁移 `0030_canonical_commerce_facts` 在原始源记录与指标层之间加入规范电商经营事实：订单、订单行、退款、库存快照和广告日绩效均保留企业、来源、Schema、映射版本和同步批次血缘。第三方测试沙箱按 12 个店铺/渠道生成可重复的大型档数据，当前开发库已形成 18,761 条规范事实；`/console/data/commerce` 从数据库展示店铺贡献、履约漏斗、跨域异常、事实血缘和最近订单，经营驾驶舱也将规范事实作为独立资产族统计。连接器会显式声明成功取得的权威事实族，完整档同步可移除同源缺失旧事实，部分失败资源则保留历史数据。客户进场时可以按实际吉客云、CRM、广告或文件结构替换连接器映射，不需要让源字段进入分析、AI 或 MCP 上层契约。该切片不提前关闭正式数据中心任务或生产容量验收。

最新迁移 `0031_data_scope_mappings` 将平台授权范围与客户来源业务键做成版本化映射。连接器同步店铺目录时写入 `store-flagship -> TM-001` 等当前客户映射，经营事实 API、`query_commerce_facts` MCP 与 AI 分析共用同一解析器；员工只能读取授权门店，CEO 可以读取企业汇总。经营诊断现在同时冻结四条指标序列、订单/退款/库存/投放汇总和具体异常，真实 `gpt-5.4-mini` 运行使用 14 条可重放证据并在页面显示来源与同步批次。客户进场只需替换来源映射，不在 Prompt、MCP 或页面中硬编码客户店铺 ID。

客服工作台现已接入同一规范事实与范围映射底座。当前开发种子版本为 `1.30.0`，10 个订单型会话使用可与第三方测试沙箱规范订单关联的稳定键；页面将客服/物流履约上下文与数据中心交易事实分层展示，并独立显示事实关联与字段对账结果。测试源保持 9 个一致订单、1 个故意冲突订单和 2 个售前会话。只有企业、订单、客户和门店映射全部匹配时，规范金额、成本、退款、来源和同步批次才会进入 AI 草稿证据；重大金额、状态、件数或退款差异冻结为 `D5` 并强制进入人工核验，发送时还会按当前事实重新检查。完整 ERP 批次还会用同一对账器生成追加式数据质量结果，把一致、冲突、缺失、范围不符和上下文缺口汇总到 `/console/data/quality` 的跨源对账队列；不另建客服事实或对账真值表。客服制度扩展为补偿、物流、退货退款、订单发票支付、商品活动与高风险六类可引用条款，模型必须同时使用当前问题所需的 `D*` 数据和 `K*` 制度证据。

Skill 注册与版本治理已接入数据库、API 和 Web 管理台。迁移 `0049_skill_registry` 新增企业隔离的 Skill、版本和配置事件表；`/api/v1/skills/studio` 提供当前注册表与可编排工具清单，创建/发布版本时校验工具必须已在 Tool Registry 登记，发布会自动退役旧版本并保留不可变历史。Web 侧 `/console/twins/skills` 以 Skill Studio 形式完成创建草稿、选择工具、编辑 JSON Schema、版本发布和审计事件回显；它只编排已登记工具，不复制权限，实际运行仍由当前 ActorContext 与 MCP Gateway 决定。

当前数据库迁移 head 为 `0053_runtime_resume_spec`：数字会议的角色独立分析、两轮质询、反方审查和主持汇总已可选用统一 Codex Runtime，并保存会议、参会分身、证据快照、Skill、Runtime Session/Turn/Event 和每次重跑历史；Runtime Session 同时保存排除短期凭据的恢复规格，为 API 重启后的受控恢复提供持久化基础。

真实客户数据接入的第一层连接器契约已补齐：`ConnectorSyncRequest` 支持全量、增量和回填，游标保持不透明，`ConnectorResourceResult` 记录资源级部分失败、重试语义和下一游标，`ConnectorBatch` 继续只输出平台规范事实。详见 [`docs/reports/dat-connector-contract-verification.md`](docs/reports/dat-connector-contract-verification.md)；客户真实字段映射和生产连接器仍待客户样例与白名单条件。

Skill Runtime 注入已完成首轮：Web 分身运行前固定当前企业已发布 Skill 版本，并将 Skill 工具与当前 ActorContext 已授权的 R0 工具取交集；停用工具、未发布版本或无权限交集会在 Codex 子进程启动前拒绝。实际 Skill 键和版本写入 Runtime metadata，详见 [`docs/reports/agt-010-skill-runtime-injection.md`](docs/reports/agt-010-skill-runtime-injection.md)。

最新迁移 `0032_customer_360_facts` 将 CRM 客户主档、行为触点和 ERP 交易真值正式分层。大型 CRM 档同步后形成 600 个客户主档和 3,600 条触点，`/console/data/customers` 按企业或授权门店展示生命周期、渠道贡献、30 日行为趋势、价值/流失风险队列和三类资产血缘。客户可以进一步下钻到独立运营工作台，查看主档、订单、退款、触点、统一时间线和规则策略建议；每项建议携带证据键、适用条件和禁止边界，当前不会自动发券、发送消息或写回第三方系统。`query_customer_360` 1.1 是第五个只读企业工具，可读取范围汇总或同一客户详情，并与页面共用 `customer.profile.read`、范围映射和审计服务；CRM 不能覆盖规范订单与退款金额。连接器分别声明主档和触点事实族是否完整，部分资源失败不会误删上一批有效触点。该切片不表示生产客户身份合并、同意历史、实时事件或正式数据任务已经完成。

最新迁移 `0033_customer_operation_plans` 在单客运营工作台加入受治理的 AI 方案链路。具备客户读取与分析权限的主体可以针对当前授权范围发起幂等运行；系统先冻结客户主档、汇总、订单、退款和触点证据，再要求模型只引用本次 `E*` 证据生成结构化诊断与 3–6 个内部动作。服务端固定所有步骤必须人工审批、禁止外部写入，并排除自动消息、发券积分、退款补偿承诺和 CRM/ERP 写回；模型不可用或引用越界时退回同一确定性 Playbook。运行保存可信发起人、Actor 快照、范围、证据哈希、模型、Token、耗时和降级原因，并进入平台 AI 运行控制台。开发库已用真实 `gpt-5.4-mini` 完成一条高风险客户运行：冻结 11 条证据、生成 6 个步骤，非法引用和绕过人工审批均为 0。该切片验证建议生成与治理闭环，不开放生产自动触达或正式外部执行。

最新迁移 `0034_generalized_action_sources` 将行动提案从“只能来自数字会议”改为通用受治理来源。会议决策与客户运营方案现在共用同一提案、职责分离审批和内部执行台账；每条提案保存来源类型/对象/标题、授权范围、步骤序号和可选证据快照，会议与客户运行外键保持显式且互斥。客户运营页面可以选择尚未提议的模型步骤并幂等送入行动中心，重新读取后显示待审批、已批准或已驳回状态；行动中心按当前主体权限与范围过滤所有来源。开发库已从真实模型方案生成 2 条客户行动，其中 1 条由不同主体批准并登记 `external_write=false`，另 1 条保持待审批。该切片不开放外部任务、消息、优惠或 CRM/ERP 写入，也不提前完成正式 `ACT-*` 任务。

最新迁移 `0035_operational_work_items` 将经营诊断建议接入同一受治理行动来源，并把审批后的内部执行从一次性台账推进为员工可承接的工作状态机。管理者可选择分析建议并幂等送审；不同主体批准后创建 `ready` 工作项，员工只能在授权范围内领取和更新本人工作，经理可以重新分派和重开。领取、推进、阻塞、完成与释放均要求乐观版本和幂等键，并形成追加式事件；工作项继续保持 `external_write=false`，不调用第三方任务、消息、CRM 或 ERP。开发库已使用真实 AI 经营诊断生成提案，由财务主体批准后完成员工领取、开始和结果提交的全链路验证。

最新迁移 `0036_scheduled_store_reviews` 将人工店铺诊断扩展为受治理的自动巡店计划。CEO 或运营负责人可以在授权企业/门店范围内设置 IANA 业务时区、运行日、时间、观察窗口和建议送审阈值；API 调度器只幂等入队，通用 Worker 领取后再由领域 API 重查计划创建人的当前账号、分析权限和数据范围。运行复用统一经营分析与证据快照生成诊断和版本化简报，高风险建议最多创建为 `pending_approval`，不会自动批准或写入店铺、CRM、ERP。`/console/analysis/review-plans` 展示计划、边界、队列与运行台账，并对员工投影为只读。

最新迁移 `0040_local_password_auth` 将身份管理推进为受治理写入纵向切片，并增加服务端会话与可替换的本地密码认证。平台管理员可以创建账号并绑定组织岗位、访问角色和逐角色数据范围，也可以在乐观版本保护下调岗、换角色、调整范围或停用账号；同一请求键的重放不会重复写入，改变请求内容会返回冲突。组织、岗位和访问角色现在支持独立的版本化目录变更，停用组织前会检查生效岗位，停用岗位前会检查生效任职。岗位与访问角色仍保持分离，`self` 和企业范围由服务端收敛到目标主体与当前企业，管理员不能停用自身或改变自身访问包。每次创建和配置会写入 `IdentityManagementEvent`，目录变更写入 `IdentityCatalogEvent`，与普通允许/拒绝授权决策分账展示。生产入口使用 `/api/v1/auth/login` 建立 HttpOnly 会话；密码初始值只从运行时 `AUTH_BOOTSTRAP_PASSWORD` 注入，正式 SSO 和真实渠道认证提供者仍未实现；临时权限委托已在 `0044` 接入统一身份解析。

最新迁移 `0041_worker_authorization_context` 将自动巡店 Worker 接入统一授权链。后台任务 v2 固化发起主体快照、排队时权限版本、声明权限、企业和目标范围；Worker 每次领取生成一次性执行令牌，数据库只保存哈希，完成、失败或租约过期立即失效。内部执行 API 同时核对领取 Worker、令牌、`request_id`、`run_id`、计划范围和任务声明，不接受 Worker 传入任意主体或权限。执行时重新加载发起人的当前账号、角色和范围，排队后停用账号、撤销权限或移除门店范围都会拒绝执行并写入 `AuthorizationDecision`。该切片只覆盖 `analysis.daily-store-review`，不提前宣称全部 Worker、MCP 或 Agent 入口完成。

最新迁移 `0042_trusted_mcp_gateway_sessions` 将企业 MCP 网关从开发身份头升级为短期受限会话。登录主体可以为明确的 MCP 客户端签发工具白名单、可选数据范围和可选 `AgentRun` 关联；令牌只在签发响应返回一次，数据库仅保存 SHA-256 哈希。网关每个请求携带专用会话、客户端 ID、独立 `request_id` 和稳定 `run_id`，API 重新加载当前账号、角色、权限与范围，再与会话上限取交集。工具被移出白名单、账号停用、权限撤销或门店范围变化会在下一次调用生效；调用台账保存认证方式、会话、AgentRun、签发与执行权限版本。该切片覆盖当前五个 R0 工具和 STDIO 网关，不代表完整 Agent Runtime 或 R1/R2 行动工具已完成。

最新迁移 `0043_channel_identity_bindings` 增加外部渠道身份的数据库生命周期。平台管理员可以检索未知身份并执行绑定、换绑、解绑、停用和启用；写入使用乐观版本、幂等请求和追加式 `ChannelIdentityEvent`。数据库只保存外部身份 SHA-256 与短提示，渠道身份解析后仍重新读取本地账号、角色和范围。`/console/admin/channels` 已接入真实 API、组合筛选、配置工作区和审计投影；真实飞书签名校验、通讯录同步和消息收发仍由后续渠道适配器实现。

最新迁移 `0044_platform_management_controls` 新增平台管理控制面：数据库后台任务详情、Attempt 时间线和受控重试；参数与字典；领域事件、站内通知和渠道投递状态；文件资产、本地对象存储适配、完整性校验与权限下载；通用 CSV 预检、错误行、确认写入和导出；组织子树、临时权限委托及权限解释。所有写入使用自有契约、企业边界、幂等键或乐观版本，不包含 PigX 专用导入器、侧车或运行时依赖。

迁移 `0045_agent_runtime_control` 新增运行时无关的 `AgentRuntime` 契约、确定性 `FakeAgentRuntime`、Codex `app-server` STDIO 适配器、运行时握手 API、数据库探针台账和 AI 运行控制台。适配器支持线程启动、续跑、事件流、取消和关闭，并默认使用只读沙箱；命令、文件修改、额外权限、动态工具和用户输入请求默认拒绝。该迁移阶段已完成本机 Codex Harness 握手，业务主链切换由后续迁移继续推进。

迁移 `0046_agent_runtime_sessions` 将内部 Web 分身问答切到 Codex Runtime 主链。`AgentRun` 在调用前落库，随后签发绑定真实提问人、R0 工具白名单和该运行的短期 MCP 会话；Session、Thread、`thread.sessionId`、Turn 与脱敏规范事件分别持久化，回答结束即撤销 MCP 会话并释放子进程。API 重启后适配器可以用已保存 Thread 调用 `thread/resume`。Runtime 结构化回答继续经过证据数值校验，失败时明确降级到 Responses Provider，再失败才使用确定性证据摘要。

最新迁移 `0047_agent_runtime_multiturn` 将一个 Runtime Session 固定映射为一个 Codex Thread，并让每次分身追问创建独立 AgentRun、最新证据快照、短期 MCP 会话和 Runtime Turn。续问只允许同企业、同真实提问主体、同角色分身在上一轮完成后发起，不继承被模拟领导或历史主体的权限。AI Runtime 控制台可以查看逐 Turn 的角色版本、证据/上下文数量、耗时、错误、追踪 ID 与脱敏事件，并可对当前 API 实例中的活动 Turn 发起受控 `turn/interrupt`；取消不会切换 Provider 继续生成答案。人工审批恢复以及会议、分析、客服迁移仍待后续实现。

最新迁移 `0048_enterprise_scope_foundation` 为多子公司场景增加集团、法人企业、事业单元、企业成员关系、范围授权声明、合并口径、中心启用和来源映射底座。现有单企业数据会自动归入以 `grp_<enterprise_id>` 命名的默认集团，原有 `enterprise_id` 继续作为法人数据边界。`/api/v1/centers/me` 输出按当前 ActorContext 权限裁剪的中心目录，`/api/v1/context` 输出集团/法人/业务单元范围上下文，`POST /api/v1/context/switch` 在有效成员关系下切换当前会话法人并重新计算授权；Web 侧栏按工作入口、经营管理、数据中心、业务中心、治理中心、智能中心和平台中心分组，`/console` 为数字孪生默认入口，`/console/workspaces` 为独立岗位工作台。当前请求不会接受客户端伪造企业范围。

岗位工作空间改造已完成首轮实现：`/api/v1/workspaces/me`、工作空间 Profile、Read Model 与受控刷新接口由服务端按当前身份投影；`/console` 首屏按 CEO、经理、运营、客服、财务、人员制度、数据治理、平台运维和 AI 运维工作空间呈现不同关注点，仍复用数据、分析、知识、分身、会议、行动和平台中心。分身问答、经营分析、数字会议和 Codex Runtime 使用同一 `workspace_key` 上下文并写入运行/会议/MCP 会话快照，工作空间切换不会改变权限或数据范围。实现和验收边界见 `docs/development/07-role-oriented-workspace-modification-guide.md`，当前 `UIA-009` 进入产品复核状态。

`DX-008` 进一步固定企业中心域与岗位工作台边界：`/console` 作为数字孪生默认首页，`/console/spatial` 保留为兼容入口，`/console/workspaces/{workspace_key}` 作为岗位视图；数据基础（来源、同步、实体、指标、质量、血缘）与数据产品/经营洞察（经营事实、实体 360、分析、驾驶舱）分层，知识中心只负责知识资产生命周期，业务执行回到运营、商品、客户、履约、供应链等中心。Web 侧栏已移除跨中心全局 Tab，数据基础和数据产品使用独立 canonical 路由，渠道与店铺使用 `/console/commerce/stores` 独立页面，未具备独立页面的中心不再出现在菜单中；旧 `/console/data/*` 地址仅保留兼容解析。指南同时增加集团、法人企业、业务单元、组织和店铺的多企业扩展，要求集团合并口径、企业明细、范围授权、知识继承和 AI/会议/MCP 运行快照显式绑定；后续实现任务登记为 `UIA-010`，等待产品验收门和 `UIA-009` 复核后执行。详见 `docs/development/08-enterprise-center-domain-and-workspace-boundary-guide.md`。

平台管理台现已提供数据库驱动的统一审计检索中心。`/api/v1/audit/events` 在查询时归一化授权决策、身份目录与渠道绑定变更、MCP 会话、工具调用、后台任务、AgentRun、行动工作和平台操作八类现有事实，不复制第二套日志真值；管理员可以按来源、结果、主体、时间、`request_id`、`run_id` 或 `agent_run_id` 检索和分页，并查看来源、结果与主体 Facet。响应只返回允许清单内的业务属性，不返回令牌、Cookie、外部身份原文、Prompt、工具完整输入、后台任务载荷、Agent 回答或客户原始数据。全部关键审批类型尚未纳入，因此不提前关闭正式 `IAM-007`。

数据中心 HTTP 入口已接入同一数据库身份与授权决策服务：概览要求有效会话与平台导航权限；来源、同步批次、实体、指标和质量管理要求对应功能权限及企业范围；指标序列、规范经营事实和客户 360 按企业或门店范围检查。允许和拒绝均保存主体、资源、权限、范围、策略版本、`request_id` 与 `run_id`。经理和员工的菜单投影只显示其可用的经营事实与客户页面，经营事实页默认使用当前账号首个有效企业或门店范围；前端不再为客户数据请求发送开发身份头。Agent Runtime 控制面、业务线程/事件持久化和内部 Web 分身主链已经完成，其他 Worker/Action、AI 业务和真实渠道适配器仍按任务依赖推进。

真实运行依赖切换已形成 `OPS-006` 实现切片：API 支持托管 PostgreSQL、S3 兼容对象存储、Redis 多实例调度互斥、标准 `OPENAI_*` 密钥兼容和生产启动门禁；SQLite 到 PostgreSQL 的迁移脚本保留源库并提供预检。正式配置不再自动迁移数据库或装载开发种子，知识/记忆 Provider 没有真实端点和凭据时保持禁用。详见 `docs/architecture/18-production-runtime-dependencies.md`。

## 目录

- `AGENTS.md`：Codex 在本仓库工作的最高优先级协作规则。
- `docs/product/`：产品愿景、客户价值、版本范围。
- `docs/architecture/00-product-architecture.md`：产品、业务、应用、数据、AI、安全与部署的一体化架构总纲。
- `docs/architecture/`：领域专题设计、接口边界、开源项目采用策略与 ADR。
- `docs/development/`：Codex 驱动研发方式和技术决策。
- `tasks/`：可由 Codex 逐项执行的任务索引与任务包。
- `contracts/`：未来内部 API、事件、MCP 工具的契约。
- `apps/`：Web、飞书和其他渠道应用。
- `services/`：数据、知识、记忆、智能体和行动服务。
- `packages/`：共享领域模型、SDK、UI 和工具包。
- `mcp/`：企业自有 MCP 网关及业务工具。
- `evals/`：知识问答、指标问数、角色风格、会议与工具调用评测。
- `references/open-source/`：只读参考仓库，不属于产品源码。

## 首个可验证结果

进入真实纵向切片前，先完成产品全景 v0.1：

1. CEO、部门经理、员工、平台管理员和客服视角可以切换验收。
2. 数据、知识、分身、会议、分析、行动、客服和平台管理代表性页面可操作。
3. 制度问答、经营异常、数字会议、行动审批和客服草稿可以用统一模拟数据串联。
4. 原型能力、真实能力和不可用能力有明确标识。

全景验收通过后的首个真实版本至少完成：

1. 创建通用角色分身，并配置 CEO 作为第一个实例。
2. 导入当前生效制度和经过审核的管理者记忆。
3. 接入一个店铺或业务单元的日级经营数据。
4. 在飞书中回答制度问题和有限的经营问题。
5. 每次回答显示制度版本、数据时间、引用证据和回答类型。
6. 建立纠错、反馈与自动评测闭环。
7. 员工、管理者、分身和渠道使用同一身份与数据范围，分身不会扩大提问者权限。

当前本地纵向切片已打通数据库日级指标、角色权限、真实 AI 和运行证据：`/console/assistant` 可按 CEO 企业范围或员工门店范围读取 30 日指标序列，并以 D/E/M 三类上下文展示实际数据、制度版本和审核记忆。该结果用于持续验收，不替代任务索引中的正式依赖和里程碑完成条件。

产品全景蓝图位于 `docs/product/02-product-experience-blueprint.md`，验收任务位于 `tasks/EPIC-M0-product-experience.md`。

## 开始使用 Codex

1. 先阅读 `AGENTS.md`。
2. 阅读 `tasks/README.md` 和 `tasks/task-index.yaml`。
3. 一次只领取一个状态为 `ready` 且依赖已完成的任务。
4. 实现前阅读该任务指向的产品、架构和验收文档。
5. 完成代码、测试、文档和任务状态更新后再结束任务。

## 本地开发

运行时基线：Node.js 22、pnpm 9、Python 3.11 和 uv。Docker 在 FND-005 引入本地 PostgreSQL/MinIO 编排时成为必需工具。

```powershell
pnpm run doctor
pnpm bootstrap
pnpm check
```

- `pnpm run doctor`：只读检查本机运行时；显式使用 `run` 避免与 pnpm 内置命令重名。
- `pnpm bootstrap`：安装 pnpm workspace 依赖并创建 uv 环境。
- `pnpm dev`：启动 `workspace.config.json` 中已登记的应用进程。
- `pnpm check`：运行工作区、任务依赖、架构文档和快速测试检查。
- `pnpm test`：运行自动化测试。
- `pnpm codex:task -- --task <TASK_ID>`：以默认只读、临时会话执行 Codex 非交互任务。
- `pnpm codex:task -- --task <TASK_ID> --write`：仅对 `ready/in_progress` 任务显式开放工作区写入。
- `pnpm infra:up`：FND-005 完成且 Docker 可用后启动本地基础设施。
- `pnpm infra:verify`：在隔离 Compose 项目中验证健康检查、建桶和重启持久化，并自动清理验收卷。
- `pnpm db:status` / `pnpm db:upgrade`：查看并升级数据库 revision。
- `pnpm db:seed`：升级结构后幂等应用版本化业务快照与模拟连接器数据。
- `pnpm db:rebuild:test`：仅对名称含 `test` 或 `verify` 的数据库执行完整重建。

首次启用本地密码登录时，在运行环境注入 `AUTH_BOOTSTRAP_PASSWORD`（至少 12 位）后执行 `pnpm db:seed`；密码只以 PBKDF2 哈希写入账号表，仓库不保存密码。管理员后续可在“平台管理 / 用户账号”创建账号时设置初始密码，编辑账号不会回显密码。
- `pnpm worker:once`：最多领取一个后台任务后退出，适合验收和运维探针。
- `pnpm worker:run`：独立运行通用 Worker，支持 `SIGINT/SIGTERM` 优雅停止。
- `pnpm mcp:run`：启动企业只读 MCP STDIO 网关。
- `pnpm mcp:verify`：用协议内进程与真实 STDIO 子进程验证工具清单、知识、制度、指标、规范经营事实与客户 360 读取。

统一 `pnpm dev` 为保证 Windows 下三进程稳定运行，不为 Python 服务开启热重载；需要单独开发 API 时使用服务 README 中的 `uvicorn --reload` 命令。

`pnpm dev` 会同时启动 Web 管理台、产品 API、通用 Worker 和电商模拟连接器。未设置 `DATABASE_URL` 时使用本地持久化 SQLite；客户环境改用 PostgreSQL。默认地址：

- Web：`http://127.0.0.1:3000`
- API 存活检查：`http://127.0.0.1:8000/health/live`
- API 模块边界：`http://127.0.0.1:8000/api/v1/platform/modules`
- 数字孪生数据：`http://127.0.0.1:8000/api/v1/data-center/overview`
- 数字会议状态：`POST http://127.0.0.1:8000/api/v1/data-center/meetings/{meeting_key}/actions`
- 电商模拟连接器：`http://127.0.0.1:8100/docs`

客户讲解文档位于仓库根目录：`知行数枢-企业数据智能运营中枢产品介绍.docx`。
