const REQUEST_ID_HEADER = "X-Request-ID";
const RUN_ID_HEADER = "X-Run-ID";
const RUN_ID_STORAGE_KEY = "zhixing.active_run_id";
const TRACE_ID_PATTERN = /^[a-z][a-z0-9_-]{7,95}$/;

export interface TraceOptions {
  requestId?: string;
  runId?: string;
}

let memoryRunId: string | null = null;

function randomToken(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID().replaceAll("-", "");
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
}

export function newTraceId(prefix: "req" | "run"): string {
  return `${prefix}_${randomToken().slice(0, 32)}`;
}

function validTraceId(value: string | null | undefined): value is string {
  return Boolean(value && TRACE_ID_PATTERN.test(value));
}

function activeRunId(): string {
  if (validTraceId(memoryRunId)) return memoryRunId;

  if (typeof window !== "undefined") {
    const stored = window.sessionStorage.getItem(RUN_ID_STORAGE_KEY);
    if (validTraceId(stored)) {
      memoryRunId = stored;
      return stored;
    }
  }

  memoryRunId = newTraceId("run");
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(RUN_ID_STORAGE_KEY, memoryRunId);
  }
  return memoryRunId;
}

export function traceHeaders(
  initialHeaders?: HeadersInit,
  trace: TraceOptions = {}
): Headers {
  const headers = new Headers(initialHeaders);
  const requestId = trace.requestId ?? headers.get(REQUEST_ID_HEADER);
  const runId = trace.runId ?? headers.get(RUN_ID_HEADER);

  headers.set(REQUEST_ID_HEADER, validTraceId(requestId) ? requestId : newTraceId("req"));
  headers.set(RUN_ID_HEADER, validTraceId(runId) ? runId : activeRunId());
  return headers;
}

export function apiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  trace: TraceOptions = {}
): Promise<Response> {
  return fetch(input, {
    ...init,
    credentials: init.credentials ?? "include",
    headers: traceHeaders(init.headers, trace)
  });
}
