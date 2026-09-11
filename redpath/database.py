from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from redpath.config import Settings


class Base(DeclarativeBase):
    pass


def create_database(settings: Settings):
    settings.ensure_local_directories()
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def migrate_database(engine) -> None:
    """Apply small, forward-only SQLite compatibility migrations."""
    inspector = inspect(engine)
    if "findings" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("findings")}
    if "evidence_ref" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE findings ADD COLUMN evidence_ref VARCHAR(160) NOT NULL DEFAULT ''"))
            connection.execute(text("UPDATE findings SET evidence_ref = scan_import_id WHERE evidence_ref = ''"))
