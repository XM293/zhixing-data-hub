export type DemoRoleId = "ceo" | "manager" | "employee" | "admin" | "service";

export type Tone = "positive" | "warning" | "critical" | "info" | "neutral";

export type DeliveryState = "prototype" | "implemented" | "unavailable";

export interface DemoRole {
  id: DemoRoleId;
  label: string;
  name: string;
  title: string;
  scope: string;
  initials: string;
  allowedSections: string[];
}

export interface NavigationItem {
  key: string;
  label: string;
  href: string;
  requiredPermission?: string;
}

export interface NavigationSection {
  key: string;
  label: string;
  shortLabel: string;
  href: string;
  iconKey: string;
  deliveryState: DeliveryState;
  groupKey?: string;
  items: NavigationItem[];
}

export interface MetricCard {
  key: string;
  label: string;
  value: string;
  change?: string;
  comparison?: string;
  tone: Tone;
}

export interface DashboardItem {
  id: string;
  title: string;
  description: string;
  meta: string;
  status: string;
  tone: Tone;
  href: string;
}

export interface DashboardData {
  title: string;
  description: string;
  metrics: MetricCard[];
  priorityTitle: string;
  priorities: DashboardItem[];
  tasks: DashboardItem[];
  updates: DashboardItem[];
}

export interface StatusValue {
  label: string;
  tone: Tone;
}

export interface TableColumn {
  key: string;
  label: string;
  align?: "left" | "right";
}

export interface TableRow {
  id: string;
  cells: Record<string, string>;
  status?: StatusValue;
  href?: string;
}

export interface TablePageData {
  key: string;
  sectionKey: string;
  eyebrow: string;
  title: string;
  description: string;
  metrics?: MetricCard[];
  columns: TableColumn[];
  rows: TableRow[];
  updatedAt: string;
  callout?: {
    title: string;
    description: string;
    tone: Tone;
  };
}

export interface PolicyDemo {
  id: string;
  name: string;
  currentVersion: string;
  pendingVersion: string;
  status: "pending" | "published";
  effectiveAt: string;
  owner: string;
  changeSummary: string;
  citations: string[];
}

export interface MemoryDemo {
  id: string;
  roleTwin: string;
  candidate: string;
  source: string;
  conflict: string;
  status: "pending" | "approved" | "rejected";
}

export interface MeetingDemo {
  id: string;
  title: string;
  status: "analysis" | "deliberation" | "decision_ready";
  evidenceSnapshot: string;
  asOf: string;
  participants: Array<{
    role: string;
    position: string;
    finding: string;
    tone: Tone;
  }>;
  disagreements: string[];
  decision: string;
}

export interface ActionDemo {
  id: string;
  title: string;
  status: "pending" | "approved" | "simulated_succeeded";
  risk: string;
  target: string;
  requestedBy: string;
  approver: string;
  parameters: string[];
  evidence: string;
  idempotencyKey: string;
}

export interface ConversationDemo {
  id: string;
  customer: string;
  topic: string;
  order: string;
  logistics: string;
  syncedAt: string;
  customerMessage: string;
  policy: string;
  draft: string;
  risk: string;
  status: "waiting" | "drafted" | "escalated";
}

export interface AnalysisDemo {
  storeName: string;
  asOf: string;
  facts: string[];
  inference: string;
  recommendation: string;
  evidence: Array<{ label: string; detail: string }>;
}

export interface ExperienceSnapshot {
  schemaVersion: 1;
  dataMode: "connector-sandbox";
  enterprise: string;
  businessTime: string;
  roles: DemoRole[];
  dashboards: Record<DemoRoleId, DashboardData>;
  tablePages: Record<string, TablePageData>;
  policy: PolicyDemo;
  memory: MemoryDemo;
  meeting: MeetingDemo;
  action: ActionDemo;
  conversation: ConversationDemo;
  analysis: AnalysisDemo;
}

export interface ExperienceDataSource {
  readSnapshot(): ExperienceSnapshot;
}
