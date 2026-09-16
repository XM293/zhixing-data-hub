"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { OrderSummaryPanel } from "@/components/data-center/order-summary-panel";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";

interface OrganizationNode { id: string; parent_id: string | null; kind: string; name: string }
interface Location { origin_id: string; enterprise_id: string; business_unit_id: string;
  kind: string; name: string; entity_status: string; source_name: string; source_status: string;
  connection_status: string; resource_key: string; resource_enabled: boolean;
  schema_status: string; observed_at: string }
interface Projection { organizations: OrganizationNode[]; locations: Location[];
  total: number; offset: number; limit: number; data_as_of: string | null }
const API = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/data-center/canonical/scope-twin`;
const kindLabels: Record<string, string> = { group: "集团", enterprise: "法人", business_unit: "业务单元", store: "店铺", warehouse: "仓库" };
const connectionLabels: Record<string, string> = { connected: "已连接", disconnected: "未连接", unknown: "未探测", probe_queued: "探测排队中", failed: "连接失败" };
const statusLabels: Record<string, string> = { active: "启用", inactive: "停用", suspended: "暂停", authorization_error: "授权异常" };

export function ScopeTwinPanel() {
  const { scopeContext } = useExperience();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const key = `${scopeContext?.scope_version}:${offset}:${revision}`;
  const [result, setResult] = useState<{ key: string; data?: Projection; error?: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await apiFetch(`${API}?offset=${offset}&limit=20`, { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error(await apiErrorMessage(response, "组织来源读取失败"));
        const data = await response.json() as Projection;
        if (!controller.signal.aborted) setResult({ key, data });
      } catch (error) {
        if (!controller.signal.aborted) setResult({ key, error: error instanceof Error ? error.message : "读取失败" });
      }
    })();
    return () => controller.abort();
  }, [key, offset]);
  const current = result?.key === key ? result : null;
  const data = current?.data;
  const names = new Map(data?.organizations.map((node) => [node.id, node.name]));
  return <>
    <section className="data-source-panel">
      <header><h1>组织与来源</h1><div className="console-toolbar">
        <Link className="button secondary" href="/console/data/products/commerce">经营事实</Link>
        <button type="button" className="button secondary" onClick={() => setRevision((value) => value + 1)}>刷新</button>
      </div></header>
      {current?.error ? <p role="alert">{current.error}</p> : !data ? <p role="status">正在读取</p> : <>
        <div className="table-wrap"><table><thead><tr><th>组织</th><th>类型</th><th>范围内上级</th></tr></thead><tbody>
          {data.organizations.map((node) => <tr key={`${node.kind}:${node.id}`}><td>{node.name}</td><td>{kindLabels[node.kind] ?? node.kind}</td><td>{node.parent_id ? names.get(node.parent_id) ?? "—" : "—"}</td></tr>)}
          {!data.organizations.length ? <tr><td colSpan={3}>当前范围暂无组织</td></tr> : null}
        </tbody></table></div>
        <h2>店铺与仓库来源</h2>
        <div className="table-wrap"><table><thead><tr><th>对象 / 类型</th><th>法人 / 业务单元</th><th>来源 / 资源</th><th>来源状态</th><th>采集 / Schema</th><th>目录采集时间</th></tr></thead><tbody>
          {data.locations.map((row) => <tr key={row.origin_id}>
            <td>{row.name}<br />{kindLabels[row.kind] ?? row.kind} / {statusLabels[row.entity_status] ?? row.entity_status}</td>
            <td>{names.get(row.enterprise_id)} / {names.get(row.business_unit_id)}</td>
            <td>{row.source_name}<br />{row.resource_key}</td>
            <td>{row.source_status === "disabled" ? "已停用" : connectionLabels[row.connection_status] ?? row.connection_status}</td>
            <td>{row.resource_enabled ? "已启用" : "已停用"} / {row.schema_status === "confirmed" ? "已确认" : "待确认"}</td>
            <td>{new Date(row.observed_at).toLocaleString("zh-CN")}</td>
          </tr>)}
          {!data.locations.length ? <tr><td colSpan={6}>当前范围暂无已归属店铺或仓库</td></tr> : null}
        </tbody></table></div>
        <footer><span>共 {data.total} 条</span>
          <button type="button" className="button secondary" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>上一页</button>
          <button type="button" className="button secondary" disabled={offset + 20 >= data.total} onClick={() => setOffset(offset + 20)}>下一页</button>
        </footer>
      </>}
    </section>
    <OrderSummaryPanel />
  </>;
}
