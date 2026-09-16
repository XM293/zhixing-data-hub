import { describe, expect, it } from "vitest";

import { DEMO_EXPERIENCE } from "../demo/fixtures";
import { NAVIGATION, pageKeyForPath, projectNavigation, sectionForPath } from "./navigation";

describe("产品全景读取模型", () => {
  it("导航键、路由和页面键保持唯一", () => {
    const sectionKeys = NAVIGATION.map((section) => section.key);
    const routes = NAVIGATION.flatMap((section) => section.items.map((item) => item.href));
    const pageKeys = NAVIGATION.flatMap((section) => section.items.map((item) => item.key));

    expect(new Set(sectionKeys).size).toBe(sectionKeys.length);
    expect(new Set(routes).size).toBe(routes.length);
    expect(new Set(pageKeys).size).toBe(pageKeys.length);
    expect(pageKeyForPath("/console/data/foundation/sources")).toBe("data/foundation/sources");
    expect(sectionForPath("/console/actions/approvals").key).toBe("actions");
    expect(sectionForPath("/console/commerce/stores").key).toBe("commerce");
  });

  it("默认入口被裁剪时采用后端授权入口", () => {
    const projected = projectNavigation(
      ["home", "data"],
      [
        { key: "home", href: "/console" },
        { key: "data", href: "/console/data/products/commerce" }
      ]
    );

    expect(projected.find((section) => section.key === "data")?.href).toBe("/console/data/products/commerce");
  });

  it("菜单目标保持数据基础与数据产品的中心边界", () => {
    const routes = NAVIGATION.flatMap((section) => section.items.map((item) => item.href));
    expect(routes).not.toContain("/console/data/sources");
    expect(routes).not.toContain("/console/data/commerce");
    expect(routes).toContain("/console/data/foundation/sources");
    expect(routes).toContain("/console/data/products/commerce");
    expect(NAVIGATION.find((section) => section.key === "commerce")?.href).toBe("/console/commerce/stores");
  });

  it("拒绝本地路由目录之外的后端入口", () => {
    const projected = projectNavigation(
      ["data"],
      [{ key: "data", href: "https://untrusted.example/data" }]
    );

    expect(projected[0]?.href).toBe("/console/data/foundation/sources");
  });

  it("五类角色只引用已注册中心", () => {
    const sectionKeys = new Set(NAVIGATION.map((section) => section.key));

    expect(DEMO_EXPERIENCE.roles.map((role) => role.id)).toEqual([
      "ceo",
      "manager",
      "employee",
      "admin",
      "service"
    ]);
    for (const role of DEMO_EXPERIENCE.roles) {
      expect(role.allowedSections.every((section) => sectionKeys.has(section))).toBe(true);
      expect(DEMO_EXPERIENCE.dashboards[role.id]).toBeDefined();
    }
  });

  it("表格投影具有稳定键且属于已注册中心", () => {
    const sectionKeys = new Set(NAVIGATION.map((section) => section.key));

    for (const [key, page] of Object.entries(DEMO_EXPERIENCE.tablePages)) {
      expect(page.key).toBe(key);
      expect(sectionKeys.has(page.sectionKey)).toBe(true);
      expect(new Set(page.rows.map((row) => row.id)).size).toBe(page.rows.length);
    }
  });

  it("所有非详情导航都有读取模型或专用页面", () => {
    const specialPages = new Set([
      "home",
      "workspaces",
      "inbox",
      "cockpit",
      "commerce/stores",
      "assistant",
      "data/commerce",
      "data/reconciliation",
      "data/foundation/reconciliation",
      "data/products/commerce",
      "data/products/customers",
      "data/foundation/sources",
      "data/foundation/sync-jobs",
      "data/foundation/entities",
      "data/foundation/metrics",
      "data/foundation/quality",
      "data/customers",
      "knowledge/policies",
      "twins/memories",
      "twins/feedback",
      "twins/skills",
      "twins/evaluations",
      "analysis/ask",
      "analysis/store-review",
      "actions/work",
      "analysis/review-plans",
      "actions/approvals",
      "admin/ai-runtime",
      "admin/jobs",
      "admin/config",
      "admin/files",
      "admin/exchange",
      "admin/delegations"
    ]);

    for (const route of NAVIGATION.flatMap((section) => section.items.map((item) => item.href))) {
      const key = pageKeyForPath(route);
      expect(Boolean(DEMO_EXPERIENCE.tablePages[key]) || specialPages.has(key)).toBe(true);
    }
  });

  it("跨模块故事共享稳定对象引用和固定业务时间", () => {
    expect(DEMO_EXPERIENCE.schemaVersion).toBe(1);
    expect(DEMO_EXPERIENCE.dataMode).toBe("connector-sandbox");
    expect(DEMO_EXPERIENCE.businessTime).toBe("2026-08-25 09:30");
    expect(DEMO_EXPERIENCE.tablePages.meetings.rows[0].id).toBe(DEMO_EXPERIENCE.meeting.id);
    expect(DEMO_EXPERIENCE.tablePages["actions/proposals"].rows[0].id).toBe(DEMO_EXPERIENCE.action.id);
    expect(DEMO_EXPERIENCE.action.evidence).toContain(DEMO_EXPERIENCE.meeting.evidenceSnapshot);
    expect(DEMO_EXPERIENCE.tablePages["customer-service/conversations"].rows[0].id).toBe(
      DEMO_EXPERIENCE.conversation.id
    );
  });

  it("员工和客服视角不会获得平台管理入口", () => {
    const employee = DEMO_EXPERIENCE.roles.find((role) => role.id === "employee");
    const service = DEMO_EXPERIENCE.roles.find((role) => role.id === "service");

    expect(employee?.allowedSections).not.toContain("admin");
    expect(service?.allowedSections).not.toContain("admin");
    expect(service?.allowedSections).toContain("customer-service");
  });

  it("页面入口可以声明细粒度权限投影", () => {
    expect(NAVIGATION.find((section) => section.key === "data")?.items.find((item) => item.key === "sources")?.requiredPermission).toBe("source.manage");
    expect(NAVIGATION.find((section) => section.key === "admin")?.items.find((item) => item.key === "access")?.requiredPermission).toBe("identity.access.manage");
    expect(NAVIGATION.flatMap((section) => section.items).every((item) => item.requiredPermission || ["home", "inbox", "channels"].includes(item.key))).toBe(true);
  });
});
