from pathlib import Path


def test_production_twin_has_no_fixed_mock_source_sync_command():
    root = Path(__file__).resolve().parents[3]
    component = root / "apps/web/src/components/twin/enterprise-twin-page.tsx"
    text = component.read_text(encoding="utf-8")
    assert "/sources/mock-commerce/sync" not in text
    assert "volume_profile" not in text


def test_source_governance_page_does_not_load_twin_business_overview():
    root = Path(__file__).resolve().parents[3]
    component = root / "apps/web/src/components/data-center/data-sources-page.tsx"
    text = component.read_text(encoding="utf-8")
    assert "/data-center/overview" not in text
    assert "volume_profile" not in text


def test_commerce_page_has_no_demo_group_or_independent_scope_selection():
    root = Path(__file__).resolve().parents[3]
    text = (root / "apps/web/src/components/data-center/data-center-pages.tsx").read_text(
        encoding="utf-8")
    assert 'scopeLabel = "知行电商集团"' not in text
    assert 'const [scopeKey, setScopeKey] = useState("enterprise")' not in text


def test_cockpit_has_no_fixed_acceptance_targets_or_demo_coverage():
    root = Path(__file__).resolve().parents[3]
    text = (root / "apps/web/src/components/cockpit/enterprise-cockpit-page.tsx").read_text(
        encoding="utf-8")
    assert "buildDataReadinessSeries" not in text
    assert "item.target" not in text
