"use client";

import { useEffect, useState } from "react";

import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import { displayDecimal } from "@/lib/decimal-display";

interface OrderSummary {
  order_count: number;
  currency_totals: Record<string, string>;
  missing_amount_count: number;
  status_counts: Record<string, number>;
  data_as_of: string | null;
  quality_flags: string[];
  lineage: { enterprise_id: string; business_unit_id: string; external_system_id: string;
    resource_key: string; schema_version: string; mapping_version: string; order_count: number }[];
}

const qualityLabels: Record<string, string> = {
  coverage_unverified: "覆盖完整性未核验", fx_unavailable: "汇率未确认",
  no_authoritative_orders: "暂无权威订单", amount_or_currency_missing: "金额或币种缺失",
  intercompany_elimination_unavailable: "未做内部交易抵销",
};
const API = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/data-center/canonical/orders/summary`;

export interface OrderLineageSelection {
  source_id: string; business_unit_id: string; resource_key: string;
  schema_version: string; mapping_version: string; date_from: string; date_to: string;
}

export function OrderSummaryPanel({ onInspect }: { onInspect?: (selection: OrderLineageSelection) => void }) {
  const { scopeContext, scopeOptions } = useExperience();
  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date(Date.now() + 86400000).toISOString().slice(0, 10));
  const [revision, setRevision] = useState(0);
  const queryKey = `${scopeContext?.scope_version}:${dateFrom}:${dateTo}:${revision}`;
  const [result, setResult] = useState<{ key: string; data?: OrderSummary; error?: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    if (!dateFrom || !dateTo || dateTo <= dateFrom) return () => controller.abort();
    void (async () => {
      try {
        const response = await apiFetch(`${API}?${new URLSearchParams({ date_from: dateFrom, date_to: dateTo })}`, {
          cache: "no-store", signal: controller.signal,
        });
        if (!response.ok) throw new Error(await apiErrorMessage(response, "订单汇总读取失败"));
        const data = await response.json() as OrderSummary;
        if (!controller.signal.aborted) setResult({ key: queryKey, data });
      } catch (error) {
        if (!controller.signal.aborted) setResult({ key: queryKey, error: error instanceof Error ? error.message : "读取失败" });
      }
    })();
    return () => controller.abort();
  }, [dateFrom, dateTo, queryKey]);
  const current = result?.key === queryKey ? result : null;
  const data = current?.data;
  return <section className="data-source-panel order-summary-panel">
    <header><h2>权威订单汇总</h2><div className="order-summary-filters">
      <label>业务日期起<input aria-label="汇总开始日期" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
      <label>截止日期（不含）<input aria-label="汇总截止日期" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
      <button type="button" className="button secondary" onClick={() => setRevision((value) => value + 1)}>刷新汇总</button>
    </div></header>
    {!dateFrom || !dateTo || dateTo <= dateFrom ? <p role="alert">请选择有效日期区间</p> : current?.error ? <p role="alert">{current.error}</p> : !data ? <p role="status">正在读取</p> : <>
      <dl className="sync-run-meta">
        <div><dt>订单记录数（全部状态）</dt><dd>{data.order_count}</dd></div>
        <div><dt>金额或币种缺失</dt><dd>{data.missing_amount_count}</dd></div>
        {Object.entries(data.currency_totals).map(([currency, amount]) => <div key={currency}><dt>订单金额 · {currency}</dt><dd>{displayDecimal(amount)}</dd></div>)}
        <div><dt>数据时间</dt><dd>{data.data_as_of ? new Date(data.data_as_of).toLocaleString("zh-CN") : "—"}</dd></div>
      </dl>
      <p>{data.quality_flags.map((flag) => qualityLabels[flag] ?? flag).join(" · ")}</p>
      <div className="table-wrap"><table><thead><tr><th>法人 / 项目</th><th>来源 / 资源</th><th>Schema / 映射版本</th><th>订单记录数</th>{onInspect ? <th>操作</th> : null}</tr></thead><tbody>
        {data.lineage.map((row) => <tr key={[row.enterprise_id, row.business_unit_id, row.external_system_id, row.resource_key, row.schema_version, row.mapping_version].join(":")}>
          <td>{scopeOptions?.enterprises.find((item) => item.key === row.enterprise_id)?.label ?? row.enterprise_id} / {scopeOptions?.business_units.find((item) => item.key === row.business_unit_id)?.label ?? row.business_unit_id}</td>
          <td>{row.external_system_id} / {row.resource_key}</td><td>{row.schema_version} / {row.mapping_version}</td><td>{row.order_count}</td>
          {onInspect ? <td><button type="button" className="button secondary" onClick={() => onInspect({
            source_id: row.external_system_id, business_unit_id: row.business_unit_id,
            resource_key: row.resource_key, schema_version: row.schema_version,
            mapping_version: row.mapping_version, date_from: dateFrom, date_to: dateTo,
          })}>查看订单</button></td> : null}
        </tr>)}
        {!data.lineage.length ? <tr><td colSpan={onInspect ? 5 : 4}>当前范围暂无权威订单</td></tr> : null}
      </tbody></table></div>
    </>}
  </section>;
}
