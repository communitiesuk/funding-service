from sqlalchemy.orm import Mapped, mapped_column

from app.common.data.base import BaseModel, CIStr


class Grant(BaseModel):
    __tablename__ = "grant"

    name: Mapped[CIStr] = mapped_column(unique=True)
