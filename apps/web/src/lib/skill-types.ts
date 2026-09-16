export type SkillVersionStatus = "draft" | "published" | "retired";

export interface SkillVersion {
  id: string;
  version_number: number;
  status: SkillVersionStatus;
  instructions: string;
  tool_keys: string[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  change_summary: string;
  created_by: string | null;
  created_at: string;
  published_at: string | null;
}

export interface SkillDefinition {
  id: string;
  key: string;
  name: string;
  description: string;
  status: SkillVersionStatus;
  current_version_number: number | null;
  versions: SkillVersion[];
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface SkillStudioResponse {
  schema_version: 1;
  data_mode: "database";
  stats: {
    skill_count: number;
    published_skill_count: number;
    draft_version_count: number;
    published_version_count: number;
    registered_tool_count: number;
  };
  skills: SkillDefinition[];
  available_tools: string[];
  generated_at: string;
}

export interface SkillStudioMutationResponse {
  schema_version: 1;
  idempotent: boolean;
  event: {
    id: string;
    skill_key: string;
    version_number: number;
    event_type: "created" | "version-created" | "published";
    actor_name: string;
    reason: string;
    request_id: string;
    run_id: string;
    occurred_at: string;
  };
  studio: SkillStudioResponse;
}
