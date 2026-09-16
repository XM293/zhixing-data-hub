import { describe, expect, it } from "vitest";

import {
  auditOutcomeLabel,
  auditPaginationLabel,
  auditRangeStart,
  auditStatusValue,
  buildAuditSearchParams,
  EMPTY_AUDIT_FILTERS,
  type AuditFilters
} from "./audit-query";

describe("统一审计查询契约", () => {
  it("只提交已生效筛选并固定分页和时间窗口", () => {
    const now = Date.parse("2026-08-30T08:00:00.000Z");
    const filters: AuditFilters = {
      source: "tool",
      outcome: "failed",
      actor: "principal-admin-zhou",
      requestId: "req_audit_001",
      runId: "run_audit_001",
      query: "query_customer_360",
      timeRange: "7d"
    };

    const parameters = buildAuditSearchParams(filters, 50, 50, now);

    expect(Object.fromEntries(parameters)).toEqual({
      offset: "50",
      limit: "50",
      source: "tool",
      outcome: "failed",
      actor_principal_id: "principal-admin-zhou",
      request_id: "req_audit_001",
      run_id: "run_audit_001",
      query: "query_customer_360",
      start_at: "2026-08-23T08:00:00.000Z"
    });
  });

  it("全部时间和空筛选不会产生空查询字段", () => {
    const parameters = buildAuditSearchParams(
      { ...EMPTY_AUDIT_FILTERS, timeRange: "all" },
      0,
      100,
      0
    );

    expect(Object.fromEntries(parameters)).toEqual({ offset: "0", limit: "100" });
    expect(auditRangeStart("all", 0)).toBeNull();
  });

  it("统一映射成功、告警、失败和未知结果", () => {
    expect(auditStatusValue("completed", "normal")).toEqual({
      label: "完成",
      tone: "positive"
    });
    expect(auditStatusValue("revoked", "warning")).toEqual({
      label: "已撤销",
      tone: "warning"
    });
    expect(auditStatusValue("failed", "critical")).toEqual({
      label: "失败",
      tone: "critical"
    });
    expect(auditOutcomeLabel("custom_outcome")).toBe("custom_outcome");
  });

  it("分页标签不会在空结果时显示反向区间", () => {
    expect(auditPaginationLabel(0, 0, 0)).toBe("0 / 0");
    expect(auditPaginationLabel(0, 50, 1219)).toBe("1-50 / 1219");
    expect(auditPaginationLabel(1200, 19, 1219)).toBe("1201-1219 / 1219");
  });
});
