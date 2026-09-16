"""Resolve reviewed Lingxing parameters into bounded, deterministic partitions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import islice, product
from math import prod
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from zhixing_connectors.catalog import (
    ResourceSpec,
    partition_parameter_names,
    resource_spec,
    validate_partition_parameters,
    validate_resource_parameters,
)
from zhixing_connectors.parameter_policies import (
    PARAMETER_POLICY_VERSION,
    ParameterRule,
    parameter_policy,
)

from zhixing_api.data_models import SourceDependencyTuple, SourceDependencyValue

MAX_DEPENDENCY_VALUES = 10_000


@dataclass(frozen=True, slots=True)
class ParameterFanoutPage:
    resource_key: str
    policy_version: str
    items: list[dict[str, str]]
    total: int
    offset: int
    limit: int
    next_offset: int | None
    waiting_code: str | None = None


def validate_parameter_fanout_base(
    resource_key: str, parameters: dict[str, str]
) -> dict[str, str]:
    """Validate the immutable scope portion while generated parameters stay server-owned."""
    spec = resource_spec(resource_key)
    policy = parameter_policy(resource_key)
    if spec is None or policy is None or policy.status != "ready_for_bounded_fanout":
        raise ValueError("source.parameter_policy_missing")
    generated = {rule.field for rule in policy.rules}
    generated.update(rule.value_field for rule in policy.rules if rule.value_field is not None)
    expected = set(partition_parameter_names(spec)) - generated
    if set(parameters) != expected:
        raise ValueError("resource.parameters_invalid")
    if any(isinstance(value, bool) or not isinstance(value, (str, int))
           or not str(value).strip() or len(str(value)) > 500
           for value in parameters.values()):
        raise ValueError("resource.parameters_invalid")
    if spec.scope_kind == "store" and spec.scope_parameter:
        raw = str(parameters.get(spec.scope_parameter, ""))
        values = [item.strip() for item in raw.split(",") if item.strip()]
        if (not values or any(not item.isdigit() or int(item) <= 0 for item in values)
                or (spec.scope_parameter_mode == "scalar" and len(values) != 1)):
            raise ValueError("resource.request_scope_invalid")
    return {key: str(value) for key, value in parameters.items()}


def _scope_keys(spec: ResourceSpec, parameters: dict[str, str]) -> tuple[str, ...]:
    if spec.scope_kind != "store" or not spec.scope_parameter:
        return ()
    raw = parameters.get(spec.scope_parameter)
    if raw is None:
        return ()
    values = [item.strip() for item in str(raw).split(",") if item.strip()]
    prefix = "store:multiplatform:" if spec.scope_namespace == "multiplatform" else "store:"
    return tuple(f"{prefix}{item}" for item in dict.fromkeys(values))


def _scope_predicate(model: Any, scope_keys: tuple[str, ...]) -> ColumnElement[bool]:
    predicates = [model.scope_kind == "source"]
    if scope_keys:
        predicates.append(model.scope_external_key.in_(scope_keys))
    return or_(*predicates)


def _dependency_choices(session: Session, *, external_system_id: str,
                        rule: ParameterRule, scope_keys: tuple[str, ...],
                        observed_before: datetime) -> list[dict[str, str]]:
    values: list[str] = []
    seen: set[str] = set()
    for value_type in rule.value_types:
        count = session.scalar(select(func.count()).select_from(SourceDependencyValue).where(
            SourceDependencyValue.external_system_id == external_system_id,
            SourceDependencyValue.value_type == value_type,
            SourceDependencyValue.status == "active",
            SourceDependencyValue.first_seen_at <= observed_before,
            _scope_predicate(SourceDependencyValue, scope_keys),
        )) or 0
        if count > MAX_DEPENDENCY_VALUES:
            raise ValueError("source.dependency_fanout_limit")
        rows = session.execute(select(
            SourceDependencyValue.external_value,
        ).where(
            SourceDependencyValue.external_system_id == external_system_id,
            SourceDependencyValue.value_type == value_type,
            SourceDependencyValue.status == "active",
            SourceDependencyValue.first_seen_at <= observed_before,
            _scope_predicate(SourceDependencyValue, scope_keys),
        ).order_by(SourceDependencyValue.value_hash)).scalars()
        for value in rows:
            if value not in seen:
                values.append(value)
                seen.add(value)
    return [{rule.field: value} for value in values]


def _tuple_choices(session: Session, *, external_system_id: str,
                   fields: tuple[str, ...], scope_keys: tuple[str, ...],
                   observed_before: datetime) -> list[dict[str, str]]:
    tuple_type = "+".join(fields)
    count = session.scalar(select(func.count()).select_from(SourceDependencyTuple).where(
        SourceDependencyTuple.external_system_id == external_system_id,
        SourceDependencyTuple.tuple_type == tuple_type,
        SourceDependencyTuple.status == "active",
        SourceDependencyTuple.first_seen_at <= observed_before,
        _scope_predicate(SourceDependencyTuple, scope_keys),
    )) or 0
    if count > MAX_DEPENDENCY_VALUES:
        raise ValueError("source.dependency_fanout_limit")
    rows = session.scalars(select(SourceDependencyTuple).where(
        SourceDependencyTuple.external_system_id == external_system_id,
        SourceDependencyTuple.tuple_type == tuple_type,
        SourceDependencyTuple.status == "active",
        SourceDependencyTuple.first_seen_at <= observed_before,
        _scope_predicate(SourceDependencyTuple, scope_keys),
    ).order_by(SourceDependencyTuple.tuple_hash))
    result: list[dict[str, str]] = []
    for row in rows:
        if set(row.tuple_values) == set(fields):
            result.append({field: str(row.tuple_values[field]) for field in fields})
    return result


def _paired_choices(session: Session, *, external_system_id: str,
                    rule: ParameterRule, scope_keys: tuple[str, ...],
                    observed_before: datetime) -> list[dict[str, str]]:
    if rule.value_field is None:
        raise ValueError("source.parameter_policy_invalid")
    result: list[dict[str, str]] = []
    for dimension, value_types in rule.dimensions:
        dependency_rule = ParameterRule(
            field=rule.value_field, strategy="dependency", value_types=value_types)
        for item in _dependency_choices(session, external_system_id=external_system_id,
                                        rule=dependency_rule, scope_keys=scope_keys,
                                        observed_before=observed_before):
            result.append({rule.field: dimension, **item})
    return result


def _calendar_choice(rule: ParameterRule, as_of: datetime) -> dict[str, str]:
    resolved = as_of.replace(tzinfo=UTC) if as_of.tzinfo is None else as_of.astimezone(UTC)
    if rule.unit == "day":
        return {rule.field: resolved.date().isoformat()}
    if rule.unit == "month":
        return {rule.field: resolved.strftime("%Y-%m")}
    raise ValueError("source.parameter_policy_invalid")


def plan_parameter_fanout(
    session: Session,
    *,
    external_system_id: str,
    resource_key: str,
    base_parameters: dict[str, str],
    as_of: datetime,
    dependency_as_of: datetime | None = None,
    offset: int,
    limit: int,
) -> ParameterFanoutPage:
    """Return one page of reviewed partitions without issuing an external request."""
    if offset < 0 or limit < 1 or limit > 64:
        raise ValueError("source.parameter_fanout_page_invalid")
    spec = resource_spec(resource_key)
    policy = parameter_policy(resource_key)
    if spec is None or policy is None:
        raise ValueError("source.parameter_policy_missing")
    if policy.status == "manual_required":
        return ParameterFanoutPage(
            resource_key, PARAMETER_POLICY_VERSION, [], 0, offset, limit, None,
            "source.parameters_manual_required")
    scope_keys = _scope_keys(spec, base_parameters)
    dependency_cutoff = dependency_as_of or as_of
    observed_before = (dependency_cutoff.replace(tzinfo=UTC)
                       if dependency_cutoff.tzinfo is None
                       else dependency_cutoff.astimezone(UTC))
    groups: list[list[dict[str, str]]] = []
    tuple_fields = tuple(rule.field for rule in policy.rules if rule.strategy == "dependency")
    if policy.combination == "source_tuple":
        choices = _tuple_choices(session, external_system_id=external_system_id,
                                 fields=tuple_fields, scope_keys=scope_keys,
                                 observed_before=observed_before)
        if not choices:
            return ParameterFanoutPage(
                resource_key, PARAMETER_POLICY_VERSION, [], 0, offset, limit, None,
                "source.dependency_values_unavailable")
        groups.append(choices)
    for rule in policy.rules:
        if rule.strategy in {"provided_by_pair", "manual"}:
            continue
        if rule.strategy == "dependency":
            if policy.combination == "source_tuple":
                continue
            choices = _dependency_choices(session, external_system_id=external_system_id,
                                           rule=rule, scope_keys=scope_keys,
                                           observed_before=observed_before)
        elif rule.strategy == "paired_dependency":
            choices = _paired_choices(session, external_system_id=external_system_id,
                                      rule=rule, scope_keys=scope_keys,
                                      observed_before=observed_before)
        elif rule.strategy == "enum":
            choices = [{rule.field: value} for value in rule.values]
        elif rule.strategy == "calendar":
            choices = [_calendar_choice(rule, as_of)]
        else:
            raise ValueError("source.parameter_policy_invalid")
        if not choices:
            return ParameterFanoutPage(
                resource_key, PARAMETER_POLICY_VERSION, [], 0, offset, limit, None,
                "source.dependency_values_unavailable")
        groups.append(choices)
    total = prod(len(group) for group in groups)
    items: list[dict[str, str]] = []
    for selected in islice(product(*groups), offset, offset + limit):
        merged = dict(base_parameters)
        for values in selected:
            if set(merged).intersection(values):
                raise ValueError("source.parameter_policy_conflict")
            merged.update(values)
        validated = (validate_partition_parameters(spec, dict(merged))
                     if spec.window_fields else validate_resource_parameters(spec, dict(merged)))
        items.append({key: str(value) for key, value in validated.items()})
    next_offset = offset + len(items) if offset + len(items) < total else None
    return ParameterFanoutPage(
        resource_key, PARAMETER_POLICY_VERSION, items, total, offset, limit, next_offset)
