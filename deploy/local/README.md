# 本地基础设施

`compose.yaml` 默认提供 PostgreSQL 16 与 MinIO，并在启动时幂等创建 `S3_BUCKET`。Redis 位于可选 `redis` profile，不是 M0 默认依赖。默认镜像同时固定版本标签和多架构 Manifest Digest；端口、镜像、开发账号和桶名仍可通过环境变量覆盖。

本地开发支持原生 Docker，也支持 Windows 上的 WSL Docker。`infra:verify` 会优先使用原生 Docker；原生引擎不可用时，会自动尝试 `Ubuntu-24.04` 中的 Docker。发行版名称不同时可设置 `ZHIXING_WSL_DISTRIBUTION`。执行：

```powershell
pnpm infra:up
$env:DATABASE_URL = "postgresql+psycopg://zhixing:zhixing_dev_only@127.0.0.1:5432/zhixing"
pnpm dev
```

`pnpm infra:up` 会先执行 `docker compose config --quiet`，等待 PostgreSQL 与 MinIO 健康，再运行一次性 `minio-init` 建桶。重复运行不会清空数据，也不会因桶已存在而失败。

完整自动验收使用隔离项目名、独立端口和专用卷，不接触日常开发数据。它会分别向 PostgreSQL、MinIO 和 Redis 写入探针，重启全部服务，确认探针仍可读取，最后无论成功失败都删除验收容器和专用卷：

```powershell
pnpm infra:verify
pnpm infra:verify -- --dry-run
```

`--dry-run` 输出会对测试口令字段脱敏。2026-08-28 已在 WSL Ubuntu 24.04、Docker 29.1.3 和 Compose 2.40.3 上连续完成两次全量持久化验收。

同一命令也在 CI 的独立 `infrastructure` 作业执行。

需要验证可选 Redis 时：

```powershell
docker compose -f deploy/local/compose.yaml --profile redis up -d --wait redis
```

停止服务使用 `pnpm infra:down`，命名卷仍保留。删除卷会永久移除本地基础设施数据，因此不包含在统一命令中；确需重建时应先确认目标项目名和卷，再人工执行 `docker compose -f deploy/local/compose.yaml down --volumes`。

不启动 Compose 时，产品 API 自动使用 `services/api/var/zhixing.db`，并运行同一套 Alembic 迁移。
