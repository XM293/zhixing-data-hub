from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.data_models import ExternalSystem, MappingConflict
from zhixing_api.errors import ApiProblem


def mark_resolved(session: Session, source: ExternalSystem, resource: str,
                  key: str, manifest: str) -> None:
    rows = session.scalars(select(MappingConflict).where(
        MappingConflict.enterprise_id == source.enterprise_id,
        MappingConflict.external_system_id == source.id,
        MappingConflict.resource_key == resource,
        MappingConflict.external_object_key == key,
    ).with_for_update())
    for row in rows:
        row.resolution = {**(row.resolution or {}), "resolved_manifest_id": manifest}


def review_conflict(session: Session, conflict: MappingConflict, *,
                    status: str, principal_id: str) -> None:
    if status not in {"approved", "rejected"}:
        raise ValueError("conflict.status_invalid")
    if status == "approved" and not (conflict.resolution or {}).get("resolved_manifest_id"):
        raise ApiProblem(status_code=409, code="mapping_conflict.unresolved",
                         message="冲突尚未通过重新映射验证")
    conflict.status = status
    conflict.reviewed_by = principal_id
    conflict.reviewed_at = datetime.now(UTC)
    session.flush()
