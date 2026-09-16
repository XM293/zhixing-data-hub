# UIA-007 数字孪生三维视觉增强记录

日期：2026-09-06

## 本轮范围

- 园区增加边缘灯带、路灯节点、环境星点和远景轮廓层；
- Three.js 渲染链增加低强度 Unreal Bloom 后处理，保留原有阴影、雾效和色调映射；
- 仓储子场景增加顶部灯带与装卸区点光源；
- 数字会议子场景增加顶部环形灯带与中心照明；
- 仓储和会议室热点标签缩小，避免近景镜头下覆盖货架和业务对象；
- 保持数据库空间、热点、分身路线、选择反馈和二维跳转契约不变。

## 验收

- `pnpm --filter @zhixing/web check` 通过；
- `pnpm --filter @zhixing/web build` 通过；
- 浏览器实际验收通过园区总览、仓储空间和仓储内部场景；
- 截图保存在 `output/playwright/digital-twin-polished-campus.png`、`output/playwright/digital-twin-polished-warehouse.png` 和 `output/playwright/digital-twin-polished-warehouse-interior.png`。

## 后续增强

下一轮可继续接入 GLB/GLTF 资产、LOD、InstancedMesh、会议室数据屏、人物骨骼动画和更细的建筑内部结构；本轮不引入外部模型依赖，避免破坏当前可替换的数据库驱动场景契约。
