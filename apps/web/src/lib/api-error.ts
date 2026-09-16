export interface ApiErrorEnvelope {
  schema_version: 1;
  error: {
    code: string;
    message: string;
    status: number;
    request_id: string;
    run_id: string;
    retryable: boolean;
    details?: Record<string, unknown>;
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function parseApiError(payload: unknown): ApiErrorEnvelope | null {
  if (!isRecord(payload) || payload.schema_version !== 1 || !isRecord(payload.error)) return null;
  const error = payload.error;
  if (
    typeof error.code !== "string"
    || typeof error.message !== "string"
    || typeof error.status !== "number"
    || typeof error.request_id !== "string"
    || typeof error.run_id !== "string"
    || typeof error.retryable !== "boolean"
  ) return null;
  return payload as unknown as ApiErrorEnvelope;
}

export async function apiErrorMessage(response: Response, fallback: string): Promise<string> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return `${fallback} (${response.status})`;
  }

  const envelope = parseApiError(payload);
  if (envelope) return `${envelope.error.message} · ${envelope.error.run_id}`;

  if (isRecord(payload) && typeof payload.detail === "string") return payload.detail;
  if (isRecord(payload) && isRecord(payload.detail) && typeof payload.detail.message === "string") {
    return payload.detail.message;
  }
  return `${fallback} (${response.status})`;
}
