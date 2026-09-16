from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from zhixing_connectors.catalog import (
    resource_spec,
    validate_partition_parameters,
    validate_resource_parameters,
)

from zhixing_api.data_center_schemas import SyncRequest
from zhixing_api.ingestion.parameter_fanout import validate_parameter_fanout_base


class ImportSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    resource_key: str = Field(min_length=1, max_length=120)
    resource_parameters: dict[str, str] = Field(default_factory=dict)
    window_start: datetime | None = None
    window_end: datetime | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> "ImportSelection":
        spec = resource_spec(self.resource_key)
        if spec is None or not spec.path:
            raise ValueError("source.resource_unknown")
        if spec.window_fields:
            validate_partition_parameters(spec, dict(self.resource_parameters))
            if (self.window_start is None or self.window_end is None
                    or self.window_start.tzinfo is None or self.window_end.tzinfo is None
                    or self.window_start >= self.window_end):
                raise ValueError("source.window_required")
        elif self.window_start is not None or self.window_end is not None:
            raise ValueError("source.window_unsupported")
        else:
            validate_resource_parameters(spec, dict(self.resource_parameters))
        return self


class ImportRequest(BaseModel):
    projection_mode: Literal["inline", "deferred"] = "inline"
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    client_request_key: str = Field(min_length=1, max_length=120)
    selections: list[ImportSelection] = Field(min_length=1, max_length=32)
    partition_days: int = Field(default=7, ge=1, le=366)

    @model_validator(mode="after")
    def validate_partition_size(self) -> "ImportRequest":
        if self.partition_days != 1 and any(
            (spec := resource_spec(item.resource_key)) is not None
            and len(spec.window_fields) == 1
            for item in self.selections
        ):
            raise ValueError("source.single_date_partition_requires_one_day")
        if any(
            (spec := resource_spec(item.resource_key)) is not None
            and bool(spec.window_fields)
            and self.partition_days > spec.max_window_days
            for item in self.selections
        ):
            raise ValueError("source.partition_exceeds_contract")
        return self


def plan_import(request: ImportRequest) -> list[SyncRequest]:
    result: list[SyncRequest] = []
    seen: set[str] = set()
    for selection in request.selections:
        start, end = selection.window_start, selection.window_end
        windows: list[tuple[datetime | None, datetime | None]] = []
        if start is None or end is None:
            windows.append((None, None))
        else:
            start, end = start.astimezone(UTC), end.astimezone(UTC)
            if (end - start) / timedelta(days=request.partition_days) > 128:
                raise ValueError("source.partition_limit")
            while start < end:
                boundary = min(end, start + timedelta(days=request.partition_days))
                windows.append((start, boundary))
                start = boundary
        for lower, upper in windows:
            item = SyncRequest(resource_key=selection.resource_key,
                               projection_mode=request.projection_mode,
                               resource_parameters=selection.resource_parameters,
                               window_start=lower, window_end=upper)
            identity = item.model_dump_json()
            if identity in seen:
                raise ValueError("source.partition_duplicate")
            seen.add(identity)
            result.append(item)
            if len(result) > 128:
                raise ValueError("source.partition_limit")
    return result


SNAPSHOT_RESOURCES = frozenset({"erp_users", "shops", "marketplaces", "concept_shops",
                              "product_tags", "logistics_channels", "product_styles",
                              "multiplatform_shops", "brands", "product_categories", "suppliers",
                              "products", "inventory", "warehouses_local",
                              "warehouses_overseas", "warehouses_platform", "warehouses_awd",
                              "listings", "country_subdivisions", "multiplatform_subdivisions",
                              "product_attributes", "head_logistics_providers", "warehouse_bins",
                              "fba_inventory", "advertising"})


def schedule_strategy(key: str) -> str | None:
    spec = resource_spec(key)
    if spec is not None and spec.schedule_strategy:
        return spec.schedule_strategy
    return ("snapshot" if key in SNAPSHOT_RESOURCES or (
        spec is not None and spec.scope_kind is not None and not spec.window_fields
    ) else None)


class ScheduleRequest(BaseModel):
    projection_mode: Literal["inline", "deferred"] = "inline"
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    name: str = Field(min_length=1, max_length=120)
    resource_key: str
    resource_parameters: dict[str, str] = Field(default_factory=dict)
    strategy: Literal["updated_utc", "source_window", "snapshot"]
    status: Literal["paused", "active"] = "paused"
    interval_seconds: int = Field(default=300, ge=60, le=86400)
    overlap_seconds: int = Field(default=300, ge=1, le=86400)
    safety_lag_seconds: int = Field(default=120, ge=0, le=3600)
    reconcile_days: int = Field(default=7, ge=1, le=30)
    initial_start: datetime | None = None

    @model_validator(mode="after")
    def validate_strategy(self) -> "ScheduleRequest":
        spec = resource_spec(self.resource_key)
        if spec is None:
            raise ValueError("source.resource_unknown")
        expected = schedule_strategy(self.resource_key)
        if expected != self.strategy:
            raise ValueError("source.schedule_strategy_unconfirmed")
        if self.strategy in {"updated_utc", "source_window"}:
            try:
                validate_partition_parameters(spec, dict(self.resource_parameters))
            except ValueError:
                validate_parameter_fanout_base(self.resource_key, self.resource_parameters)
            if self.initial_start is None or self.initial_start.tzinfo is None:
                raise ValueError("source.incremental_strategy_unconfirmed")
        elif self.initial_start is not None:
            raise ValueError("source.snapshot_strategy_unconfirmed")
        else:
            try:
                validate_resource_parameters(spec, dict(self.resource_parameters))
            except ValueError:
                validate_parameter_fanout_base(self.resource_key, self.resource_parameters)
        return self
