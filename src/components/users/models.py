import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Enum, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class LookupCategory(str, enum.Enum):
    USER_ROLE = "user_role"
    USER_TYPE = "user_type"
    USER_STATUS = "user_status"
    GENDER = "gender"


class SystemLookup(Base):
    __tablename__ = "system_lookups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    weight: Mapped[int | None] = mapped_column(Integer, nullable=True)  # For role hierarchy
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("category", "code", name="uq_lookup_category_code"),
    )


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MAINTAINER = "maintainer"
    VICE_PRESIDENT = "vice_president"
    SENIOR_ACCOUNT_MANAGER = "senior_account_manager"
    ACCOUNT_MANAGER = "account_manager"
    SENIOR_APPLICATION_MANAGER = "senior_application_manager"
    APPLICATION_MANAGER = "application_manager"
    TEAM_LEAD = "team_lead"
    ASSOCIATE = "associate"
    MANAGER = "manager"
    CONSULTANT = "consultant"


class UserType(str, enum.Enum):
    EXTERNAL = "external"
    INTERNAL = "internal"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)

    gender: Mapped[Gender] = mapped_column(
        Enum(Gender, name="gender_enum"), nullable=False
    )
    user_role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"),
        default=UserRole.ASSOCIATE,  # Fixed default
        nullable=False,
    )
    user_status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status_enum"),
        default=UserStatus.PENDING,
        nullable=False,
    )
    user_type: Mapped[UserType] = mapped_column(
        Enum(UserType, name="user_type_enum"), default=UserType.EXTERNAL, nullable=False
    )

    # Multi-tenancy & Auditing
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
