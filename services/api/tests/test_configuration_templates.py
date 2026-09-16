import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest


def test_env_example_contains_only_empty_configuration_values():
    root = Path(__file__).resolve().parents[3]
    for line in (root / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        assert value.strip() == "", f".env.example: {key} must be explicitly configured"


@pytest.mark.parametrize("relative", [".env.example", "deploy/server/zhixing-staging.env"])
def test_configuration_templates_require_explicit_credentials(relative):
    root = Path(__file__).resolve().parents[3]
    for line in (root / relative).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("\"'")
        if re.search(r"password|token|secret|api_key|access_key", key, re.IGNORECASE) and value:
            pytest.fail(f"{relative}: {key} must be empty in a configuration template")
        if key == "DATABASE_URL" and value and urlsplit(value).password is not None:
            pytest.fail(f"{relative}: DATABASE_URL must not contain a password")
