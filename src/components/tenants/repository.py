from datetime import datetime, timezone
import json
from typing import Sequence

from redis.asyncio import Redis
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.tenants.models import Tenant, PlanConfig, ApiPermissionRule

DEFAULT_PLAN_CONFIGS = [
    {
        "tier": "free",
        "name": "Free Tier",
        "description": "Individual evaluation plan",
        "max_users": 1,
        "daily_token_quota": 50_000,
        "can_upload_documents": True,
        "can_manage_team": False,
        "allowed_roles": "associate",
        "team_creator_roles": "admin",
        "allowed_features": "documents:upload,documents:read,rag:query,users:read,workspace:read,analytics:read",
        "is_active": True,
    },
    {
        "tier": "plus",
        "name": "Plus Tier",
        "description": "Small team collaboration",
        "max_users": 5,
        "daily_token_quota": 250_000,
        "can_upload_documents": True,
        "can_manage_team": True,
        "allowed_roles": "associate,consultant",
        "team_creator_roles": "admin",
        "allowed_features": "documents:upload,documents:read,rag:query,users:create,users:read,users:update,workspace:read,analytics:read",
        "is_active": True,
    },
    {
        "tier": "pro",
        "name": "Pro Tier",
        "description": "Professional teams with team lead and manager support",
        "max_users": 25,
        "daily_token_quota": 1_000_000,
        "can_upload_documents": True,
        "can_manage_team": True,
        "allowed_roles": "associate,consultant,team_lead,manager",
        "team_creator_roles": "admin,manager",
        "allowed_features": "documents:upload,documents:read,documents:delete,rag:query,users:create,users:read,users:update,users:delete,workspace:read,workspace:manage,analytics:read",
        "is_active": True,
    },
    {
        "tier": "max",
        "name": "Max Tier",
        "description": "High-volume department scale",
        "max_users": 100,
        "daily_token_quota": 5_000_000,
        "can_upload_documents": True,
        "can_manage_team": True,
        "allowed_roles": "associate,consultant,team_lead,manager,account_manager",
        "team_creator_roles": "admin,manager",
        "allowed_features": "documents:upload,documents:read,documents:delete,rag:query,users:create,users:read,users:update,users:delete,workspace:read,workspace:manage,analytics:read",
        "is_active": True,
    },
    {
        "tier": "enterprise",
        "name": "Enterprise Tier",
        "description": "Unlimited enterprise workspace",
        "max_users": 10000,
        "daily_token_quota": 999_999_999,
        "can_upload_documents": True,
        "can_manage_team": True,
        "allowed_roles": "associate,consultant,team_lead,manager,account_manager,senior_account_manager,application_manager,senior_application_manager,vice_president,maintainer,admin",
        "team_creator_roles": "admin,maintainer,manager",
        "allowed_features": "documents:upload,documents:read,documents:delete,rag:query,users:create,users:read,users:update,users:delete,workspace:read,workspace:manage,analytics:read",
        "is_active": True,
    },
]

# Standard feature registry with descriptions
KNOWN_FEATURES = [
    {"code": "documents:upload", "name": "Upload Documents", "description": "Upload PDFs and embed vectors"},
    {"code": "documents:read", "name": "View Documents", "description": "Browse and search uploaded documents"},
    {"code": "documents:delete", "name": "Delete Documents", "description": "Remove documents and vectors from workspace"},
    {"code": "rag:query", "name": "Query RAG Engine", "description": "Send questions to AI knowledge base"},
    {"code": "users:create", "name": "Create Team Members", "description": "Add new users to workspace up to plan quota"},
    {"code": "users:read", "name": "View Team Members", "description": "List users in workspace"},
    {"code": "users:update", "name": "Update Team Members", "description": "Update user profiles in workspace"},
    {"code": "users:delete", "name": "Deactivate Team Members", "description": "Deactivate users in workspace"},
    {"code": "workspace:read", "name": "View Workspace", "description": "View workspace status and token quotas"},
    {"code": "workspace:manage", "name": "Manage Workspace", "description": "Modify workspace settings"},
    {"code": "analytics:read", "name": "View Analytics", "description": "Inspect daily token consumption and quotas"},
]

