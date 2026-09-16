from zhixing_jobs.sync_status import SYNC_PARTIAL_FAILED, SYNC_QUEUED


def test_sync_status_contract():
    assert SYNC_QUEUED == "queued"
    assert SYNC_PARTIAL_FAILED == "partial_failed"
