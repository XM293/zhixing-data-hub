from dataclasses import dataclass
from os import environ, getenv
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    timezone: str
    cors_origins: tuple[str, ...]
    database_url: str
    mock_commerce_url: str
    meeting_auto_start_seconds: float = 4.8
    meeting_scheduler_poll_seconds: float = 0.5
    review_schedule_poll_seconds: float = 15.0
    auth_session_ttl_seconds: int = 8 * 60 * 60
    auth_bootstrap_password: str = ""
    ai_enabled: bool = False
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-5.4-mini"
    ai_timeout_seconds: float = 45.0
    agent_runtime_enabled: bool = False
    codex_command: str = "codex"
    codex_runtime_model: str = ""
    codex_runtime_timeout_seconds: float = 20.0
    codex_runtime_cwd: str = ""
    codex_runtime_mcp_client_id: str = "codex-project"
    codex_runtime_mcp_ttl_seconds: int = 900
    memory_provider_mode: str = "contract-sandbox"
    memory_provider_timeout_seconds: float = 12.0
    tencentdb_memory_base_url: str = "http://127.0.0.1:8200/tencentdb"
    tencentdb_memory_api_key: str = ""
    mem0_base_url: str = "http://127.0.0.1:8200/mem0"
    mem0_api_key: str = ""
    knowledge_provider_mode: str = "contract-sandbox"
    knowledge_provider_timeout_seconds: float = 15.0
    weknora_base_url: str = "http://127.0.0.1:8300/weknora"
    weknora_api_key: str = ""
    weknora_knowledge_base_id: str = "zhixing-evaluation"
    ragflow_base_url: str = "http://127.0.0.1:8300/ragflow"
    ragflow_api_key: str = ""
    ragflow_dataset_id: str = "zhixing-evaluation"
    openviking_base_url: str = "http://127.0.0.1:8300/openviking"
    openviking_api_key: str = ""
    openviking_account: str = ""
    openviking_user: str = ""
    file_asset_storage_path: str = ""
    file_asset_storage_provider: str = "local"
    s3_endpoint: str = ""
    s3_region: str = "us-east-1"
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_force_path_style: bool = False
    s3_auto_create_bucket: bool = False
    redis_enabled: bool = False
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_key_prefix: str = "zhixing"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout_seconds: float = 30.0
    database_pool_recycle_seconds: int = 1800
    database_auto_migrate: bool = True
    seed_enabled: bool = True
    source_archive_path: str = ""
    lingxing_enabled: bool = False
    lingxing_base_url: str = "https://openapi.lingxing.com"


API_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = API_ROOT.parents[1]


def _load_local_environment() -> None:
    env_path = WORKSPACE_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        environ.setdefault(key, value)


