from sqlalchemy.orm import Mapped

from app.extensions import BaseModel


class Grant(BaseModel):
    __tablename__ = 'grant'

    name: Mapped[str]
