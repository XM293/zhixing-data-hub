import ast
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).parents[1] / "src" / "zhixing_api"

def test_demo_enterprise_ids_only_in_seed_or_tests():
    violations = []
    for path in ROOT.rglob("*.py"):
        if "seed" in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        for token in ("ent_zhixing_demo", "grp_ent_zhixing_demo"):
            if token in text:
                violations.append(f"{path}:{token}")
    assert not violations, "demo enterprise leaked into runtime: " + ", ".join(violations)


def test_runtime_does_not_import_demo_enterprise_constant():
    violations = []
    for path in ROOT.rglob("*.py"):
        if "seed" in path.name:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "zhixing_api.seed":
                if any(alias.name == "ENTERPRISE_ID" for alias in node.names):
                    violations.append(str(path))
    assert not violations, "runtime imported demo enterprise constant: " + ", ".join(violations)


def test_local_authentication_is_enterprise_agnostic_and_ambiguity_is_explicit():
    source = (ROOT / "actor_context.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "authenticate_local_actor"
    )
    body = ast.get_source_segment(source, function) or ""
    assert "UserAccount.enterprise_id == ENTERPRISE_ID" not in body
    assert 'code="auth.login_ambiguous"' in body


def test_sync_scope_resolves_from_persisted_enterprises_not_demo_constant():
    source = (ROOT / "data_center_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "synchronize"
    )
    body = ast.get_source_segment(source, function) or ""
    assert "enterprise_id or ENTERPRISE_ID" not in body
    assert "_resolve_enterprise_id" in source


def test_group_two_enterprise_three_business_unit_scope_isolation(tmp_path: Path):
    from sqlalchemy import select

    from zhixing_api.config import Settings
    from zhixing_api.data_center_service import list_business_entities
    from zhixing_api.data_models import BusinessEntity, BusinessUnit, Enterprise
    from zhixing_api.database import Database
    from zhixing_api.seed import seed_database

    settings = Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'scope-isolation.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )
    database = Database(settings.database_url)
    database.migrate()
    seed_database(database, settings)
    now = datetime.now(UTC)
    with database.session() as session:
        primary = session.scalar(select(Enterprise).order_by(Enterprise.id).limit(1))
        assert primary is not None and primary.group_id is not None
        secondary = Enterprise(
            id="ent_scope_secondary",
            code="SCOPE-SECONDARY",
            name="合成法人二",
            timezone="Asia/Shanghai",
            group_id=primary.group_id,
            created_at=now,
        )
        session.add(secondary)
        session.add_all(
            [
                BusinessUnit(
                    id="bu_scope_primary_a",
                    enterprise_id=primary.id,
                    unit_key="primary-a",
                    name="法人一事业部 A",
                    unit_type="brand",
                    parent_id=None,
                    status="active",
                    version=1,
                    created_at=now,
                    updated_at=now,
                ),
                BusinessUnit(
                    id="bu_scope_primary_b",
                    enterprise_id=primary.id,
                    unit_key="primary-b",
                    name="法人一事业部 B",
                    unit_type="region",
                    parent_id=None,
                    status="active",
                    version=1,
                    created_at=now,
                    updated_at=now,
                ),
                BusinessUnit(
                    id="bu_scope_secondary_a",
                    enterprise_id=secondary.id,
                    unit_key="secondary-a",
                    name="法人二事业部 A",
                    unit_type="brand",
                    parent_id=None,
                    status="active",
                    version=1,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.add_all(
            [
                BusinessEntity(
                    id="entity_scope_primary",
                    enterprise_id=primary.id,
                    entity_type="store",
                    canonical_key="store-primary",
                    display_name="法人一店铺",
                    status="active",
                    attributes={},
                    updated_at=now,
                ),
                BusinessEntity(
                    id="entity_scope_secondary",
                    enterprise_id=secondary.id,
                    entity_type="store",
                    canonical_key="store-secondary",
                    display_name="法人二店铺",
                    status="active",
                    attributes={},
                    updated_at=now,
                ),
            ]
        )
        assert len(session.scalars(select(BusinessUnit)).all()) >= 3
        session.commit()

    first = list_business_entities(
        database,
        enterprise_id="ent_scope_secondary",
        entity_type="store",
        status=None,
        query=None,
        offset=0,
        limit=50,
    )
    second = list_business_entities(
        database,
        enterprise_id=primary.id,
        entity_type="store",
        status=None,
        query=None,
        offset=0,
        limit=50,
    )
    assert [item.canonical_key for item in first.items] == ["store-secondary"]
    assert [item.canonical_key for item in second.items] == ["store-primary"]
