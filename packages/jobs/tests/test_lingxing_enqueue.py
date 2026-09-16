from zhixing_jobs.lingxing import LingxingSyncCommand


def test_lingxing_command_builds_worker_job():
    job = LingxingSyncCommand("ent-a", "src", "orders").to_enqueue_job(
        initiator_id="user", request_id="req", run_id="run"
    )
    assert job.job_type == "data-source.sync"
    assert job.scope_id == "ent-a"