DEFAULT_API_PERMISSION_RULES = [
    # --- FREE TIER ---
    {"tier": "free", "user_role": "admin", "feature_code": "documents:upload", "is_allowed": True, "description": "Free admin can upload documents"},
    {"tier": "free", "user_role": "admin", "feature_code": "documents:read", "is_allowed": True, "description": "Free admin can view documents"},
    {"tier": "free", "user_role": "admin", "feature_code": "rag:query", "is_allowed": True, "description": "Free admin can query AI"},
    {"tier": "free", "user_role": "admin", "feature_code": "users:read", "is_allowed": True, "description": "Free admin can view self profile"},
    {"tier": "free", "user_role": "admin", "feature_code": "users:create", "is_allowed": False, "description": "Free plan cannot add team members (max 1 user)"},
    {"tier": "free", "user_role": "admin", "feature_code": "workspace:read", "is_allowed": True, "description": "Free admin can view workspace"},
    {"tier": "free", "user_role": "admin", "feature_code": "analytics:read", "is_allowed": True, "description": "Free admin can view token stats"},
    {"tier": "free", "user_role": "associate", "feature_code": "documents:read", "is_allowed": True, "description": "Read documents"},
    {"tier": "free", "user_role": "associate", "feature_code": "rag:query", "is_allowed": True, "description": "Query AI"},

    # --- PLUS TIER ---
    {"tier": "plus", "user_role": "admin", "feature_code": "documents:upload", "is_allowed": True, "description": "Upload documents"},
    {"tier": "plus", "user_role": "admin", "feature_code": "documents:read", "is_allowed": True, "description": "View documents"},
    {"tier": "plus", "user_role": "admin", "feature_code": "rag:query", "is_allowed": True, "description": "Query AI"},
    {"tier": "plus", "user_role": "admin", "feature_code": "users:create", "is_allowed": True, "description": "Plus admin can add up to 5 members"},
    {"tier": "plus", "user_role": "admin", "feature_code": "users:read", "is_allowed": True, "description": "View workspace members"},
    {"tier": "plus", "user_role": "admin", "feature_code": "users:update", "is_allowed": True, "description": "Update workspace members"},
    {"tier": "plus", "user_role": "admin", "feature_code": "workspace:read", "is_allowed": True, "description": "View workspace"},
    {"tier": "plus", "user_role": "admin", "feature_code": "analytics:read", "is_allowed": True, "description": "View token usage"},
    {"tier": "plus", "user_role": "consultant", "feature_code": "documents:upload", "is_allowed": True, "description": "Consultant upload"},
    {"tier": "plus", "user_role": "consultant", "feature_code": "documents:read", "is_allowed": True, "description": "Consultant read"},
    {"tier": "plus", "user_role": "consultant", "feature_code": "rag:query", "is_allowed": True, "description": "Consultant query"},
    {"tier": "plus", "user_role": "associate", "feature_code": "documents:read", "is_allowed": True, "description": "Associate read"},
    {"tier": "plus", "user_role": "associate", "feature_code": "rag:query", "is_allowed": True, "description": "Associate query"},

    # --- PRO TIER ---
    {"tier": "pro", "user_role": "admin", "feature_code": "documents:upload", "is_allowed": True, "description": "Admin full access"},
    {"tier": "pro", "user_role": "admin", "feature_code": "documents:read", "is_allowed": True, "description": "Admin full access"},
    {"tier": "pro", "user_role": "admin", "feature_code": "documents:delete", "is_allowed": True, "description": "Admin delete docs"},
    {"tier": "pro", "user_role": "admin", "feature_code": "rag:query", "is_allowed": True, "description": "Admin query AI"},
    {"tier": "pro", "user_role": "admin", "feature_code": "users:create", "is_allowed": True, "description": "Pro admin can add up to 25 members"},
    {"tier": "pro", "user_role": "admin", "feature_code": "users:read", "is_allowed": True, "description": "Pro admin list users"},
    {"tier": "pro", "user_role": "admin", "feature_code": "users:update", "is_allowed": True, "description": "Pro admin update users"},
    {"tier": "pro", "user_role": "admin", "feature_code": "users:delete", "is_allowed": True, "description": "Pro admin deactivate users"},
    {"tier": "pro", "user_role": "admin", "feature_code": "workspace:read", "is_allowed": True, "description": "View workspace"},
    {"tier": "pro", "user_role": "admin", "feature_code": "workspace:manage", "is_allowed": True, "description": "Manage workspace"},
    {"tier": "pro", "user_role": "admin", "feature_code": "analytics:read", "is_allowed": True, "description": "View token analytics"},
    {"tier": "pro", "user_role": "manager", "feature_code": "documents:upload", "is_allowed": True, "description": "Manager upload docs"},
    {"tier": "pro", "user_role": "manager", "feature_code": "documents:read", "is_allowed": True, "description": "Manager read docs"},
    {"tier": "pro", "user_role": "manager", "feature_code": "rag:query", "is_allowed": True, "description": "Manager query AI"},
    {"tier": "pro", "user_role": "manager", "feature_code": "users:create", "is_allowed": True, "description": "Manager can add users on Pro"},
    {"tier": "pro", "user_role": "manager", "feature_code": "users:read", "is_allowed": True, "description": "Manager list users"},
    {"tier": "pro", "user_role": "team_lead", "feature_code": "documents:upload", "is_allowed": True, "description": "Team lead upload"},
    {"tier": "pro", "user_role": "team_lead", "feature_code": "documents:read", "is_allowed": True, "description": "Team lead read"},
    {"tier": "pro", "user_role": "team_lead", "feature_code": "rag:query", "is_allowed": True, "description": "Team lead query"},
    {"tier": "pro", "user_role": "consultant", "feature_code": "documents:read", "is_allowed": True, "description": "Consultant read"},
    {"tier": "pro", "user_role": "consultant", "feature_code": "rag:query", "is_allowed": True, "description": "Consultant query"},
    {"tier": "pro", "user_role": "associate", "feature_code": "documents:read", "is_allowed": True, "description": "Associate read"},
    {"tier": "pro", "user_role": "associate", "feature_code": "rag:query", "is_allowed": True, "description": "Associate query"},

    # --- MAX TIER ---
    {"tier": "max", "user_role": "admin", "feature_code": "documents:upload", "is_allowed": True, "description": "Max admin upload"},
    {"tier": "max", "user_role": "admin", "feature_code": "documents:read", "is_allowed": True, "description": "Max admin read"},
    {"tier": "max", "user_role": "admin", "feature_code": "documents:delete", "is_allowed": True, "description": "Max admin delete docs"},
    {"tier": "max", "user_role": "admin", "feature_code": "rag:query", "is_allowed": True, "description": "Max admin query AI"},
    {"tier": "max", "user_role": "admin", "feature_code": "users:create", "is_allowed": True, "description": "Max admin can add up to 100 members"},
    {"tier": "max", "user_role": "admin", "feature_code": "users:read", "is_allowed": True, "description": "Max admin list users"},
    {"tier": "max", "user_role": "admin", "feature_code": "users:update", "is_allowed": True, "description": "Max admin update users"},
    {"tier": "max", "user_role": "admin", "feature_code": "users:delete", "is_allowed": True, "description": "Max admin deactivate users"},
    {"tier": "max", "user_role": "admin", "feature_code": "workspace:read", "is_allowed": True, "description": "View workspace"},
    {"tier": "max", "user_role": "admin", "feature_code": "workspace:manage", "is_allowed": True, "description": "Manage workspace"},
    {"tier": "max", "user_role": "admin", "feature_code": "analytics:read", "is_allowed": True, "description": "View analytics"},
    {"tier": "max", "user_role": "manager", "feature_code": "documents:upload", "is_allowed": True, "description": "Manager upload"},
    {"tier": "max", "user_role": "manager", "feature_code": "documents:read", "is_allowed": True, "description": "Manager read"},
    {"tier": "max", "user_role": "manager", "feature_code": "rag:query", "is_allowed": True, "description": "Manager query"},
    {"tier": "max", "user_role": "manager", "feature_code": "users:create", "is_allowed": True, "description": "Manager create users"},
    {"tier": "max", "user_role": "manager", "feature_code": "users:read", "is_allowed": True, "description": "Manager read users"},
    {"tier": "max", "user_role": "team_lead", "feature_code": "documents:upload", "is_allowed": True, "description": "Team lead upload"},
    {"tier": "max", "user_role": "team_lead", "feature_code": "documents:read", "is_allowed": True, "description": "Team lead read"},
    {"tier": "max", "user_role": "team_lead", "feature_code": "rag:query", "is_allowed": True, "description": "Team lead query"},
    {"tier": "max", "user_role": "associate", "feature_code": "documents:read", "is_allowed": True, "description": "Associate read"},
    {"tier": "max", "user_role": "associate", "feature_code": "rag:query", "is_allowed": True, "description": "Associate query"},

    # --- ENTERPRISE TIER ---
    {"tier": "enterprise", "user_role": "*", "feature_code": "documents:upload", "is_allowed": True, "description": "Enterprise docs upload"},
    {"tier": "enterprise", "user_role": "*", "feature_code": "documents:read", "is_allowed": True, "description": "Enterprise docs read"},
    {"tier": "enterprise", "user_role": "*", "feature_code": "rag:query", "is_allowed": True, "description": "Enterprise query AI"},
    {"tier": "enterprise", "user_role": "admin", "feature_code": "users:create", "is_allowed": True, "description": "Enterprise create up to 10k users"},
    {"tier": "enterprise", "user_role": "admin", "feature_code": "users:read", "is_allowed": True, "description": "Enterprise list users"},
    {"tier": "enterprise", "user_role": "admin", "feature_code": "users:update", "is_allowed": True, "description": "Enterprise update users"},
    {"tier": "enterprise", "user_role": "admin", "feature_code": "users:delete", "is_allowed": True, "description": "Enterprise deactivate users"},
    {"tier": "enterprise", "user_role": "manager", "feature_code": "users:create", "is_allowed": True, "description": "Enterprise manager create users"},
    {"tier": "enterprise", "user_role": "maintainer", "feature_code": "users:create", "is_allowed": True, "description": "Enterprise maintainer create users"},
    {"tier": "enterprise", "user_role": "*", "feature_code": "workspace:read", "is_allowed": True, "description": "Enterprise workspace view"},
    {"tier": "enterprise", "user_role": "*", "feature_code": "analytics:read", "is_allowed": True, "description": "Enterprise analytics"},
]


