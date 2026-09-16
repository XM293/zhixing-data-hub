export type RoleVersionStatus = "draft" | "published" | "retired";

export interface RoleTemplateVersion {
  id: string;
  version_number: number;
  status: RoleVersionStatus;
  role_title: string;
  responsibilities: string[];
  capability_boundaries: string[];
  default_voice_guide: string;
  default_reasoning_guide: string;
  default_answer_policy: string;
  change_summary: string;
  created_by: string | null;
  created_at: string;
  published_at: string | null;
}

export interface RoleTemplate {
  id: string;
  key: string;
  name: string;
  description: string;
  status: RoleVersionStatus;
  current_version_number: number | null;
  twin_count: number;
  versions: RoleTemplateVersion[];
  created_at: string;
  updated_at: string;
}

export interface RoleTwinVersion {
  id: string;
  version_number: number;
  template_version_number: number;
  status: RoleVersionStatus;
  display_name: string;
  voice_guide: string;
  reasoning_guide: string;
  answer_policy: string;
  provider: string;
  model: string;
  capabilities: string[];
  change_summary: string;
  created_by: string | null;
  created_at: string;
  published_at: string | null;
}

export interface RoleTwinInstance {
  id: string;
  key: string;
  template_key: string;
  template_name: string;
  owner_principal_key: string | null;
  owner_name: string | null;
  role_title: string;
  status: RoleVersionStatus;
  current_version_number: number | null;
  run_count: number;
  versions: RoleTwinVersion[];
  published_at: string | null;
  updated_at: string;
}

export interface RoleOwnerOption {
  key: string;
  display_name: string;
  status: string;
}

export interface RoleStudioResponse {
  schema_version: 1;
  data_mode: "database";
  stats: {
    template_count: number;
    instance_count: number;
    published_template_count: number;
    published_instance_count: number;
    draft_version_count: number;
    run_count: number;
  };
  owners: RoleOwnerOption[];
  templates: RoleTemplate[];
  twins: RoleTwinInstance[];
  generated_at: string;
}

export interface RoleStudioMutationResponse {
  schema_version: 1;
  idempotent: boolean;
  event: {
    id: string;
    configuration_type: "template" | "twin";
    configuration_key: string;
    version_id: string;
    version_number: number;
    event_type: "created" | "version-created" | "published";
    actor_name: string;
    reason: string;
    request_id: string;
    run_id: string;
    occurred_at: string;
  };
  studio: RoleStudioResponse;
}
