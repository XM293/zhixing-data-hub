from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from zhixing_api.models import ApiModel


def _default_object_schema() -> dict[str, object]:
    return {"type": "object"}


class SkillVersionFields(ApiModel):
    instructions: str = Field(min_length=10, max_length=12000)
    tool_keys: list[str] = Field(min_length=1, max_length=32)
    input_schema: dict[str, object] = Field(default_factory=_default_object_schema)
    output_schema: dict[str, object] = Field(default_factory=_default_object_schema)
    change_summary: str = Field(min_length=2, max_length=1000)

    @field_validator("tool_keys")
    @classmethod
    def normalize_tool_keys(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(values) or len(normalized) != len(set(normalized)):
            raise ValueError("Skill 工具键不能为空或重复")
        return sorted(normalized)


class SkillCreateRequest(SkillVersionFields):
    skill_key: str = Field(
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]+$",
    )
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=2, max_length=1000)


class SkillVersionCreateRequest(SkillVersionFields):
    pass


class SkillPublishRequest(ApiModel):
    reason: str = Field(min_length=2, max_length=1000)


class SkillVersionView(ApiModel):
    id: str
    version_number: int
    status: Literal["draft", "published", "retired"]
    instructions: str
    tool_keys: list[str]
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    change_summary: str
    created_by: str | None
    created_at: datetime
    published_at: datetime | None


class SkillView(ApiModel):
    id: str
    key: str
    name: str
    description: str
    status: Literal["draft", "published", "retired"]
    current_version_number: int | None
    versions: list[SkillVersionView]
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class SkillStudioStats(ApiModel):
    skill_count: int
    published_skill_count: int
    draft_version_count: int
    published_version_count: int
    registered_tool_count: int


class SkillStudioResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    stats: SkillStudioStats
    skills: list[SkillView]
    available_tools: list[str]
    generated_at: datetime


class SkillConfigurationEventView(ApiModel):
    id: str
    skill_key: str
    version_number: int
    event_type: Literal["created", "version-created", "published"]
    actor_name: str
    reason: str
    request_id: str
    run_id: str
    occurred_at: datetime


class SkillStudioMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    event: SkillConfigurationEventView
    studio: SkillStudioResponse
