import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  ROOT,
  infrastructureCommands,
  parseTaskIndex,
  validateTaskIndex,
  validateWorkspace
} from "../tools/workspace.mjs";
import {
  infrastructureVerificationPlan,
  redactVerificationPlan
} from "../tools/infra-verify.mjs";

test("任务索引拥有唯一 ID 和闭合依赖", () => {
  const text = readFileSync(resolve(ROOT, "tasks/task-index.yaml"), "utf8");
  const result = validateTaskIndex(text);
  assert.equal(result.failures.length, 0, result.failures.join("\n"));
  assert.ok(result.tasks.length >= 100);
  assert.equal(new Set(result.tasks.map((task) => task.id)).size, result.tasks.length);
});

test("任务索引解析关键 M0 依赖", () => {
  const text = readFileSync(resolve(ROOT, "tasks/task-index.yaml"), "utf8");
  const tasks = parseTaskIndex(text);
  const fnd003 = tasks.find((task) => task.id === "FND-003");
  const fnd004 = tasks.find((task) => task.id === "FND-004");
  assert.deepEqual(fnd003.dependencies, ["FND-002"]);
  assert.deepEqual(fnd004.dependencies, ["FND-001", "FND-002", "FND-003"]);
});

test("身份权限任务形成闭合的 M0 授权链路", () => {
  const text = readFileSync(resolve(ROOT, "tasks/task-index.yaml"), "utf8");
  const tasks = parseTaskIndex(text);
  const fnd007 = tasks.find((task) => task.id === "FND-007");
  const fnd010 = tasks.find((task) => task.id === "FND-010");
  const iam004 = tasks.find((task) => task.id === "IAM-004");
  assert.deepEqual(fnd007.dependencies, ["FND-006", "IAM-001"]);
  assert.deepEqual(fnd010.dependencies, ["FND-006", "FND-008"]);
  assert.deepEqual(iam004.dependencies, ["FND-010", "IAM-002", "IAM-003", "IAM-007"]);
});

test("产品全景原型形成领域实现前的人工验收门", () => {
  const text = readFileSync(resolve(ROOT, "tasks/task-index.yaml"), "utf8");
  const tasks = parseTaskIndex(text);
  const uia001 = tasks.find((task) => task.id === "UIA-001");
  const uia006 = tasks.find((task) => task.id === "UIA-006");
  const dom001 = tasks.find((task) => task.id === "DOM-001");
  assert.equal(uia001.status, "done");
  assert.deepEqual(uia001.dependencies, ["FND-001", "FND-004"]);
  assert.deepEqual(uia006.dependencies, ["UIA-005"]);
  assert.equal(dom001.status, "blocked");
  assert.deepEqual(dom001.dependencies, ["FND-001", "UIA-006"]);
});

test("工作区必需文件和架构决策完整", () => {
  const result = validateWorkspace();
  assert.equal(result.failures.length, 0, result.failures.join("\n"));
  assert.ok(result.taskCount >= 100);
});

