# 数据库迁移与种子框架

状态：Implemented / Accepted  
任务：`FND-006`

## 约束

1. Alembic 是数据库结构的唯一变更入口，应用模型不得调用 `create_all` 绕过迁移历史。
2. 服务启动、CLI 和测试使用同一 `Database.migrate()`，空库与已有库均升级到 `head`。
3. 测试数据通过稳定业务键幂等写入；`seed_versions` 记录数据集版本、内容 SHA-256 和应用时间。
4. 同一清单版本对应的内容发生变化时拒绝播种，必须先提升 `services/api/seeds` 中的版本。
5. `rebuild` 是破坏性测试工具，必须显式确认，且目标名称必须包含 `test` 或 `verify`。

## 命令

| 命令 | 行为 |
| --- | --- |
| `pnpm db:status` | 只读输出当前 revision；空库为 `base` |
| `pnpm db:upgrade` | 升级到最新 revision，可重复执行 |
| `pnpm db:seed` | 先升级，再应用允许当前环境使用的种子 |
| `pnpm db:rebuild:test` | 回退到 `base`、升级到 `head` 并重新播种测试库 |

所有命令只输出结构化结果，不回显数据库 URL 或凭据。可用 `DATABASE_URL` 或 CLI 的 `--database-url` 覆盖目标。

## 回滚与前向修复

- 本地测试库允许通过 `rebuild` 从头重建。
- 已有环境的迁移失败时，优先修复迁移并继续前向升级；不得手工修改 `alembic_version`。
- 单版本回滚仅用于已经验证 downgrade 的开发环境。含客户数据的环境在回滚前必须先备份并审查数据丢失范围。
- 种子版本不做隐式回滚；恢复旧数据集需要新增更高版本的修复清单。

## 自动验收

`services/api/tests/test_database_lifecycle.py` 覆盖空库升级、重复升级、重复播种、漂移检测、测试库重建和生产库保护。PostgreSQL 动态验收使用隔离 `verify` 数据库运行相同 CLI，并在结束后删除容器与卷。

当前开发结构头为 `0056_currency_and_source_time`，种子清单为 `1.30.0`。新增迁移必须从实际 `head` 继续，并在实施前用 `pnpm db:status` 和 Alembic heads 核对；不得修改已经执行过的历史迁移。
