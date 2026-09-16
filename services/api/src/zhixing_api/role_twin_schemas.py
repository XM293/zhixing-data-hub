from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from zhixing_api.models import ApiModel


class RoleTemplateVersionFields(ApiModel):
    role_title: str = Field(min_length=2, max_length=160)
    responsibilities: list[str] = Field(min_length=1, max_length=20)
    capability_boundaries: list[str] = Field(min_length=1, max_length=20)
    default_voice_guide: str = Field(min_length=10, max_length=4000)
    default_reasoning_guide: str = Field(min_length=10, max_length=4000)
    default_answer_policy: str = Field(min_length=10, max_length=4000)
    change_summary: str = Field(min_length=2, max_length=1000)


class RoleTemplateCreateRequest(RoleTemplateVersionFields):
    template_key: str = Field(
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]+$",
    )
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=2, max_length=1000)


class RoleTemplateVersionCreateRequest(RoleTemplateVersionFields):
    pass


class RoleTwinVersionFields(ApiModel):
    display_name: str = Field(min_length=2, max_length=160)
    voice_guide: str = Field(min_length=10, max_length=4000)
    reasoning_guide: str = Field(min_length=10, max_length=4000)
    answer_policy: str = Field(min_length=10, max_length=4000)
    provider: str = Field(min_length=2, max_length=64)
    model: str = Field(min_length=2, max_length=120)
    capabilities: list[str] = Field(min_length=1, max_length=20)
    change_summary: str = Field(min_length=2, max_length=1000)


class RoleTwinCreateRequest(RoleTwinVersionFields):
    twin_key: str = Field(
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]+$",
    )
    template_key: str = Field(min_length=3, max_length=100)
    owner_principal_key: str | None = Field(default=None, min_length=2, max_length=120)


class RoleTwinVersionCreateRequest(RoleTwinVersionFields):
    pass


class RoleVersionPublishRequest(ApiModel):
    reason: str = Field(min_length=2, max_length=1000)


class RoleTemplateVersionView(ApiModel):
    id: str
    version_number: int
    status: str
    role_title: str
    responsibilities: list[str]
    capability_boundaries: list[str]
    default_voice_guide: str
    default_reasoning_guide: str
    default_answer_policy: str
    change_summary: str
    created_by: str | None
    created_at: datetime
    published_at: datetime | None


class RoleTemplateView(ApiModel):
    id: str
    key: str
    name: str
    description: str
    status: str
    current_version_number: int | None
    twin_count: int
    versions: list[RoleTemplateVersionView]
    created_at: datetime
    updated_at: datetime


class RoleTwinVersionView(ApiModel):
    id: str
    version_number: int
    template_version_number: int
    status: str
    display_name: str
    voice_guide: str
    reasoning_guide: str
    answer_policy: str
    provider: str
    model: str
    capabilities: list[str]
    change_summary: str
    created_by: str | None
    created_at: datetime
    published_at: datetime | None


class RoleTwinInstanceView(ApiModel):
    id: str
    key: str
    template_key: str
    template_name: str
    owner_principal_key: str | None
    owner_name: str | None
    role_title: str
    status: str
    current_version_number: int | None
    run_count: int
    versions: list[RoleTwinVersionView]
    published_at: datetime | None
    updated_at: datetime


class RoleStudioStats(ApiModel):
    template_count: int
    instance_count: int
    published_template_count: int
    published_instance_count: int
    draft_version_count: int
    run_count: int


class RoleOwnerOption(ApiModel):
    key: str
    display_name: str
    status: str


class RoleStudioResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    stats: RoleStudioStats
    owners: list[RoleOwnerOption]
    templates: list[RoleTemplateView]
    twins: list[RoleTwinInstanceView]
    generated_at: datetime


class RoleConfigurationEventView(ApiModel):
    id: str
    configuration_type: Literal["template", "twin"]
    configuration_key: str
    version_id: str
    version_number: int
    event_type: Literal["created", "version-created", "published"]
    actor_name: str
    reason: str
    request_id: str
    run_id: str
    occurred_at: datetime


class RoleStudioMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    event: RoleConfigurationEventView
    studio: RoleStudioResponse
