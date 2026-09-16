# DAT-011 新 Codex 会话执行提示词

将下面代码块完整复制到新的 Codex 会话。不要把任何密码、AppID、AppSecret、Token、数据库连接串或真实客户响应附在提示词中。

```text
你将在本地仓库 D:\722\codex-tools\zhixing-data-hub 执行 DAT-011：完成领星 ERP 与集团范围的本地生产化闭环。

这是一个持续执行任务。请在同一会话内按阶段自动推进，完成契约、数据库迁移、后端、Worker、Web、测试和文档后再统一汇报；不要每完成一个小步骤就停下来等待确认。遇到规划与代码冲突时，以当前代码和测试为证据，先更新实施文档或 ADR，再选择范围最小且可扩展的解决方案继续推进。不要用静态 Demo、硬编码数据、说明性文案或假成功代替真实功能。

开始前必须完整阅读：

1. D:\722\codex-tools\AGENTS.md
2. D:\722\codex-tools\SERVER_INVENTORY.md（只用于确认远程操作边界；本任务禁止远程变更）
3. D:\722\codex-tools\zhixing-data-hub\AGENTS.md
4. D:\722\codex-tools\zhixing-data-hub\README.md
5. D:\722\codex-tools\zhixing-data-hub\tasks\README.md
6. D:\722\codex-tools\zhixing-data-hub\tasks\task-index.yaml
7. D:\722\codex-tools\zhixing-data-hub\docs\PROJECT-STATE-AND-ROADMAP.md
8. D:\722\codex-tools\zhixing-data-hub\docs\architecture\adr\ADR-022-group-scoped-real-source-ingestion.md
9. D:\722\codex-tools\zhixing-data-hub\docs\development\10-lingxing-erp-real-data-and-group-rollout-plan.md
10. D:\722\codex-tools\zhixing-data-hub\docs\development\11-lingxing-local-one-pass-implementation-plan.md
11. D:\722\codex-tools\zhixing-data-hub\docs\reports\2026-09-08-lingxing-connectivity-and-production-data-audit.md

执行边界：

- 只修改本地代码、迁移、合成 fixture、测试和文档。
- 禁止 SSH、远程数据库、DNS、Nginx、Docker/systemd 生产变更、服务器发布和线上清理。
- 禁止使用或索要此前聊天中的领星密钥、服务器密码、数据库密码或任何真实 Token。
- 禁止把真实密钥、客户数据、Cookie、访问令牌或真实响应写入仓库、日志、数据库 fixture、截图或报告。
- 领星只实现只读资源；不调用创建、修改、删除、发货、调价、库存调整或消息发送接口。
- 外部协议研究只使用领星官方文档；如果无法确认字段，不猜测，登记为 schema_pending 并用合成 fixture 验证通用 Raw 链路。
- 不执行生产 demo-retire 或清表。清理工具只能在名称含 test/verify 的隔离数据库中 dry-run 和自动化测试。
- 遵守仓库 UI 规则：新增/编辑使用统一 Dialog，危险操作使用 ConfirmDialog；页面不写教程、架构说明、演示旁白、“即将支持”或用于解释界面本身的文字。
- 保留用户现有改动，不使用 git reset --hard、git checkout -- 或其他破坏性恢复命令；所有手工文件编辑使用 apply_patch。

任务启动：

1. 检查当前 git 工作树、迁移头、运行时版本和测试基线。
2. 确认 task-index 中 DAT-011 的依赖和验收，把状态从 ready 改为 in_progress。
3. 输出一段简短实施计划，然后开始工作，不要停在分析阶段。
4. 先写或补契约与失败测试，再实现代码。

必须完成的工作：

一、去除生产运行路径中的演示企业硬编码。seed、tests、明确 mock/fixture 可以保留；业务 service、router、Actor/Scope 解析和 Web 组件不得默认 ent_zhixing_demo。增加静态回归测试。登录不能依靠演示企业定位账号；跨企业同名登录必须有确定的歧义处理。使用一个集团、两个法人、三个业务单元的合成测试证明隔离。

二、实现 ScopeContext v2 和集团治理闭环。enterprise_id 继续表示法人，集团视图只能展开当前主体获权的 enterprise 集合。ScopeContext 至少包含 group、当前法人、选中法人集合、业务单元、店铺、仓库、scope level、本位币、合并口径版本、data_as_of 和 scope version。补齐集团、法人、业务单元、成员、合并口径、来源归属 API，并让 Runtime/MCP/会议/Action/工作台/数字孪生只做必要的范围快照兼容。

三、从迁移 0054 开始按语义建立来源接入台账。扩展 ExternalSystem，新增或等价实现 SourceResource、SyncResourceRun、SyncCheckpoint、RawPageManifest、MappingConflict、SourceAuthorityRule，并扩展 SyncRun 的主体、追踪、任务和范围快照。迁移必须同时通过空 PostgreSQL 和 0053 升级库；采用新增/回填/收紧方式，不破坏现有数据。

四、实现 connectors/lingxing 只读 Provider：CredentialProvider、Token 生命周期、签名、GET/JSON POST/multipart/异步报告、分页、资源级限流、有界退避、错误分类、官方 Host/只读资源 allowlist 和完整脱敏。使用 httpx.MockTransport 或本地模拟服务及合成数据。签名测试覆盖固定时间、中文、数组、嵌套 JSON、空值和 URL 编码。不要访问真实领星账号。

五、建立 W0-W8 版本化资源目录和通用分页 Raw 链路。W0-W3 必须完成规范映射：目录与店铺、主数据、订单/售后、库存/履约。W4-W8 完成可确认只读资源的目录、分页或异步报告状态和 Raw 落地；缺少可靠 Schema 的资源必须标记 schema_pending，不能进入指标、AI 或集团汇总，不能伪装为完成。

六、把同步改成 API 入队、Worker 执行。POST sync 立即返回 queued；Worker 按资源/范围/分区/页执行外部请求，写 Raw、校验、规范映射和 checkpoint。实现租约、重试、取消、幂等、断点恢复、部分失败、父子运行汇总和审计。外部网络请求不能发生在用户 API 请求生命周期内，也不能由 Worker 再同步调用 API 执行整批。若 Worker 需要复用 API 领域模块，建立显式 workspace 依赖，不用临时 PYTHONPATH 或复制模型。

七、完善 Raw/Staging/Core。增加 SOURCE_ARCHIVE_PATH，原始页压缩、内容寻址、原子改名、哈希和路径安全；数据库只保存 manifest。映射冲突进入人工队列。金额支持原币、本位币、币种和汇率版本，不假设所有币种两位小数；时间支持来源时间、UTC、店铺时区和业务日期；规范事实保存来源、资源、外部键、Schema、映射和 Raw 页追溯。局部失败不得删除上一批有效事实。

八、完成真实管理 API 和 Web：顶部集团/法人/业务单元/店铺范围选择；集团组织治理；来源创建编辑停用探测；来源资源与 checkpoint；父子同步运行；Raw manifest/血缘；未分配店铺和映射冲突审核；权威资源与质量状态。页面使用服务端权限和范围，数据来自真实 API，不在组件内散落 fixture。

九、实现 production-bootstrap 和 demo-retire 的安全 CLI 与 dry-run。默认不执行，执行模式要求显式确认、测试数据库门禁、备份 ID 和 manifest。自动化测试覆盖逐表影响、重复执行、计数漂移、外键阻断和会话撤销。本任务绝不在生产环境执行。

十、更新 .env.example、API/Worker README、任务索引、架构/开发文档，并创建 docs/reports/dat-011-lingxing-local-verification.md。所有配置仅写变量名和空值，绝不写密钥。验证报告要列出 schema_pending、未解决风险和生产交接条件，不能宣称真实数据已接入。

阶段质量门：

- 每完成一个工作包先运行相应 API/Worker/Web/migration 定向测试，修复后自动进入下一包。
- 最后运行 pnpm run doctor、node tools/workspace.mjs check、pnpm check、pnpm build。
- 如果完整测试长时间没有输出，定位具体进程和失败原因；不要直接中断并宣称通过。
- 检查工作树中没有秘密、真实客户响应和意外生成物。

完成定义以 docs/development/11-lingxing-local-one-pass-implementation-plan.md 第 8 节为准。只有所有完成定义满足时，才能把 DAT-011 改为 review；不得自行标记 done。最终汇报只包含：完成模块、迁移、测试结果、schema_pending/外部依赖、生产阶段下一步。不要发布服务器，也不要触碰线上数据。
```