def load_settings() -> Settings:
    _load_local_environment()
    environment = getenv("APP_ENV", "development")
    production = environment.casefold() in {"production", "prod"}
    origins = tuple(
        value.strip()
        for value in getenv(
            "API_CORS_ORIGINS",
            "http://127.0.0.1:3000,http://localhost:3000",
        ).split(",")
        if value.strip()
    )
    return Settings(
        environment=environment,
        timezone=getenv("APP_TIMEZONE", "Asia/Shanghai"),
        cors_origins=origins,
        database_url=getenv(
            "DATABASE_URL",
            f"sqlite+pysqlite:///{(API_ROOT / 'var' / 'zhixing.db').as_posix()}",
        ),
        mock_commerce_url=getenv("MOCK_COMMERCE_URL", "http://127.0.0.1:8100"),
        meeting_auto_start_seconds=float(getenv("MEETING_AUTO_START_SECONDS", "4.8")),
        meeting_scheduler_poll_seconds=float(getenv("MEETING_SCHEDULER_POLL_SECONDS", "0.5")),
        review_schedule_poll_seconds=float(getenv("REVIEW_SCHEDULE_POLL_SECONDS", "15")),
        auth_session_ttl_seconds=int(getenv("AUTH_SESSION_TTL_SECONDS", str(8 * 60 * 60))),
        auth_bootstrap_password=getenv("AUTH_BOOTSTRAP_PASSWORD", ""),
        ai_enabled=getenv("AI_ENABLED", "false").strip().casefold() in {"1", "true", "yes", "on"},
        ai_base_url=(
            getenv("AI_BASE_URL")
            or getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/"),
        ai_api_key=getenv("AI_API_KEY") or getenv("OPENAI_API_KEY") or "",
        ai_model=getenv("AI_MODEL") or getenv("OPENAI_MODEL") or "gpt-5.4-mini",
        ai_timeout_seconds=float(getenv("AI_TIMEOUT_SECONDS", "45")),
        agent_runtime_enabled=getenv("AGENT_RUNTIME_ENABLED", "true").strip().casefold()
        in {"1", "true", "yes", "on"},
        codex_command=getenv("CODEX_COMMAND", "codex").strip() or "codex",
        codex_runtime_model=getenv("CODEX_RUNTIME_MODEL", "").strip(),
        codex_runtime_timeout_seconds=float(getenv("CODEX_RUNTIME_TIMEOUT_SECONDS", "20")),
        codex_runtime_cwd=getenv("CODEX_RUNTIME_CWD", str(WORKSPACE_ROOT)).strip()
        or str(WORKSPACE_ROOT),
        codex_runtime_mcp_client_id=getenv(
            "CODEX_RUNTIME_MCP_CLIENT_ID",
            "codex-project",
        ).strip().casefold()
        or "codex-project",
        codex_runtime_mcp_ttl_seconds=int(
            getenv("CODEX_RUNTIME_MCP_TTL_SECONDS", "900")
        ),
        memory_provider_mode=getenv("MEMORY_PROVIDER_MODE", "contract-sandbox"),
        memory_provider_timeout_seconds=float(getenv("MEMORY_PROVIDER_TIMEOUT_SECONDS", "12")),
        tencentdb_memory_base_url=getenv(
            "TENCENTDB_MEMORY_BASE_URL",
            "http://127.0.0.1:8200/tencentdb",
        ).rstrip("/"),
        tencentdb_memory_api_key=getenv("TENCENTDB_MEMORY_API_KEY", ""),
        mem0_base_url=getenv("MEM0_BASE_URL", "http://127.0.0.1:8200/mem0").rstrip("/"),
        mem0_api_key=getenv("MEM0_API_KEY", ""),
        knowledge_provider_mode=getenv("KNOWLEDGE_PROVIDER_MODE", "contract-sandbox"),
        knowledge_provider_timeout_seconds=float(
            getenv("KNOWLEDGE_PROVIDER_TIMEOUT_SECONDS", "15")
        ),
        weknora_base_url=getenv("WEKNORA_BASE_URL", "http://127.0.0.1:8300/weknora").rstrip("/"),
        weknora_api_key=getenv("WEKNORA_API_KEY", ""),
        weknora_knowledge_base_id=getenv("WEKNORA_KNOWLEDGE_BASE_ID", "zhixing-evaluation"),
        ragflow_base_url=getenv("RAGFLOW_BASE_URL", "http://127.0.0.1:8300/ragflow").rstrip("/"),
        ragflow_api_key=getenv("RAGFLOW_API_KEY", ""),
        ragflow_dataset_id=getenv("RAGFLOW_DATASET_ID", "zhixing-evaluation"),
        openviking_base_url=getenv(
            "OPENVIKING_BASE_URL", "http://127.0.0.1:8300/openviking"
        ).rstrip("/"),
        openviking_api_key=getenv("OPENVIKING_API_KEY", ""),
        openviking_account=getenv("OPENVIKING_ACCOUNT", ""),
        openviking_user=getenv("OPENVIKING_USER", ""),
        file_asset_storage_path=getenv(
            "FILE_ASSET_STORAGE_PATH",
            str(API_ROOT / "var" / "file-assets"),
        ),
        file_asset_storage_provider=(
            getenv("FILE_ASSET_STORAGE_PROVIDER", "local").strip().casefold()
        ),
        s3_endpoint=(getenv("S3_ENDPOINT", "").strip().rstrip("/")),
        s3_region=getenv("S3_REGION", "us-east-1").strip() or "us-east-1",
        s3_bucket=getenv("S3_BUCKET", "").strip(),
        s3_access_key=(
            getenv("S3_ACCESS_KEY") or getenv("AWS_ACCESS_KEY_ID") or ""
        ).strip(),
        s3_secret_key=(
            getenv("S3_SECRET_KEY") or getenv("AWS_SECRET_ACCESS_KEY") or ""
        ).strip(),
        s3_force_path_style=getenv("S3_FORCE_PATH_STYLE", "false").strip().casefold()
        in {"1", "true", "yes", "on"},
        s3_auto_create_bucket=getenv("S3_AUTO_CREATE_BUCKET", "false").strip().casefold()
        in {"1", "true", "yes", "on"},
        redis_enabled=getenv("REDIS_ENABLED", "false").strip().casefold()
        in {"1", "true", "yes", "on"},
        redis_url=getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip(),
        redis_key_prefix=getenv("REDIS_KEY_PREFIX", "zhixing").strip() or "zhixing",
        database_pool_size=int(getenv("DATABASE_POOL_SIZE", "10")),
        database_max_overflow=int(getenv("DATABASE_MAX_OVERFLOW", "20")),
        database_pool_timeout_seconds=float(getenv("DATABASE_POOL_TIMEOUT_SECONDS", "30")),
        database_pool_recycle_seconds=int(getenv("DATABASE_POOL_RECYCLE_SECONDS", "1800")),
        database_auto_migrate=getenv(
            "DATABASE_AUTO_MIGRATE",
            "false" if production else "true",
        ).strip().casefold()
        in {"1", "true", "yes", "on"},
        seed_enabled=getenv(
            "SEED_ENABLED",
            "false" if production else "true",
        ).strip().casefold()
        in {"1", "true", "yes", "on"},
        source_archive_path=getenv("SOURCE_ARCHIVE_PATH", "").strip(),
        lingxing_enabled=getenv("LINGXING_ENABLED", "false").strip().casefold()
        in {"1", "true", "yes", "on"},
        lingxing_base_url=(getenv("LINGXING_BASE_URL", "").strip()
                           or "https://openapi.lingxing.com").rstrip("/"),
    )


def validate_settings(settings: Settings) -> None:
    errors: list[str] = []
    if settings.ai_enabled and not settings.ai_api_key:
        errors.append("AI_ENABLED 已开启，但未配置 AI_API_KEY 或 OPENAI_API_KEY")
    if settings.file_asset_storage_provider not in {"local", "s3"}:
        errors.append("FILE_ASSET_STORAGE_PROVIDER 只能是 local 或 s3")
    if settings.file_asset_storage_provider == "s3":
        if not settings.s3_bucket:
            errors.append("S3 文件存储缺少 S3_BUCKET")
        if bool(settings.s3_access_key) != bool(settings.s3_secret_key):
            errors.append("S3_ACCESS_KEY 与 S3_SECRET_KEY 必须同时配置")
    if settings.database_pool_size < 1:
        errors.append("DATABASE_POOL_SIZE 必须大于 0")
    if settings.database_max_overflow < 0:
        errors.append("DATABASE_MAX_OVERFLOW 不能小于 0")

    if settings.environment.casefold() in {"production", "prod"}:
        if settings.database_url.startswith("sqlite"):
            errors.append("生产环境禁止使用 SQLite")
        if settings.file_asset_storage_provider != "s3":
            errors.append("生产环境必须使用 S3 兼容对象存储")
        if not settings.redis_enabled:
            errors.append("生产环境必须启用 Redis 调度协调")
        if settings.s3_auto_create_bucket:
            errors.append("生产环境禁止由应用自动创建对象存储桶")
        if settings.database_auto_migrate:
            errors.append("生产 API 禁止自动迁移数据库；请在发布阶段单独执行迁移")
        if settings.seed_enabled:
            errors.append("生产环境禁止装载开发种子数据")
        if settings.memory_provider_mode == "contract-sandbox":
            errors.append("生产环境禁止使用模拟记忆 Provider")
        if settings.knowledge_provider_mode == "contract-sandbox":
            errors.append("生产环境禁止使用模拟知识 Provider")

    if errors:
        raise ValueError("；".join(errors))
