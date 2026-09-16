# FND-005 本地基础设施验收记录

- 验收日期：2026-08-28
- 当前状态：静态、外部制品与容器动态持久化验收全部通过
- 任务状态：`done`

## 已验证

1. `deploy/local/compose.yaml` 可由 YAML 解析器读取，包含 PostgreSQL、MinIO、一次性建桶服务和可选 Redis profile。
2. 四个默认镜像同时固定版本标签与多架构 Manifest Digest，不使用 `latest`。
3. 公开 OCI Registry 在 2026-08-28 对四个 Manifest 均返回 HTTP 200：

| 组件 | 固定版本 | Manifest Digest |
| --- | --- | --- |
| PostgreSQL | `16.15-alpine` | `sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685` |
| MinIO | `RELEASE.2025-07-23T15-54-02Z` | `sha256:d249d1fb6966de4d8ad26c04754b545205ff15a62e4fd19ebd0f26fa5baacbc0` |
| MinIO Client | `RELEASE.2025-08-13T08-35-41Z` | `sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727` |
| Redis | `7.4.10-alpine` | `sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2` |

4. `tools/infra-verify.mjs --dry-run` 生成隔离验收计划：使用专用 Compose 项目名、数据库、用户、桶、端口与卷。
5. 验收计划会向 PostgreSQL、MinIO 和 Redis 分别写入探针，重启服务后读取探针，并在 `finally` 路径删除专用容器和卷。
6. 根级测试覆盖版本固定、持久化卷、Redis profile、`infra:up`/`infra:down` 参数和动态验收命令计划。
7. 从 Docker 官方 GitHub Release 下载独立 Compose 5.4.0 Linux x86_64 二进制，SHA-256 与官方值 `837fd1d35bf6a494f41b5b5988269a7be79de337cf1a1a6ff0e45ab51bb4e9be` 一致；默认配置和启用 Redis profile 的配置均通过真实 `config --quiet` 解析。临时二进制已删除，未安装到系统目录。
8. 在 WSL Ubuntu 24.04 安装 Docker Engine 29.1.3 与 Compose 2.40.3；Windows 仓库入口在没有原生 Docker 时会自动选用该 WSL 引擎。
9. `pnpm infra:verify` 连续执行两次均返回 `persistence_verified: true`：PostgreSQL、MinIO 与 Redis 的探针在服务重启后全部可读取。
10. 两次执行完成后均未残留 `zhixing-fnd005-verify` 容器或命名卷；失败路径也通过 `finally` 清理。
11. `pnpm infra:verify -- --dry-run` 对测试口令字段脱敏，不在控制台输出密码或 Secret Key。

## 动态验收命令

在仓库根目录运行：

```powershell
pnpm infra:verify
```

Windows 会优先使用原生 Docker；原生引擎不可用时自动尝试 `Ubuntu-24.04` 中的 Docker。可通过 `ZHIXING_WSL_DISTRIBUTION` 覆盖发行版名称。该命令使用独立项目名、端口与命名卷，不接触开发数据。

## 上游依据

- PostgreSQL 官方镜像：https://hub.docker.com/_/postgres
- MinIO 官方发行记录：https://github.com/minio/minio/releases/tag/RELEASE.2025-07-23T15-54-02Z
- MinIO Client 镜像：https://hub.docker.com/r/minio/mc/tags
- Redis 官方镜像：https://hub.docker.com/_/redis
- nerdctl rootless 前置条件：https://github.com/containerd/nerdctl/blob/main/docs/rootless.md
- Docker Compose 官方发行：https://github.com/docker/compose/releases/tag/v5.4.0
