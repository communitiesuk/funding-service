from sqlalchemy.orm import Mapped, mapped_column

from app.common.data.base import BaseModel


class Grant(BaseModel):
    __tablename__ = "grant"

    name: Mapped[str] = mapped_column(unique=True)
