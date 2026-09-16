from types import SimpleNamespace

import pytest

from zhixing_api.errors import ApiProblem


def test_legacy_data_queries_cannot_expand_selected_store_project_or_group(monkeypatch):
    from zhixing_api.data_selection import require_selected_data_scope

    scope = SimpleNamespace(scope_level="store", selected_enterprise_ids=("a",),
                            store_ids=("selected-store",))
    monkeypatch.setattr("zhixing_api.data_selection.build_scope_context",
                        lambda database, actor: scope)
    actor = SimpleNamespace(enterprise_id="a", scope_selection={"scope_level": "store"})
    require_selected_data_scope(None, actor, "selected-store")
    for key in ("enterprise", "sibling-store"):
        with pytest.raises(ApiProblem) as denied:
            require_selected_data_scope(None, actor, key)
        assert denied.value.status_code == 403
    scope.scope_level = "group"
    scope.selected_enterprise_ids = ("a", "b")
    actor.scope_selection = {"scope_level": "group"}
    with pytest.raises(ApiProblem):
        require_selected_data_scope(None, actor, "enterprise")
    scope.scope_level = "enterprise"
    scope.selected_enterprise_ids = ("a",)
    actor.scope_selection = {"scope_level": "enterprise", "business_unit_ids": ["project-a"]}
    with pytest.raises(ApiProblem):
        require_selected_data_scope(None, actor, "enterprise")
    actor.scope_selection = {"scope_level": "enterprise"}
    require_selected_data_scope(None, actor, "enterprise")
    actor.scope_selection = None
    require_selected_data_scope(None, actor, "enterprise")


def test_twin_overview_rejects_selected_group_before_reading_legacy_data(monkeypatch):
    import asyncio

    from zhixing_api.routers import data_center

    actor = SimpleNamespace(enterprise_id="a", scope_selection={"scope_level": "group"})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=object())))
    monkeypatch.setattr(data_center, "resolve_development_actor", lambda request: actor)
    monkeypatch.setattr(data_center, "require_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr("zhixing_api.data_selection.build_scope_context", lambda *args:
        SimpleNamespace(scope_level="group", selected_enterprise_ids=("a", "b")))

    def forbidden_read(*args, **kwargs):
        pytest.fail("Legacy enterprise overview must not run for a selected group")

    monkeypatch.setattr(data_center, "build_overview", forbidden_read)
    with pytest.raises(ApiProblem) as denied:
        asyncio.run(data_center.overview(request))
    assert denied.value.code == "scope.selection_denied"


def test_queued_sync_contract_does_not_include_business_overview():
    from zhixing_api.data_center_schemas import SyncResponse

    assert set(SyncResponse.model_fields) == {"run"}


def test_meeting_action_rejects_selected_group_before_mutation(monkeypatch):
    import asyncio

    from zhixing_api.data_center_schemas import MeetingActionRequest
    from zhixing_api.routers import data_center

    actor = SimpleNamespace(enterprise_id="a", scope_selection={"scope_level": "group"})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        database=object(), settings=SimpleNamespace(meeting_auto_start_seconds=0))))
    monkeypatch.setattr(data_center, "resolve_development_actor", lambda request: actor)
    monkeypatch.setattr(data_center, "require_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr("zhixing_api.data_selection.build_scope_context", lambda *args:
        SimpleNamespace(scope_level="group", selected_enterprise_ids=("a", "b")))

    def forbidden_mutation(*args, **kwargs):
        pytest.fail("Denied selected scope must not mutate a meeting")

    monkeypatch.setattr(data_center, "advance_meeting", forbidden_mutation)
    with pytest.raises(ApiProblem) as denied:
        asyncio.run(data_center.meeting_action(
            request, "synthetic-meeting", MeetingActionRequest(action="start")))
    assert denied.value.code == "scope.selection_denied"
