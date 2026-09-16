"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Dialog } from "@/components/console/interaction";
import { OrderSummaryPanel, type OrderLineageSelection } from "@/components/data-center/order-summary-panel";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import { displayDecimal } from "@/lib/decimal-display";

interface Fact { id: string; enterprise_id: string; business_unit_id: string | null; external_system_id: string; external_key: string; resource_key: string; raw_manifest_id: string; schema_version: string; mapping_version: string; observed_at: string; source_updated_at: string | null; store_key: string | null; warehouse_key?: string | null; product_key?: string | null; sku?: string; status?: string; fact_type?: string; amount?: string | null; currency_code?: string | null; quantity?: string | number | null; base_amount?: string | null; base_currency_code?: string | null; exchange_rate_version?: string | null; business_date?: string | null; store_timezone?: string | null; source_local_time?: string | null; available?: number; total?: number; reserved?: number; in_transit?: number | null; attributes?: Record<string, unknown> }
interface AfterSaleFact extends Fact { order_external_key?: string; source_item_key?: string; after_type?: string; quantity?: number; source_amount_text?: string; source_updated_local_time?: string; quality_flags?: string[]; shipment_number?: string; freight_amount?: string | null; freight_currency_code?: string | null; source_timezone?: string | null; dispatched_local_time?: string | null; lines?: { external_key: string; sku: string; quantity: number; bundle_type: number; parent_external_key: string | null }[] }
interface FactPage { items: AfterSaleFact[]; total: number; data_as_of: string | null }
const qualityLabels: Record<string, string> = { currency_pending: "币种待确认", timezone_pending: "时区待确认", source_timezone_pending: "来源时区待确认", freight_currency_pending: "运费币种待确认", amount_format_pending: "金额格式待确认" };
const fulfillmentStatus: Record<string, string> = { logistics_ordering: "物流下单中", awaiting_dispatch: "待出库", dispatched: "已出库", intercepted: "已拦截" };
const afterTypeLabels: Record<string, string> = { refund: "退款", return: "退货", replacement: "换货" };
const API = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/data-center/canonical`;

export function CanonicalFactsPanel() {
  const { scopeContext, scopeOptions } = useExperience();
  const [family, setFamily] = useState("orders");
  const [authoritativeOnly, setAuthoritativeOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<{ key: string; page: FactPage } | null>(null);
  const [lineage, setLineage] = useState<{ scope: string | undefined; selection: OrderLineageSelection } | null>(null);
  const activeLineage = lineage?.scope === scopeContext?.scope_version ? lineage?.selection : null;
  const filterQuery = activeLineage ? new URLSearchParams({ ...activeLineage }).toString() : "";
  const queryKey = `${scopeContext?.scope_version}:${family}:${offset}:${authoritativeOnly}:${filterQuery}`;
  const data = result?.key === queryKey ? result.page : null;
  const controller = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<AfterSaleFact | null>(null);
  const load = useCallback(async () => {
    controller.current?.abort();
    const requestController = new AbortController();
    controller.current = requestController;
    setBusy(true); setError(null);
    try {
      const response = await apiFetch(`${API}/${family}?offset=${offset}&limit=20&authoritative_only=${authoritativeOnly}&${filterQuery}`, { cache: "no-store", signal: requestController.signal });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "规范事实读取失败"));
      const page = await response.json() as FactPage;
      if (!requestController.signal.aborted) setResult({ key: queryKey, page });
    } catch (reason) { if (!requestController.signal.aborted) { setResult(null); setError(reason instanceof Error ? reason.message : "读取失败"); } }
    finally { if (!requestController.signal.aborted) setBusy(false); }
  }, [family, offset, authoritativeOnly, filterQuery, queryKey]);
  useEffect(() => { setDetail(null); void load(); return () => controller.current?.abort(); }, [load]);
  const enterpriseName = (key: string) => scopeOptions?.enterprises.find((item) => item.key === key)?.label ?? key;
  const unitName = (key: string | null) => scopeOptions?.business_units.find((item) => item.key === key)?.label ?? key ?? "集团参考";
  const storeName = (key: string | null) => scopeOptions?.stores.find((item) => item.key === key)?.label ?? key ?? "—";
  return <><OrderSummaryPanel onInspect={(selection) => {
    setLineage({ scope: scopeContext?.scope_version, selection });
    setFamily("orders"); setAuthoritativeOnly(true); setOffset(0); setDetail(null);
  }} /><section className="data-source-panel">
    <header><h2>来源规范事实</h2><div className="console-toolbar">
      <select aria-label="规范事实类型" value={family} onChange={(event) => { setFamily(event.target.value); setLineage(null); setOffset(0); setDetail(null); }}><option value="orders">销售订单</option><option value="after_sales">销售售后</option><option value="inventory">仓库库存</option><option value="fulfillments">销售出库</option><option value="operational">其他运营事实</option></select>
      {activeLineage ? <button className="button secondary" type="button" onClick={() => { setLineage(null); setOffset(0); }}>清除血缘筛选</button> : null}
      <button className="button secondary" type="button" disabled={busy} onClick={() => void load()}>刷新</button>
      {family !== "operational" ? <label><input type="checkbox" checked={authoritativeOnly} onChange={(event) => { setAuthoritativeOnly(event.target.checked); setOffset(0); setDetail(null); }} />仅权威来源</label> : null}
    </div></header>
    {error ? <p role="alert">{error}</p> : null}
    <div className="table-wrap"><table><thead><tr><th>法人 / 业务单元</th><th>{family === "operational" ? "类型 / 外部键" : family === "fulfillments" ? "出库单 / 店铺" : family !== "inventory" ? "订单 / 店铺" : "SKU / 仓库"}</th><th>{family === "operational" ? "数量 / 金额" : family === "fulfillments" ? "运费" : family === "after_sales" ? "售后类型 / 数量 / 金额" : family === "orders" ? "订单总额" : "实际 / 可用 / 锁定"}</th><th>{family !== "inventory" ? "业务日期 / 状态" : "在途"}</th><th>操作</th></tr></thead><tbody>
      {data?.items.map((row) => <tr key={row.id}>
        <td>{enterpriseName(row.enterprise_id)} / {unitName(row.business_unit_id)}</td>
        <td>{family === "operational" ? <>{row.fact_type ?? row.resource_key}<br />{row.external_key}</> : family !== "inventory" ? <>{row.shipment_number ?? row.order_external_key ?? row.external_key}<br />{storeName(row.store_key)}</> : <>{row.sku}<br />{scopeOptions?.warehouses.find((item) => item.key === row.warehouse_key)?.label ?? row.warehouse_key}</>}</td>
        <td>{family === "operational" ? <>{displayDecimal(row.quantity === null || row.quantity === undefined ? row.quantity : String(row.quantity))}<br />{displayDecimal(row.amount)} {row.currency_code ?? ""}</> : family === "fulfillments" ? `${displayDecimal(row.freight_amount)} ${row.freight_currency_code ?? ""}` : family === "after_sales" ? <>{afterTypeLabels[row.after_type ?? ""] ?? row.after_type} / {row.quantity}<br />{row.source_amount_text || "—"}</> : family === "orders" ? `${displayDecimal(row.amount)} ${row.currency_code ?? ""}` : `${row.total} / ${row.available} / ${row.reserved}`}</td>
        <td>{family !== "inventory" ? <>{row.business_date} / {family === "fulfillments" ? fulfillmentStatus[row.status ?? ""] ?? row.status : row.status ?? "—"}{row.quality_flags?.map((flag) => <div key={flag}>{qualityLabels[flag] ?? flag}</div>)}</> : row.in_transit ?? "—"}</td>
        <td><button className="button secondary" type="button" onClick={() => setDetail(row)}>血缘</button></td>
      </tr>)}
      {!data?.items.length ? <tr><td colSpan={5}>{busy ? "正在读取" : "当前范围暂无规范事实"}</td></tr> : null}
    </tbody></table></div>
    <footer><span>共 {data?.total ?? 0} 条 · 数据时间 {data?.data_as_of ? new Date(data.data_as_of).toLocaleString("zh-CN") : "—"}</span>
      <button className="button secondary" type="button" disabled={busy || !offset} onClick={() => setOffset(Math.max(0, offset - 20))}>上一页</button>
      <button className="button secondary" type="button" disabled={busy || offset + 20 >= (data?.total ?? 0)} onClick={() => setOffset(offset + 20)}>下一页</button>
    </footer>
    {detail ? <Dialog title="规范事实血缘" onClose={() => setDetail(null)}><dl className="sync-run-meta">
      {detail.source_item_key ? <div><dt>售后子项</dt><dd>{detail.source_item_key}</dd></div> : null}
      {detail.source_updated_local_time ? <div><dt>来源本地更新时间</dt><dd>{detail.source_updated_local_time}</dd></div> : null}
      {[["来源", detail.external_system_id], ["资源", detail.resource_key], ["外部键", detail.external_key], ["Raw 页", detail.raw_manifest_id], ["Schema", detail.schema_version], ["映射版本", detail.mapping_version], ["采集时间", detail.observed_at], ["来源更新时间", detail.source_updated_at], ["店铺时区", detail.store_timezone], ["本位币金额", detail.base_amount], ["本位币", detail.base_currency_code], ["汇率版本", detail.exchange_rate_version]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? "—"}</dd></div>)}
    </dl>{detail.lines ? <><dl className="sync-run-meta"><div><dt>仓库</dt><dd>{scopeOptions?.warehouses.find((item) => item.key === detail.warehouse_key)?.label ?? detail.warehouse_key}</dd></div><div><dt>来源出库时间</dt><dd>{detail.dispatched_local_time ?? "—"}</dd></div><div><dt>来源时区</dt><dd>{detail.source_timezone ?? "待确认"}</dd></div></dl><div className="table-wrap"><table><thead><tr><th>明细 ID</th><th>SKU</th><th>数量</th><th>类型 / 父明细</th></tr></thead><tbody>{detail.lines.map((line) => <tr key={line.external_key}><td>{line.external_key}</td><td>{line.sku}</td><td>{line.quantity}</td><td>{["普通商品", "组合商品", "组合子商品"][line.bundle_type]} / {line.parent_external_key ?? "—"}</td></tr>)}</tbody></table></div></> : null}</Dialog> : null}
  </section></>;
}
