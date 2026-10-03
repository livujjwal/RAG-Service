from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Annotated

from src.core.database import get_db
from src.core.deps import get_current_user, RequireRole
from src.components.users.repository import UserRepository
from src.components.users.service import UserService
from src.components.users.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    LookupItemCreate,
    LookupItemUpdate,
    LookupItemResponse,
    LookupsGroupedResponse,
    UserTypeChangeRequest,
)
from src.components.users.models import User, UserRole, UserStatus, UserType

router = APIRouter(prefix="/users", tags=["Users"])


from src.components.tenants.repository import TenantRepository
from src.core.deps import get_current_user, RequireRole, require_internal_admin
from src.core.permissions import is_internal_admin


# --- Dependency Injection ---
def get_user_service(session: AsyncSession = Depends(get_db)) -> UserService:
    repository = UserRepository(session)
    tenant_repository = TenantRepository(session)
    return UserService(repository, tenant_repository)


# --- Endpoints ---


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: Annotated[User, Depends(get_current_user)]):
    """Retrieve the profile of the currently authenticated user."""
    return current_user


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    service: UserService = Depends(get_user_service),
    # External Admin / Manager or Internal Admin
    current_user: User = Depends(
        RequireRole([UserRole.ADMIN, UserRole.MAINTAINER, UserRole.MANAGER])
    ),
):
    """
    Register a new user in the system.
    - External admins can create users in their workspace up to their plan quota.
    - Internal admins have unlimited user creation powers across all tenants.
    """
    return await service.create_user(user_in, creator=current_user)


# ---------------------------------------------------------
# Dynamic System Lookups (UserRole, UserType, UserStatus, Gender)
# ---------------------------------------------------------
@router.get("/lookups", response_model=LookupsGroupedResponse)
async def get_all_lookups(
    active_only: bool = Query(True, description="Filter for active options only"),
    service: UserService = Depends(get_user_service),
):
    """
    Retrieve all lookup options grouped by category:
    user_role, user_type, user_status, and gender.
    Ideal for client-side forms and frontend dropdowns.
    """
    return await service.get_lookups_grouped(active_only=active_only)


@router.get("/lookups/{category}", response_model=list[LookupItemResponse])
async def get_lookups_by_category(
    category: str,
    active_only: bool = Query(True, description="Filter for active options only"),
    service: UserService = Depends(get_user_service),
):
    """Retrieve lookup options for a specific category (e.g. 'user_role', 'gender')."""
    return await service.get_lookups_by_category(category, active_only=active_only)


@router.post(
    "/lookups",
    response_model=LookupItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_lookup_option(
    item_in: LookupItemCreate,
    service: UserService = Depends(get_user_service),
    # Only Admins and Maintainers can add new lookup options
    current_user: User = Depends(RequireRole([UserRole.ADMIN, UserRole.MAINTAINER])),
):
    """Add a new option to a lookup category (Admin/Maintainer only)."""
    return await service.create_lookup(item_in)


@router.patch(
    "/lookups/{category}/{code}",
    response_model=LookupItemResponse,
)
async def update_lookup_option(
    category: str,
    code: str,
    item_in: LookupItemUpdate,
    service: UserService = Depends(get_user_service),
    # Only Admins and Maintainers can update lookup options
    current_user: User = Depends(RequireRole([UserRole.ADMIN, UserRole.MAINTAINER])),
):
    """Update an existing lookup option's label, active status, weight, or sort order (Admin/Maintainer only)."""
    return await service.update_lookup(category, code, item_in)


@router.delete(
    "/lookups/{category}/{code}",
    status_code=status.HTTP_200_OK,
)
async def delete_lookup_option(
    category: str,
    code: str,
    service: UserService = Depends(get_user_service),
    # Only Admins and Maintainers can delete lookup options
    current_user: User = Depends(RequireRole([UserRole.ADMIN, UserRole.MAINTAINER])),
):
    """
    Delete a custom lookup option (Admin/Maintainer only).
    Note: Built-in system options cannot be permanently deleted, but can be deactivated.
    """
    return await service.delete_lookup(category, code)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user),
):
    """Fetch a single user's profile by their ID."""
    return await service.get_user(user_id)


@router.get("/", response_model=dict[str, Any])
async def list_users(
    tenant_id: int | None = Query(None, description="Filter by tenant ID"),
    user_role: UserRole | None = Query(None, description="Filter by user role"),
    user_status: UserStatus | None = Query(None, description="Filter by user status"),
    user_type: UserType | None = Query(
        None, description="Filter by user type (internal/external)"
    ),
    search: str | None = Query(None, description="Search by name, email, or phone"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=100, description="Pagination limit"),
    service: UserService = Depends(get_user_service),
    # Require at least MANAGER level to list users
    current_user: User = Depends(
        RequireRole([UserRole.ADMIN, UserRole.MAINTAINER, UserRole.MANAGER])
    ),
):
    """
    List users with optional filtering, search, and pagination.
    External admins & managers are scoped strictly to their workspace members.
    Internal admins can view users across all workspaces.
    """
    effective_tenant_id = tenant_id
    if not is_internal_admin(current_user):
        effective_tenant_id = current_user.tenant_id

    return await service.list_users(
        tenant_id=effective_tenant_id,
        user_role=user_role,
        user_status=user_status,
        user_type=user_type,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_in: UserUpdate,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user),
):
    """Apply partial updates to a user."""
    return await service.update_user(user_id, user_in, updater=current_user)


@router.patch("/{user_id}/user-type", response_model=UserResponse)
async def change_user_type(
    user_id: int,
    payload: UserTypeChangeRequest,
    service: UserService = Depends(get_user_service),
    # Strictly restricted to Internal Admin
    current_user: User = Depends(require_internal_admin),
):
    """
    Switch user type between 'internal' and 'external' (Internal Admin only).
    Immediately refreshes cache.
    """
    return await service.change_user_type(
        user_id, payload.user_type, updated_by=current_user.id
    )


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def deactivate_user(
    user_id: int,
    service: UserService = Depends(get_user_service),
    # Only Admins and Maintainers can delete users
    current_user: User = Depends(RequireRole([UserRole.ADMIN, UserRole.MAINTAINER])),
):
    """Soft-delete a user (changes status to DELETED)."""
    return await service.deactivate_user(user_id, updater=current_user)
