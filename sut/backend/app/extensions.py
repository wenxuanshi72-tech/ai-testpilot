from __future__ import annotations

from flask_migrate import Migrate  # type: ignore[import-untyped]
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


db = SQLAlchemy(model_class=Base)
migrate = Migrate(compare_type=True)


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    module_name = type(dbapi_connection).__module__
    if not module_name.startswith("sqlite3"):
        return
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
