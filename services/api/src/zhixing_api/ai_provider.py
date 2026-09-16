from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

import httpx

from zhixing_api.config import Settings

TWIN_ANSWER_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "string"}},
        "actions": {"type": "array", "items": {"type": "string"}},
        "caveats": {"type": "array", "items": {"type": "string"}},
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
    },
    "required": ["summary", "facts", "actions", "caveats", "confidence"],
}


class AIProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AICompletion:
    payload: dict[str, object]
    input_tokens: int | None
    output_tokens: int | None
    structured_output: bool = True


class ResponsesAIProvider:
    async def generate(
        self,
        settings: Settings,
        *,
        instructions: str,
        input_text: str,
        run_id: str,
        schema_name: str = "enterprise_twin_answer",
        response_schema: dict[str, object] | None = None,
    ) -> AICompletion:
        if not settings.ai_enabled or not settings.ai_api_key:
            raise AIProviderError("AI 模型接口未启用")

        schema = response_schema or TWIN_ANSWER_SCHEMA
        base_url = settings.ai_base_url.rstrip("/")

        use_chat_completions = (
            "/chat/completions" in base_url
            or "deepseek" in base_url.lower()
            or "deepseek" in settings.ai_model.lower()
            or "x5m5x" in base_url.lower()
            or (
                not base_url.endswith("/responses")
                and not base_url.startswith("https://api.openai.com")
                and "maysu.com" not in base_url.lower()
            )
        )

        headers = {
            "Authorization": f"Bearer {settings.ai_api_key}",
            "Content-Type": "application/json",
        }

        structured_output = True
        body: dict[str, object] = {}
        output_text: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None

        if use_chat_completions:
            endpoint = base_url if "/chat/completions" in base_url else f"{base_url}/chat/completions"
            schema_str = json.dumps(schema, ensure_ascii=False)
            chat_instructions = (
                f"{instructions}\n\n"
                f"【输出格式规范】\n"
                f"你必须严格返回一个符合以下 JSON Schema 的单个合法 JSON 字典对象，"
                f"不要使用 Markdown 代码块（如 ```json），不要添加任何前后注释文字：\n"
                f"{schema_str}"
            )
            chat_payload: dict[str, object] = {
                "model": settings.ai_model,
                "messages": [
                    {"role": "system", "content": chat_instructions},
                    {"role": "user", "content": input_text},
                ],
                "response_format": {"type": "json_object"},
            }
            try:
                async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
                    response = await client.post(endpoint, headers=headers, json=chat_payload)
                    if response.status_code == 400:
                        chat_payload.pop("response_format", None)
                        structured_output = False
                        response = await client.post(endpoint, headers=headers, json=chat_payload)
                    response.raise_for_status()
                    body = cast(dict[str, object], response.json())
            except (httpx.HTTPError, ValueError) as exc:
                status_code = (
                    exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                )
                suffix = f"（HTTP {status_code}）" if status_code else ""
                if isinstance(exc, httpx.HTTPStatusError):
                    detail = _provider_error_message(exc.response)
                    if detail:
                        suffix = f"{suffix}：{detail}"
                raise AIProviderError(f"AI 模型接口调用失败{suffix}") from exc

            output_text = _extract_chat_output_text(body)
            usage = body.get("usage")
            usage_dict = usage if isinstance(usage, dict) else {}
            input_tokens = _optional_int(usage_dict.get("prompt_tokens")) or _optional_int(usage_dict.get("input_tokens"))
            output_tokens = _optional_int(usage_dict.get("completion_tokens")) or _optional_int(usage_dict.get("output_tokens"))
        else:
            if not base_url.endswith("/v1") and not base_url.endswith("/responses"):
                base_url = f"{base_url}/v1"
            url = base_url if base_url.endswith("/responses") else f"{base_url}/responses"
            request_payload = {
                "model": settings.ai_model,
                "instructions": instructions,
                "input": input_text,
                "store": False,
                "metadata": {"run_id": run_id, "application": "zhixing-data-hub"},
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "strict": True,
                        "schema": schema,
                    }
                },
            }
            try:
                async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
                    response = await client.post(
                        url,
                        headers=headers,
                        json=request_payload,
                    )
                    if response.status_code == 400:
                        compatible_payload = dict(request_payload)
                        compatible_payload.pop("metadata", None)
                        response = await client.post(
                            url,
                            headers=headers,
                            json=compatible_payload,
                        )
                    if response.status_code == 400:
                        compatible_payload.pop("text", None)
                        structured_output = False
                        compatible_payload["instructions"] = (
                            f"{instructions}\n只输出一个 JSON 对象，不要使用 Markdown 代码块。"
                        )
                        response = await client.post(
                            url,
                            headers=headers,
                            json=compatible_payload,
                        )
                    if response.status_code == 404:
                        chat_endpoint = f"{base_url}/chat/completions"
                        schema_str = json.dumps(schema, ensure_ascii=False)
                        fallback_payload: dict[str, object] = {
                            "model": settings.ai_model,
                            "messages": [
                                {"role": "system", "content": f"{instructions}\n\n请返回符合以下 JSON Schema 的单个合法 JSON 对象：\n{schema_str}"},
                                {"role": "user", "content": input_text},
                            ],
                            "response_format": {"type": "json_object"},
                        }
                        response = await client.post(chat_endpoint, headers=headers, json=fallback_payload)
                        if response.status_code == 400:
                            fallback_payload.pop("response_format", None)
                            response = await client.post(chat_endpoint, headers=headers, json=fallback_payload)

                    response.raise_for_status()
                    body = cast(dict[str, object], response.json())
            except (httpx.HTTPError, ValueError) as exc:
                status_code = (
                    exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                )
                suffix = f"（HTTP {status_code}）" if status_code else ""
                if isinstance(exc, httpx.HTTPStatusError):
                    detail = _provider_error_message(exc.response)
                    if detail:
                        suffix = f"{suffix}：{detail}"
                raise AIProviderError(f"AI 模型接口调用失败{suffix}") from exc

            output_text = body.get("output_text")
            if not isinstance(output_text, str):
                output_text = _extract_output_text(body)
            if not output_text:
                output_text = _extract_chat_output_text(body)
            usage = body.get("usage")
            usage_dict = usage if isinstance(usage, dict) else {}
            input_tokens = _optional_int(usage_dict.get("input_tokens")) or _optional_int(usage_dict.get("prompt_tokens"))
            output_tokens = _optional_int(usage_dict.get("output_tokens")) or _optional_int(usage_dict.get("completion_tokens"))

        if not output_text:
            raise AIProviderError("AI 模型未返回可读取文本")
        try:
            answer_payload = json.loads(_strip_json_fence(output_text))
        except json.JSONDecodeError as exc:
            raise AIProviderError("AI 模型返回内容不是有效 JSON") from exc
        if not isinstance(answer_payload, dict):
            raise AIProviderError("AI 模型返回结构无效")
        return AICompletion(
            payload=cast(dict[str, object], answer_payload),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            structured_output=structured_output,
        )


def _extract_chat_output_text(body: dict[str, object]) -> str | None:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    reasoning = message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning
    return None


def _extract_output_text(body: dict[str, object]) -> str | None:
    output = body.get("output")
    if not isinstance(output, list):
        return None
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return cast(str, part["text"])
    return None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _provider_error_message(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:300] if text else None
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    message = error.get("message") if isinstance(error, dict) else body.get("message")
    return str(message)[:300] if message else None


def _strip_json_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        return stripped[7:-3].strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        return stripped[3:-3].strip()
    return stripped
