from __future__ import annotations

import json
from os import getenv

from sqlalchemy import create_engine, select
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session
from zhixing_jobs import BackgroundJob, EnqueueJob, JobRepository


def probe_request(key: str) -> EnqueueJob:
    return EnqueueJob(
        enterprise_id="ent_zhixing_demo",
        job_type="system.noop",
        payload={"probe": key},
        idempotency_key=key,
        initiator_type="system",
        initiator_id="fnd010-verifier",
        actor_snapshot={"principal_id": "fnd010-verifier"},
        permission_set_version="fnd010-verifier-v1",
        required_permissions=(),
        scope_type="enterprise",
        scope_id="ent_zhixing_demo",
        request_id="req_fnd010_verify",
        run_id="run_fnd010_verify",
        max_attempts=2,
        timeout_seconds=5,
    )


def main() -> int:
    database_url = getenv("DATABASE_URL", "")
    database_name = (make_url(database_url).database or "").casefold()
    if not any(marker in database_name for marker in ("test", "verify")):
        raise RuntimeError("Worker 动态验收只允许 test 或 verify 数据库")

    engine = create_engine(database_url, pool_pre_ping=True)
    repository = JobRepository(engine)
    try:
        first = repository.enqueue(probe_request("fnd010-lock-probe"))
        duplicate = repository.enqueue(probe_request("fnd010-lock-probe"))
        second = repository.enqueue(probe_request("fnd010-skip-probe"))
        if not first.created or duplicate.created or duplicate.job.id != first.job.id:
            raise RuntimeError("幂等入队验收失败")

        with Session(engine) as locking_session:
            locking_session.begin()
            locked = locking_session.scalar(
                select(BackgroundJob)
                .where(BackgroundJob.id == first.job.id)
                .with_for_update()
            )
            if locked is None:
                raise RuntimeError("锁定探针任务不存在")
            claimed = repository.claim("worker-skip-locked", lease_seconds=10)
            if claimed is None or claimed.id != second.job.id:
                raise RuntimeError("SKIP LOCKED 未领取到未锁定任务")
            locking_session.rollback()

        repository.complete(
            second.job.id,
            "worker-skip-locked",
            {"skip_locked": True},
        )
        remaining = repository.claim("worker-final", lease_seconds=10)
        if remaining is None or remaining.id != first.job.id:
            raise RuntimeError("释放行锁后的任务领取失败")
        completed = repository.complete(first.job.id, "worker-final", {"idempotent": True})
        print(
            json.dumps(
                {
                    "idempotency_verified": True,
                    "skip_locked_verified": True,
                    "status": completed.status,
                    "trace_verified": completed.run_id == "run_fnd010_verify",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
