from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.tenants.repository import TenantRepository
from src.components.tenants.schemas import (
    TenantCreate,
    TenantResponse,
    TenantUpdate,
    PlanTokenQuotas,
    PlanTokenQuotasUpdate,
    TokenUsageResponse,
    ConsumeTokensRequest,
    ConsumeTokensResponse,
    PlanConfigBase,
    PlanConfigCreate,
    PlanConfigResponse,
    PlanConfigUpdate,
    WorkspaceUserQuotaResponse,
)
from src.components.tenants.service import TenantService
from src.components.users.models import User, UserRole
from src.components.users.repository import UserRepository
from src.core.database import get_db
from src.core.deps import RequireRole, get_current_user, require_internal_admin
from src.core.redis import get_redis

router = APIRouter(prefix="/tenants", tags=["Tenants & Workspaces"])


def get_tenant_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TenantService:
    return TenantService(TenantRepository(session), redis)


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_in: TenantCreate,
    service: Annotated[TenantService, Depends(get_tenant_service)],
    # ONLY System Admins can create new billing workspaces
    _: User = Depends(RequireRole([UserRole.ADMIN])),
):
    """Create a new workspace/tenant (Admin only)."""
    return await service.create_tenant(tenant_in)


@router.get("/my-workspace", response_model=TenantResponse)
async def get_my_workspace(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
):
    """Get details of the workspace the current user belongs to."""
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=400, detail="User does not belong to a workspace."
        )
    return await service.get_tenant(current_user.tenant_id)


@router.get("/my-workspace/user-quota", response_model=WorkspaceUserQuotaResponse)
async def get_my_workspace_user_quota(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get user limit, seats used, remaining slots, and permitted assignable roles
    for the current user's workspace plan.
    """
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=400, detail="User does not belong to a workspace."
        )
    user_repo = UserRepository(session)
    active_count = await user_repo.count_active_users_by_tenant(current_user.tenant_id)
    return await service.get_workspace_user_quota(current_user.tenant_id, active_count)


# ---------------------------------------------------------
# Plan Configurations & Limits (Internal Admin Managed)
# ---------------------------------------------------------
@router.get("/plans", response_model=list[PlanConfigResponse])
async def list_plan_configs(
    service: Annotated[TenantService, Depends(get_tenant_service)],
):
    """
    List all subscription plans and their limits (max users, token quotas, allowed roles).
    Publicly accessible so frontends can render plan comparisons.
    """
    return await service.list_plan_configs()


@router.get("/plans/{tier}", response_model=PlanConfigResponse)
async def get_plan_config(
    tier: str,
    service: Annotated[TenantService, Depends(get_tenant_service)],
):
    """Fetch configuration and limits for a specific plan tier."""
    return await service.get_plan_config(tier)


@router.post("/plans", response_model=PlanConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_plan_config(
    plan_in: PlanConfigCreate,
    service: Annotated[TenantService, Depends(get_tenant_service)],
    # Restricted to Internal Admin
    current_user: User = Depends(require_internal_admin),
):
    """
    Create a new subscription plan with max_users, token quota,
    allowed assignable roles, and allowed creator roles (Internal Admin only).
    """
    return await service.create_plan_config(plan_in)


@router.patch("/plans/{tier}", response_model=PlanConfigResponse)
async def update_plan_config(
    tier: str,
    updates: PlanConfigUpdate,
    service: Annotated[TenantService, Depends(get_tenant_service)],
    # Restricted to Internal Admin
    current_user: User = Depends(require_internal_admin),
):
    """
    Update a plan's limits: max users allowed, daily token quota,
    allowed creator roles, and roles external admins on this plan are allowed to create.
    (Internal Admin only).
    """
    return await service.update_plan_config(tier, updates)


# ---------------------------------------------------------
# Token Quotas Management (Internal Admin)
# ---------------------------------------------------------
@router.get("/quotas/plans", response_model=dict[str, int])
async def get_plan_token_quotas(
    service: Annotated[TenantService, Depends(get_tenant_service)],
    current_user: User = Depends(get_current_user),
):
    """
    Get daily token quotas for all subscription tiers (free, plus, pro, max, enterprise).
    """
    return await service.get_plan_token_quotas()


@router.patch("/quotas/plans", response_model=dict[str, int])
async def update_plan_token_quotas(
    updates: PlanTokenQuotasUpdate,
    service: Annotated[TenantService, Depends(get_tenant_service)],
    # Restricted to Internal Admins / Maintainers
    current_user: User = Depends(RequireRole([UserRole.ADMIN, UserRole.MAINTAINER])),
):
    """
    Define / update daily token quotas for plans (Internal Admin only).
    Changes take effect immediately across all workspaces.
    """
    return await service.update_plan_token_quotas(updates)


@router.get("/", response_model=list[TenantResponse])
async def list_tenants(
    service: Annotated[TenantService, Depends(get_tenant_service)],
    current_user: User = Depends(RequireRole([UserRole.ADMIN, UserRole.MAINTAINER])),
    skip: int = 0,
    limit: int = 50,
):
    """List all workspaces/tenants (Admin/Maintainer only)."""
    return await service.list_tenants(skip=skip, limit=limit)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant_by_id(
    tenant_id: int,
    service: Annotated[TenantService, Depends(get_tenant_service)],
    current_user: User = Depends(RequireRole([UserRole.ADMIN, UserRole.MAINTAINER])),
):
    """Fetch details of any workspace/tenant by ID (Admin/Maintainer only)."""
    return await service.get_tenant(tenant_id)


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: int,
    tenant_in: TenantUpdate,
    service: Annotated[TenantService, Depends(get_tenant_service)],
    current_user: User = Depends(RequireRole([UserRole.ADMIN, UserRole.MAINTAINER])),
):
    """Update workspace name, tier, or active status (Admin/Maintainer only)."""
    return await service.update_tenant(tenant_id, tenant_in)


@router.get("/{tenant_id}/token-usage", response_model=TokenUsageResponse)
async def get_tenant_token_usage(
    tenant_id: int,
    service: Annotated[TenantService, Depends(get_tenant_service)],
    current_user: User = Depends(get_current_user),
):
    """
    Get token usage statistics for a workspace today.
    Accessible to users belonging to the workspace or Admins.
    """
    is_staff = current_user.user_role in [UserRole.ADMIN, UserRole.MAINTAINER]
    if not is_staff and current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access token usage for your own workspace.",
        )
    return await service.get_token_usage(tenant_id)


@router.post("/{tenant_id}/consume-tokens", response_model=ConsumeTokensResponse)
async def consume_tenant_tokens(
    tenant_id: int,
    payload: ConsumeTokensRequest,
    service: Annotated[TenantService, Depends(get_tenant_service)],
    current_user: User = Depends(get_current_user),
):
    """
    Record and consume tokens for an AI operation.
    - External users: enforced against the workspace's daily plan token limit (429 if exceeded).
    - Internal users: tracked, but never throttled.
    """
    is_staff = current_user.user_role in [UserRole.ADMIN, UserRole.MAINTAINER]
    if not is_staff and current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only consume tokens for your own workspace.",
        )
    return await service.check_and_consume_tokens(
        tenant_id=tenant_id, user=current_user, tokens=payload.tokens
    )
