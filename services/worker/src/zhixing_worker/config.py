from __future__ import annotations

from dataclasses import dataclass, field
from os import environ, getenv, getpid
from pathlib import Path
from socket import gethostname


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    database_url: str = field(repr=False)
    worker_id: str
    poll_seconds: float
    lease_seconds: float
    retry_delay_seconds: float
    schema_wait_seconds: float
    api_base_url: str = "http://127.0.0.1:8000"
    api_timeout_seconds: float = 110.0
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout_seconds: float = 30.0
    database_pool_recycle_seconds: int = 1800
    lingxing_app_id: str = field(default="", repr=False)
    lingxing_app_secret: str = field(default="", repr=False)
    lingxing_enabled: bool = False
    lingxing_base_url: str = "https://openapi.lingxing.com"
    source_archive_path: str = ""
    report_download_hosts: tuple[str, ...] = ()


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]


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


def load_settings() -> WorkerSettings:
    _load_local_environment()
    default_database = WORKSPACE_ROOT / "services" / "api" / "var" / "zhixing.db"
    return WorkerSettings(
        database_url=getenv(
            "DATABASE_URL",
            f"sqlite+pysqlite:///{default_database.as_posix()}",
        ),
        worker_id=getenv("WORKER_ID", f"{gethostname()}-{getpid()}")[:120],
        poll_seconds=float(getenv("WORKER_POLL_SECONDS", "0.5")),
        lease_seconds=float(getenv("WORKER_LEASE_SECONDS", "30")),
        retry_delay_seconds=float(getenv("WORKER_RETRY_DELAY_SECONDS", "1")),
        schema_wait_seconds=float(getenv("WORKER_SCHEMA_WAIT_SECONDS", "30")),
        api_base_url=getenv("WORKER_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        api_timeout_seconds=float(getenv("WORKER_API_TIMEOUT_SECONDS", "110")),
        database_pool_size=int(getenv("WORKER_DATABASE_POOL_SIZE", "5")),
        database_max_overflow=int(getenv("WORKER_DATABASE_MAX_OVERFLOW", "10")),
        database_pool_timeout_seconds=float(getenv("WORKER_DATABASE_POOL_TIMEOUT_SECONDS", "30")),
        database_pool_recycle_seconds=int(getenv("WORKER_DATABASE_POOL_RECYCLE_SECONDS", "1800")),
        lingxing_app_id=getenv("LINGXING_APP_ID", ""),
        lingxing_app_secret=getenv("LINGXING_APP_SECRET", ""),
        lingxing_enabled=getenv("LINGXING_ENABLED", "").strip().lower()
        in {"1", "true", "yes", "on"},
        lingxing_base_url=getenv("LINGXING_BASE_URL", "").strip() or "https://openapi.lingxing.com",
        source_archive_path=getenv("SOURCE_ARCHIVE_PATH", ""),
        report_download_hosts=tuple(host.strip().lower() for host in
                                    getenv("SOURCE_REPORT_DOWNLOAD_HOSTS", "").split(",")
                                    if host.strip()),
    )
