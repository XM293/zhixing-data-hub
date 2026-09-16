# 数据库种子

`demo-operational-twin.v1.json` 是当前开发与测试数据集的版本化清单。实际数据由 `zhixing_api.seed:seed_database` 以稳定业务键幂等写入，数据库中的 `seed_versions` 保存版本、内容校验和与最后应用时间。

规则：

- 修改种子内容时必须提升清单 `version`；同一版本出现不同校验和会被拒绝。
- 种子不负责创建表，执行前必须先完成 Alembic 升级。
- 生产数据、客户数据和凭据不得进入本目录。
- 测试库重建只允许数据库名称或 SQLite 文件名包含 `test` 或 `verify`。
