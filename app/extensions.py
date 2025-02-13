import uuid
from datetime import datetime

from flask_debugtoolbar import DebugToolbarExtension
from flask_migrate import Migrate
from flask_sqlalchemy_lite import SQLAlchemy
from sqlalchemy import MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

convention = {
  "ix": "ix_%(column_0_label)s",
  "uq": "uq_%(table_name)s_%(column_0_name)s",
  "ck": "ck_%(table_name)s_%(constraint_name)s",
  "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
  "pk": "pk_%(table_name)s"
}


class BaseModel(DeclarativeBase):
    __abstract__ = True
    metadata = MetaData(naming_convention=convention)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, sort_order=-100)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), sort_order=-99)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), server_onupdate=func.now(), sort_order=-98)


db = SQLAlchemy()
migrate = Migrate(metadatas=BaseModel.metadata)
toolbar = DebugToolbarExtension()
