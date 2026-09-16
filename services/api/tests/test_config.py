from __future__ import annotations

from os import environ

import pytest

import zhixing_api.config as config_module
from zhixing_api.config import Settings


def test_local_env_initializes_bootstrap_password(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.delenv("AUTH_BOOTSTRAP_PASSWORD", raising=False)
    (tmp_path / ".env").write_text(
        "# local credentials\nAUTH_BOOTSTRAP_PASSWORD='local-config-password'\n",
        encoding="utf-8",
    )
    try:
        assert config_module.load_settings().auth_bootstrap_password == "local-config-password"
    finally:
        environ.pop("AUTH_BOOTSTRAP_PASSWORD", None)


def test_process_environment_takes_precedence_over_local_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setenv("AUTH_BOOTSTRAP_PASSWORD", "runtime-password")
    (tmp_path / ".env").write_text(
        "AUTH_BOOTSTRAP_PASSWORD=local-config-password\n",
        encoding="utf-8",
    )

    assert config_module.load_settings().auth_bootstrap_password == "runtime-password"


def test_standard_openai_environment_is_supported(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "standard-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "provider-model")
    monkeypatch.setenv("AI_ENABLED", "true")

    settings = config_module.load_settings()

    assert settings.ai_api_key == "standard-key"
    assert settings.ai_base_url == "https://provider.example/v1"
    assert settings.ai_model == "provider-model"


def test_production_settings_reject_development_dependencies() -> None:
    settings = Settings(
        environment="production",
        timezone="Asia/Shanghai",
        cors_origins=("https://zhixing.maysu.com",),
        database_url="sqlite+pysqlite:///production.db",
        mock_commerce_url="http://127.0.0.1:8100",
    )

    with pytest.raises(ValueError) as error:
        config_module.validate_settings(settings)

    message = str(error.value)
    assert "生产环境禁止使用 SQLite" in message
    assert "生产环境必须使用 S3" in message
    assert "生产环境必须启用 Redis" in message


def test_production_settings_accept_managed_dependency_profile() -> None:
    settings = Settings(
        environment="production",
        timezone="Asia/Shanghai",
        cors_origins=("https://zhixing.maysu.com",),
        database_url="postgresql+psycopg://service@database.internal/zhixing",
        mock_commerce_url="https://connector.internal",
        file_asset_storage_provider="s3",
        s3_bucket="zhixing-production",
        redis_enabled=True,
        redis_url="rediss://redis.internal:6379/0",
        database_auto_migrate=False,
        seed_enabled=False,
        memory_provider_mode="disabled",
        knowledge_provider_mode="disabled",
    )

    config_module.validate_settings(settings)
