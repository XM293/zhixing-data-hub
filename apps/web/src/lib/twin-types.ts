export interface EnterpriseTwinOverview {
  schema_version: 9;
  data_mode: "database";
  enterprise: {
    id: string;
    code: string;
    name: string;
    timezone: string;
  };
  database: {
    engine: string;
    persistent: boolean;
    schema_revision: string;
  };
  sources: Array<{
    key: string;
    name: string;
    system_type: string;
    status: string;
    connection_status?: string | null;
    source_schema_version: string;
    mapping_version: string;
    last_sync_at: string | null;
    source_record_count: number;
    sync_run_count: number;
  }>;
  metrics: Array<{
    key: string;
    label: string;
    value: number;
    unit: string;
    change_rate: number | null;
    as_of: string;
  }>;
  nodes: TwinNode[];
  edges: TwinEdge[];
  events: Array<{
    id: string;
    event_type: string;
    severity: string;
    title: string;
    detail: string;
    occurred_at: string;
  }>;
  scene: TwinScene | null;
  scenes: TwinScene[];
  spaces: TwinSpace[];
  actors: TwinActor[];
  routes: TwinRoute[];
  hotspots: TwinHotspot[];
  data_layers: TwinDataLayer[];
  interactions: TwinInteraction[];
  meeting: TwinMeeting | null;
  latest_sync: {
    source_key?: string | null;
    id: string;
    status: string;
    scenario: string;
    volume_profile: string;
    records_read: number;
    records_written: number;
    warning: string | null;
    error: string | null;
    started_at: string;
    finished_at: string | null;
  } | null;
  entity_count: number;
  source_record_count: number;
  commerce_fact_count: number;
  customer_profile_count: number;
  customer_touchpoint_count: number;
  metric_definition_count: number;
  knowledge_document_count: number;
  knowledge_version_count: number;
  knowledge_chunk_count: number;
  role_twin_profile_count: number;
  agent_run_count: number;
  customer_operation_run_count: number;
  tool_definition_count: number;
  tool_invocation_count: number;
  generated_at: string;
}

export interface TwinNode {
  key: string;
  label: string;
  node_type: string;
  status: string;
  health: number;
  position: [number, number, number];
  description: string;
}

export interface TwinEdge {
  key: string;
  source: string;
  target: string;
  flow_type: string;
  status: string;
  traffic: number;
}

export interface TwinScene {
  key: string;
  name: string;
  version: string;
  status: string;
  description: string;
  parent_scene_key: string | null;
  scene_level: string;
  entry_space_key: string | null;
  asset_bundle_key: string | null;
  camera_preset: Record<string, unknown>;
  updated_at: string;
}

export interface TwinHotspot {
  key: string;
  scene_key: string;
  label: string;
  hotspot_type: string;
  status: string;
  severity: "normal" | "warning" | "critical";
  business_ref: string;
  metric_key: string | null;
  position: [number, number, number];
  details: Record<string, unknown>;
}

export interface TwinDataLayer {
  key: string;
  scene_key: string;
  label: string;
  category: string;
  enabled_default: boolean;
  style: Record<string, unknown>;
}

export interface TwinSpace {
  key: string;
  label: string;
  space_type: string;
  parent_space_key: string | null;
  status: string;
  health: number;
  alert_level: string;
  metric_key: string | null;
  position: [number, number, number];
  size: [number, number, number];
  description: string;
}

export interface TwinActor {
  key: string;
  display_name: string;
  role_title: string;
  status: string;
  home_space_key: string;
  current_space_key: string;
  avatar_style: string;
  color: string;
  position: [number, number, number];
  capabilities: string[];
}

export interface TwinRoute {
  key: string;
  source_space_key: string;
  target_space_key: string;
  route_type: string;
  path: Array<[number, number, number]>;
}

export interface TwinMeetingParticipant {
  actor_key: string;
  seat_key: string | null;
  position: string;
  finding: string;
  status: string;
  speaking_order: number;
}

export interface TwinMeetingSeat {
  key: string;
  label: string;
  layout_key: string;
  position: [number, number, number];
  rotation_y: number;
  status: string;
}

export interface TwinMeeting {
  key: string;
  title: string;
  topic: string;
  status: "scheduled" | "convening" | "in_session" | "decision_ready";
  evidence_snapshot: string;
  decision: string;
  room_space_key: string;
  next_transition_at: string | null;
  updated_at: string;
  participants: TwinMeetingParticipant[];
  seats: TwinMeetingSeat[];
}

export interface TwinObjectAction {
  key: string;
  label: string;
  action_type: "navigate" | "enter" | "focus";
  href: string | null;
  target_key: string | null;
  icon_key: string;
  emphasis: "primary" | "secondary";
}

export interface TwinInteraction {
  entity_key: string;
  entity_type: "space" | "actor" | "hotspot" | "meeting-seat";
  detail_route: string | null;
  enter_space_key: string | null;
  actions: TwinObjectAction[];
}

export type TwinSceneFocus = "campus" | "operations" | "warehouse" | "meeting";
export type CameraInteractionMode = "rotate" | "pan";
export type MeetingAction = "convene" | "start" | "decide" | "reset";

export type SyncScenario = "normal" | "delayed" | "partial" | "failure";
export type SyncVolumeProfile = "small" | "standard" | "large";
