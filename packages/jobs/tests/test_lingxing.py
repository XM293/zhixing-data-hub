from zhixing_jobs.lingxing import LingxingSyncCommand


def test_command_idempotency_is_stable_and_scoped():
    a = LingxingSyncCommand("ent-a", "src", "orders")
    b = LingxingSyncCommand("ent-b", "src", "orders")
    assert a.idempotency_key == LingxingSyncCommand("ent-a", "src", "orders").idempotency_key
    assert a.idempotency_key != b.idempotency_key
    assert a.payload()["provider"] == "lingxing"
def test_partitions_separate_project_scopes_and_explicit_source_parameters():
    a = LingxingSyncCommand("a", "src", "purchases", scope_snapshot={"business_unit_ids": ["a1"]},
                           resource_parameters={"start_date": "2026-01-01"})
    b = LingxingSyncCommand("a", "src", "purchases", scope_snapshot={"business_unit_ids": ["a2"]},
                           resource_parameters={"start_date": "2026-01-01"})
    assert a.payload()["partition"] != b.payload()["partition"]
