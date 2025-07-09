import typing
import uuid
from datetime import datetime

from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import MetaData, TypeDecorator, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.common.data.types import json_flat_scalars, json_scalars

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

type CIStr = str


class DataSourceChoice(PydanticBaseModel):
    id: str
    label: str


class DataSourceDataTypeModel(PydanticBaseModel):
    choices: list[DataSourceChoice]


class DataSourceDataType(TypeDecorator):
    impl = JSONB

    cache_ok = False

    def process_bind_param(self, value: PydanticBaseModel, dialect):
        return value.model_dump(mode="json")["choices"]

    def process_result_value(self, value: typing.Any, dialect) -> DataSourceDataTypeModel:
        return DataSourceDataTypeModel(choices=value)


class BaseModel(DeclarativeBase):
    __abstract__ = True
    metadata = MetaData(naming_convention=convention)
    type_annotation_map = {
        json_scalars: postgresql.JSONB,
        json_flat_scalars: postgresql.JSONB,
        CIStr: CITEXT,
        DataSourceDataTypeModel: DataSourceDataType,
    }

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, sort_order=-100, default=uuid.uuid4)
    created_at_utc: Mapped[datetime] = mapped_column(server_default=func.now(), sort_order=-99)
    updated_at_utc: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), sort_order=-98)
