import type { AuditSeverity, AuditSource } from "@/lib/audit-types";

export type AuditTimeRange = "24h" | "7d" | "30d" | "all";

export interface AuditFilters {
  source: AuditSource | "";
  outcome: string;
  actor: string;
  requestId: string;
  runId: string;
  query: string;
  timeRange: AuditTimeRange;
}

export const EMPTY_AUDIT_FILTERS: AuditFilters = {
  source: "",
  outcome: "",
  actor: "",
  requestId: "",
  runId: "",
  query: "",
  timeRange: "7d"
};

const OUTCOME_LABELS: Record<string, string> = {
  allow: "允许",
  deny: "拒绝",
  succeeded: "成功",
  completed: "完成",
  failed: "失败",
  denied: "拒绝",
  blocked: "阻塞",
  degraded: "降级",
  pending: "等待",
  queued: "排队",
  running: "运行中",
  issued: "已签发",
  revoked: "已撤销",
  expired: "已过期",
  ready: "待领取",
  claimed: "已领取",
  in_progress: "执行中",
  cancelled: "已取消"
};

export function buildAuditSearchParams(
  filters: AuditFilters,
  offset: number,
  limit: number,
  nowMs = Date.now()
): URLSearchParams {
  const parameters = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (filters.source) parameters.set("source", filters.source);
  if (filters.outcome) parameters.set("outcome", filters.outcome);
  if (filters.actor) parameters.set("actor_principal_id", filters.actor);
  if (filters.requestId) parameters.set("request_id", filters.requestId);
  if (filters.runId) parameters.set("run_id", filters.runId);
  if (filters.query) parameters.set("query", filters.query);
  const startAt = auditRangeStart(filters.timeRange, nowMs);
  if (startAt) parameters.set("start_at", startAt);
  return parameters;
}

export function auditOutcomeLabel(value: string): string {
  return OUTCOME_LABELS[value] ?? value;
}

export function auditStatusValue(
  outcome: string,
  severity: AuditSeverity
): { label: string; tone: "positive" | "warning" | "critical" | "neutral" } {
  return {
    label: auditOutcomeLabel(outcome),
    tone: severity === "critical"
      ? "critical"
      : severity === "warning"
        ? "warning"
        : ["allow", "succeeded", "completed"].includes(outcome)
          ? "positive"
          : "neutral"
  };
}

export function auditRangeStart(value: AuditTimeRange, nowMs = Date.now()): string | null {
  if (value === "all") return null;
  const hours = value === "24h" ? 24 : value === "7d" ? 24 * 7 : 24 * 30;
  return new Date(nowMs - hours * 60 * 60 * 1000).toISOString();
}

export function auditPaginationLabel(offset: number, itemCount: number, total: number): string {
  if (total === 0) return "0 / 0";
  return `${offset + 1}-${Math.min(offset + itemCount, total)} / ${total}`;
}