async def seed_default_plan_configs(session: AsyncSession) -> None:
    """Seed initial plan configurations in the database if empty."""
    result = await session.execute(select(func.count(PlanConfig.id)))
    count = result.scalar() or 0
    if count == 0:
        for item in DEFAULT_PLAN_CONFIGS:
            plan = PlanConfig(**item)
            session.add(plan)
        await session.commit()
    else:
        # Ensure new columns on existing seeds are populated if missing
        for item in DEFAULT_PLAN_CONFIGS:
            existing = await session.execute(
                select(PlanConfig).where(PlanConfig.tier == item["tier"])
            )
            plan = existing.scalars().first()
            if plan:
                if not hasattr(plan, "team_creator_roles") or not plan.team_creator_roles:
                    plan.team_creator_roles = item["team_creator_roles"]
                if not hasattr(plan, "allowed_features") or not plan.allowed_features:
                    plan.allowed_features = item["allowed_features"]
        await session.commit()


async def seed_default_api_permissions(session: AsyncSession) -> None:
    """Seed default API & feature permission rules in the database if empty."""
    result = await session.execute(select(func.count(ApiPermissionRule.id)))
    count = result.scalar() or 0
    if count == 0:
        for rule_data in DEFAULT_API_PERMISSION_RULES:
            rule = ApiPermissionRule(**rule_data)
            session.add(rule)
        await session.commit()


class TenantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, tenant_id: int) -> Tenant | None:
        result = await self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalars().first()

    async def get_by_name(self, name: str) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.name == name))
        return result.scalars().first()

    async def list_tenants(self, skip: int = 0, limit: int = 50) -> Sequence[Tenant]:
        result = await self.session.execute(select(Tenant).offset(skip).limit(limit))
        return result.scalars().all()

    async def create(self, data: dict) -> Tenant:
        tenant = Tenant(**data)
        self.session.add(tenant)
        await self.session.commit()
        await self.session.refresh(tenant)
        return tenant

    async def update(self, tenant_id: int, data: dict) -> Tenant | None:
        data["updated_at"] = datetime.now(timezone.utc)
        await self.session.execute(
            update(Tenant).where(Tenant.id == tenant_id).values(**data)
        )
        await self.session.commit()
        return await self.get_by_id(tenant_id)

    # --------------------------------------------------------------------------
    # Database Stored Plan Configurations
    # --------------------------------------------------------------------------
    async def list_plan_configs(self) -> Sequence[PlanConfig]:
        result = await self.session.execute(
            select(PlanConfig).order_by(PlanConfig.daily_token_quota.asc())
        )
        return result.scalars().all()

    async def get_plan_config(self, tier: str) -> PlanConfig | None:
        result = await self.session.execute(
            select(PlanConfig).where(PlanConfig.tier == tier.strip().lower())
        )
        return result.scalars().first()

    async def create_plan_config(self, data: dict) -> PlanConfig:
        plan = PlanConfig(**data)
        self.session.add(plan)
        await self.session.commit()
        await self.session.refresh(plan)
        return plan

    async def update_plan_config(self, plan: PlanConfig) -> PlanConfig:
        plan.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(plan)
        return plan

    # --------------------------------------------------------------------------
    # API & Feature Permission Rules (Plan x Role x Feature Matrix)
    # --------------------------------------------------------------------------
    async def list_api_permission_rules(
        self,
        tier: str | None = None,
        user_role: str | None = None,
        feature_code: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ApiPermissionRule]:
        query = select(ApiPermissionRule)
        if tier:
            query = query.where(ApiPermissionRule.tier == tier.strip().lower())
        if user_role:
            query = query.where(ApiPermissionRule.user_role == user_role.strip().lower())
        if feature_code:
            query = query.where(ApiPermissionRule.feature_code == feature_code.strip())

        query = query.order_by(
            ApiPermissionRule.tier.asc(),
            ApiPermissionRule.user_role.asc(),
            ApiPermissionRule.feature_code.asc(),
        ).offset(skip).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_api_permission_rule_by_id(self, rule_id: int) -> ApiPermissionRule | None:
        result = await self.session.execute(
            select(ApiPermissionRule).where(ApiPermissionRule.id == rule_id)
        )
        return result.scalars().first()

    async def get_api_permission_rule(
        self, tier: str, user_role: str, feature_code: str
    ) -> ApiPermissionRule | None:
        result = await self.session.execute(
            select(ApiPermissionRule).where(
                ApiPermissionRule.tier == tier.strip().lower(),
                ApiPermissionRule.user_role == user_role.strip().lower(),
                ApiPermissionRule.feature_code == feature_code.strip(),
            )
        )
        return result.scalars().first()

    async def create_api_permission_rule(self, data: dict) -> ApiPermissionRule:
        rule = ApiPermissionRule(**data)
        self.session.add(rule)
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def update_api_permission_rule(
        self, rule_id: int, data: dict
    ) -> ApiPermissionRule | None:
        rule = await self.get_api_permission_rule_by_id(rule_id)
        if not rule:
            return None
        for key, val in data.items():
            if val is not None:
                setattr(rule, key, val)
        rule.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def delete_api_permission_rule(self, rule_id: int) -> bool:
        rule = await self.get_api_permission_rule_by_id(rule_id)
        if not rule:
            return False
        await self.session.delete(rule)
        await self.session.commit()
        return True

    # --------------------------------------------------------------------------
    # Dynamic Permission Checking Engine (Redis Cached -> DB Query)
    # --------------------------------------------------------------------------
    async def check_feature_access(
        self,
        tenant_id: int,
        user_role: str,
        feature_code: str,
        redis: Redis | None = None,
    ) -> tuple[bool, str | None]:
        """
        Check if a given role in a given tenant has access to a feature.
        1. Tenant must exist and be active.
        2. Resolve tenant's plan tier.
        3. Check Redis cache for fast sub-millisecond evaluation.
        4. Check ApiPermissionRule in DB:
           - Matches exact (tier, user_role, feature_code)
           - OR wildcard role (tier, "*", feature_code)
           - OR wildcard tier ("*", user_role, feature_code)
        5. Check PlanConfig allowed_features string.
        """
        tenant = await self.get_by_id(tenant_id)
        if not tenant:
            return False, "Workspace not found."
        if not tenant.is_active:
            return False, "Workspace is inactive or suspended."

        tier_str = tenant.tier.value if hasattr(tenant.tier, "value") else str(tenant.tier).lower()
        role_str = user_role.strip().lower()
        feature_str = feature_code.strip()

        # Cache check
        cache_key = f"perm:{tier_str}:{role_str}:{feature_str}"
        if redis:
            cached_val = await redis.get(cache_key)
            if cached_val is not None:
                return (cached_val == "1"), None if cached_val == "1" else f"Feature '{feature_str}' is not permitted for role '{role_str}' on plan '{tier_str}'."

        # Database rule lookup
        # Priority 1: Exact match
        rule = await self.get_api_permission_rule(tier_str, role_str, feature_str)
        if rule is not None:
            is_allowed = rule.is_allowed
            if redis:
                await redis.set(cache_key, "1" if is_allowed else "0", ex=600)
            return (
                is_allowed,
                None if is_allowed else f"Feature '{feature_str}' is denied for role '{role_str}' on plan '{tier_str}'.",
            )

        # Priority 2: Wildcard role for this tier
        wildcard_role_rule = await self.get_api_permission_rule(tier_str, "*", feature_str)
        if wildcard_role_rule is not None:
            is_allowed = wildcard_role_rule.is_allowed
            if redis:
                await redis.set(cache_key, "1" if is_allowed else "0", ex=600)
            return (
                is_allowed,
                None if is_allowed else f"Feature '{feature_str}' is not enabled for plan '{tier_str}'.",
            )

        # Priority 3: Fallback check against PlanConfig.allowed_features
        plan_config = await self.get_plan_config(tier_str)
        if plan_config and plan_config.allowed_features:
            allowed_list = [f.strip() for f in plan_config.allowed_features.split(",") if f.strip()]
            is_in_plan = feature_str in allowed_list
            if not is_in_plan:
                if redis:
                    await redis.set(cache_key, "0", ex=600)
                return False, f"Feature '{feature_str}' is not included in the {plan_config.name} plan."

        # If role is admin on that tenant, grant by default unless explicitly denied
        if role_str == "admin":
            if redis:
                await redis.set(cache_key, "1", ex=600)
            return True, None

        if redis:
            await redis.set(cache_key, "0", ex=600)
        return False, f"Role '{role_str}' does not have permission for '{feature_str}' on plan '{tier_str}'."
