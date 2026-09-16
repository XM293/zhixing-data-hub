import type { TwinMeeting, TwinScene, TwinSceneFocus } from "./twin-types";

export function detailSceneForSpace(scenes: TwinScene[], spaceKey: string): TwinScene | undefined {
  return scenes.find((scene) => scene.entry_space_key === spaceKey && scene.scene_level === "space");
}

export function resolveTwinFocus(
  selectedFocus: TwinSceneFocus,
  status: TwinMeeting["status"],
  followMeeting: boolean
): TwinSceneFocus {
  if (followMeeting && (status === "convening" || status === "in_session" || status === "decision_ready")) {
    return "meeting";
  }
  return selectedFocus;
}

export function meetingStatusLabel(status: TwinMeeting["status"]): string {
  const labels: Record<TwinMeeting["status"], string> = {
    scheduled: "待召集",
    convening: "分身到场中",
    in_session: "研判进行中",
    decision_ready: "决策包已形成"
  };
  return labels[status];
}
