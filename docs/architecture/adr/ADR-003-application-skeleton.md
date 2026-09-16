# ADR-003：Web 与 API 应用骨架

- 状态：Accepted
- 日期：2026-08-24
- 决策任务：FND-004

## 决策

1. Web 使用 Next.js App Router、React 和严格 TypeScript，不在首个骨架引入组件库或全局状态框架。
2. API 使用 FastAPI 应用工厂，路由按 `health` 与版本化业务 API 分开。
3. API 通过只读模块注册表展示 ADR-001 的领域边界；注册表只描述模块，不模拟未实现业务能力。
4. Web 运行时读取模块注册表，按客户产品导航展示当前边界与里程碑。
5. Web 和 API 是独立进程，通过 HTTP 交互；浏览器不直接访问数据库或 MCP。
6. FND-004 只交付应用骨架、存活/就绪检查和模块导航，不接数据库、真实用户或模型。

模块注册表中的 `milestone` 和 `availability` 只表示规划阶段，不表示模块已经实现。实现状态以 `tasks/task-index.yaml` 为准；`IAM-005` 建立正式应用壳后，用户导航由有效权限与已发布能力共同投影。

ADR-005 在本骨架与真实领域实现之间增加产品全景原型。FND-004 的介绍首页将演进为可操作管理台；原型使用模拟数据源，不能反向改变本 ADR 的 Web/API 边界或把未实现能力标为真实可用。

## 目录

```text
apps/web/
  src/app/                 Next.js 页面和样式
  src/components/          客户可见组件
  src/lib/                 API 类型与产品导航

services/api/
  src/zhixing_api/main.py  应用工厂
  src/zhixing_api/routers/ HTTP 路由
  src/zhixing_api/modules/ 领域模块注册表
  tests/                   API 骨架测试
```

## 验收

- `pnpm dev` 同时启动 Web 与 API。
- `/health/live` 和 `/health/ready` 返回结构化成功结果。
- `/api/v1/platform/modules` 返回唯一模块键和七个产品导航分组。
- Web 可见产品定位、API 状态和各中心模块边界；规划中模块有明确阶段。
