import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
export const ROOT = resolve(SCRIPT_DIR, "..");

const REQUIRED_PATHS = [
  "AGENTS.md",
  "README.md",
  "package.json",
  "pnpm-workspace.yaml",
  "pyproject.toml",
  "workspace.config.json",
  ".env.example",
  ".github/workflows/ci.yml",
  "apps/README.md",
  "apps/web/package.json",
  "services/README.md",
  "services/api/src/zhixing_api/main.py",
  "services/mock-commerce/src/mock_commerce/main.py",
  "services/mock-memory/src/mock_memory/main.py",
  "services/mock-knowledge/src/mock_knowledge/main.py",
  "services/worker/src/zhixing_worker/main.py",
  "services/worker/scripts/worker.py",
  "services/worker/scripts/verify.py",
  "deploy/local/compose.yaml",
  "packages/README.md",
  "packages/contracts/observability/error-envelope.schema.json",
  "packages/contracts/observability/trace-context.schema.json",
  "packages/observability/pyproject.toml",
  "packages/jobs/pyproject.toml",
  "packages/agent-runtime/pyproject.toml",
  "services/adapters/codex-runtime/pyproject.toml",
  "packages/contracts/jobs/job-record.schema.json",
  "scripts/codex/run-task.mjs",
  "scripts/codex/README.md",
  "tools/infra-verify.mjs",
  "docs/architecture/06-observability-and-error-contract.md",
  "docs/architecture/07-database-migrations-and-seeds.md",
  "docs/architecture/08-background-jobs-and-worker.md",
  "docs/architecture/12-role-template-and-twin-versioning.md",
  "docs/architecture/13-agent-feedback-and-human-handoff.md",
  "docs/architecture/14-enterprise-ai-evaluation-runner.md",
  "docs/architecture/15-business-analysis-and-briefs.md",
  "docs/architecture/16-ai-provider-operations.md",
  "docs/architecture/17-codex-agent-runtime.md",
  "docs/architecture/18-production-runtime-dependencies.md",
  "docs/architecture/adr/ADR-011-memory-provider-dual-run-adapters.md",
  "docs/architecture/adr/ADR-001-domain-boundaries.md",
  "docs/architecture/adr/ADR-002-initial-stack.md",
  "docs/architecture/adr/ADR-004-identity-access-and-application-shell.md",
  "docs/architecture/adr/ADR-005-panoramic-product-prototype-gate.md",
  "docs/architecture/adr/ADR-006-database-backed-twin-and-flexible-connectors.md",
  "docs/architecture/05-identity-access-and-authorization.md",
  "docs/product/02-product-experience-blueprint.md",
  "docs/development/04-panoramic-prototype-delivery.md",
  "docs/reports/m0-product-experience-review.md",
  "docs/reports/fnd-005-infrastructure-verification.md",
  "docs/reports/fnd-006-database-lifecycle-verification.md",
  "docs/reports/fnd-008-009-foundation-review.md",
  "docs/reports/fnd-010-worker-verification.md",
  "docs/reports/2026-08-31-ai-runtime-gap-review.md",
  "services/api/migrations/versions/0006_seed_registry.py",
  "services/api/migrations/versions/0007_background_jobs.py",
  "services/api/seeds/demo-operational-twin.v1.json",
  "services/api/scripts/database.py",
  "contracts/ui/README.md",
  "contracts/ui/experience-snapshot.schema.json",
  "contracts/ui/module-manifest.schema.json",
  "contracts/role/role-twin-test.schema.json",
  "services/api/migrations/versions/0020_role_twin_test_studio.py",
  "contracts/agent-runtime/agent-feedback.schema.json",
  "services/api/migrations/versions/0021_agent_feedback_and_handoff.py",
  "evals/schema/evaluation-case.schema.json",
  "evals/schema/evaluation-run.schema.json",
  "evals/schema/evaluation-candidate.schema.json",
  "contracts/analysis/business-analysis-run.schema.json",
  "contracts/analysis/business-brief.schema.json",
  "contracts/customer-service/conversation.schema.json",
  "contracts/customer-service/reply-draft.schema.json",
  "contracts/customer-service/canonical-order-fact.schema.json",
  "contracts/meeting/meeting-create.schema.json",
  "docs/product/customer-service-scope.md",
  "services/api/migrations/versions/0022_evaluation_runner.py",
  "services/api/migrations/versions/0023_feedback_evaluation_candidates.py",
  "services/api/migrations/versions/0024_business_analysis_and_briefs.py",
  "services/api/migrations/versions/0025_customer_service_copilot.py",
  "services/api/migrations/versions/0026_ai_provider_operations.py",
  "services/api/migrations/versions/0027_scoped_meeting_creation.py",
  "services/api/migrations/versions/0028_memory_provider_evaluations.py",
  "services/api/migrations/versions/0029_knowledge_provider_evaluations.py",
  "services/api/migrations/versions/0030_canonical_commerce_facts.py",
  "services/api/migrations/versions/0031_data_scope_mappings.py",
  "services/api/migrations/versions/0045_agent_runtime_control.py",
  "services/api/migrations/versions/0046_agent_runtime_sessions.py",
  "services/api/migrations/versions/0047_agent_runtime_multiturn.py",
  "services/api/scripts/migrate_sqlite_to_postgres.py",
  "services/api/scripts/runtime_verify.py",
  "contracts/data/commerce-fact-batch.schema.json",
  "docs/architecture/adr/ADR-012-knowledge-provider-dual-run-adapters.md",
  "docs/architecture/adr/ADR-013-canonical-commerce-fact-layer.md",
  "docs/architecture/adr/ADR-014-governed-scope-mapping-and-fact-tools.md",
  "docs/architecture/adr/ADR-015-customer-service-canonical-fact-projection.md",
  "tasks/EPIC-M0-identity-access.md",
  "tasks/EPIC-M0-product-experience.md",
  "tasks/task-index.yaml"
];

