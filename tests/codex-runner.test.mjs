import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

import { prepareRun } from "../scripts/codex/run-task.mjs";
import { ROOT } from "../tools/workspace.mjs";

const RUNNER = resolve(ROOT, "scripts/codex/run-task.mjs");

function dryRun(...args) {
  return spawnSync(process.execPath, [RUNNER, ...args, "--dry-run"], {
    cwd: ROOT,
    encoding: "utf8"
  });
}

test("Codex 任务入口默认只读且不持久化会话", () => {
  const result = dryRun("--task", "FND-009");
  assert.equal(result.status, 0, result.stderr);
  const payload = JSON.parse(result.stdout);
  assert.equal(payload.sandbox, "read-only");
  assert.equal(payload.ephemeral, true);
  assert.ok(payload.args.includes("--ephemeral"));
  assert.deepEqual(payload.args.slice(2, 4), ["--sandbox", "read-only"]);
});

test("Codex 写模式必须显式开启并限制任务状态", () => {
  const syntheticIndex = `
tasks:
  - id: TST-001
    title: 可执行测试任务
    status: ready
    depends_on: []
`;
  const allowed = prepareRun(
    { taskId: "TST-001", write: true, dryRun: true },
    syntheticIndex
  );
  assert.equal(allowed.sandbox, "workspace-write");

  const denied = dryRun("--task", "UIA-006", "--write");
  assert.notEqual(denied.status, 0);
  assert.match(denied.stderr, /写模式只允许 ready 或 in_progress/);
});

test("CI 只授予仓库读取权限并执行全量质量门", () => {
  const workflow = readFileSync(resolve(ROOT, ".github/workflows/ci.yml"), "utf8");
  assert.match(workflow, /permissions:\s*\n  contents: read/);
  assert.match(workflow, /pnpm install --frozen-lockfile/);
  assert.match(workflow, /uv sync --all-packages --frozen/);
  assert.match(workflow, /run: pnpm check/);
  assert.match(workflow, /run: pnpm build/);
  assert.match(workflow, /run: node tools\/infra-verify\.mjs/);
  assert.doesNotMatch(workflow, /codex exec|danger-full-access|OPENAI_API_KEY/);
});
