import type { EnterpriseTwinOverview } from "@/lib/twin-types";

export const INITIAL_DATA_ACCEPTANCE_BASELINES = [
  { key: "sources", label: "首期接入来源", target: 4, unit: "个", note: "吉客云、CRM、广告与客服渠道" },
  { key: "records", label: "可验证原始记录", target: 100_000, unit: "条", note: "形成首个可回放的历史分析窗口" },
  { key: "entities", label: "统一业务实体", target: 20_000, unit: "个", note: "店铺、SKU、订单、客户与库存" },
  { key: "metrics", label: "首期经营指标", target: 30, unit: "个", note: "经营、投放、利润与服务质量" }
] as const;

export interface DataReadinessItem {
  key: (typeof INITIAL_DATA_ACCEPTANCE_BASELINES)[number]["key"];
  label: string;
  current: number;
  target: number;
  unit: string;
  note: string;
  progress: number;
  coverageLabel: string;
}

export function buildDataReadinessSeries(
  overview: Pick<
    EnterpriseTwinOverview,
    "sources" | "source_record_count" | "entity_count" | "metric_definition_count"
  >
): DataReadinessItem[] {
  const values = {
    sources: overview.sources.length,
    records: overview.source_record_count,
    entities: overview.entity_count,
    metrics: overview.metric_definition_count
  };

  return INITIAL_DATA_ACCEPTANCE_BASELINES.map((baseline) => {
    const current = values[baseline.key];
    const progress = Math.min((current / baseline.target) * 100, 100);
    return {
      ...baseline,
      current,
      progress,
      coverageLabel: progress < 0.1 ? "<0.1%" : `${progress.toFixed(progress < 10 ? 1 : 0)}%`
    };
  });
}
