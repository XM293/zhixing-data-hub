# UI contracts

这里保存产品全景原型使用的读取模型约束。它们是 Web 与数据适配器之间的稳定边界，不是领域数据库模型，也不约束后续表结构。

## 当前契约

- `experience-snapshot.schema.json`：一次可复现演示所需的角色、页面投影和跨模块对象。
- `module-manifest.schema.json`：导航模块、路由、交付状态和数据模式。

演示适配器位于 `apps/web/src/demo`。页面只通过 `ExperienceProvider` 读取快照和执行模拟命令。后续 API 适配器必须输出同一读取模型；真实领域契约仍由 `DOM-*` 任务定义。

## 兼容规则

1. `schemaVersion` 仅在破坏性变更时递增。
2. 对象 ID 在列表、详情、证据与命令结果中保持一致。
3. 时间值包含业务日期或明确的 `asOf`，不得用浏览器当前时间伪造。
4. `dataMode` 和 `deliveryState` 必须显式呈现，原型不得冒充真实能力。
5. AI 结论必须区分事实、分析和建议，并携带证据摘要。
