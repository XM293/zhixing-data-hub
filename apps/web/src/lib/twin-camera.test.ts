import { describe, expect, it } from "vitest";

import { resolveCameraPose } from "./twin-camera";
import type { TwinScene } from "./twin-types";

function scene(key: string, camera_preset: Record<string, unknown>): TwinScene {
  return {
    key,
    name: key,
    version: "1.0.0",
    status: "published",
    description: key,
    parent_scene_key: null,
    scene_level: key === "enterprise-campus" ? "campus" : "space",
    entry_space_key: null,
    asset_bundle_key: null,
    camera_preset,
    updated_at: "2026-08-27T00:00:00Z"
  };
}

describe("resolveCameraPose", () => {
  it("reads a structured camera pose from the active database scene", () => {
    const result = resolveCameraPose(
      [scene("enterprise-campus", {}), scene("warehouse-interior", {
        entry: { position: [13, 7.5, 14.5], look_at: [0, 1.4, 0] }
      })],
      "warehouse-interior",
      "warehouse"
    );

    expect(result.position).toEqual([13, 7.5, 14.5]);
    expect(result.lookAt).toEqual([0, 1.4, 0]);
  });

  it("keeps legacy position-only presets compatible", () => {
    const result = resolveCameraPose(
      [scene("enterprise-campus", { operations: [18, 9.5, 19] })],
      null,
      "operations"
    );

    expect(result.position).toEqual([18, 9.5, 19]);
    expect(result.lookAt).toEqual([-2, 2.8, -10]);
  });
});
