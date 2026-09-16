from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from zhixing_api.config import API_ROOT


class Database:
    @classmethod
    def from_engine(cls, engine: Engine) -> Database:
        database = cls.__new__(cls)
        database.engine = engine
        database.engine.hide_parameters = True
        database.url = engine.url.render_as_string(hide_password=False)
        database.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        return database

    def __init__(
        self,
        url: str,
        *,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout_seconds: float = 30.0,
        pool_recycle_seconds: int = 1800,
    ) -> None:
        self.url = url
        self._ensure_sqlite_directory()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        pool_options: dict[str, int | float] = {}
        if not url.startswith("sqlite"):
            pool_options = {
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_timeout": pool_timeout_seconds,
                "pool_recycle": pool_recycle_seconds,
            }
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args=connect_args,
            **pool_options,
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _ensure_sqlite_directory(self) -> None:
        if not self.url.startswith("sqlite"):
            return
        path_text = self.url.split("///", 1)[-1]
        if path_text != ":memory:":
            Path(path_text).parent.mkdir(parents=True, exist_ok=True)

    def _alembic_config(self) -> Config:
        config = Config(str(API_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(API_ROOT / "migrations"))
        config.set_main_option("sqlalchemy.url", self.url.replace("%", "%%"))
        return config

    def migrate(self, revision: str = "head") -> None:
        command.upgrade(self._alembic_config(), revision)

    def migration_head(self) -> str:
        head = ScriptDirectory.from_config(self._alembic_config()).get_current_head()
        return str(head) if head is not None else "base"

    def rebuild_test_schema(self) -> None:
        assert_test_database_url(self.url)
        self.dispose()
        command.downgrade(self._alembic_config(), "base")
        command.upgrade(self._alembic_config(), "head")

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()

    def ready(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def revision(self) -> str:
        with self.engine.connect() as connection:
            if not connection.dialect.has_table(connection, "alembic_version"):
                return "base"
            value = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
        return str(value) if value is not None else "base"

    def migrations_ready(self) -> bool:
        return self.revision() == self.migration_head()

    @property
    def engine_name(self) -> str:
        return self.engine.dialect.name

    def dispose(self) -> None:
        self.engine.dispose()


def assert_test_database_url(url: str) -> None:
    parsed = make_url(url)
    database_name = Path(parsed.database or "").name.casefold()
    if database_name == ":memory:":
        return
    if any(marker in database_name for marker in ("test", "verify")):
        return
    raise ValueError("拒绝重建非测试数据库：数据库名称或 SQLite 文件名必须包含 test 或 verify")
