# FND-006 数据库生命周期验收记录

- 验收日期：2026-08-28
- 任务状态：`done`
- 最新 revision：`0006_seed_registry`

## 自动化验收

`services/api/tests/test_database_lifecycle.py` 已验证：

1. 全新 SQLite 数据库从 `base` 升级到 `head`。
2. 连续运行升级与种子不会重复创建实体、场景、席位或种子登记。
3. 同一清单版本对应不同内容校验和时抛出 `SeedDriftError`。
4. 测试库可以完整降级到 `base`、重新升级并播种。
5. 名称不含 `test` 或 `verify` 的数据库被重建保护拒绝。

## PostgreSQL 动态验收

在隔离 Compose 项目 `zhixing-fnd006-verify` 中启动 PostgreSQL 16.15，并对数据库 `zhixing_fnd006_verify` 执行同一 CLI：

```text
status(base) -> upgrade -> seed -> seed -> rebuild -> status(0006_seed_registry)
```

全部步骤成功。首次 PostgreSQL 运行发现 Alembic 默认 `version_num varchar(32)` 无法保存现有 0005 revision；迁移已在写入长 revision 前将严格数据库的列扩展到 128 字符。SQLite 不强制字符串长度，因此原测试未暴露该问题。

验收结束后已确认并删除隔离容器、网络和命名卷。临时 Python 虚拟环境只创建在 WSL `/tmp/zhixing-fnd006.*`，通过路径保护的退出钩子删除。

## 结论

FND-006 的三项验收标准均满足：空库升级成功、重复运行安全、测试库可重建。迁移与种子命令不输出数据库 URL 或凭据，种子版本和内容校验和可追溯。
