import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(SCRIPT_DIR, "..");
const COMPOSE_FILE = resolve(ROOT, "deploy/local/compose.yaml");
const PROJECT_NAME = "zhixing-fnd005-verify";
const PROBE_ID = "fnd005-probe";
const PROBE_VALUE = "persistent";
const PROBE_OBJECT = ".system/fnd005-persistence-probe.txt";
const VERIFY_DATABASE = "zhixing_verify";
const VERIFY_USER = "zhixing_verify";

function composeArgs(composeFile, ...args) {
  return ["compose", "-p", PROJECT_NAME, "-f", composeFile, ...args];
}

export function infrastructureVerificationPlan({ composeFile = COMPOSE_FILE } = {}) {
  const minioAlias = "mc alias set local http://minio:9000 \"$S3_ACCESS_KEY\" \"$S3_SECRET_KEY\"";
  return {
    environment: {
      POSTGRES_PORT: "55432",
      POSTGRES_DB: VERIFY_DATABASE,
      POSTGRES_USER: VERIFY_USER,
      POSTGRES_PASSWORD: "zhixing_verify_dev_only",
      MINIO_API_PORT: "59000",
      MINIO_CONSOLE_PORT: "59001",
      S3_ACCESS_KEY: "zhixingverify",
      S3_SECRET_KEY: "zhixing_verify_dev_only",
      S3_BUCKET: "zhixing-verify",
      REDIS_PORT: "56379"
    },
    commands: [
      { label: "校验 Compose", args: composeArgs(composeFile, "config", "--quiet") },
      {
        label: "启动 PostgreSQL 与 MinIO",
        args: composeArgs(composeFile, "up", "-d", "--wait", "--wait-timeout", "120", "postgres", "minio")
      },
      { label: "幂等创建对象存储桶", args: composeArgs(composeFile, "run", "--rm", "minio-init") },
      {
        label: "启动可选 Redis",
        args: composeArgs(composeFile, "--profile", "redis", "up", "-d", "--wait", "--wait-timeout", "120", "redis")
      },
      {
        label: "写入 PostgreSQL 持久化探针",
        args: composeArgs(
          composeFile,
          "exec", "-T", "postgres", "psql", "-U", VERIFY_USER, "-d", VERIFY_DATABASE, "-v", "ON_ERROR_STOP=1", "-c",
          `CREATE TABLE IF NOT EXISTS fnd005_persistence_probe (id text PRIMARY KEY, value text NOT NULL); INSERT INTO fnd005_persistence_probe (id, value) VALUES ('${PROBE_ID}', '${PROBE_VALUE}') ON CONFLICT (id) DO UPDATE SET value = EXCLUDED.value;`
        )
      },
      {
        label: "写入 MinIO 持久化探针",
        args: composeArgs(
          composeFile,
          "run", "--rm", "--entrypoint", "/bin/sh", "minio-init", "-c",
          `${minioAlias} >/dev/null && printf '${PROBE_VALUE}' | mc pipe \"local/$S3_BUCKET/${PROBE_OBJECT}\" >/dev/null`
        )
      },
      {
        label: "写入 Redis 持久化探针",
        args: composeArgs(composeFile, "--profile", "redis", "exec", "-T", "redis", "sh", "-c", `redis-cli SET '${PROBE_ID}' '${PROBE_VALUE}' >/dev/null && redis-cli SAVE >/dev/null`)
      },
      {
        label: "重启全部基础设施",
        args: composeArgs(composeFile, "--profile", "redis", "restart", "postgres", "minio", "redis")
      },
      {
        label: "等待重启后健康",
        args: composeArgs(composeFile, "--profile", "redis", "up", "-d", "--wait", "--wait-timeout", "120", "postgres", "minio", "redis")
      },
      {
        label: "读取 PostgreSQL 持久化探针",
        args: composeArgs(composeFile, "exec", "-T", "postgres", "psql", "-U", VERIFY_USER, "-d", VERIFY_DATABASE, "-Atc", `SELECT value FROM fnd005_persistence_probe WHERE id = '${PROBE_ID}';`),
        expect: PROBE_VALUE
      },
      {
        label: "读取 MinIO 持久化探针",
        args: composeArgs(composeFile, "run", "--rm", "--entrypoint", "/bin/sh", "minio-init", "-c", `${minioAlias} >/dev/null && mc cat \"local/$S3_BUCKET/${PROBE_OBJECT}\"`),
        expect: PROBE_VALUE
      },
      {
        label: "读取 Redis 持久化探针",
        args: composeArgs(composeFile, "--profile", "redis", "exec", "-T", "redis", "redis-cli", "--raw", "GET", PROBE_ID),
        expect: PROBE_VALUE
      }
    ],
    cleanup: {
      label: "清理隔离验收环境",
      args: composeArgs(composeFile, "--profile", "redis", "down", "--volumes", "--remove-orphans")
    }
  };
}

