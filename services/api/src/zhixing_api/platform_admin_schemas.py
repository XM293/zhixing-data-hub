from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MutationRequest(ApiModel):
    schema_version: Literal[1] = 1
    client_request_key: str = Field(min_length=8, max_length=160)
    reason: str = Field(min_length=3, max_length=500)


class JobAttemptView(ApiModel):
    attempt_no: int
    worker_id: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None


class BackgroundJobView(ApiModel):
    id: str
    job_type: str
    status: str
    priority: int
    attempt: int
    max_attempts: int
    continuation_count: int = 0
    continuation_progress: int = 0
    initiator_id: str
    scope_type: str
    scope_id: str
    request_id: str
    run_id: str
    worker_id: str | None
    last_error_code: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None


class JobAdminResponse(ApiModel):
    schema_version: Literal[1] = 1
    stats: dict[str, int]
    job_types: list[str]
    items: list[BackgroundJobView]
    generated_at: datetime


class JobDetailResponse(ApiModel):
    schema_version: Literal[1] = 1
    job: BackgroundJobView
    payload: dict[str, object]
    result: dict[str, object] | None
    required_permissions: list[str]
    permission_set_version: str
    attempts: list[JobAttemptView]


class JobRetryRequest(MutationRequest):
    expected_attempt: int = Field(ge=0)


class JobRetryResponse(ApiModel):
    schema_version: Literal[1] = 1
    operation: Literal["retry_queued"] = "retry_queued"
    job: BackgroundJobView
    event_id: str
    replayed: bool


class ParameterView(ApiModel):
    parameter_key: str
    group_key: str
    label: str
    value_type: str
    value: object
    status: str
    revision: int
    updated_at: datetime


class DictionaryItemView(ApiModel):
    item_key: str
    label: str
    value: object
    sort_order: int
    status: str
    revision: int


class DictionaryView(ApiModel):
    dictionary_key: str
    name: str
    status: str
    revision: int
    items: list[DictionaryItemView]


class PlatformConfigResponse(ApiModel):
    schema_version: Literal[1] = 1
    parameters: list[ParameterView]
    dictionaries: list[DictionaryView]
    generated_at: datetime


class ParameterUpdateRequest(MutationRequest):
    expected_revision: int = Field(ge=1)
    value: object
    status: Literal["active", "inactive"]


class DictionaryItemUpsertRequest(MutationRequest):
    expected_revision: int | None = Field(default=None, ge=1)
    label: str = Field(min_length=1, max_length=160)
    value: object
    sort_order: int = Field(default=0, ge=0, le=100000)
    status: Literal["active", "inactive"] = "active"


class PlatformConfigMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    operation: Literal["configured"] = "configured"
    event_id: str
    replayed: bool


class NotificationView(ApiModel):
    id: str
    category: str
    title: str
    body: str
    severity: str
    status: str
    action_route: str | None
    created_at: datetime
    read_at: datetime | None
    deliveries: dict[str, str]


class NotificationInboxResponse(ApiModel):
    schema_version: Literal[1] = 1
    stats: dict[str, int]
    items: list[NotificationView]
    generated_at: datetime


class NotificationReadRequest(ApiModel):
    schema_version: Literal[1] = 1
    read: bool = True


class NotificationPublishRequest(MutationRequest):
    principal_ids: list[str] = Field(min_length=1, max_length=100)
    category: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=1000)
    severity: Literal["info", "success", "warning", "critical"] = "info"
    action_route: str | None = Field(default=None, max_length=300)
    channels: list[Literal["inbox", "feishu", "wechat"]] = Field(default=["inbox"])


class NotificationMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    affected: int
    event_id: str | None = None
    replayed: bool = False


class FileAssetView(ApiModel):
    id: str
    asset_key: str
    file_name: str
    media_type: str
    size_bytes: int
    checksum_sha256: str
    storage_provider: str
    category: str
    status: str
    uploader_name: str
    required_permission: str
    scope_type: str
    scope_id: str
    revision: int
    created_at: datetime


