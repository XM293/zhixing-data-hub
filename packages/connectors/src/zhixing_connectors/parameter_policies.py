"""Versioned Lingxing parameter policies; contains no credentials or business values."""
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Literal, cast

from .official_contracts import OFFICIAL_CONTRACT_VERSION

_PAYLOAD = json.loads(files(__package__).joinpath(
    "lingxing_parameter_policies.json").read_text(encoding="utf-8"))
PARAMETER_POLICY_VERSION = str(_PAYLOAD["policy_version"])
assert _PAYLOAD["official_contract_version"] == OFFICIAL_CONTRACT_VERSION


RuleStrategy = Literal[
    "dependency", "calendar", "manual", "enum",
    "paired_dependency", "provided_by_pair",
]
PolicyStatus = Literal["ready_for_bounded_fanout", "manual_required"]
Combination = Literal["bounded_product", "source_tuple"]


@dataclass(frozen=True, slots=True)
class ParameterRule:
    field: str
    strategy: RuleStrategy
    value_types: tuple[str, ...] = ()
    values: tuple[str, ...] = ()
    unit: str | None = None
    purpose: str | None = None
    reason: str | None = None
    value_field: str | None = None
    dimensions: tuple[tuple[str, tuple[str, ...]], ...] = ()
    allow_empty: bool = False


@dataclass(frozen=True, slots=True)
class ResourceParameterPolicy:
    resource_key: str
    operation_id: str
    wave: str
    status: PolicyStatus
    combination: Combination
    max_partitions_per_batch: int
    rules: tuple[ParameterRule, ...]


def _strings(value: object) -> tuple[str, ...]:
    assert isinstance(value, list)
    return tuple(str(item) for item in value)


def _rule(value: dict[str, object]) -> ParameterRule:
    dimensions = value.get("dimensions") or {}
    assert isinstance(dimensions, dict)
    return ParameterRule(
        field=str(value["field"]),
        strategy=cast(RuleStrategy, str(value["strategy"])),
        value_types=_strings(value.get("value_types") or []),
        values=_strings(value.get("values") or []),
        unit=str(value["unit"]) if value.get("unit") is not None else None,
        purpose=str(value["purpose"]) if value.get("purpose") is not None else None,
        reason=str(value["reason"]) if value.get("reason") is not None else None,
        value_field=(str(value["value_field"])
                     if value.get("value_field") is not None else None),
        dimensions=tuple((str(key), _strings(choices))
                         for key, choices in sorted(dimensions.items())),
        allow_empty=bool(value.get("allow_empty", False)),
    )


_POLICIES = tuple(ResourceParameterPolicy(
    resource_key=str(item["resource_key"]), operation_id=str(item["operation_id"]),
    wave=str(item["wave"]), status=cast(PolicyStatus, str(item["status"])),
    combination=cast(Combination, str(item["combination"])),
    max_partitions_per_batch=int(item["max_partitions_per_batch"]),
    rules=tuple(_rule(rule) for rule in item["rules"]),
) for item in _PAYLOAD["resources"])
_BY_KEY = {item.resource_key: item for item in _POLICIES}


def parameter_policy(resource_key: str) -> ResourceParameterPolicy | None:
    return _BY_KEY.get(resource_key)


def parameter_policies() -> tuple[ResourceParameterPolicy, ...]:
    return _POLICIES