export function redactVerificationPlan(plan) {
  return {
    ...plan,
    environment: Object.fromEntries(
      Object.entries(plan.environment).map(([key, value]) => [
        key,
        /PASSWORD|SECRET/.test(key) ? "[redacted]" : value
      ])
    )
  };
}

function probe(command, args, options = {}) {
  return spawnSync(command, args, {
    cwd: ROOT,
    encoding: "utf8",
    windowsHide: true,
    ...options
  });
}

function resolveWslPath(distribution, windowsPath) {
  const result = probe(
    "wsl.exe",
    ["-d", distribution, "-u", "root", "--exec", "wslpath", "-a", windowsPath]
  );
  if (result.status !== 0 || !result.stdout.trim()) {
    throw new Error(`无法将路径映射到 WSL：${(result.stderr || result.stdout || "未知错误").trim()}`);
  }
  return result.stdout.trim();
}

function resolveDockerRuntime() {
  const native = probe("docker", ["info", "--format", "{{.ServerVersion}}"], {
    shell: process.platform === "win32"
  });
  if (native.status === 0) {
    return { command: "docker", prefix: [], composeFile: COMPOSE_FILE, label: "native" };
  }

  if (process.platform === "win32") {
    const distribution = process.env.ZHIXING_WSL_DISTRIBUTION?.trim() || "Ubuntu-24.04";
    const wsl = probe(
      "wsl.exe",
      ["-d", distribution, "-u", "root", "--exec", "docker", "info", "--format", "{{.ServerVersion}}"]
    );
    if (wsl.status === 0) {
      return {
        command: "wsl.exe",
        prefix: ["-d", distribution, "-u", "root", "--exec"],
        composeFile: resolveWslPath(distribution, COMPOSE_FILE),
        label: `wsl:${distribution}`
      };
    }
  }

  throw new Error("未找到可用的 Docker Engine；请启动原生 Docker，或在 WSL Ubuntu-24.04 中启动 Docker 服务");
}

function runDocker(step, environment, runtime, tolerateFailure = false) {
  console.log(`→ ${step.label}`);
  const commandArgs = runtime.command === "wsl.exe"
    ? [
        ...runtime.prefix,
        "env",
        ...Object.entries(environment).map(([key, value]) => `${key}=${value}`),
        "docker",
        ...step.args
      ]
    : step.args;
  const result = spawnSync(runtime.command, commandArgs, {
    cwd: ROOT,
    encoding: "utf8",
    env: { ...process.env, ...environment },
    shell: runtime.command === "docker" && process.platform === "win32",
    windowsHide: true
  });
  if (result.error && !tolerateFailure) throw result.error;
  if (result.status !== 0 && !tolerateFailure) {
    throw new Error(`${step.label}失败：${(result.stderr || result.stdout || "未知错误").trim()}`);
  }
  if (step.expect && result.stdout.trim() !== step.expect) {
    throw new Error(`${step.label}返回 ${JSON.stringify(result.stdout.trim())}，预期 ${JSON.stringify(step.expect)}`);
  }
}

function main(argv) {
  const dryRun = argv.includes("--dry-run");
  if (argv.some((argument) => !["--dry-run", "--help", "-h"].includes(argument))) {
    throw new Error("用法：node tools/infra-verify.mjs [--dry-run]");
  }
  if (argv.includes("--help") || argv.includes("-h")) {
    console.log("用法：node tools/infra-verify.mjs [--dry-run]");
    return;
  }

  if (dryRun) {
    console.log(JSON.stringify(redactVerificationPlan(infrastructureVerificationPlan())));
    return;
  }

  const runtime = resolveDockerRuntime();
  const plan = infrastructureVerificationPlan({ composeFile: runtime.composeFile });
  console.log(`容器运行时：${runtime.label}`);
  let touched = false;
  try {
    for (const step of plan.commands) {
      if (step.args.includes("up")) touched = true;
      runDocker(step, plan.environment, runtime);
    }
    console.log(JSON.stringify({
      status: "passed",
      project: PROJECT_NAME,
      services: ["postgres", "minio", "redis"],
      persistence_verified: true
    }));
  } finally {
    if (touched) runDocker(plan.cleanup, plan.environment, runtime, true);
  }
}

const invokedDirectly = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  try {
    main(process.argv.slice(2));
  } catch (error) {
    console.error(`错误：${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}
