import type { EnterpriseTwinOverview } from "@/lib/twin-types";
import type { MetricSeriesResponse } from "@/lib/data-center-types";

export interface CockpitSeriesItem {
  key: string;
  label: string;
  value: number;
  color: string;
}

export interface CockpitDeltaItem extends CockpitSeriesItem {
  changeRate: number;
  favorable: boolean;
}

export interface CockpitTrendPoint {
  x: number;
  y: number;
  value: number;
  asOf: string;
}

export interface CockpitTrendItem {
  key: string;
  label: string;
  unit: string;
  color: string;
  periodChangeRate: number | null;
  favorable: boolean;
  path: string;
  points: CockpitTrendPoint[];
}

const NODE_GROUPS: Array<{
  key: string;
  label: string;
  types: string[];
  color: string;
}> = [
  { key: "source", label: "业务来源", types: ["source"], color: "#55c7a8" },
  { key: "foundation", label: "数据知识底座", types: ["integration", "core", "knowledge", "memory"], color: "#4da3d8" },
  { key: "intelligence", label: "智能决策", types: ["agent", "meeting", "analysis"], color: "#e3b45f" },
  { key: "execution", label: "执行与服务", types: ["action", "service"], color: "#e37c68" }
];

const ASSET_COLORS = [
  "#55c7a8",
  "#4da3d8",
  "#d19745",
  "#e3b45f",
  "#e37c68",
  "#8b84d7",
  "#6ab7c9",
  "#9fb35b"
];

const TREND_COLORS: Record<string, string> = {
  gmv_today: "#5dd6b7",
  orders_today: "#64a8e8",
  refund_rate: "#e58170",
  ad_roi: "#e7b85f",
  active_members: "#a58ce2",
  low_stock_skus: "#79b76d"
};

export function buildMetricTrendSeries(
  response: MetricSeriesResponse,
  width = 720,
  height = 220
): CockpitTrendItem[] {
  const normalized = response.series
    .filter((series) => series.points.length > 0)
    .map((series) => {
      const baseline = series.points[0]?.value ?? 0;
      return {
        series,
        values: series.points.map((point) => baseline === 0 ? 100 : (point.value / baseline) * 100)
      };
    });
  const values = normalized.flatMap((item) => item.values);
  if (values.length === 0) return [];
  const valueMin = Math.min(...values);
  const valueMax = Math.max(...values);
  const padding = Math.max((valueMax - valueMin) * 0.12, 2);
  const chartMin = valueMin - padding;
  const chartMax = valueMax + padding;
  const chartRange = Math.max(chartMax - chartMin, 1);

  return normalized.map(({ series, values: seriesValues }) => {
    const points = series.points.map((point, index) => ({
      x: series.points.length === 1 ? width / 2 : (index / (series.points.length - 1)) * width,
      y: height - ((seriesValues[index] - chartMin) / chartRange) * height,
      value: point.value,
      asOf: point.as_of
    }));
    const periodChangeRate = series.period_change_rate;
    const favorable = series.key === "refund_rate"
      ? (periodChangeRate ?? 0) <= 0
      : (periodChangeRate ?? 0) >= 0;
    return {
      key: series.key,
      label: series.label,
      unit: series.unit,
      color: TREND_COLORS[series.key] ?? "#8ea8a2",
      periodChangeRate,
      favorable,
      path: points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" "),
      points
    };
  });
}

export function buildAssetSeries(
  overview: Pick<
    EnterpriseTwinOverview,
    | "source_record_count"
    | "commerce_fact_count"
    | "customer_profile_count"
    | "customer_touchpoint_count"
    | "entity_count"
    | "metric_definition_count"
    | "knowledge_document_count"
    | "knowledge_version_count"
    | "knowledge_chunk_count"
    | "role_twin_profile_count"
    | "agent_run_count"
    | "customer_operation_run_count"
    | "tool_definition_count"
    | "tool_invocation_count"
  >
): CockpitSeriesItem[] {
  return [
    ["records", "原始业务记录", overview.source_record_count],
    ["commerce-facts", "规范经营事实", overview.commerce_fact_count],
    [
      "customer-assets",
      "客户主档与触点",
      overview.customer_profile_count + overview.customer_touchpoint_count
    ],
    ["entities", "统一实体", overview.entity_count],
    ["metrics", "指标口径", overview.metric_definition_count],
    [
      "knowledge-assets",
      "知识资产记录",
      overview.knowledge_document_count + overview.knowledge_version_count + overview.knowledge_chunk_count
    ],
    [
      "twin-ai-runs",
      "分身与 AI 记录",
      overview.role_twin_profile_count + overview.agent_run_count + overview.customer_operation_run_count
    ],
    ["tool-activity", "工具与调用记录", overview.tool_definition_count + overview.tool_invocation_count]
  ].map(([key, label, value], index) => ({
    key: String(key),
    label: String(label),
    value: Number(value),
    color: ASSET_COLORS[index]
  }));
}

export function buildNodeGroups(
  nodes: EnterpriseTwinOverview["nodes"]
): CockpitSeriesItem[] {
  return NODE_GROUPS.map((group) => ({
    key: group.key,
    label: group.label,
    value: nodes.filter((node) => group.types.includes(node.node_type)).length,
    color: group.color
  }));
}

export function buildMetricDeltas(
  metrics: EnterpriseTwinOverview["metrics"]
): CockpitDeltaItem[] {
  return metrics
    .filter((metric) => metric.change_rate !== null)
    .map((metric, index) => {
      const changeRate = (metric.change_rate ?? 0) * 100;
      const favorable = metric.key === "refund_rate" ? changeRate <= 0 : changeRate >= 0;
      return {
        key: metric.key,
        label: metric.label,
        value: Math.abs(changeRate),
        changeRate,
        favorable,
        color: favorable ? "#55c7a8" : "#e37c68"
      };
    })
    .sort((left, right) => right.value - left.value || left.key.localeCompare(right.key));
}

export function buildNodeRing(groups: CockpitSeriesItem[]): string {
  const total = groups.reduce((sum, item) => sum + item.value, 0);
  if (total === 0) return "#263d42 0deg 360deg";

  let cursor = 0;
  return groups
    .map((item) => {
      const start = cursor;
      cursor += (item.value / total) * 360;
      return `${item.color} ${start.toFixed(1)}deg ${cursor.toFixed(1)}deg`;
    })
    .join(", ");
}
