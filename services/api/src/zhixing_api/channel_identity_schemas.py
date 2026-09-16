from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from zhixing_api.models import ApiModel


class ChannelIdentityStats(ApiModel):
    total: int
    bound: int
    unknown: int
    suspended: int
    seen_last_24h: int
    channel_count: int


class ChannelIdentityAccountView(ApiModel):
    principal_id: str
    account_key: str
    display_name: str
    login_name: str
    organization: str
    position: str


class ChannelIdentityView(ApiModel):
    id: str
    channel_key: str
    channel_label: str
    external_tenant_key: str
    external_identity_hint: str
    external_identity_fingerprint: str
    observed_display_name: str | None
    principal_id: str | None
    principal_name: str | None
    principal_account_key: str | None
    binding_status: Literal["unknown", "bound", "suspended"]
    version: int
    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: datetime


class ChannelIdentityEventView(ApiModel):
    id: str
    event_type: str
    channel_identity_id: str
    actor_name: str
    before_status: str
    after_status: str
    before_principal_name: str | None
    after_principal_name: str | None
    reason: str
    request_id: str
    run_id: str
    occurred_at: datetime


class ChannelIdentityAdminResponse(ApiModel):
    schema_version: Literal[1] = 1
    enterprise_id: str
    stats: ChannelIdentityStats
    accounts: list[ChannelIdentityAccountView]
    items: list[ChannelIdentityView]
    recent_events: list[ChannelIdentityEventView] = Field(max_length=100)
    generated_at: datetime


class ChannelIdentityConfigureRequest(ApiModel):
    schema_version: Literal[1] = 1
    client_request_key: str = Field(min_length=8, max_length=160)
    expected_version: int = Field(ge=1)
    principal_id: str | None = Field(default=None, max_length=64)
    status: Literal["active", "suspended"]
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("client_request_key", "reason")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("principal_id")
    @classmethod
    def normalize_principal_id(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


class ChannelIdentityMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    operation: Literal["configured"] = "configured"
    identity: ChannelIdentityView
    event_id: str
    replayed: bool
