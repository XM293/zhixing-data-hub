# 数据驱动产品全景交付规范

> 2026-08-25：纯静态 v0.1 未通过产品负责人验收。本规范已按 ADR-006 修订，首页和后续代表性流程必须逐步替换为数据库与 API 驱动；Fixture 只保留为尚未重做页面的需求参考和自动化样例。

## 1. 目标与边界

产品全景用于在完整领域实现前验证整体信息架构、工作流、术语和视觉方向。它必须是可运行产品，而不是图片或演示文稿；代表性首页和接入链路必须有真实持久化状态。

该阶段可以建立接入底座、原始记录、标准化投影、第三方测试沙箱和只读业务 API；不连接客户生产系统、不调用真实写操作，也不以 UI Read Model 替代最终领域契约。

## 2. 代码结构目标

```text
apps/web/src/
  app/(console)/              管理台路由与布局
  modules/                    各产品中心页面和视图组件
  demo/fixtures/              稳定模拟对象
  demo/scenarios/             跨模块故事与状态转换
  lib/data-source/            UI 数据源接口

contracts/ui/
  navigation/                 导航投影和角色视角
  read-models/                页面读取模型
  commands/                   原型命令及模拟结果
```

实际目录可以在 `UIA-002/UIA-003` 根据 Next.js 本地版本文档微调，但职责边界不得混合。

## 3. 可替换数据源

页面依赖 `ExperienceDataSource` 或等价自有接口，不直接导入 Fixture。未重做页面暂用 `DemoExperienceDataSource`；已重做页面必须增加 API 数据源并明确显示 `data_mode: database`。

```text
Page / View
    ↓
UI query or command
    ↓
ExperienceDataSource
    ├─ Demo adapter
    └─ API adapter（后续）
```

模拟命令返回确定性状态变化，例如“制度草稿 → 待审核 → 已发布”，但刷新或重置后可以恢复固定场景。需要跨页面保持的临时状态由统一 Demo Store 管理，不散落在页面组件。

## 4. UI Read Model 规则

- Read Model 只包含页面需要的信息和稳定对象引用。
- 列表摘要与详情模型可以不同，不要求复用一个万能对象。
- 金额、比率、时区、业务日期、版本、来源和状态使用统一格式。
- 所有对象携带 `data_mode: demo` 或等价元数据。
- AI 输出包含 `statement_type`、证据摘要和 `as_of`。
- 页面模型不得包含开源组件内部 ID 或未来数据库字段假设。

## 5. 模块清单与导航

建立版本化模块清单，至少包含：

```text
module_key
navigation_key
route
label
icon_key
required_capability
delivery_state
data_mode
```

`delivery_state` 区分 `prototype`、`implemented`、`unavailable`，不得继续使用一个含糊字段同时表示里程碑和实现状态。演示角色的菜单投影使用模拟能力集生成，以便提前验证权限体验。

## 6. 视觉与交互要求

- 使用实际企业软件布局，优先扫描、比较和重复操作效率。
- 使用统一侧栏、顶栏、内容宽度、筛选栏、表格、详情抽屉和状态反馈。
- 不把每个页面区域包装成浮动卡片，不嵌套装饰性卡片。
- 图标按钮使用项目图标库并提供 Tooltip；状态、风险和来源不能只靠颜色区分。
- 固定格式组件设置稳定尺寸，动态数据不得造成布局跳动。
- 桌面端至少验收 1440×900，移动端至少验收 390×844。
- 页面包含长名称、空值、异常值和部分失败数据，避免只为理想样例设计。

## 7. 原型测试

每个 UIA 任务按风险执行：

- Read Model 与 Fixture 契约测试；
- 模块清单唯一键、路由和角色投影测试；
- 关键状态组件测试；
- Playwright 串联四个代表性故事；
- 桌面端和移动端截图验收；
- 浏览器控制台、失败请求、溢出和遮挡检查。

截图和验收材料放入 `output/playwright/`，验收结论放入 `docs/reports/`。截图不是任务状态的唯一依据，可复现操作路径必须同时记录。

## 8. 真实实现替换规则

UIA-006 通过后：

1. `DOM-*` 根据验收术语定义领域契约，但不照抄页面模型。
2. 真实 API 保持 UI 查询接口稳定，内部通过应用用例生成投影。
3. 一个页面只有在真实鉴权、数据、错误和测试均完成后才能从 `prototype` 改为 `implemented`。
4. 同一模块允许部分页面真实、部分页面演示，但必须在模块清单和界面状态中明确。
5. 纵向切片仍优先管理者分身，不按页面顺序逐个建设全部后端。

## 9. v0.1 实际实现映射

```text
apps/web/src/app/console/[[...path]]/   可选捕获路由
apps/web/src/components/console/       管理台壳和通用界面组件
apps/web/src/modules/console-page.tsx  中心页面与跨模块详情
apps/web/src/demo/fixtures.ts          固定业务对象和列表投影
apps/web/src/demo/experience-provider.tsx
                                      演示状态与模拟命令
apps/web/src/lib/experience-types.ts   TypeScript UI Read Model
contracts/ui/                          可替换数据源的 JSON 契约
```

`ExperienceProvider` 是当前界面与后续 API 适配器之间的替换边界。列表与详情通过稳定 ID 关联；任何模拟命令都必须同步更新相关投影。

## 10. v0.2 数据驱动验收映射

```text
services/mock-commerce/                       独立第三方电商测试沙箱
services/api/migrations/                      Alembic 可重复迁移
services/api/src/zhixing_api/connectors/      第三方字段隔离与版本化映射
services/api/src/zhixing_api/data_models.py   原始、标准化与孪生运行投影
services/api/src/zhixing_api/data_center_*    同步用例和首页查询 API
apps/web/src/components/twin/                 Three.js 企业数字孪生工作台
deploy/local/compose.yaml                     PostgreSQL 16 与 MinIO
```

首页不得导入 `apps/web/src/demo`。第三方返回字段只允许在连接器和 `SourceRecord.payload` 中出现。

## 11. v0.3 数据管理纵向切片

```text
services/api/migrations/versions/0008_*      指标目录、质量规则与检查结果
services/api/migrations/versions/0009_*      同步数据规模档位
services/api/src/zhixing_api/data_center_*   五个数据库查询与同步 API
apps/web/src/components/data-center/         数据源、批次、实体、指标和质量页面
```

第三方沙箱按小型、标准、大型三个档位生成稳定数据；标准档用于日常产品验收，大型档用于分页和性能检查。测试数据量只能证明链路和界面可用，数据源页继续显示与生产基线的差距。
