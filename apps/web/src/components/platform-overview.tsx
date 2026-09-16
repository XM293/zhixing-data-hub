"use client";

import { useEffect, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import {
  PRODUCT_CENTERS,
  type PlatformModule,
  type PlatformModulesResponse
} from "@/lib/platform-modules";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; modules: PlatformModule[] }
  | { status: "error"; message: string };

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function PlatformOverview() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await apiFetch(`${apiBaseUrl}/api/v1/platform/modules`, {
          signal: controller.signal
        });
        if (!response.ok) throw new Error(await apiErrorMessage(response, "平台模块接口不可用"));
        const payload = (await response.json()) as PlatformModulesResponse;
        setState({ status: "ready", modules: payload.modules });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "无法连接 API"
        });
      }
    }
    void load();
    return () => controller.abort();
  }, []);

  const grouped = useMemo(() => {
    if (state.status !== "ready") return new Map<string, PlatformModule[]>();
    return state.modules.reduce((result, module) => {
      const current = result.get(module.navigation) ?? [];
      current.push(module);
      result.set(module.navigation, current);
      return result;
    }, new Map<string, PlatformModule[]>());
  }, [state]);

  return (
    <section className="centers" id="centers" aria-labelledby="centers-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">PLATFORM MAP</p>
          <h2 id="centers-title">七个入口，同一企业事实底座</h2>
        </div>
        <ApiState state={state} />
      </div>

      {state.status === "ready" ? (
        <div className="center-grid">
          {PRODUCT_CENTERS.map((center, index) => {
            const modules = grouped.get(center) ?? [];
            return (
              <article className="center-card" key={center}>
                <span className="card-index">{String(index + 1).padStart(2, "0")}</span>
                <h3>{center}</h3>
                <ul>
                  {modules.map((module) => (
                    <li key={module.key}>
                      <div>
                        <strong>{module.label}</strong>
                        <span>{module.summary}</span>
                      </div>
                      <em className={module.availability}>{module.milestone}</em>
                    </li>
                  ))}
                </ul>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="empty-state" role="status">
          {state.status === "loading"
            ? "正在读取平台模块边界…"
            : `模块边界暂不可用：${state.message}`}
        </div>
      )}
    </section>
  );
}

function ApiState({ state }: { state: LoadState }) {
  const label =
    state.status === "loading"
      ? "正在连接 API"
      : state.status === "ready"
        ? `API 已连接 · ${state.modules.length} 个模块`
        : "API 未连接";
  return (
    <div className={`api-state ${state.status}`} aria-live="polite">
      <span aria-hidden="true" />
      {label}
    </div>
  );
}
