import { describe, expect, it } from "vitest";

import {
  buildAssetSeries,
  buildMetricDeltas,
  buildMetricTrendSeries,
  buildNodeGroups,
  buildNodeRing
} from "./cockpit-model";

describe("企业经营驾驶舱读取模型", () => {
  it("从持久化概览计算资产数量，不制造历史数据", () => {
    const assets = buildAssetSeries({
      source_record_count: 17,
      commerce_fact_count: 41,
      customer_profile_count: 12,
      customer_touchpoint_count: 64,
      entity_count: 3,
      metric_definition_count: 6,
      knowledge_document_count: 4,
      knowledge_version_count: 7,
      knowledge_chunk_count: 28,
      role_twin_profile_count: 2,
      agent_run_count: 9,
      customer_operation_run_count: 5,
      tool_definition_count: 3,
      tool_invocation_count: 14
    });

    expect(Object.fromEntries(assets.map((item) => [item.key, item.value]))).toMatchObject({
      records: 17,
      "commerce-facts": 41,
      "customer-assets": 76,
      entities: 3,
      metrics: 6,
      "knowledge-assets": 39,
      "twin-ai-runs": 16,
      "tool-activity": 17
    });
    expect(assets).toHaveLength(8);
    expect(assets.every((item) => Boolean(item.color))).toBe(true);
  });

  it("将退款率上升判定为不利变化", () => {
    const deltas = buildMetricDeltas([
      { key: "gmv_today", label: "成交", value: 100, unit: "元", change_rate: 0.08, as_of: "2026-08-27" },
      { key: "refund_rate", label: "退款率", value: 5, unit: "%", change_rate: 0.01, as_of: "2026-08-27" },
      { key: "stock", label: "库存", value: 20, unit: "件", change_rate: null, as_of: "2026-08-27" }
    ]);

    expect(deltas).toHaveLength(2);
    expect(deltas.find((item) => item.key === "gmv_today")?.favorable).toBe(true);
    expect(deltas.find((item) => item.key === "refund_rate")?.favorable).toBe(false);
  });

  it("按平台层级聚合节点并生成完整环图", () => {
    const groups = buildNodeGroups([
      { node_type: "source" },
      { node_type: "core" },
      { node_type: "knowledge" },
      { node_type: "agent" },
      { node_type: "action" }
    ] as never);

    expect(groups.map((item) => item.value)).toEqual([1, 2, 1, 1]);
    expect(buildNodeRing(groups)).toContain("360.0deg");
  });

  it("用数据库序列生成归一化趋势路径，不补造缺失日期", () => {
    const trends = buildMetricTrendSeries({
      schema_version: 1,
      data_mode: "database",
      scope_key: "enterprise",
      date_from: "2026-08-25T00:00:00Z",
      date_to: "2026-08-27T00:00:00Z",
      granularity: "day",
      generated_at: "2026-08-28T00:00:00Z",
      series: [
        {
          key: "gmv_today",
          label: "成交金额",
          unit: "元",
          scope_key: "enterprise",
          definition_version: "1.0.0",
          latest_value: 150,
          period_change_rate: 0.5,
          minimum: 100,
          maximum: 150,
          points: [
            { as_of: "2026-08-25T00:00:00Z", value: 100, change_rate: null },
            { as_of: "2026-08-27T00:00:00Z", value: 150, change_rate: 0.5 }
          ]
        },
        {
          key: "refund_rate",
          label: "退款率",
          unit: "%",
          scope_key: "enterprise",
          definition_version: "1.0.0",
          latest_value: 5.2,
          period_change_rate: 0.04,
          minimum: 5,
          maximum: 5.2,
          points: [
            { as_of: "2026-08-25T00:00:00Z", value: 5, change_rate: null },
            { as_of: "2026-08-27T00:00:00Z", value: 5.2, change_rate: 0.04 }
          ]
        }
      ]
    });

    expect(trends).toHaveLength(2);
    expect(trends[0].points).toHaveLength(2);
    expect(trends[0].path).toMatch(/^M0\.0,/);
    expect(trends[0].path).toContain("L720.0,");
    expect(trends.find((item) => item.key === "gmv_today")?.favorable).toBe(true);
    expect(trends.find((item) => item.key === "refund_rate")?.favorable).toBe(false);
  });
});
