from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from importlib.resources import files
from typing import Literal, cast

from .catalog import RESOURCE_CATALOG

ReviewStatus = Literal[
    "read_candidate", "read_only_confirmed", "read_only_schema_pending"
]
ExecutionStatus = Literal[
    "metadata_only", "runtime_raw_only", "runtime_projectable"
]
SchemaStatus = Literal["schema_pending", "confirmed"]
Wave = Literal["W0", "W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8"]


@dataclass(frozen=True)
class OfficialOperation:
    id: str
    title: str
    document_path: str
    documentation_url: str
    method: Literal["GET", "POST"]
    path: str
    wave: Wave
    review_status: ReviewStatus
    execution_status: ExecutionStatus
    schema_status: SchemaStatus
    resource_keys: tuple[str, ...]
    document_sha256: str

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["resource_keys"] = list(self.resource_keys)
        return value


def _load() -> tuple[str, tuple[OfficialOperation, ...]]:
    path = files("zhixing_connectors").joinpath("lingxing_official_registry.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise RuntimeError("lingxing.registry_schema_unsupported")
    operations = tuple(
        OfficialOperation(
            id=str(item["id"]),
            title=str(item["title"]),
            document_path=str(item["document_path"]),
            documentation_url=str(item["documentation_url"]),
            method=cast(Literal["GET", "POST"], item["method"]),
            path=str(item["path"]),
            wave=cast(Wave, item["wave"]),
            review_status=cast(ReviewStatus, item["review_status"]),
            execution_status=cast(ExecutionStatus, item["execution_status"]),
            schema_status=cast(SchemaStatus, item["schema_status"]),
            resource_keys=tuple(str(key) for key in item["resource_keys"]),
            document_sha256=str(item["document_sha256"]),
        )
        for item in payload["operations"]
    )
    if len({(item.method, item.path) for item in operations}) != len(operations):
        raise RuntimeError("lingxing.registry_operation_duplicate")
    return str(payload["registry_version"]), operations


OFFICIAL_REGISTRY_VERSION, _OPERATIONS = _load()
_BY_ID = {item.id: item for item in _OPERATIONS}


def official_operations() -> tuple[OfficialOperation, ...]:
    return _OPERATIONS


def official_operation(operation_id: str) -> OfficialOperation | None:
    return _BY_ID.get(operation_id)


def registry_summary() -> dict[str, object]:
    execution = Counter(item.execution_status for item in _OPERATIONS)
    return {
        "official_read_operations": len(_OPERATIONS),
        "runtime_operations": len(_OPERATIONS) - execution["metadata_only"],
        "runtime_resources": len(RESOURCE_CATALOG),
        "metadata_only_operations": execution["metadata_only"],
        "runtime_raw_only_operations": execution["runtime_raw_only"],
        "runtime_projectable_operations": execution["runtime_projectable"],
        "waves": dict(sorted(Counter(item.wave for item in _OPERATIONS).items())),
    }
