import { describe, expect, it } from "vitest";

import { detailSceneForSpace, meetingStatusLabel, resolveTwinFocus } from "./twin-experience";
import type { TwinScene } from "./twin-types";

describe("企业经营数字孪生状态投影", () => {
  it("只在用户跟随会议时聚焦会议空间", () => {
    expect(resolveTwinFocus("campus", "convening", true)).toBe("meeting");
    expect(resolveTwinFocus("warehouse", "convening", false)).toBe("warehouse");
    expect(resolveTwinFocus("warehouse", "decision_ready", false)).toBe("warehouse");
    expect(resolveTwinFocus("campus", "decision_ready", false)).toBe("campus");
  });

  it("向操作层提供明确的会议状态文案", () => {
    expect(meetingStatusLabel("scheduled")).toBe("待召集");
    expect(meetingStatusLabel("decision_ready")).toBe("决策包已形成");
  });

  it("根据空间入口解析数据库定义的子场景", () => {
    const scene = {
      key: "warehouse-interior",
      scene_level: "space",
      entry_space_key: "warehouse"
    } as TwinScene;

    expect(detailSceneForSpace([scene], "warehouse")?.key).toBe("warehouse-interior");
    expect(detailSceneForSpace([scene], "operations-center")).toBeUndefined();
  });
});
