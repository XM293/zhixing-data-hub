from datetime import date, datetime
from typing import Literal

from pydantic import Field

from zhixing_api.models import ApiModel


class AIProviderProbeRequest(ApiModel):
    model: str | None = Field(default=None, min_length=2, max_length=120)


class AIProviderConfigView(ApiModel):
    provider_key: str
    label: str
    protocol: str
    endpoint_kind: Literal["official", "private-compatible"]
    enabled: bool
    configured: bool
    model: str
    timeout_seconds: float
    capabilities: list[str]


class AIProviderProbeRunView(ApiModel):
    id: str
    provider_key: str
    model: str
    protocol: str
    structured_output_supported: bool
    status: Literal["succeeded", "failed"]
    duration_ms: int
    input_tokens: int | None
    output_tokens: int | None
    error_code: str | None
    error_message: str | None
    actor_name: str
    request_id: str
    run_id: str
    created_at: datetime


class AgentRuntimeConfigView(ApiModel):
    runtime_key: str
    label: str
    protocol: str
    enabled: bool
    command_available: bool
    model: str | None
    timeout_seconds: float
    capabilities: list[str]
    default_sandbox: str
    approval_policy: str


class AgentRuntimeProbeRunView(ApiModel):
    id: str
    runtime_key: str
    protocol: str
    command_version: str | None
    initialized: bool
    status: Literal["succeeded", "failed"]
    duration_ms: int
    error_code: str | None
    error_message: str | None
    actor_name: str
    request_id: str
    run_id: str
    created_at: datetime


class AgentRuntimeSessionView(ApiModel):
    id: str
    agent_run_id: str
    runtime_key: str
    runtime_thread_id: str
    runtime_session_id: str | None
    mcp_gateway_session_id: str | None
    status: str
    model: str | None
    turn_count: int
    event_count: int
    latest_event_type: str | None
    can_cancel: bool
    failure_code: str | None
    failure_message: str | None
    request_id: str
    run_id: str
    created_at: datetime
    completed_at: datetime | None


class AgentRuntimeApprovalView(ApiModel):
    id: str
    runtime_session_id: str
    agent_run_id: str
    request_method: str
    item_id: str | None
    skill_key: str | None
    skill_version: int | None
    tool_keys: list[str]
    status: Literal["pending", "approved", "declined", "expired"]
    decision: str | None
    requested_at: datetime
    decided_at: datetime | None


class AgentRuntimeTurnView(ApiModel):
    id: str
    agent_run_id: str
    mcp_gateway_session_id: str | None
    runtime_turn_id: str
    turn_number: int
    status: str
    model: str | None
    evidence_count: int
    context_count: int
    duration_ms: int
    failure_code: str | None
    failure_message: str | None
    request_id: str
    run_id: str
    started_at: datetime
    completed_at: datetime | None


class AgentRuntimeEventView(ApiModel):
    id: str
    runtime_turn_id: str | None
    sequence: int
    runtime_sequence: int
    event_type: str
    status: str
    event_payload: dict[str, object]
    occurred_at: datetime


class AgentRuntimeSessionDetailResponse(ApiModel):
    schema_version: Literal[1] = 1
    session: AgentRuntimeSessionView
    actor_name: str
    twin_name: str
    role_twin_version_number: int | None
    turns: list[AgentRuntimeTurnView]
    events: list[AgentRuntimeEventView]
    generated_at: datetime


class AgentRuntimeCancelResponse(ApiModel):
    schema_version: Literal[1] = 1
    accepted: Literal[True] = True
    session_id: str
    agent_run_id: str
    status: Literal["interrupt_requested"] = "interrupt_requested"


class AIRuntimeStats(ApiModel):
    total_runs: int
    successful_runs: int
    degraded_runs: int
    success_rate: float
    average_duration_ms: int
    input_tokens: int
    output_tokens: int
    token_coverage_rate: float
    runs_last_24h: int
    meeting_runs: int
    answer_runs: int
    customer_service_runs: int
    customer_operation_runs: int
    evaluation_batches: int
    probe_runs: int


class AIRunTypeStat(ApiModel):
    run_type: str
    label: str
    total_runs: int
    successful_runs: int
    degraded_runs: int
    average_duration_ms: int
    input_tokens: int
    output_tokens: int


class AIModelStat(ApiModel):
    provider: str
    model: str
    total_runs: int
    successful_runs: int
    degraded_runs: int
    average_duration_ms: int
    input_tokens: int
    output_tokens: int


class AIDailyStat(ApiModel):
    business_date: date
    total_runs: int
    successful_runs: int
    degraded_runs: int
    input_tokens: int
    output_tokens: int


class AILatestRunView(ApiModel):
    id: str
    category: Literal["agent", "analysis", "customer-operation"]
    run_type: str
    label: str
    status: str
    execution_mode: str
    provider: str
    model: str
    duration_ms: int
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime


class AIOperationsOverviewResponse(ApiModel):
    schema_version: Literal[1] = 1
    enterprise_id: str
    provider: AIProviderConfigView
    runtime: AgentRuntimeConfigView
    stats: AIRuntimeStats
    run_types: list[AIRunTypeStat]
    models: list[AIModelStat]
    daily: list[AIDailyStat] = Field(max_length=14)
    latest_runs: list[AILatestRunView] = Field(max_length=30)
    probes: list[AIProviderProbeRunView] = Field(max_length=20)
    runtime_probes: list[AgentRuntimeProbeRunView] = Field(max_length=20)
    runtime_sessions: list[AgentRuntimeSessionView] = Field(max_length=30)
    runtime_approvals: list[AgentRuntimeApprovalView] = Field(max_length=30)
    generated_at: datetime
