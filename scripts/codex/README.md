# Codex 非交互任务入口

默认只读分析一个仓库任务：

```powershell
pnpm codex:task -- --task FND-009
```

允许修改工作区时必须显式加入 `--write`。脚本只允许对 `ready` 或 `in_progress` 任务启用写模式；`blocked`、`review`、`done` 和 `deferred` 会直接失败。

```powershell
pnpm codex:task -- --task FND-009 --write
```

`--dry-run` 只输出任务、沙箱和 CLI 参数，不调用模型，供本地和 CI 验证：

```powershell
pnpm codex:task -- --task FND-009 --dry-run
```

每次调用都使用 `codex exec --ephemeral`，不保存会话 rollout；默认沙箱固定为 `read-only`，写模式固定为 `workspace-write`。脚本不会启用 `danger-full-access`，也不会绕过审批和沙箱。