test("产品界面规则禁止说明性文案和演示旁白", () => {
  const rootRules = readFileSync(resolve(ROOT, "AGENTS.md"), "utf8");
  const webRules = readFileSync(resolve(ROOT, "apps/web/AGENTS.md"), "utf8");
  assert.match(rootRules, /页面可见文字必须直接服务于业务数据/);
  assert.match(webRules, /禁止在页面中加入功能介绍/);

  const componentRoot = resolve(ROOT, "apps/web/src/components");
  const componentText = readdirSync(componentRoot, { recursive: true })
    .filter((path) => typeof path === "string" && /\.tsx?$/.test(path))
    .map((path) => readFileSync(resolve(componentRoot, path), "utf8"))
    .join("\n");
  for (const phrase of [
    "用于演示",
    "这里展示",
    "即将支持",
    "已预留",
    "接入前规划",
    "面向未知客户结构",
    "当前连接器提供",
    "功能介绍",
    "操作教学",
    "设计意图",
    "演示旁白",
    "菜单隐藏只是体验提示",
    "尚未进入产品全景"
  ]) {
    assert.doesNotMatch(componentText, new RegExp(phrase), `组件包含禁止文案：${phrase}`);
  }

  const sharedUi = readFileSync(
    resolve(ROOT, "apps/web/src/components/console/ui.tsx"),
    "utf8"
  );
  assert.doesNotMatch(sharedUi, /className="page-description"/);
  assert.match(sharedUi, /const visibleEyebrow = eyebrow && \/\[\\u3400-\\u9fff\]\//);
});

test("中心导航不回退到旧数据 Tab 或跨中心入口", () => {
  const navigation = readFileSync(
    resolve(ROOT, "apps/web/src/lib/navigation.ts"),
    "utf8"
  );
  const centerNavigation = readFileSync(
    resolve(ROOT, "apps/web/src/components/navigation/center-navigation.tsx"),
    "utf8"
  );
  assert.doesNotMatch(navigation, /\/console\/data\/(sources|sync-jobs|commerce|customers|entities|metrics|quality)(?:["/])/);
  assert.doesNotMatch(centerNavigation, /SectionTabs|section-tabs/);
  assert.match(navigation, /\/console\/data\/foundation\/sources/);
  assert.match(navigation, /\/console\/data\/products\/commerce/);
  assert.match(navigation, /\/console\/commerce\/stores/);
});

test("可观测性契约固定追踪 ID 和统一错误结构", () => {
  const errorSchema = JSON.parse(
    readFileSync(
      resolve(ROOT, "packages/contracts/observability/error-envelope.schema.json"),
      "utf8"
    )
  );
  const traceSchema = JSON.parse(
    readFileSync(
      resolve(ROOT, "packages/contracts/observability/trace-context.schema.json"),
      "utf8"
    )
  );
  assert.equal(errorSchema.properties.schema_version.const, 1);
  assert.deepEqual(errorSchema.required, ["schema_version", "error"]);
  assert.ok(errorSchema.properties.error.required.includes("request_id"));
  assert.ok(errorSchema.properties.error.required.includes("run_id"));
  assert.equal(traceSchema.properties.schema_version.const, 1);
  assert.equal(
    traceSchema.properties.request_id.pattern,
    traceSchema.properties.run_id.pattern
  );
});

test("工作区进程清单登记 Web、API、第三方测试沙箱与 Worker", () => {
  const config = JSON.parse(readFileSync(resolve(ROOT, "workspace.config.json"), "utf8"));
  assert.equal(config.schemaVersion, 1);
  assert.deepEqual(config.processes.map((item) => item.name), [
    "web",
    "api",
    "mock-commerce",
    "mock-memory",
    "mock-knowledge",
    "worker"
  ]);
  assert.equal(config.infrastructure.composeFile, "deploy/local/compose.yaml");
});

test("后台任务契约保留可信主体、授权范围、追踪与幂等边界", () => {
  const schema = JSON.parse(
    readFileSync(resolve(ROOT, "packages/contracts/jobs/job-record.schema.json"), "utf8")
  );
  assert.equal(schema.properties.schema_version.const, 2);
  for (const field of [
    "enterprise_id",
    "idempotency_key",
    "initiator_type",
    "initiator_id",
    "actor_snapshot",
    "permission_set_version",
    "required_permissions",
    "scope_type",
    "scope_id",
    "request_id",
    "run_id"
  ]) {
    assert.ok(schema.required.includes(field));
  }
});

test("MCP 会话契约固定工具白名单、范围、主体和权限版本", () => {
  const schema = JSON.parse(
    readFileSync(resolve(ROOT, "contracts/mcp/gateway-session.schema.json"), "utf8")
  );
  assert.equal(schema.properties.schema_version.const, 1);
  for (const field of [
    "session_id",
    "client_id",
    "principal_id",
    "allowed_tool_keys",
    "scope_constraints",
    "issued_permission_set_version",
    "status",
    "issued_at",
    "expires_at"
  ]) {
    assert.ok(schema.required.includes(field));
  }
  assert.equal(schema.properties.allowed_tool_keys.uniqueItems, true);
  assert.equal(schema.properties.scope_constraints.items.additionalProperties, false);
  assert.equal(schema.properties.session_token, undefined);
});

test("渠道身份契约只返回脱敏外部身份并固定绑定生命周期", () => {
  const schema = JSON.parse(
    readFileSync(resolve(ROOT, "contracts/identity/channel-identity.schema.json"), "utf8")
  );
  assert.equal(schema.properties.schema_version.const, 1);
  const item = schema.properties.items.items.properties;
  assert.equal(item.external_identity_fingerprint.pattern, "^[a-f0-9]{12}$");
  assert.deepEqual(item.binding_status.enum, ["unknown", "bound", "suspended"]);
  assert.equal(Object.hasOwn(item, "external_identity_key"), false);
});

test("统一审计契约固定来源、追踪、分页和受控属性", () => {
  const schema = JSON.parse(
    readFileSync(
      resolve(ROOT, "contracts/audit/unified-audit-ledger.schema.json"),
      "utf8"
    )
  );
  assert.equal(schema.properties.schema_version.const, 1);
  assert.deepEqual(schema.$defs.source.enum, [
    "authorization",
    "identity",
    "mcp",
    "tool",
    "worker",
    "agent",
    "action"
  ]);
  for (const field of [
    "actor_principal_id",
    "request_id",
    "run_id",
    "agent_run_id",
    "occurred_at",
    "attributes"
  ]) {
    assert.ok(schema.$defs.event.required.includes(field));
  }
  assert.equal(schema.$defs.event.additionalProperties, false);
  assert.equal(schema.$defs.attribute.additionalProperties, false);
  assert.equal(schema.$defs.pagination.properties.limit.maximum, 100);
});

test("人工纠错评测候选复用正式案例契约并保留来源链路", () => {
  const schema = JSON.parse(
    readFileSync(resolve(ROOT, "evals/schema/evaluation-candidate.schema.json"), "utf8")
  );
  assert.equal(schema.properties.schema_version.const, 1);
  assert.equal(schema.properties.input.$ref, "evaluation-case.schema.json#/$defs/input");
  assert.equal(
    schema.properties.expectations.$ref,
    "evaluation-case.schema.json#/$defs/expectations"
  );
  for (const field of [
    "source_handoff_case_id",
    "source_feedback_event_id",
    "source_agent_run_id",
    "resolution_summary",
    "status"
  ]) {
    assert.ok(schema.required.includes(field));
  }
});

test("经营分析与简报契约固定授权范围、证据和来源运行", () => {
  const runSchema = JSON.parse(
    readFileSync(
      resolve(ROOT, "contracts/analysis/business-analysis-run.schema.json"),
      "utf8"
    )
  );
  const briefSchema = JSON.parse(
    readFileSync(resolve(ROOT, "contracts/analysis/business-brief.schema.json"), "utf8")
  );
  assert.equal(runSchema.properties.schema_version.const, 1);
  assert.equal(runSchema.properties.scope.$ref, "#/$defs/scope");
  assert.ok(runSchema.required.includes("evidence_snapshot"));
  assert.ok(runSchema.required.includes("actor_context"));
  assert.ok(runSchema.required.includes("idempotency_key"));
  assert.equal(runSchema.$defs.metric.properties.evidence_ref.pattern, "^E[1-9][0-9]*$");
  assert.equal(briefSchema.properties.schema_version.const, 1);
  assert.equal(
    briefSchema.properties.scope.$ref,
    "business-analysis-run.schema.json#/$defs/scope"
  );
  assert.ok(briefSchema.required.includes("source_analysis_run_id"));
  assert.ok(briefSchema.required.includes("version_number"));
});

test("客服会话与回复草稿契约分离事实、证据和人工动作", () => {
  const conversationSchema = JSON.parse(
    readFileSync(
      resolve(ROOT, "contracts/customer-service/conversation.schema.json"),
      "utf8"
    )
  );
  const draftSchema = JSON.parse(
    readFileSync(
      resolve(ROOT, "contracts/customer-service/reply-draft.schema.json"),
      "utf8"
    )
  );
  const canonicalFactSchema = JSON.parse(
    readFileSync(
      resolve(ROOT, "contracts/customer-service/canonical-order-fact.schema.json"),
      "utf8"
    )
  );
  assert.equal(conversationSchema.properties.schema_version.const, 1);
  assert.ok(conversationSchema.required.includes("source_system_key"));
  assert.ok(conversationSchema.required.includes("first_response_due_at"));
  assert.equal(draftSchema.properties.schema_version.const, 1);
  assert.ok(draftSchema.required.includes("evidence_snapshot_id"));
  assert.ok(draftSchema.required.includes("agent_run_id"));
  assert.ok(draftSchema.required.includes("role_twin_version_id"));
  assert.ok(draftSchema.required.includes("safe_to_send"));
  assert.deepEqual(draftSchema.properties.status.enum, [
    "generated",
    "sandbox_sent",
    "rejected",
    "superseded"
  ]);
  assert.deepEqual(canonicalFactSchema.properties.match_status.enum, [
    "matched",
    "not_applicable",
    "missing",
    "scope_mismatch"
  ]);
  assert.ok(canonicalFactSchema.required.includes("scope_mapping_id"));
  assert.ok(canonicalFactSchema.required.includes("sync_run_ids"));
  assert.ok(canonicalFactSchema.required.includes("gross_margin_rate"));
});

test("本地基础设施固定版本并保留可选 Redis 和持久化卷", () => {
  const compose = readFileSync(resolve(ROOT, "deploy/local/compose.yaml"), "utf8");
  assert.match(compose, /postgres:16\.15-alpine/);
  assert.match(compose, /quay\.io\/minio\/minio:RELEASE\.2025-07-23T15-54-02Z/);
  assert.match(compose, /minio\/mc:RELEASE\.2025-08-13T08-35-41Z/);
  assert.match(compose, /mc mb --ignore-existing/);
  assert.match(compose, /profiles: \["redis"\]/);
  assert.match(compose, /redis:7\.4\.10-alpine/);
  assert.equal((compose.match(/@sha256:[a-f0-9]{64}/g) ?? []).length, 4);
  for (const volume of ["zhixing-postgres", "zhixing-minio", "zhixing-redis"]) {
    assert.match(compose, new RegExp(`${volume}:`));
  }
  assert.doesNotMatch(compose, /image:\s*[^\n]*:latest/);
});

test("基础设施命令先校验编排并安全区分启动与停止", () => {
  const composeFile = resolve(ROOT, "deploy/local/compose.yaml");
  const up = infrastructureCommands("up", composeFile);
  const down = infrastructureCommands("down", composeFile);
  assert.deepEqual(up[0][1].slice(-2), ["config", "--quiet"]);
  assert.ok(up[1][1].includes("--wait"));
  assert.deepEqual(up[2][1].slice(-3), ["run", "--rm", "minio-init"]);
  assert.deepEqual(down[1][1].slice(-1), ["down"]);
  assert.ok(!down[1][1].includes("-d"));
});

test("基础设施动态验收计划隔离端口并覆盖三类持久化", () => {
  const plan = infrastructureVerificationPlan();
  assert.deepEqual(plan.environment, {
    POSTGRES_PORT: "55432",
    POSTGRES_DB: "zhixing_verify",
    POSTGRES_USER: "zhixing_verify",
    POSTGRES_PASSWORD: "zhixing_verify_dev_only",
    MINIO_API_PORT: "59000",
    MINIO_CONSOLE_PORT: "59001",
    S3_ACCESS_KEY: "zhixingverify",
    S3_SECRET_KEY: "zhixing_verify_dev_only",
    S3_BUCKET: "zhixing-verify",
    REDIS_PORT: "56379"
  });
  const commandText = plan.commands.map((step) => step.args.join(" ")).join("\n");
  assert.match(commandText, /zhixing-fnd005-verify/);
  assert.match(commandText, /fnd005_persistence_probe/);
  assert.match(commandText, /fnd005-persistence-probe\.txt/);
  assert.match(commandText, /redis-cli.*fnd005-probe/);
  assert.equal(plan.commands.filter((step) => step.expect === "persistent").length, 3);
  assert.ok(plan.cleanup.args.includes("--volumes"));
  assert.ok(plan.cleanup.args.includes("--remove-orphans"));
});

test("基础设施动态验收公开计划不暴露测试口令", () => {
  const plan = infrastructureVerificationPlan();
  const publicPlan = redactVerificationPlan(plan);
  assert.equal(publicPlan.environment.POSTGRES_PASSWORD, "[redacted]");
  assert.equal(publicPlan.environment.S3_SECRET_KEY, "[redacted]");
  assert.equal(publicPlan.environment.POSTGRES_DB, "zhixing_verify");
  assert.equal(plan.environment.POSTGRES_PASSWORD, "zhixing_verify_dev_only");
});
