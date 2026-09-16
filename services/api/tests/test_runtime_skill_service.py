from pathlib import Path

import pytest

from zhixing_api.actor_context import resolve_database_actor
from zhixing_api.config import Settings
from zhixing_api.main import create_app
from zhixing_api.runtime_skill_service import select_runtime_skill


def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://test",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'runtime-skill.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:9",
    )


def test_runtime_skill_resolves_published_version_and_tool_intersection(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path))
    database = app.state.database
    actor = resolve_database_actor(database, login_name="ceo", request_id="test", run_id="test")
    selected = select_runtime_skill(
        database,
        actor,
        skill_key="policy-grounded-answer",
        required_tool_keys={"read_policy", "search_knowledge", "get_metric"},
    )
    assert selected.version_number == 1
    assert selected.tool_keys == ("read_policy", "search_knowledge")
    assert "当前生效制度" in selected.instructions


def test_runtime_skill_rejects_unknown_or_unpublished_skill(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path))
    database = app.state.database
    actor = resolve_database_actor(database, login_name="ceo", request_id="test", run_id="test")
    with pytest.raises(Exception, match="Skill 没有可运行"):
        select_runtime_skill(database, actor, skill_key="missing-skill")
