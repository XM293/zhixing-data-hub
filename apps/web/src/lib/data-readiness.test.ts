import { describe, expect, it } from "vitest";

import { buildDataReadinessSeries } from "./data-readiness";

describe("首期数据接入验收基线", () => {
  it("使用统一口径计算当前覆盖率", () => {
    const series = buildDataReadinessSeries({
      sources: [{ key: "mock-commerce" }] as never,
      source_record_count: 485,
      entity_count: 461,
      metric_definition_count: 6
    });

    expect(Object.fromEntries(series.map((item) => [item.key, item.coverageLabel]))).toEqual({
      sources: "25%",
      records: "0.5%",
      entities: "2.3%",
      metrics: "20%"
    });
  });
});