function read(relativePath) {
  return readFileSync(resolve(ROOT, relativePath), "utf8");
}

function parseVersion(versionText) {
  const match = versionText.trim().match(/v?(\d+)\.(\d+)\.(\d+)/);
  if (!match) {
    throw new Error(`无法解析版本：${versionText}`);
  }
  return match.slice(1).map(Number);
}

function runVersion(command, args = ["--version"]) {
  const result = spawnSync(command, args, {
    cwd: ROOT,
    encoding: "utf8",
    shell: process.platform === "win32"
  });
  if (result.status !== 0) {
    return { ok: false, output: (result.stderr || result.stdout || "未安装").trim() };
  }
  return { ok: true, output: (result.stdout || result.stderr).trim() };
}

export function parseTaskIndex(text) {
  const taskPattern = /^  - id:\s*([A-Z]+-\d+)\s*$/gm;
  const matches = [...text.matchAll(taskPattern)];
  const tasks = [];
  for (const [index, match] of matches.entries()) {
    const blockStart = match.index + match[0].length;
    const blockEnd = matches[index + 1]?.index ?? text.length;
    const block = text.slice(blockStart, blockEnd);
    const field = (name) => {
      const fieldMatch = block.match(new RegExp(`^    ${name}:\\s*(.+)$`, "m"));
      return fieldMatch?.[1]?.trim();
    };
    const dependencies = (field("depends_on") || "[]")
      .replace(/^\[|\]$/g, "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    tasks.push({
      id: match[1],
      milestone: field("milestone"),
      epic: field("epic"),
      title: field("title"),
      status: field("status"),
      dependencies
    });
  }
  return tasks;
}

export function validateTaskIndex(text) {
  const tasks = parseTaskIndex(text);
  const failures = [];
  const ids = new Set();
  const taskById = new Map();
  const allowedStatuses = new Set([
    "ready",
    "blocked",
    "in_progress",
    "review",
    "done",
    "deferred"
  ]);

  for (const task of tasks) {
    if (ids.has(task.id)) failures.push(`重复任务 ID：${task.id}`);
    ids.add(task.id);
    taskById.set(task.id, task);
    for (const name of ["milestone", "epic", "title", "status"]) {
      if (!task[name]) failures.push(`${task.id} 缺少 ${name}`);
    }
    if (!allowedStatuses.has(task.status)) {
      failures.push(`${task.id} 使用未知状态 ${task.status}`);
    }
  }
  for (const task of tasks) {
    for (const dependency of task.dependencies) {
      if (!ids.has(dependency)) failures.push(`${task.id} 依赖未知任务 ${dependency}`);
    }
    if (task.status === "ready") {
      const unfinished = task.dependencies.filter(
        (dependency) => taskById.get(dependency)?.status !== "done"
      );
      if (unfinished.length > 0) {
        failures.push(`${task.id} 标记为 ready 但依赖未完成：${unfinished.join(", ")}`);
      }
    }
  }

  const visited = new Set();
  const visiting = new Set();
  function visit(taskId, path) {
    if (visiting.has(taskId)) {
      failures.push(`任务依赖存在循环：${[...path, taskId].join(" -> ")}`);
      return;
    }
    if (visited.has(taskId)) return;
    visiting.add(taskId);
    const task = taskById.get(taskId);
    for (const dependency of task?.dependencies ?? []) {
      if (taskById.has(dependency)) visit(dependency, [...path, taskId]);
    }
    visiting.delete(taskId);
    visited.add(taskId);
  }
  for (const task of tasks) visit(task.id, []);

  if (tasks.length < 80) failures.push(`任务数量异常：${tasks.length}`);
  return { tasks, failures };
}