class FileAssetListResponse(ApiModel):
    schema_version: Literal[1] = 1
    stats: dict[str, int]
    items: list[FileAssetView]
    generated_at: datetime


class FileAssetUploadRequest(MutationRequest):
    asset_key: str = Field(min_length=3, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    file_name: str = Field(min_length=1, max_length=300)
    media_type: str = Field(min_length=3, max_length=160)
    content_base64: str = Field(min_length=1)
    category: str = Field(min_length=2, max_length=64)
    required_permission: str = Field(min_length=3, max_length=120)
    scope_type: str = Field(min_length=2, max_length=48)
    scope_id: str = Field(min_length=1, max_length=160)


class FileAssetMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    asset: FileAssetView
    event_id: str
    replayed: bool


class BulkExchangeRowView(ApiModel):
    row_number: int
    status: str
    normalized_data: dict[str, object]
    errors: list[dict[str, object]]


class BulkExchangeJobView(ApiModel):
    id: str
    operation: str
    dataset_key: str
    file_format: str
    status: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    applied_rows: int
    validation_summary: dict[str, object]
    created_at: datetime
    completed_at: datetime | None


class BulkExchangeListResponse(ApiModel):
    schema_version: Literal[1] = 1
    datasets: list[str]
    items: list[BulkExchangeJobView]
    generated_at: datetime


class BulkExchangeDetailResponse(ApiModel):
    schema_version: Literal[1] = 1
    job: BulkExchangeJobView
    rows: list[BulkExchangeRowView]


class BulkExchangePreflightRequest(MutationRequest):
    dataset_key: Literal["platform.dictionary-items"]
    file_format: Literal["csv"] = "csv"
    content: str = Field(min_length=1, max_length=5_000_000)


class BulkExchangeCommitRequest(MutationRequest):
    pass


class BulkExchangeExportRequest(MutationRequest):
    dataset_key: Literal["platform.dictionary-items"]
    file_format: Literal["csv"] = "csv"


class BulkExchangeMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    job: BulkExchangeJobView
    event_id: str
    replayed: bool


class OrgTreeNode(ApiModel):
    id: str
    org_key: str
    name: str
    unit_type: str
    status: str
    member_count: int
    children: list[OrgTreeNode]


class PrincipalOption(ApiModel):
    id: str
    display_name: str
    account_key: str
    organization: str
    position: str


class AccessDelegationView(ApiModel):
    id: str
    delegation_key: str
    delegator_principal_id: str
    delegator_name: str
    delegatee_principal_id: str
    delegatee_name: str
    permissions: list[str]
    scopes: list[dict[str, object]]
    status: str
    valid_from: datetime
    valid_to: datetime
    reason: str
    revision: int
    created_at: datetime


class AccessGovernanceResponse(ApiModel):
    schema_version: Literal[1] = 1
    org_tree: list[OrgTreeNode]
    principals: list[PrincipalOption]
    delegations: list[AccessDelegationView]
    permission_catalog: list[str]
    generated_at: datetime


class AccessDelegationCreateRequest(MutationRequest):
    delegation_key: str = Field(min_length=3, max_length=160)
    delegator_principal_id: str = Field(min_length=3, max_length=64)
    delegatee_principal_id: str = Field(min_length=3, max_length=64)
    permissions: list[str] = Field(min_length=1, max_length=50)
    scopes: list[dict[str, object]] = Field(default_factory=list, max_length=50)
    valid_from: datetime
    valid_to: datetime


class AccessDelegationRevokeRequest(MutationRequest):
    expected_revision: int = Field(ge=1)


class AccessDelegationMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    delegation: AccessDelegationView
    event_id: str
    replayed: bool


class PermissionExplanationResponse(ApiModel):
    schema_version: Literal[1] = 1
    principal_id: str
    principal_name: str
    direct_roles: list[str]
    direct_permissions: list[str]
    delegated_permissions: list[str]
    effective_permissions: list[str]
    scopes: list[dict[str, object]]
    active_delegations: list[str]
    generated_at: datetime
