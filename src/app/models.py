"""ORM models for the sumo competition system."""
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    competitions: Mapped[list["Competition"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class PasswordReset(Base):
    """A one-time reset code e-mailed to the user."""

    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(64), index=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    birth_years: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped["User"] = relationship(back_populates="competitions")
    permissions: Mapped[list["CompetitionPermission"]] = relationship(
        back_populates="competition", cascade="all, delete-orphan"
    )
    age_categories: Mapped[list["AgeCategory"]] = relationship(
        back_populates="competition",
        cascade="all, delete-orphan",
        order_by="AgeCategory.id",
    )


class CompetitionPermission(Base):
    """Per-(user, competition) access rights."""

    __tablename__ = "competition_permissions"
    __table_args__ = (
        UniqueConstraint("competition_id", "user_id", name="uq_comp_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    can_create: Mapped[bool] = mapped_column(Boolean, default=False)
    can_update: Mapped[bool] = mapped_column(Boolean, default=False)
    can_read: Mapped[bool] = mapped_column(Boolean, default=True)
    can_delete: Mapped[bool] = mapped_column(Boolean, default=False)

    competition: Mapped["Competition"] = relationship(back_populates="permissions")
    user: Mapped["User"] = relationship()


class AgeCategory(Base):
    __tablename__ = "age_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE")
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    min_birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    competition: Mapped["Competition"] = relationship(back_populates="age_categories")
    weight_categories: Mapped[list["WeightCategory"]] = relationship(
        back_populates="age_category",
        cascade="all, delete-orphan",
        order_by="WeightCategory.weight",
    )


class WeightCategory(Base):
    __tablename__ = "weight_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    age_category_id: Mapped[int] = mapped_column(
        ForeignKey("age_categories.id", ondelete="CASCADE")
    )
    weight: Mapped[float | None] = mapped_column(nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    age_category: Mapped["AgeCategory"] = relationship(
        back_populates="weight_categories"
    )
    participants: Mapped[list["Participant"]] = relationship(
        back_populates="weight_category",
        cascade="all, delete-orphan",
        order_by="Participant.order_index",
    )
    rounds: Mapped[list["Round"]] = relationship(
        back_populates="weight_category",
        cascade="all, delete-orphan",
        order_by="Round.index",
    )


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    weight_category_id: Mapped[int] = mapped_column(
        ForeignKey("weight_categories.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))  # Name and Surname
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    team: Mapped[str | None] = mapped_column(String(255), nullable=True)
    other_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Position used for the shuffled draw order (NULL = not yet ordered).
    order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    weight_category: Mapped["WeightCategory"] = relationship(
        back_populates="participants"
    )


class Round(Base):
    """A tournament round; its bracket/schedule is stored as JSON in ``data``."""

    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    weight_category_id: Mapped[int] = mapped_column(
        ForeignKey("weight_categories.id", ondelete="CASCADE")
    )
    index: Mapped[int] = mapped_column(Integer)  # Round 1, 2, ...
    num_participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    weight_category: Mapped["WeightCategory"] = relationship(back_populates="rounds")
