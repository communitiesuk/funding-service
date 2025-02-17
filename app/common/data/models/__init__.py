from sqlalchemy.orm import Mapped

from app.common.data.base import BaseModel


class Grant(BaseModel):
    __tablename__ = "grant"

    name: Mapped[str]
