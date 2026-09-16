from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from zhixing_api.analysis_schemas import AnalysisScopeView
from zhixing_api.models import ApiModel

AutoProposePriority = Literal["off", "urgent", "high"]
ReviewPlanStatus = Literal["active", "paused"]
ReviewRunStatus = Literal["preparing", "queued", "running", "succeeded", "failed"]


class StoreReviewPlanRequest(ApiModel):
    name: str = Field(min_length=2, max_length=120)
    scope_key: str = Field(min_length=2, max_length=160)
    window_days: int = Field(default=30, ge=7, le=90)
    timezone: str = Field(default="Asia/Shanghai", min_length=3, max_length=64)
    local_time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    weekdays: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5], min_length=1)
    auto_propose_min_priority: AutoProposePriority = "high"
    client_request_key: str = Field(min_length=8, max_length=160)

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        normalized = sorted(set(value))
        if len(normalized) != len(value) or any(day < 1 or day > 7 for day in normalized):
            raise ValueError("weekdays 必须是 1 到 7 之间且不重复的星期编号")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone 必须是有效的 IANA 时区") from exc
        return value


class StoreReviewPlanActionRequest(ApiModel):
    action: Literal["pause", "resume", "run_now"]
    expected_version: int | None = Field(default=None, ge=1)
    idempotency_key: str = Field(min_length=8, max_length=200)


class StoreReviewPlanView(ApiModel):
    key: str
    name: str
    scope: AnalysisScopeView
    window_days: int
    timezone: str
    local_time: str
    weekdays: list[int]
    auto_propose_min_priority: AutoProposePriority
    status: ReviewPlanStatus
    next_run_at: datetime | None
    last_enqueued_at: datetime | None
    created_by_name: str
    version: int
    created_at: datetime
    updated_at: datetime


class StoreReviewScheduleRunView(ApiModel):
    id: str
    plan_key: str
    plan_name: str
    scope: AnalysisScopeView
    business_date: date
    trigger_type: Literal["scheduled", "manual"]
    status: ReviewRunStatus
    background_job_id: str | None
    background_job_attempt: int
    analysis_run_id: str | None
    brief_id: str | None
    proposal_count: int
    execution_mode: Literal["model", "evidence-fallback"] | None
    error_code: str | None
    error_message: str | None
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class StoreReviewScheduleStats(ApiModel):
    plan_count: int
    active_plan_count: int
    queued_or_running_count: int
    succeeded_count: int
    failed_count: int
    pending_proposal_count: int


class StoreReviewScheduleResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    actor_name: str
    can_manage: bool
    available_scopes: list[AnalysisScopeView]
    stats: StoreReviewScheduleStats
    plans: list[StoreReviewPlanView]
    runs: list[StoreReviewScheduleRunView]
    generated_at: datetime


class StoreReviewPlanMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    schedule: StoreReviewScheduleResponse
