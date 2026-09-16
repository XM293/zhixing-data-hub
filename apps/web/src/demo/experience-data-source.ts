import { DEMO_EXPERIENCE } from "@/demo/fixtures";
import type { ExperienceDataSource, ExperienceSnapshot } from "@/lib/experience-types";

function cloneSnapshot(): ExperienceSnapshot {
  return structuredClone(DEMO_EXPERIENCE);
}

export const demoExperienceDataSource: ExperienceDataSource = {
  readSnapshot: cloneSnapshot
};

