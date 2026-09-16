import pytest

from zhixing_api.errors import ApiProblem


def test_runtime_resume_rejects_old_or_changed_scope_before_reusing_history():
    from zhixing_api.agent_runtime_service import validate_runtime_scope_for_resume

    current = {"schema_version": 2, "enterprise_id": "legal-a", "scope_version": "store-a-v2"}
    validate_runtime_scope_for_resume({"scope_context": current}, current)
    for saved in ({}, {"scope_context": {**current, "scope_version": "store-b-v2"}},
                  {"scope_context": {**current, "enterprise_id": "legal-b"}},
                  {"scope_context": {**current, "schema_version": 1}}):
        with pytest.raises(ApiProblem) as caught:
            validate_runtime_scope_for_resume(saved, current)
        assert caught.value.status_code == 409
        assert caught.value.code == "runtime.scope_changed"
