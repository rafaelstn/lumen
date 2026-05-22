"""Base declarativa do SQLAlchemy. Modelos concretos chegam nos módulos futuros (02+)."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
