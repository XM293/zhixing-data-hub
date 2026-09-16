from pathlib import Path


def test_runtime_modules_do_not_embed_demo_tenant_defaults() -> None:
    root = Path(__file__).parents[1] / "src"
    excluded = {"seed.py", "identity_seed.py", "channel_identity_seed.py"}
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if path.name in excluded:
            continue
        text = path.read_text(encoding="utf-8")
        if "ent_zhixing_demo" in text or "grp_ent_zhixing_demo" in text:
            offenders.append(str(path))
    assert offenders == []
