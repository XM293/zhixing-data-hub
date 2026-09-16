# 后台任务包

`zhixing-jobs` 提供与业务类型无关的任务记录、幂等入队、PostgreSQL `FOR UPDATE SKIP LOCKED` 领取、重试、租约超时和 Worker 执行循环。

任务记录 v2 必须保存发起人快照、排队时权限版本、声明权限和目标范围。领取任务时生成只返回给当前 Worker 的一次性执行令牌，数据库仅保存 SHA-256 哈希；完成、失败或租约回收会使令牌失效。领域 Worker 仍须在执行写入或生成行动前通过 API 按当前权限重新授权，排队快照只用于复盘，不能延续已经撤销的权限。

生产结构只通过 `services/api/migrations` 创建。包内 ORM 元数据仅用于映射和单元测试，不得由运行时代码调用 `create_all`。
