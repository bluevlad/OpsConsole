"""SQLAlchemy 2.0 declarative Base — 모든 ORM 모델의 부모."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 OpsConsole ORM 모델의 부모. 테이블명은 ops_ prefix 강제."""
    pass
