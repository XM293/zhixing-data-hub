import { describe, expect, it } from "vitest";

import {
  PRODUCT_CENTERS,
  type PlatformModule,
  validatePlatformModules
} from "./platform-modules";

describe("平台模块契约", () => {
  it("固定七个客户可见导航", () => {
    expect(PRODUCT_CENTERS).toEqual([
      "企业数据中心",
      "企业知识中心",
      "角色分身中心",
      "数字会议中心",
      "智能分析中心",
      "行动与执行中心",
      "平台管理"
    ]);
  });

  it("识别重复模块和缺失导航", () => {
    const modules: PlatformModule[] = [
      {
        key: "metric",
        label: "指标",
        navigation: "企业数据中心",
        owner: "metric",
        summary: "指标口径",
        milestone: "M2",
        availability: "planned"
      },
      {
        key: "metric",
        label: "指标副本",
        navigation: "企业数据中心",
        owner: "metric",
        summary: "不应出现",
        milestone: "M2",
        availability: "planned"
      }
    ];

    const failures = validatePlatformModules(modules);
    expect(failures).toContain("重复模块键：metric");
    expect(failures).toContain("缺少产品导航：企业知识中心");
  });
});
