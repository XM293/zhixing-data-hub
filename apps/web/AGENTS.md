<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## 产品界面文案规则

- 页面可见文字只能用于业务数据、字段名称、状态、操作命令、校验错误和完成工作所必需的空状态。
- 禁止在页面中加入功能介绍、架构解释、实现说明、教程、操作教学、演示旁白、设计意图或描述界面本身的文字。
- 不得通过“即将支持”“这里展示”“用于演示”等文字掩盖缺失的数据、交互或后端能力；应实现真实状态和完整交互。
- 图标按钮只为不熟悉的图标提供简短 tooltip；错误和空状态必须简洁、可操作，不扩展为产品说明。
- 新增或修改页面时必须检查桌面与移动布局，并扫描新增可见文案是否违反以上约束。

## 后台操作交互规则

- 列表是稳定工作区。简单新增和编辑使用统一 `Dialog`，不得把表单临时插入列表上方或行间导致页面跳动。
- 字段较多、需要保留列表或详情上下文的账号、权限、委托配置使用统一右侧 `Drawer`；复杂编排和数据预检可以保留独立工作区。
- 删除、停用、解绑、换绑、撤销、批准、驳回、正式写入、决策确认和受控重试必须使用统一 `ConfirmDialog`，明确对象与影响；需要原因时在确认框内填写。
- 创建或保存成功使用全局成功消息；普通写操作失败使用全局错误消息，并保持当前弹窗、抽屉和已填写内容不变。
- 字段格式和必填错误显示在字段附近；页面查询或首次加载失败保留内容区错误状态和重试操作，不使用模态框。
- 权限不足、只读边界、数据冲突和需要持续阅读的风险信息使用页面内联状态，不得用短暂消息替代。
- 所有弹窗和抽屉必须使用 `components/console/interaction.tsx`，支持 Portal、焦点回收、Tab 约束、Esc、滚动锁定和移动端布局；禁止继续复制自制遮罩层。
- 一个操作能在当前列表、详情或侧栏中清晰完成时保留上下文，不为追求弹窗而弹窗；是否使用覆盖层由操作复杂度、风险和上下文需求决定。
