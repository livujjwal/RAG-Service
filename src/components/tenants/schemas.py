from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.components.tenants.models import SubscriptionTier


class TenantBase(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    tier: SubscriptionTier = SubscriptionTier.FREE


class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    name: str | None = None
    tier: SubscriptionTier | None = None
    is_active: bool | None = None


class TenantResponse(TenantBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Token Quotas & Usage Tracking Schemas
# ==============================================================================
class PlanTokenQuotas(BaseModel):
    free: int = Field(ge=0, description="Daily token quota for Free tier")
    plus: int = Field(ge=0, description="Daily token quota for Plus tier")
    pro: int = Field(ge=0, description="Daily token quota for Pro tier")
    max: int = Field(ge=0, description="Daily token quota for Max tier")
    enterprise: int = Field(ge=0, description="Daily token quota for Enterprise tier")


class PlanTokenQuotasUpdate(BaseModel):
    free: int | None = Field(None, ge=0)
    plus: int | None = Field(None, ge=0)
    pro: int | None = Field(None, ge=0)
    max: int | None = Field(None, ge=0)
    enterprise: int | None = Field(None, ge=0)


class TokenUsageResponse(BaseModel):
    tenant_id: int
    tenant_name: str
    tier: str
    daily_token_limit: int
    tokens_used_today: int
    tokens_remaining_today: int
    usage_percentage: float
    date: str


class ConsumeTokensRequest(BaseModel):
    tokens: int = Field(gt=0, description="Number of tokens consumed by the AI operation")


class ConsumeTokensResponse(BaseModel):
    allowed: bool
    tokens_consumed: int
    total_used_today: int
    daily_limit: int
    remaining_tokens: int
    is_internal_user: bool


# ==============================================================================
# Database Stored Plan Configurations (Managed by Internal Admin)
# ==============================================================================
class PlanConfigBase(BaseModel):
    tier: str
    name: str
    description: str | None = None
    max_users: int = Field(ge=1, description="Maximum users allowed in workspace on this plan")
    daily_token_quota: int = Field(ge=0, description="Daily token quota for the plan")
    can_upload_documents: bool = True
    can_manage_team: bool = False
    allowed_roles: str = Field("associate", description="Comma-separated allowed roles external admin can assign")
    team_creator_roles: str = Field("admin", description="Comma-separated roles allowed to create users in this plan")
    allowed_features: str = Field(
        "documents:upload,documents:read,rag:query,users:read,workspace:read",
        description="Comma-separated enabled feature codes for this tier",
    )
    is_active: bool = True


class PlanConfigCreate(PlanConfigBase):
    pass


class PlanConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    max_users: int | None = Field(None, ge=1)
    daily_token_quota: int | None = Field(None, ge=0)
    can_upload_documents: bool | None = None
    can_manage_team: bool | None = None
    allowed_roles: str | None = None
    team_creator_roles: str | None = None
    allowed_features: str | None = None
    is_active: bool | None = None


class PlanConfigResponse(PlanConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceUserQuotaResponse(BaseModel):
    tenant_id: int
    tenant_name: str
    tier: str
    plan_name: str
    max_users: int
    current_users: int
    remaining_slots: int
    can_create_users: bool
    allowed_roles_to_assign: list[str]
    team_creator_roles: list[str]


# ==============================================================================
# API & Feature Permission Rules (Plan x Role x Feature Matrix)
# ==============================================================================
class ApiPermissionRuleBase(BaseModel):
    tier: str = Field(description="Plan tier e.g. free, plus, pro, max, enterprise, or '*' for all")
    user_role: str = Field(description="User role e.g. admin, manager, associate, or '*' for all")
    feature_code: str = Field(description="Feature/API code e.g. documents:upload, users:create")
    description: str | None = None
    is_allowed: bool = True


class ApiPermissionRuleCreate(ApiPermissionRuleBase):
    pass


class ApiPermissionRuleUpdate(BaseModel):
    is_allowed: bool | None = None
    description: str | None = None


class ApiPermissionRuleResponse(ApiPermissionRuleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PermissionMatrixResponse(BaseModel):
    tiers: list[str]
    roles: list[str]
    features: list[dict[str, str]]
    matrix: dict[str, dict[str, list[str]]]  # tier -> role -> [allowed feature codes]


class MyAccessResponse(BaseModel):
    user_id: int
    email: str
    user_role: str
    user_type: str
    is_internal_admin: bool
    tenant_id: int | None
    tenant_name: str | None
    plan_tier: str | None
    plan_name: str | None
    allowed_features: list[str]
    can_create_users: bool
    max_users_allowed: int
    current_workspace_users: int
    remaining_user_slots: int
    allowed_assignable_roles: list[str]


class CheckPermissionRequest(BaseModel):
    feature_code: str
    tier: str | None = None
    user_role: str | None = None


class CheckPermissionResponse(BaseModel):
    feature_code: str
    tier: str
    user_role: str
    is_allowed: bool
    reason: str



