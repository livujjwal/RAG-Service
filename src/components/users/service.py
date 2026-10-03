from typing import Sequence

import redis.asyncio as redis
from fastapi import HTTPException, status

from src.core.config import settings
from src.core.permissions import is_internal_admin
from src.core.security import get_password_hash
from src.components.users.models import (
    User,
    UserRole,
    UserStatus,
    UserType,
    SystemLookup,
    LookupCategory,
)
from src.components.users.repository import UserRepository
from src.components.tenants.repository import TenantRepository
from src.components.users.schemas import (
    UserCreate,
    UserUpdate,
    LookupItemCreate,
    LookupItemUpdate,
)

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        tenant_repository: TenantRepository | None = None,
    ):
        self.repository = repository
        self.tenant_repository = tenant_repository

    async def get_user(self, user_id: int) -> User:
        """Fetch a user and raise 404 if not found."""
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )
        return user

    async def create_user(
        self,
        user_in: UserCreate,
        creator: User | None = None,
        created_by: int | None = None,
    ) -> User:
        """
        Business logic for user creation:
        1. Ensure email uniqueness.
        2. Hash password.
        3. If creator is an External Admin:
           - Force target tenant to creator's workspace.
           - Force user_type to EXTERNAL.
           - Enforce tenant plan limits (max_users, allowed_roles).
        4. If creator is an Internal Admin: Full access across any tenant or user_type.
        """
        # Rule 1: Email must be unique
        existing_user = await self.repository.get_by_email(user_in.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )

        user_data = user_in.model_dump(exclude={"password"})
        user_data["hashed_password"] = get_password_hash(user_in.password)

        actual_creator_id = creator.id if creator else created_by
        if actual_creator_id:
            user_data["created_by"] = actual_creator_id

        # External Admin plan limit checks
        if creator and not is_internal_admin(creator):
            # External admins can ONLY create users in their own workspace
            if not creator.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="External admin does not belong to a workspace.",
                )
            target_tenant_id = creator.tenant_id
            user_data["tenant_id"] = target_tenant_id
            user_data["user_type"] = UserType.EXTERNAL  # External admin cannot create internal users

            # Validate against Tenant's Plan Configuration
            if self.tenant_repository:
                tenant = await self.tenant_repository.get_by_id(target_tenant_id)
                if not tenant:
                    raise HTTPException(status_code=404, detail="Workspace not found.")
                if not tenant.is_active:
                    raise HTTPException(status_code=403, detail="Workspace is inactive or suspended.")

                plan_config = await self.tenant_repository.get_plan_config(tenant.tier.value)
                if plan_config:
                    # 1. Check if creator's role is authorized to create users on this plan
                    creator_role_str = (
                        creator.user_role.value
                        if hasattr(creator.user_role, "value")
                        else str(creator.user_role).lower()
                    )
                    creator_roles = [
                        r.strip().lower() for r in plan_config.team_creator_roles.split(",") if r.strip()
                    ]
                    if creator_role_str not in creator_roles:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=(
                                f"Role '{creator_role_str}' is not permitted to create users on the {plan_config.name} plan. "
                                f"Permitted roles: {creator_roles}"
                            ),
                        )

                    # 2. Check if plan allows team management
                    if not plan_config.can_manage_team and plan_config.max_users <= 1:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=(
                                f"Your {plan_config.name} does not support adding team members. "
                                f"Please upgrade your plan to invite more users."
                            ),
                        )

                    # 3. Check max active users allowed on plan
                    current_count = await self.repository.count_active_users_by_tenant(target_tenant_id)
                    if current_count >= plan_config.max_users:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=(
                                f"User limit reached ({current_count}/{plan_config.max_users} users) "
                                f"for {plan_config.name}. Upgrade your plan to add more team members."
                            ),
                        )

                    # 4. Check if requested role is permitted by this plan
                    allowed_roles_list = [
                        r.strip().lower() for r in plan_config.allowed_roles.split(",") if r.strip()
                    ]
                    requested_role = (
                        user_in.user_role.value
                        if hasattr(user_in.user_role, "value")
                        else str(user_in.user_role).lower()
                    )
                    if requested_role not in allowed_roles_list and requested_role != "associate":
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=(
                                f"Role '{requested_role}' cannot be assigned on your {plan_config.name} plan. "
                                f"Permitted assignable roles: {allowed_roles_list}"
                            ),
                        )

        return await self.repository.create(user_data)

    async def update_user(
        self,
        user_id: int,
        user_in: UserUpdate,
        updater: User | None = None,
        updated_by: int | None = None,
    ) -> User:
        """Apply partial updates to a user profile with role/plan validation."""
        # 1. Ensure user exists
        target_user = await self.get_user(user_id)

        # Multi-tenant and permission boundary for external users
        if updater and not is_internal_admin(updater):
            if target_user.tenant_id != updater.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only manage users within your own workspace.",
                )
            if user_in.user_type and user_in.user_type != UserType.EXTERNAL:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="External admins cannot change user type to internal.",
                )
            if user_in.user_role and self.tenant_repository and updater.tenant_id:
                tenant = await self.tenant_repository.get_by_id(updater.tenant_id)
                if tenant:
                    plan = await self.tenant_repository.get_plan_config(tenant.tier.value)
                    if plan:
                        allowed = [r.strip().lower() for r in plan.allowed_roles.split(",") if r.strip()]
                        r_role = user_in.user_role.value if hasattr(user_in.user_role, "value") else str(user_in.user_role).lower()
                        if r_role not in allowed and r_role != "associate":
                            raise HTTPException(
                                status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Role '{r_role}' cannot be assigned on your {plan.name} plan. Allowed: {allowed}",
                            )

        # 2. Extract only fields that were actually provided (exclude None)
        update_data = user_in.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid fields provided for update.",
            )

        # 3. Call repository to perform update
        actual_updater_id = updater.id if updater else updated_by
        updated_user = await self.repository.update(user_id, update_data, actual_updater_id)

        # INVALIDATE CACHE: Force the next request to hit the DB for fresh roles/status
        await redis_client.delete(f"user_cache:{user_id}")
        return updated_user

    async def change_user_type(
        self, user_id: int, new_type: UserType, updated_by: int | None = None
    ) -> User:
        """Change a user's type (internal/external). Admin only."""
        await self.get_user(user_id)
        updated_user = await self.repository.update(
            user_id, {"user_type": new_type}, updated_by=updated_by
        )
        await redis_client.delete(f"user_cache:{user_id}")
        return updated_user

    async def list_users(
        self,
        tenant_id: int | None = None,
        user_role: UserRole | None = None,
        user_status: UserStatus | None = None,
        user_type: UserType | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        """
        Pass-through to repository for listing users, formatting
        the response into a paginated structure.
        """
        users, total_count = await self.repository.list_users(
            tenant_id=tenant_id,
            user_role=user_role,
            user_status=user_status,
            user_type=user_type,
            search=search,
            skip=skip,
            limit=limit,
        )

        return {"items": users, "total": total_count, "skip": skip, "limit": limit}

    async def deactivate_user(
        self,
        user_id: int,
        updater: User | None = None,
        updated_by: int | None = None,
    ) -> dict:
        """Business logic wrapper for soft deletion."""
        target_user = await self.get_user(user_id)

        if updater and not is_internal_admin(updater):
            if target_user.tenant_id != updater.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only deactivate users within your own workspace.",
                )
            if target_user.id == updater.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You cannot deactivate your own account.",
                )

        actual_updater_id = updater.id if updater else updated_by
        success = await self.repository.soft_delete(user_id, actual_updater_id)

        # INVALIDATE CACHE: Force the next request to hit the DB for fresh roles/status
        await redis_client.delete(f"user_cache:{user_id}")

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to deactivate user.",
            )
        return {"message": f"User {user_id} successfully deactivated."}


    # --------------------------------------------------------------------------
    # System Lookups Management (UserRole, UserType, UserStatus, Gender)
    # --------------------------------------------------------------------------
    async def get_lookups_grouped(self, active_only: bool = True) -> dict[str, list]:
        """Fetch all lookups grouped by category."""
        all_items = await self.repository.get_lookups(active_only=active_only)
        grouped: dict[str, list] = {
            "user_role": [],
            "user_type": [],
            "user_status": [],
            "gender": [],
        }
        for item in all_items:
            cat = item.category
            if cat in grouped:
                grouped[cat].append(item)
            else:
                grouped[cat] = [item]
        return grouped

    async def get_lookups_by_category(
        self, category: str, active_only: bool = True
    ) -> Sequence[SystemLookup]:
        """Fetch lookups for a specific category."""
        return await self.repository.get_lookups(
            category=category, active_only=active_only
        )

    async def create_lookup(self, item_in: LookupItemCreate) -> SystemLookup:
        """Create a new lookup option."""
        category = item_in.category.strip().lower()
        code = item_in.code.strip().lower()

        # Check for duplication
        existing = await self.repository.get_lookup_by_category_and_code(
            category, code
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Lookup option '{code}' already exists in category '{category}'.",
            )

        new_lookup = SystemLookup(
            category=category,
            code=code,
            label=item_in.label.strip(),
            description=item_in.description,
            is_active=item_in.is_active,
            weight=item_in.weight,
            sort_order=item_in.sort_order,
            is_system=False,  # Custom options are never system-locked
        )
        return await self.repository.create_lookup(new_lookup)

    async def update_lookup(
        self, category: str, code: str, item_in: LookupItemUpdate
    ) -> SystemLookup:
        """Update an existing lookup option."""
        category = category.strip().lower()
        code = code.strip().lower()

        lookup = await self.repository.get_lookup_by_category_and_code(category, code)
        if not lookup:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lookup option '{code}' not found in category '{category}'.",
            )

        if item_in.label is not None:
            lookup.label = item_in.label.strip()
        if item_in.description is not None:
            lookup.description = item_in.description
        if item_in.is_active is not None:
            lookup.is_active = item_in.is_active
        if item_in.weight is not None:
            lookup.weight = item_in.weight
        if item_in.sort_order is not None:
            lookup.sort_order = item_in.sort_order

        return await self.repository.update_lookup(lookup)

    async def delete_lookup(self, category: str, code: str) -> dict:
        """Delete a custom lookup option. System-level built-in options cannot be deleted."""
        category = category.strip().lower()
        code = code.strip().lower()

        lookup = await self.repository.get_lookup_by_category_and_code(category, code)
        if not lookup:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lookup option '{code}' not found in category '{category}'.",
            )

        if lookup.is_system:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Built-in system option '{code}' cannot be deleted. Deactivate it with is_active=false instead.",
            )

        await self.repository.delete_lookup(lookup)
        return {
            "message": f"Lookup option '{code}' in category '{category}' successfully removed."
        }

