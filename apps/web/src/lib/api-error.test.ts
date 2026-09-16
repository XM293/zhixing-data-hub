import { describe, expect, it } from "vitest";

import { apiErrorMessage, parseApiError } from "./api-error";

describe("统一 API 错误 Envelope", () => {
  it("解析版本化错误并保留运行 ID", async () => {
    const payload = {
      schema_version: 1,
      error: {
        code: "authorization.denied",
        message: "无权访问该企业资料",
        status: 403,
        request_id: "req_12345678",
        run_id: "run_12345678",
        retryable: false,
        details: {}
      }
    };

    expect(parseApiError(payload)?.error.code).toBe("authorization.denied");
    const response = new Response(JSON.stringify(payload), {
      status: 403,
      headers: { "Content-Type": "application/json" }
    });
    await expect(apiErrorMessage(response, "请求失败")).resolves.toBe(
      "无权访问该企业资料 · run_12345678"
    );
  });

  it("兼容旧 detail 响应并处理非 JSON 错误", async () => {
    await expect(apiErrorMessage(new Response(JSON.stringify({ detail: "旧错误" }), { status: 409 }), "请求失败"))
      .resolves.toBe("旧错误");
    await expect(apiErrorMessage(new Response("bad gateway", { status: 502 }), "上游失败"))
      .resolves.toBe("上游失败 (502)");
  });
});
