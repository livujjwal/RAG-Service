from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.users.models import (
    User,
    UserRole,
    UserStatus,
    UserType,
    SystemLookup,
    LookupCategory,
)

DEFAULT_LOOKUPS = [
    # User Roles (with hierarchical weights)
    {"category": "user_role", "code": "admin", "label": "Admin", "weight": 100, "is_system": True, "sort_order": 1},
    {"category": "user_role", "code": "maintainer", "label": "Maintainer", "weight": 90, "is_system": True, "sort_order": 2},
    {"category": "user_role", "code": "vice_president", "label": "Vice President", "weight": 80, "is_system": False, "sort_order": 3},
    {"category": "user_role", "code": "senior_application_manager", "label": "Senior Application Manager", "weight": 70, "is_system": False, "sort_order": 4},
    {"category": "user_role", "code": "application_manager", "label": "Application Manager", "weight": 60, "is_system": False, "sort_order": 5},
    {"category": "user_role", "code": "senior_account_manager", "label": "Senior Account Manager", "weight": 50, "is_system": False, "sort_order": 6},
    {"category": "user_role", "code": "account_manager", "label": "Account Manager", "weight": 40, "is_system": False, "sort_order": 7},
    {"category": "user_role", "code": "manager", "label": "Manager", "weight": 30, "is_system": False, "sort_order": 8},
    {"category": "user_role", "code": "team_lead", "label": "Team Lead", "weight": 20, "is_system": False, "sort_order": 9},
    {"category": "user_role", "code": "consultant", "label": "Consultant", "weight": 10, "is_system": False, "sort_order": 10},
    {"category": "user_role", "code": "associate", "label": "Associate", "weight": 0, "is_system": False, "sort_order": 11},
    # User Types
    {"category": "user_type", "code": "external", "label": "External", "weight": None, "is_system": True, "sort_order": 1},
    {"category": "user_type", "code": "internal", "label": "Internal", "weight": None, "is_system": True, "sort_order": 2},
    # User Statuses
    {"category": "user_status", "code": "active", "label": "Active", "weight": None, "is_system": True, "sort_order": 1},
    {"category": "user_status", "code": "inactive", "label": "Inactive", "weight": None, "is_system": True, "sort_order": 2},
    {"category": "user_status", "code": "pending", "label": "Pending", "weight": None, "is_system": True, "sort_order": 3},
    {"category": "user_status", "code": "suspended", "label": "Suspended", "weight": None, "is_system": False, "sort_order": 4},
    {"category": "user_status", "code": "deleted", "label": "Deleted", "weight": None, "is_system": True, "sort_order": 5},
    # Genders
    {"category": "gender", "code": "male", "label": "Male", "weight": None, "is_system": False, "sort_order": 1},
    {"category": "gender", "code": "female", "label": "Female", "weight": None, "is_system": False, "sort_order": 2},
    {"category": "gender", "code": "other", "label": "Other", "weight": None, "is_system": False, "sort_order": 3},
]


async def seed_default_lookups(session: AsyncSession) -> None:
    """Seed initial system lookups if table is empty."""
    result = await session.execute(select(func.count(SystemLookup.id)))
    count = result.scalar() or 0
    if count == 0:
        for item in DEFAULT_LOOKUPS:
            lookup = SystemLookup(
                category=item["category"],
                code=item["code"],
                label=item["label"],
                weight=item["weight"],
                is_system=item["is_system"],
                sort_order=item["sort_order"],
                is_active=True,
            )
            session.add(lookup)
        await session.commit()