export function validateWorkspace() {
  const failures = [];
  const checks = [];

  for (const path of REQUIRED_PATHS) {
    if (existsSync(resolve(ROOT, path))) checks.push(`存在 ${path}`);
    else failures.push(`缺少 ${path}`);
  }

  const packageJson = JSON.parse(read("package.json"));
  if (!packageJson.private) failures.push("根 package.json 必须 private");
  if (packageJson.packageManager !== "pnpm@9.15.4") {
    failures.push("根 packageManager 必须锁定 pnpm@9.15.4");
  }
  for (const script of [
    "bootstrap",
    "doctor",
    "dev",
    "check",
    "test",
    "infra:up",
    "infra:verify",
    "db:upgrade",
    "db:status",
    "db:seed",
    "db:rebuild:test",
    "worker:once",
    "worker:run",
    "worker:verify",
    "codex:task"
  ]) {
    if (!packageJson.scripts?.[script]) failures.push(`缺少根命令 ${script}`);
  }

  const workspaceYaml = read("pnpm-workspace.yaml");
  for (const pattern of ["apps/*", "packages/*", "services/*", "mcp/*"]) {
    if (!workspaceYaml.includes(pattern)) failures.push(`pnpm workspace 缺少 ${pattern}`);
  }

  const taskResult = validateTaskIndex(read("tasks/task-index.yaml"));
  failures.push(...taskResult.failures);
  checks.push(`任务索引 ${taskResult.tasks.length} 项`);

  const boundaries = read("docs/architecture/adr/ADR-001-domain-boundaries.md");
  for (const term of [
    "企业数据中心",
    "企业知识中心",
    "角色分身中心",
    "数字会议中心",
    "智能分析中心",
    "行动与执行中心",
    "`memory`",
    "`agent-runtime`",
    "`action`"
  ]) {
    if (!boundaries.includes(term)) failures.push(`ADR-001 缺少 ${term}`);
  }

  const stack = read("docs/architecture/adr/ADR-002-initial-stack.md");
  for (const term of ["Next.js", "FastAPI", "PostgreSQL 16", "MinIO", "Temporal"]) {
    if (!stack.includes(term)) failures.push(`ADR-002 缺少 ${term}`);
  }

  const access = read("docs/architecture/adr/ADR-004-identity-access-and-application-shell.md");
  for (const term of [
    "`enterprise_id`",
    "`ActorContext`",
    "`AccessRole`",
    "`RoleTwin`",
    "数据范围",
    "菜单是授权结果的投影"
  ]) {
    if (!access.includes(term)) failures.push(`ADR-004 缺少 ${term}`);
  }

  const prototypeGate = read(
    "docs/architecture/adr/ADR-005-panoramic-product-prototype-gate.md"
  );
  for (const term of [
    "`UIA-001` 至 `UIA-006`",
    "UI Read Model",
    "模拟数据",
    "`UIA-006`",
    "`DOM-001`",
    "不变内容"
  ]) {
    if (!prototypeGate.includes(term)) failures.push(`ADR-005 缺少 ${term}`);
  }

  const dataTwin = read(
    "docs/architecture/adr/ADR-006-database-backed-twin-and-flexible-connectors.md"
  );
  for (const term of [
    "SourceRecord",
    "mapping_version",
    "services/mock-commerce",
    "PostgreSQL 16",
    "Three.js",
    "`UIA-006`"
  ]) {
    if (!dataTwin.includes(term)) failures.push(`ADR-006 缺少 ${term}`);
  }

  return { checks, failures, taskCount: taskResult.tasks.length };
}

