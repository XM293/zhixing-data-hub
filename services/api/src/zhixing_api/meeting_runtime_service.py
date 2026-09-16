from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from zhixing_api.data_models import MeetingRuntimeRun, TwinMeetingParticipant
from zhixing_api.database import Database


def create_meeting_runtime_run(
    database: Database,
    *,
    enterprise_id: str,
    meeting_id: str,
    participant_id: str,
    agent_run_id: str,
    evidence_snapshot_id: str,
    skill_key: str,
    skill_version: int,
    tool_keys: list[str],
    runtime_session_id: str | None = None,
    status: str = "pending",
) -> MeetingRuntimeRun:
    now = datetime.now(UTC)
    with database.session() as session:
        participant = session.get(TwinMeetingParticipant, participant_id)
        if participant is None or participant.meeting_id != meeting_id:
            raise LookupError("会议参会分身不存在")
        existing = session.scalar(
            select(MeetingRuntimeRun).where(
                MeetingRuntimeRun.meeting_id == meeting_id,
                MeetingRuntimeRun.participant_id == participant_id,
                MeetingRuntimeRun.agent_run_id == agent_run_id,
            )
        )
        if existing is not None:
            return existing
        item = MeetingRuntimeRun(
            id=f"meeting_runtime_run_{uuid4().hex}",
            enterprise_id=enterprise_id,
            meeting_id=meeting_id,
            participant_id=participant_id,
            agent_run_id=agent_run_id,
            runtime_session_id=runtime_session_id,
            evidence_snapshot_id=evidence_snapshot_id,
            skill_key=skill_key,
            skill_version=skill_version,
            tool_keys=sorted(set(tool_keys)),
            status=status,
            failure_code=None,
            failure_message=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return item


def update_meeting_runtime_run(
    database: Database,
    *,
    run_id: str,
    status: str,
    runtime_session_id: str | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
) -> MeetingRuntimeRun | None:
    """Persist the terminal state of a meeting's Runtime-backed role run."""
    now = datetime.now(UTC)
    with database.session() as session:
        item = session.get(MeetingRuntimeRun, run_id)
        if item is None:
            return None
        if runtime_session_id is not None:
            item.runtime_session_id = runtime_session_id
        item.status = status
        item.failure_code = failure_code[:120] if failure_code else None
        item.failure_message = failure_message[:500] if failure_message else None
        item.updated_at = now
        item.completed_at = now if status in {"completed", "failed", "cancelled"} else None
        session.commit()
        session.refresh(item)
        return item
