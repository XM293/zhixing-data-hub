import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { ROOT, parseTaskIndex } from "../../tools/workspace.mjs";

const USAGE = "用法：pnpm codex:task -- --task <TASK_ID> [--write] [--dry-run]";

export function parseArguments(argv) {
  const options = { taskId: null, write: false, dryRun: false };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--task") {
      options.taskId = argv[index + 1] ?? null;
      index += 1;
    } else if (argument === "--write") {
      options.write = true;
    } else if (argument === "--dry-run") {
      options.dryRun = true;
    } else if (argument === "--help" || argument === "-h") {
      return { ...options, help: true };
    } else {
      throw new Error(`未知参数：${argument}`);
    }
  }
  return options;
}

export function prepareRun(
  options,
  indexText = readFileSync(resolve(ROOT, "tasks/task-index.yaml"), "utf8")
) {
  if (!options.taskId || !/^[A-Z]+-\d+$/.test(options.taskId)) {
    throw new Error(`必须提供合法任务 ID。${USAGE}`);
  }

  const task = parseTaskIndex(indexText).find((item) => item.id === options.taskId);
  if (!task) throw new Error(`任务不存在：${options.taskId}`);
  if (options.write && !["ready", "in_progress"].includes(task.status)) {
    throw new Error(`任务 ${task.id} 当前为 ${task.status}，写模式只允许 ready 或 in_progress`);
  }

  const sandbox = options.write ? "workspace-write" : "read-only";
  const prompt = [
    `执行任务 ${task.id}：${task.title}。`,
    "先完整阅读 AGENTS.md、README.md、tasks/README.md、tasks/task-index.yaml 和所属 EPIC 文档。",
    `当前任务状态为 ${task.status}，依赖为 ${task.dependencies.join(", ") || "无"}。`,
    options.write
      ? "在任务边界内完成实现、测试、文档更新和自审；不得绕过任务状态或人工验收门。"
      : "本次为只读分析：不得修改文件、任务状态、外部系统或远程资源，只报告发现、验证结果和建议。",
    "不得读取或输出仓库外密钥，不得修改 references/open-source 中的参考仓库。"
  ].join("\n");
  const args = ["exec", "--ephemeral", "--sandbox", sandbox, "--cd", ROOT, "-"];
  return { task, sandbox, prompt, args };
}

function main(argv) {
  const options = parseArguments(argv);
  if (options.help) {
    console.log(USAGE);
    return;
  }

  const prepared = prepareRun(options);
  if (options.dryRun) {
    console.log(JSON.stringify({
      task_id: prepared.task.id,
      task_status: prepared.task.status,
      sandbox: prepared.sandbox,
      ephemeral: prepared.args.includes("--ephemeral"),
      command: "codex",
      args: prepared.args
    }));
    return;
  }

  const result = spawnSync("codex", prepared.args, {
    cwd: ROOT,
    input: prepared.prompt,
    stdio: ["pipe", "inherit", "inherit"],
    shell: process.platform === "win32",
    windowsHide: true
  });
  if (result.error) throw result.error;
  if (result.signal) throw new Error(`Codex 被信号 ${result.signal} 终止`);
  if (result.status !== 0) process.exitCode = result.status ?? 1;
}

const invokedDirectly = process.argv[1] && resolve(process.argv[1]) === resolve(import.meta.filename);
if (invokedDirectly) {
  try {
    main(process.argv.slice(2));
  } catch (error) {
    console.error(`错误：${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}
