from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from zhixing_api.models import ApiModel

McpScopeType = Literal[
    "enterprise",
    "org_subtree",
    "store",
    "knowledge_space",
    "object",
    "self",
    "business_unit",
]


class McpScopeConstraint(ApiModel):
    scope_type: McpScopeType
    scope_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("scope_ids")
    @classmethod
    def normalize_scope_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if not normalized:
            raise ValueError("MCP 会话范围至少需要一个有效标识")
        if len(normalized) != len(set(normalized)):
            raise ValueError("MCP 会话范围不能包含重复标识")
        return sorted(normalized)


class McpSessionCreateRequest(ApiModel):
    schema_version: Literal[1] = 1
    client_id: str = Field(
        min_length=3,
        max_length=120,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    allowed_tool_keys: list[str] = Field(min_length=1, max_length=32)
    scope_constraints: list[McpScopeConstraint] = Field(default_factory=list, max_length=24)
    ttl_seconds: int = Field(default=900, ge=60, le=3600)
    agent_run_id: str | None = Field(default=None, min_length=1, max_length=64)
    workspace_key: str | None = Field(default=None, min_length=2, max_length=64)

    @field_validator("client_id")
    @classmethod
    def normalize_client_id(cls, value: str) -> str:
        return value.strip().casefold()

    @field_validator("allowed_tool_keys")
    @classmethod
    def normalize_tool_keys(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(values) or len(normalized) != len(set(normalized)):
            raise ValueError("MCP 会话工具键不能为空或重复")
        return sorted(normalized)

    @model_validator(mode="after")
    def reject_duplicate_scope_constraints(self) -> McpSessionCreateRequest:
        keys = [
            (item.scope_type, scope_id)
            for item in self.scope_constraints
            for scope_id in item.scope_ids
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("MCP 会话范围约束不能重复")
        return self


class McpSessionRevokeRequest(ApiModel):
    schema_version: Literal[1] = 1
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class McpSessionView(ApiModel):
    schema_version: Literal[1] = 1
    session_id: str
    client_id: str
    principal_id: str
    agent_run_id: str | None
    workspace_key: str | None = None
    allowed_tool_keys: list[str]
    scope_constraints: list[McpScopeConstraint]
    issued_permission_set_version: str
    current_permission_set_version: str
    permission_set_version_changed: bool
    status: Literal["active", "expired", "revoked"]
    issued_at: datetime
    expires_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None


class McpSessionCreateResponse(ApiModel):
    schema_version: Literal[1] = 1
    session_token: str
    session: McpSessionView


class McpSessionListResponse(ApiModel):
    schema_version: Literal[1] = 1
    items: list[McpSessionView]
    generated_at: datetime
