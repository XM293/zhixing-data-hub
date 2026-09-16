from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine

from zhixing_jobs import EnqueueJob, JobRepository, JobsBase
from zhixing_jobs.repository import JobStateConflict


def test_stale_execution_cannot_commit_after_same_worker_id_reclaims_job(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fencing_verify.db'}")
    JobsBase.metadata.create_all(engine)
    repository = JobRepository(engine)
    repository.enqueue(EnqueueJob(enterprise_id="synthetic-legal", job_type="system.noop",
        payload={}, idempotency_key="synthetic-fence", initiator_type="user", initiator_id="actor",
        actor_snapshot={"principal_id": "actor"}, permission_set_version="1",
        required_permissions=("source.manage",),
        scope_type="enterprise", scope_id="synthetic-legal", run_id="run", request_id="request",
        timeout_seconds=1))
    now = datetime.now(UTC)
    old = repository.claim("same-worker", lease_seconds=1, now=now)
    with engine.begin() as connection:
        repository.fence_execution(connection, old.id, "same-worker", old.execution_token)
    repository.recover_expired(now=now + timedelta(seconds=3))
    current = repository.claim("same-worker", lease_seconds=60, now=now + timedelta(seconds=3))
    assert current.execution_token != old.execution_token
    with pytest.raises(JobStateConflict), engine.begin() as connection:
        repository.fence_execution(connection, old.id, "same-worker", old.execution_token)
    with pytest.raises(JobStateConflict):
        repository.complete(old.id, "same-worker", {}, execution_token=old.execution_token)
    with pytest.raises(JobStateConflict):
        repository.fail(old.id, "same-worker", error_code="synthetic", error_message="synthetic",
                        retryable=False, execution_token=old.execution_token)
    with engine.begin() as connection:
        repository.fence_execution(connection, current.id, "same-worker", current.execution_token)
    assert repository.complete(current.id, "same-worker", {},
                               execution_token=current.execution_token).status == "succeeded"
    engine.dispose()
