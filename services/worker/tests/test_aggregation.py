from zhixing_worker.lingxing_sync import aggregate_status


def test_parent_run_aggregation():
    assert aggregate_status(["succeeded", "succeeded"]) == "succeeded"
    assert aggregate_status(["succeeded", "failed"]) == "partial_failed"
    assert aggregate_status(["failed", "cancelled"]) == "failed"