class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """Fetch a single user by primary key ID."""
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a single user by email address (used during registration & login)."""
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def count_active_users_by_tenant(self, tenant_id: int) -> int:
        """Count active/pending users in a specific tenant workspace."""
        stmt = select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            User.user_status != UserStatus.DELETED,
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def list_users(
        self,
        tenant_id: int | None = None,
        user_role: UserRole | None = None,
        user_status: UserStatus | None = None,
        user_type: UserType | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[User], int]:
        """
        List users with dynamic filtering, full-text pattern matching,
        and pagination. Returns (records, total_count).
        """
        query = select(User)
        count_query = select(func.count(User.id))

        # 1. Multi-tenant isolation filter
        if tenant_id is not None:
            query = query.where(User.tenant_id == tenant_id)
            count_query = count_query.where(User.tenant_id == tenant_id)

        # 2. Enum filters
        if user_role is not None:
            query = query.where(User.user_role == user_role)
            count_query = count_query.where(User.user_role == user_role)

        if user_status is not None:
            query = query.where(User.user_status == user_status)
            count_query = count_query.where(User.user_status == user_status)

        if user_type is not None:
            query = query.where(User.user_type == user_type)
            count_query = count_query.where(User.user_type == user_type)

        # 3. Text search (first name, last name, email, or phone)
        if search:
            term = f"%{search}%"
            search_filter = (
                User.first_name.ilike(term)
                | User.last_name.ilike(term)
                | User.email.ilike(term)
                | User.phone.ilike(term)
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        # Execute total record count for pagination metadata
        total_result = await self.session.execute(count_query)
        total_count = total_result.scalar_one()

        # Apply ordering and limit/offset pagination
        query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        users = result.scalars().all()

        return users, total_count

    async def create(self, user_data: dict) -> User:
        """Persist a new user entity to the database."""
        user = User(**user_data)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update(
        self, user_id: int, update_data: dict, updated_by: int | None = None
    ) -> User | None:
        """Update fields on an existing user with audit tracking."""
        update_data["updated_at"] = datetime.now(timezone.utc)
        if updated_by is not None:
            update_data["updated_by"] = updated_by

        stmt = update(User).where(User.id == user_id).values(**update_data)
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            return None

        await self.session.commit()
        return await self.get_by_id(user_id)

    async def soft_delete(self, user_id: int, updated_by: int | None = None) -> bool:
        """
        Soft delete: Sets status to DELETED without purging
        the database row (preserves audit integrity).
        """
        values = {
            "status": UserStatus.DELETED,
            "updated_at": datetime.now(timezone.utc),
        }
        if updated_by is not None:
            values["updated_by"] = updated_by

        stmt = update(User).where(User.id == user_id).values(**values)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def hard_delete(self, user_id: int) -> bool:
        """Permanently remove a user record from the database."""
        stmt = delete(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    # --------------------------------------------------------------------------
    # System Lookups (UserRole, UserType, UserStatus, Gender)
    # --------------------------------------------------------------------------
    async def get_lookups(
        self, category: str | None = None, active_only: bool = True
    ) -> Sequence[SystemLookup]:
        """Fetch lookup items with optional category and active filtering."""
        stmt = select(SystemLookup)
        if category:
            stmt = stmt.where(SystemLookup.category == category)
        if active_only:
            stmt = stmt.where(SystemLookup.is_active == True)
        stmt = stmt.order_by(SystemLookup.sort_order.asc(), SystemLookup.id.asc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_lookup_by_category_and_code(
        self, category: str, code: str
    ) -> SystemLookup | None:
        """Fetch a single lookup item by category and code."""
        stmt = select(SystemLookup).where(
            SystemLookup.category == category, SystemLookup.code == code
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_lookup(self, lookup: SystemLookup) -> SystemLookup:
        """Create a new lookup option."""
        self.session.add(lookup)
        await self.session.commit()
        await self.session.refresh(lookup)
        return lookup

    async def update_lookup(self, lookup: SystemLookup) -> SystemLookup:
        """Save updates to an existing lookup option."""
        lookup.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(lookup)
        return lookup

    async def delete_lookup(self, lookup: SystemLookup) -> None:
        """Permanently remove a custom lookup option."""
        await self.session.delete(lookup)
        await self.session.commit()

