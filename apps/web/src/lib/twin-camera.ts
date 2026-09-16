import type { TwinScene, TwinSceneFocus } from "./twin-types";

type Vector3Tuple = [number, number, number];

export interface CameraPose {
  position: Vector3Tuple;
  lookAt: Vector3Tuple;
}

const FALLBACK_POSES: Record<TwinSceneFocus | "warehouse-interior" | "decision-room-interior", CameraPose> = {
  campus: { position: [56, 38, 62], lookAt: [0, 2, 0] },
  operations: { position: [25, 11.5, 18], lookAt: [-2, 2.8, -10] },
  warehouse: { position: [48, 11.5, 20], lookAt: [21, 2.1, -8] },
  meeting: { position: [42, 11.5, 34], lookAt: [18, 2.2, 12] },
  "warehouse-interior": { position: [13, 7.5, 14.5], lookAt: [0, 1.4, 0] },
  "decision-room-interior": { position: [11.8, 7.4, 13.2], lookAt: [0, 1.45, -0.7] }
};

function vector3(value: unknown): Vector3Tuple | null {
  if (!Array.isArray(value) || value.length !== 3 || value.some((item) => typeof item !== "number")) {
    return null;
  }
  return [value[0], value[1], value[2]];
}

export function resolveCameraPose(
  scenes: TwinScene[],
  detailSceneKey: string | null,
  focus: TwinSceneFocus
): CameraPose {
  const fallbackKey = detailSceneKey === "warehouse-interior" || detailSceneKey === "decision-room-interior"
    ? detailSceneKey
    : focus;
  const fallback = FALLBACK_POSES[fallbackKey];
  const scene = detailSceneKey
    ? scenes.find((item) => item.key === detailSceneKey)
    : scenes.find((item) => item.scene_level === "campus");
  const presetKey = detailSceneKey ? "entry" : focus === "campus" ? "overview" : focus;
  const preset = scene?.camera_preset[presetKey];
  const legacyPosition = vector3(preset);
  if (legacyPosition) return { position: legacyPosition, lookAt: fallback.lookAt };
  if (!preset || typeof preset !== "object" || Array.isArray(preset)) return fallback;

  const structured = preset as Record<string, unknown>;
  return {
    position: vector3(structured.position) ?? fallback.position,
    lookAt: vector3(structured.look_at) ?? fallback.lookAt
  };
}
