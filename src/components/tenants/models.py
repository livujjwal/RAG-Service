import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, Enum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    PLUS = "plus"
    PRO = "pro"
    MAX = "max"
    ENTERPRISE = "enterprise"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )

    tier: Mapped[SubscriptionTier] = mapped_column(
        Enum(SubscriptionTier, name="subscription_tier_enum"),
        default=SubscriptionTier.FREE,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PlanConfig(Base):
    __tablename__ = "plan_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tier: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_users: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    daily_token_quota: Mapped[int] = mapped_column(Integer, default=50000, nullable=False)
    can_upload_documents: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_manage_team: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allowed_roles: Mapped[str] = mapped_column(String(255), default="associate", nullable=False)
    team_creator_roles: Mapped[str] = mapped_column(String(255), default="admin", nullable=False)
    allowed_features: Mapped[str] = mapped_column(
        String(1000),
        default="documents:upload,documents:read,rag:query,users:read,workspace:read",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ApiPermissionRule(Base):
    __tablename__ = "api_permission_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tier: Mapped[str] = mapped_column(String(50), index=True, nullable=False)  # "free", "plus", "pro", "max", "enterprise", or "*"
    user_role: Mapped[str] = mapped_column(String(50), index=True, nullable=False)  # e.g. "admin", "manager", "associate", or "*"
    feature_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)  # e.g. "documents:upload", "users:create"
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("tier", "user_role", "feature_code", name="uq_plan_role_feature"),
    )


