import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch, traceHeaders } from "./api-client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("traceHeaders", () => {
  it("preserves valid caller context and ordinary headers", () => {
    const headers = traceHeaders(
      { "Content-Type": "application/json" },
      { requestId: "req_external001", runId: "run_external001" }
    );

    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("x-request-id")).toBe("req_external001");
    expect(headers.get("x-run-id")).toBe("run_external001");
  });

  it("replaces invalid external context", () => {
    const headers = traceHeaders(undefined, { requestId: "bad id", runId: "x" });

    expect(headers.get("x-request-id")).toMatch(/^req_[a-z0-9]+$/);
    expect(headers.get("x-run-id")).toMatch(/^run_[a-z0-9]+$/);
  });
});

describe("apiFetch", () => {
  it("adds trace headers to the actual browser request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch(
      "http://test.local/resource",
      { method: "POST", headers: { "Content-Type": "application/json" } },
      { requestId: "req_webrequest01", runId: "run_webflow0001" }
    );

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get("x-request-id")).toBe("req_webrequest01");
    expect(headers.get("x-run-id")).toBe("run_webflow0001");
    expect(headers.get("content-type")).toBe("application/json");
    expect(init.credentials).toBe("include");
  });
});