export function doctor() {
  const required = [
    ["Node.js", process.version, true],
    ["pnpm", runVersion("pnpm").output, runVersion("pnpm").ok],
    ["uv", runVersion("uv").output, runVersion("uv").ok],
    ["Git", runVersion("git").output, runVersion("git").ok]
  ];
  const failures = [];

  const [nodeMajor] = parseVersion(process.version);
  if (nodeMajor < 22 || nodeMajor >= 25) {
    failures.push(`Node.js 需要 >=22 <25，当前 ${process.version}`);
  }

  for (const [name, version, ok] of required) {
    console.log(`${ok ? "✓" : "✗"} ${name}: ${version}`);
    if (!ok) failures.push(`缺少必需工具 ${name}`);
  }

  const python = runVersion("uv", ["python", "find", "3.11"]);
  console.log(`${python.ok ? "✓" : "✗"} Python 3.11: ${python.output}`);
  if (!python.ok) failures.push("uv 找不到 Python 3.11");

  const docker = runVersion("docker");
  console.log(`${docker.ok ? "✓" : "!"} Docker（FND-005 前可选）: ${docker.output}`);
  return failures;
}

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: ROOT,
    stdio: "inherit",
    shell: process.platform === "win32"
  });
  if (result.status !== 0) {
    throw new Error(`命令失败：${command} ${args.join(" ")}`);
  }
}

function bootstrap() {
  const failures = doctor();
  if (failures.length) throw new Error(failures.join("；"));
  run("pnpm", ["install", "--frozen-lockfile=false"]);
  run("uv", ["sync", "--all-packages", "--python", "3.11"]);
  check();
}

function check() {
  const result = validateWorkspace();
  for (const message of result.checks) console.log(`✓ ${message}`);
  if (result.failures.length) {
    for (const failure of result.failures) console.error(`✗ ${failure}`);
    throw new Error(`基础检查失败，共 ${result.failures.length} 项`);
  }
  console.log(`✓ 工作区基础检查通过，任务数 ${result.taskCount}`);
}

function loadWorkspaceConfig() {
  const config = JSON.parse(read("workspace.config.json"));
  if (config.schemaVersion !== 1 || !Array.isArray(config.processes)) {
    throw new Error("workspace.config.json 格式无效");
  }
  return config;
}

function dev() {
  const config = loadWorkspaceConfig();
  if (config.processes.length === 0) {
    console.log("当前尚无可运行应用；FND-004 将加入 Web、API 和 Worker 进程。");
    console.log("工作区与统一命令已经就绪，可先运行 pnpm check。");
    return;
  }
  const children = config.processes.map((processConfig) => {
    const [command, ...args] = processConfig.command;
    console.log(`启动 ${processConfig.name}: ${processConfig.command.join(" ")}`);
    return spawn(command, args, {
      cwd: resolve(ROOT, processConfig.cwd || "."),
      stdio: "inherit",
      shell: process.platform === "win32"
    });
  });
  const stop = () => children.forEach((child) => child.kill());
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
}

export function infrastructureCommands(action, composeFile) {
  const compose = ["compose", "-f", composeFile];
  const commands = [["docker", [...compose, "config", "--quiet"]]];
  if (action === "up") {
    commands.push([
      "docker",
      [...compose, "up", "-d", "--wait", "--wait-timeout", "120", "postgres", "minio"]
    ]);
    commands.push(["docker", [...compose, "run", "--rm", "minio-init"]]);
  } else {
    commands.push(["docker", [...compose, "down"]]);
  }
  return commands;
}

function infra(action) {
  const config = loadWorkspaceConfig();
  const composeFile = resolve(ROOT, config.infrastructure.composeFile);
  if (!existsSync(composeFile)) {
    throw new Error(`基础设施编排尚未实现：${config.infrastructure.composeFile}（任务 FND-005）`);
  }
  const docker = runVersion("docker");
  if (!docker.ok) throw new Error("未找到 Docker，无法启动本地基础设施");
  for (const [command, args] of infrastructureCommands(action, composeFile)) {
    run(command, args);
  }
}

async function main(argv) {
  const [command, subcommand] = argv;
  switch (command) {
    case "bootstrap":
      bootstrap();
      break;
    case "doctor": {
      const failures = doctor();
      if (failures.length) throw new Error(failures.join("；"));
      break;
    }
    case "check":
      check();
      break;
    case "dev":
      dev();
      break;
    case "infra":
      if (!["up", "down"].includes(subcommand)) {
        throw new Error("用法：workspace.mjs infra up|down");
      }
      infra(subcommand);
      break;
    default:
      throw new Error(`未知命令：${command || "<empty>"}`);
  }
}

const invokedDirectly = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  main(process.argv.slice(2)).catch((error) => {
    console.error(`错误：${error.message}`);
    process.exitCode = 1;
  });
}
