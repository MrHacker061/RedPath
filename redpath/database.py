from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from redpath.config import Settings


class Base(DeclarativeBase):
    pass


def create_database(settings: Settings):
    settings.ensure_local_directories()
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

