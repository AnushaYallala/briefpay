from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, mapped_column

# BIGINT autoincrement in Postgres; SQLite only autoincrements INTEGER PKs.
BigInt = BigInteger().with_variant(Integer, "sqlite")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {
        dict: JSON,
        list: JSON,
        datetime: DateTime(timezone=True),
        int: BigInt,
    }


def pk():
    return mapped_column(BigInt, primary_key=True, autoincrement=True)


def created():
    return mapped_column(DateTime(timezone=True), default=utcnow)
