from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.tenants.repository import TenantRepository
from src.components.tenants.schemas import (
    ApiPermissionRuleCreate,
    ApiPermissionRuleResponse,
    ApiPermissionRuleUpdate,
    PermissionMatrixResponse,
    MyAccessResponse,
    CheckPermissionRequest,
    CheckPermissionResponse,
)
from src.components.tenants.service import TenantService
from src.components.users.models import User
from src.components.users.repository import UserRepository
from src.core.database import get_db
from src.core.deps import get_current_user, require_internal_admin
from src.core.redis import get_redis

router = APIRouter(prefix="/permissions", tags=["Permissions & Role Access"])


def get_tenant_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TenantService:
    return TenantService(TenantRepository(session), redis)


@router.get("/matrix", response_model=PermissionMatrixResponse)
async def get_permission_matrix(
    service: Annotated[TenantService, Depends(get_tenant_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Get the complete Plan Tier x Role x Feature access matrix.
    Frontend can use this to render the permissions table and evaluate feature access.
    """
    return await service.get_permission_matrix()


@router.get("/my-access", response_model=MyAccessResponse)
async def get_my_access(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Retrieve the current authenticated user's access profile:
    - Allowed features for their plan & role
    - Can they create users?
    - Workspace seat limit & current seats used
    - Permitted roles they can assign to new team members
    """
    user_repo = UserRepository(session)
    active_count = 1
    if current_user.tenant_id:
        active_count = await user_repo.count_active_users_by_tenant(current_user.tenant_id)
    return await service.get_user_access_summary(current_user, current_active_users=active_count)


@router.get("/rules", response_model=list[ApiPermissionRuleResponse])
async def list_permission_rules(
    service: Annotated[TenantService, Depends(get_tenant_service)],
    # Restricted to Internal Admin
    current_user: Annotated[User, Depends(require_internal_admin)],
    tier: str | None = Query(None, description="Filter by plan tier (free, plus, pro, max, enterprise, *)"),
    user_role: str | None = Query(None, description="Filter by user role (admin, manager, associate, *)"),
    feature_code: str | None = Query(None, description="Filter by feature code (e.g. documents:upload, users:create)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """List all API & feature permission rules stored in the database (Internal Admin only)."""
    return await service.list_permission_rules(
        tier=tier, user_role=user_role, feature_code=feature_code, skip=skip, limit=limit
    )


@router.post(
    "/rules",
    response_model=ApiPermissionRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_permission_rule(
    rule_in: ApiPermissionRuleCreate,
    service: Annotated[TenantService, Depends(get_tenant_service)],
    # Restricted to Internal Admin
    current_user: Annotated[User, Depends(require_internal_admin)],
):
    """Create a new API permission rule in the database (Internal Admin only)."""
    return await service.create_permission_rule(rule_in)


@router.patch("/rules/{rule_id}", response_model=ApiPermissionRuleResponse)
async def update_permission_rule(
    rule_id: int,
    updates: ApiPermissionRuleUpdate,
    service: Annotated[TenantService, Depends(get_tenant_service)],
    # Restricted to Internal Admin
    current_user: Annotated[User, Depends(require_internal_admin)],
):
    """Update an existing API permission rule (e.g., toggle is_allowed) (Internal Admin only)."""
    return await service.update_permission_rule(rule_id, updates)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_permission_rule(
    rule_id: int,
    service: Annotated[TenantService, Depends(get_tenant_service)],
    # Restricted to Internal Admin
    current_user: Annotated[User, Depends(require_internal_admin)],
):
    """Delete a custom permission rule from the database (Internal Admin only)."""
    return await service.delete_permission_rule(rule_id)


@router.post("/check", response_model=CheckPermissionResponse)
async def check_permission(
    payload: CheckPermissionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
):
    """Evaluate whether a specific feature is permitted for a plan and role."""
    from src.core.permissions import is_internal_admin

    if is_internal_admin(current_user) and not payload.tier and not payload.user_role:
        return CheckPermissionResponse(
            feature_code=payload.feature_code,
            tier="internal",
            user_role="admin",
            is_allowed=True,
            reason="Internal platform superusers have unconditional access to all features.",
        )

    # Use current user's workspace if not specified
    tenant_repo = TenantRepository(session)
    if payload.tier:
        tier_to_check = payload.tier.lower()
    elif current_user.tenant_id:
        t = await tenant_repo.get_by_id(current_user.tenant_id)
        tier_to_check = t.tier.value if t else "free"
    else:
        tier_to_check = "free"

    role_to_check = (
        payload.user_role.lower()
        if payload.user_role
        else (current_user.user_role.value if hasattr(current_user.user_role, "value") else str(current_user.user_role).lower())
    )

    is_ok, reason = await tenant_repo.check_feature_access(
        tenant_id=current_user.tenant_id or 1,
        user_role=role_to_check,
        feature_code=payload.feature_code,
        redis=redis,
    )

    return CheckPermissionResponse(
        feature_code=payload.feature_code,
        tier=tier_to_check,
        user_role=role_to_check,
        is_allowed=is_ok,
        reason=reason or "Feature is permitted.",
    )
