import sys
import uuid
import enum
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, Float, String, Text, Enum, DateTime, Boolean


def _uuid7_hex() -> str:
    if not hasattr(uuid, "uuid7"):
        raise RuntimeError(
            "uuid7 requires Python 3.14+. Current version: " + sys.version
        )
    return uuid.uuid7().hex


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class Gender(enum.Enum):
    MALE = "male"
    FEMALE = "female"


class Role(enum.Enum):
    ADMIN = "admin"
    ANALYST = "analyst"


class Profile(Base):
    __tablename__ = "profiles"
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid7_hex)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    gender: Mapped[Gender] = mapped_column(Enum(Gender), nullable=False)
    gender_probability: Mapped[float] = mapped_column(Float, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    age_group: Mapped[str] = mapped_column(Text, nullable=False)
    country_id: Mapped[str] = mapped_column(String(2), nullable=False)
    country_name: Mapped[str] = mapped_column(Text, nullable=False)
    country_probability: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_json(self) -> dict[str, str | int | float]:
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender.value,
            "gender_probability": self.gender_probability,
            "age": self.age,
            "age_group": self.age_group,
            "country_id": self.country_id,
            "country_name": self.country_name,
            "country_probability": self.country_probability,
            "created_at": self.created_at.isoformat(),
        }

    def to_summary(self):
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender.value,
            "age": self.age,
            "age_group": self.age_group,
            "country_id": self.country_id,
            "created_at": self.created_at.isoformat(),
        }


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid7_hex)
    github_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String)
    avatar_url: Mapped[str] = mapped_column(String)
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False, default=Role.ANALYST)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
