from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from importlib.resources import files
from typing import Literal, cast


@dataclass(frozen=True)
class OfficialField:
    path: tuple[str, ...]
    name: str
    required: bool
    type: str
    description: str


@dataclass(frozen=True)
class OfficialContract:
    id: str
    method: Literal["GET", "POST"]
    path: str
    wave: Literal["W0", "W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8"]
    documentation_url: str
    document_sha256: str
    retrieved_sha256: str
    request_fields: tuple[OfficialField, ...]
    response_fields: tuple[OfficialField, ...]
    required_fields: tuple[str, ...]
    scope_fields: tuple[str, ...]
    pagination_mode: Literal["none", "offset_length", "offset_limit", "page", "unknown"]
    window_fields: tuple[str, ...]
    window_format: Literal["date", "datetime", "unknown"]
    rows_path: tuple[str, ...]
    total_path: tuple[str, ...]
    rate_capacity: int | None
    max_window_days: int | None
    retention_days: int | None
    extraction_status: Literal["confirmed", "schema_pending", "document_changed"]

    @property
    def runtime_key(self) -> str:
        return self.id.replace("lingxing_op_", "official_")


def _field(item: dict[str, object]) -> OfficialField:
    return OfficialField(path=tuple(str(value) for value in cast(list[object], item["path"])),
        name=str(item["name"]), required=bool(item["required"]), type=str(item["type"]),
        description=str(item["description"]))


def _load() -> tuple[str, tuple[OfficialContract, ...]]:
    path = files("zhixing_connectors").joinpath("lingxing_official_contracts.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise RuntimeError("lingxing.contract_schema_unsupported")
    operations = tuple(OfficialContract(
        id=str(item["id"]), method=cast(Literal["GET", "POST"], item["method"]),
        path=str(item["path"]),
        wave=cast(Literal["W0", "W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8"],
                  item.get("wave", "W8")),
        documentation_url=str(item["documentation_url"]),
        document_sha256=str(item["document_sha256"]),
        retrieved_sha256=str(item["retrieved_sha256"]),
        request_fields=tuple(_field(value) for value in item["request_fields"]),
        response_fields=tuple(_field(value) for value in item["response_fields"]),
        required_fields=tuple(str(value) for value in item["required_fields"]),
        scope_fields=tuple(str(value) for value in item["scope_fields"]),
        pagination_mode=cast(Literal["none", "offset_length", "offset_limit", "page", "unknown"],
                             item["pagination_mode"]),
        window_fields=tuple(str(value) for value in item["window_fields"]),
        window_format=cast(Literal["date", "datetime", "unknown"], item["window_format"]),
        rows_path=tuple(str(value) for value in item["rows_path"]),
        total_path=tuple(str(value) for value in item["total_path"]),
        rate_capacity=cast(int | None, item["rate_capacity"]),
        max_window_days=cast(int | None, item.get("max_window_days")),
        retention_days=cast(int | None, item.get("retention_days")),
        extraction_status=cast(
            Literal["confirmed", "schema_pending", "document_changed"],
            item["extraction_status"]),
    ) for item in payload["operations"])
    if len({item.id for item in operations}) != len(operations):
        raise RuntimeError("lingxing.contract_duplicate")
    return str(payload["contract_version"]), operations


OFFICIAL_CONTRACT_VERSION, _CONTRACTS = _load()
_BY_ID = {item.id: item for item in _CONTRACTS}
_BY_RUNTIME_KEY = {item.runtime_key: item for item in _CONTRACTS}


def official_contracts() -> tuple[OfficialContract, ...]:
    return _CONTRACTS


def official_contract(identity: str) -> OfficialContract | None:
    return _BY_ID.get(identity) or _BY_RUNTIME_KEY.get(identity)


def contract_summary() -> dict[str, object]:
    return {
        "official_contracts": len(_CONTRACTS),
        "extraction_statuses": dict(Counter(item.extraction_status for item in _CONTRACTS)),
        "paginated_contracts": sum(item.pagination_mode != "none" for item in _CONTRACTS),
        "windowed_contracts": sum(bool(item.window_fields) for item in _CONTRACTS),
        "scoped_contracts": sum(bool(item.scope_fields) for item in _CONTRACTS),
    }
