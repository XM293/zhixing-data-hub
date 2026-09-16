import json
from pathlib import Path


def test_lingxing_business_scope_is_amazon_only_and_keeps_multiplatform_cataloged():
    path = (
        Path(__file__).parents[3]
        / "contracts"
        / "data"
        / "lingxing-official-rollout-worklist.json"
    )
    worklist = json.loads(path.read_text(encoding="utf-8"))
    scope = worklist["business_scope"]

    assert scope["included_scope_namespaces"] == ["amazon"]
    assert scope["excluded_scope_namespaces"] == ["multiplatform"]
    assert scope["excluded_resource_state"] == "excluded_by_business_scope"
    assert worklist["items"]
    assert all(
        item["scope_namespace"] in {"amazon", "multiplatform", None}
        for item in worklist["items"]
    )
