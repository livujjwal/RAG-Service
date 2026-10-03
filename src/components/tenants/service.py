from datetime import datetime, timezone

from fastapi import HTTPException, status
from redis.asyncio import Redis

from src.components.tenants.models import SubscriptionTier, Tenant, PlanConfig, ApiPermissionRule
from src.components.tenants.repository import TenantRepository, KNOWN_FEATURES
from src.components.tenants.schemas import (
    TenantCreate,
    TenantUpdate,
    PlanTokenQuotasUpdate,
    PlanConfigCreate,
    PlanConfigUpdate,
    ApiPermissionRuleCreate,
    ApiPermissionRuleUpdate,
)
from src.components.users.models import User, UserType, UserRole
from src.core.permissions import is_internal_admin

# Default daily limits for LLM queries (legacy request counting)
QUOTA_LIMITS = {
    SubscriptionTier.FREE: 50,
    SubscriptionTier.PLUS: 200,
    SubscriptionTier.PRO: 1000,
    SubscriptionTier.MAX: 5000,
    SubscriptionTier.ENTERPRISE: 999999,
}

# Default daily token limits (LLM tokens per day)
DEFAULT_TOKEN_QUOTAS: dict[str, int] = {
    "free": 50_000,        # 50k tokens / day
    "plus": 250_000,       # 250k tokens / day
    "pro": 1_000_000,      # 1M tokens / day
    "max": 5_000_000,      # 5M tokens / day
    "enterprise": 999_999_999,  # Unlimited
}


class TenantService:
    def __init__(self, repository: TenantRepository, redis: Redis):
        self.repository = repository
        self.redis = redis

    async def create_tenant(self, tenant_in: TenantCreate) -> Tenant:
        if await self.repository.get_by_name(tenant_in.name):
            raise HTTPException(status_code=409, detail="Tenant name already exists.")
        return await self.repository.create(tenant_in.model_dump())

    async def get_tenant(self, tenant_id: int) -> Tenant:
        tenant = await self.repository.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found.")
        return tenant

    async def list_tenants(self, skip: int = 0, limit: int = 50) -> list[Tenant]:
        """Fetch all tenants (Admin/Maintainer)."""
        return list(await self.repository.list_tenants(skip=skip, limit=limit))

    async def update_tenant(self, tenant_id: int, tenant_in: TenantUpdate) -> Tenant:
        """Update tenant name, subscription tier, or active status (Admin/Maintainer)."""
        await self.get_tenant(tenant_id)
        update_data = tenant_in.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields provided for update.")
        updated = await self.repository.update(tenant_id, update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Tenant update failed.")
        return updated

    async def check_and_consume_quota(self, tenant_id: int) -> bool:
        """
        Increments the tenant's daily usage counter in Redis.
        Raises 429 Too Many Requests if they exceed their plan limits.
        """
        tenant = await self.get_tenant(tenant_id)
        if not tenant.is_active:
            raise HTTPException(status_code=403, detail="Workspace is inactive.")

        limit = QUOTA_LIMITS.get(tenant.tier, 0)

        # Create a unique Redis key for today: e.g., "quota:tenant:1:date:2026-09-30"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        redis_key = f"quota:tenant:{tenant_id}:date:{today}"

        # Increment counter (creates the key at 1 if it doesn't exist)
        current_usage = await self.redis.incr(redis_key)

        # Set the key to expire in 24 hours to save memory
        if current_usage == 1:
            await self.redis.expire(redis_key, 86400)

        if current_usage > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily quota exceeded. Your {tenant.tier.value} plan allows {limit} requests per day.",
            )

        return True

    # --------------------------------------------------------------------------
    # Token Quotas & Usage Tracking (free, plus, pro, max, enterprise)
    # --------------------------------------------------------------------------
    async def get_plan_token_quotas(self) -> dict[str, int]:
        """Fetch daily token quotas for all subscription plans (Admin or system)."""
        cached = await self.redis.hgetall("system:plan_token_quotas")
        quotas = dict(DEFAULT_TOKEN_QUOTAS)
        if cached:
            for tier, limit in cached.items():
                try:
                    quotas[tier] = int(limit)
                except (ValueError, TypeError):
                    pass
        return quotas

    async def update_plan_token_quotas(
        self, updates: PlanTokenQuotasUpdate
    ) -> dict[str, int]:
        """Update daily token quotas for plans (Internal Admin only)."""
        current = await self.get_plan_token_quotas()
        update_dict = updates.model_dump(exclude_unset=True, exclude_none=True)
        for tier, limit in update_dict.items():
            current[tier] = limit
            await self.redis.hset("system:plan_token_quotas", tier, str(limit))
        return current

    async def list_plan_configs(self) -> list[PlanConfig]:
        """List all subscription plans and their limits (users, tokens, features)."""
        return list(await self.repository.list_plan_configs())

    async def get_plan_config(self, tier: str) -> PlanConfig:
        """Fetch plan configuration by tier (free, plus, pro, max, enterprise)."""
        plan = await self.repository.get_plan_config(tier)
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan '{tier}' not found.")
        return plan

    async def create_plan_config(self, plan_in: PlanConfigCreate) -> PlanConfig:
        """Create a new plan configuration (Internal Admin only)."""
        existing = await self.repository.get_plan_config(plan_in.tier)
        if existing:
            raise HTTPException(status_code=409, detail=f"Plan tier '{plan_in.tier}' already exists.")
        created = await self.repository.create_plan_config(plan_in.model_dump())
        await self.redis.hset("system:plan_token_quotas", created.tier.lower(), str(created.daily_token_quota))
        return created

    async def update_plan_config(
        self, tier: str, updates: PlanConfigUpdate
    ) -> PlanConfig:
        """Update plan user limits, token quota, and allowed roles (Internal Admin only)."""
        plan = await self.get_plan_config(tier)
        update_data = updates.model_dump(exclude_unset=True)
        for key, val in update_data.items():
            if val is not None:
                setattr(plan, key, val)
        updated = await self.repository.update_plan_config(plan)

        # Sync daily_token_quota into Redis if updated
        if updates.daily_token_quota is not None:
            await self.redis.hset(
                "system:plan_token_quotas", tier.lower(), str(updates.daily_token_quota)
            )

        # Invalidate permission caches for this tier
        pattern = f"perm:{tier.lower()}:*"
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)

        return updated

    async def get_tier_token_limit(self, tier: SubscriptionTier | str) -> int:
        """Resolve current token limit for a given tier."""
        tier_str = tier.value if hasattr(tier, "value") else str(tier).lower()
        cached = await self.redis.hget("system:plan_token_quotas", tier_str)
        if cached:
            try:
                return int(cached)
            except (ValueError, TypeError):
                pass
        plan = await self.repository.get_plan_config(tier_str)
        if plan:
            await self.redis.hset(
                "system:plan_token_quotas", tier_str, str(plan.daily_token_quota)
            )
            return plan.daily_token_quota
        return DEFAULT_TOKEN_QUOTAS.get(tier_str, 50_000)

    async def check_and_consume_tokens(
        self, tenant_id: int, user: User, tokens: int
    ) -> dict:
        """
        Count and consume tokens used by users in a workspace.
        - Internal users: tracked for metrics, but NEVER throttled.
        - External users: enforced against daily plan token quota (HTTP 429 if exceeded).
        """
        tenant = await self.get_tenant(tenant_id)
        if not tenant.is_active:
            raise HTTPException(status_code=403, detail="Workspace is inactive.")

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tenant_key = f"token_quota:tenant:{tenant_id}:date:{today}"
        user_key = f"token_usage:user:{user.id}:date:{today}"

        limit = await self.get_tier_token_limit(tenant.tier)

        # Detect internal vs external user
        is_internal = (
            getattr(user, "user_type", None) == UserType.INTERNAL
            or str(getattr(user, "user_type", "")).lower() == "internal"
        )

        if is_internal:
            # Internal users bypass throttling, but track usage
            new_usage = await self.redis.incrby(tenant_key, tokens)
            await self.redis.expire(tenant_key, 86400)
            await self.redis.incrby(user_key, tokens)
            await self.redis.expire(user_key, 86400)
            return {
                "allowed": True,
                "tokens_consumed": tokens,
                "total_used_today": new_usage,
                "daily_limit": limit,
                "remaining_tokens": max(0, limit - new_usage),
                "is_internal_user": True,
            }

        # External users: Enforce quota
        current = await self.redis.get(tenant_key)
        current_usage = int(current) if current else 0

        if current_usage + tokens > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Daily token quota exceeded for {tenant.tier.value.upper()} plan. "
                    f"Daily limit: {limit:,} tokens. Used today: {current_usage:,}. "
                    f"Requested: {tokens:,}."
                ),
            )

        new_usage = await self.redis.incrby(tenant_key, tokens)
        if new_usage == tokens:
            await self.redis.expire(tenant_key, 86400)

        await self.redis.incrby(user_key, tokens)
        await self.redis.expire(user_key, 86400)

        return {
            "allowed": True,
            "tokens_consumed": tokens,
            "total_used_today": new_usage,
            "daily_limit": limit,
            "remaining_tokens": max(0, limit - new_usage),
            "is_internal_user": False,
        }

    async def get_token_usage(self, tenant_id: int) -> dict:
        """Get today's token usage statistics for a workspace."""
        tenant = await self.get_tenant(tenant_id)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        redis_key = f"token_quota:tenant:{tenant_id}:date:{today}"
        current = await self.redis.get(redis_key)
        used = int(current) if current else 0
        limit = await self.get_tier_token_limit(tenant.tier)
        percentage = round((used / limit) * 100, 2) if limit > 0 else 0.0

        tier_str = tenant.tier.value if hasattr(tenant.tier, "value") else str(tenant.tier)

        return {
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "tier": tier_str,
            "daily_token_limit": limit,
            "tokens_used_today": used,
            "tokens_remaining_today": max(0, limit - used),
            "usage_percentage": percentage,
            "date": today,
        }

    # --------------------------------------------------------------------------
    # API & Feature Permissions Management (Internal Admin)
    # --------------------------------------------------------------------------
    async def list_permission_rules(
        self,
        tier: str | None = None,
        user_role: str | None = None,
        feature_code: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ApiPermissionRule]:
        return list(
            await self.repository.list_api_permission_rules(
                tier=tier,
                user_role=user_role,
                feature_code=feature_code,
                skip=skip,
                limit=limit,
            )
        )

    async def create_permission_rule(
        self, rule_in: ApiPermissionRuleCreate
    ) -> ApiPermissionRule:
        tier_clean = rule_in.tier.strip().lower()
        role_clean = rule_in.user_role.strip().lower()
        feature_clean = rule_in.feature_code.strip()

        existing = await self.repository.get_api_permission_rule(
            tier_clean, role_clean, feature_clean
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Permission rule for tier '{tier_clean}', role '{role_clean}', feature '{feature_clean}' already exists.",
            )

        data = rule_in.model_dump()
        data["tier"] = tier_clean
        data["user_role"] = role_clean
        data["feature_code"] = feature_clean
        rule = await self.repository.create_api_permission_rule(data)

        # Invalidate cache
        await self.redis.delete(f"perm:{tier_clean}:{role_clean}:{feature_clean}")
        return rule

    async def update_permission_rule(
        self, rule_id: int, updates: ApiPermissionRuleUpdate
    ) -> ApiPermissionRule:
        rule = await self.repository.get_api_permission_rule_by_id(rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Permission rule not found.")

        updated = await self.repository.update_api_permission_rule(
            rule_id, updates.model_dump(exclude_unset=True)
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Failed to update rule.")

        await self.redis.delete(
            f"perm:{updated.tier}:{updated.user_role}:{updated.feature_code}"
        )
        return updated

    async def delete_permission_rule(self, rule_id: int) -> dict:
        rule = await self.repository.get_api_permission_rule_by_id(rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Permission rule not found.")

        tier, role, feature = rule.tier, rule.user_role, rule.feature_code
        deleted = await self.repository.delete_api_permission_rule(rule_id)
        if not deleted:
            raise HTTPException(status_code=500, detail="Failed to delete permission rule.")

        await self.redis.delete(f"perm:{tier}:{role}:{feature}")
        return {"message": f"Permission rule {rule_id} deleted successfully."}

    async def get_permission_matrix(self) -> dict:
        """
        Build an aggregated Plan Tier -> Role -> [allowed features] matrix.
        Very useful for frontend tables and role-plan permission matrices.
        """
        rules = await self.repository.list_api_permission_rules(limit=500)
        plans = await self.repository.list_plan_configs()

        tiers = [p.tier for p in plans]
        known_roles = [
            "admin",
            "manager",
            "team_lead",
            "consultant",
            "associate",
            "account_manager",
            "senior_account_manager",
            "application_manager",
            "senior_application_manager",
            "vice_president",
            "maintainer",
        ]

        # matrix[tier][role] = list of feature_codes
        matrix: dict[str, dict[str, list[str]]] = {t: {} for t in tiers}

        for rule in rules:
            if not rule.is_allowed:
                continue
            r_tier = rule.tier
            r_role = rule.user_role
            r_feat = rule.feature_code

            target_tiers = tiers if r_tier == "*" else [r_tier]
            for t in target_tiers:
                if t not in matrix:
                    matrix[t] = {}
                target_roles = known_roles if r_role == "*" else [r_role]
                for r in target_roles:
                    if r not in matrix[t]:
                        matrix[t][r] = []
                    if r_feat not in matrix[t][r]:
                        matrix[t][r].append(r_feat)

        return {
            "tiers": tiers,
            "roles": known_roles,
            "features": KNOWN_FEATURES,
            "matrix": matrix,
        }

    async def get_workspace_user_quota(
        self, tenant_id: int, current_active_users: int
    ) -> dict:
        """Return user limits and seats available for a workspace according to its plan."""
        tenant = await self.get_tenant(tenant_id)
        tier_str = tenant.tier.value if hasattr(tenant.tier, "value") else str(tenant.tier).lower()
        plan = await self.get_plan_config(tier_str)

        max_users = plan.max_users
        remaining = max(0, max_users - current_active_users)
        can_create = (plan.can_manage_team or max_users > 1) and (remaining > 0)

        allowed_roles = [
            r.strip().lower() for r in plan.allowed_roles.split(",") if r.strip()
        ]
        creator_roles = [
            r.strip().lower() for r in plan.team_creator_roles.split(",") if r.strip()
        ]

        return {
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "tier": tier_str,
            "plan_name": plan.name,
            "max_users": max_users,
            "current_users": current_active_users,
            "remaining_slots": remaining,
            "can_create_users": can_create,
            "allowed_roles_to_assign": allowed_roles,
            "team_creator_roles": creator_roles,
        }

    async def get_user_access_summary(
        self, user: User, current_active_users: int = 1
    ) -> dict:
        """
        Evaluate full access profile for a logged-in user:
        - Internal Admin: Full platform superuser capabilities
        - External User: Features permitted by plan & role, workspace quotas, assignable roles
        """
        user_role_str = (
            user.user_role.value if hasattr(user.user_role, "value") else str(user.user_role).lower()
        )
        user_type_str = (
            user.user_type.value if hasattr(user.user_type, "value") else str(user.user_type).lower()
        )

        if is_internal_admin(user):
            # Internal platform superusers have access to all features
            all_feats = [f["code"] for f in KNOWN_FEATURES]
            return {
                "user_id": user.id,
                "email": user.email,
                "user_role": user_role_str,
                "user_type": user_type_str,
                "is_internal_admin": True,
                "tenant_id": None,
                "tenant_name": "Global / Platform Superuser",
                "plan_tier": "enterprise",
                "plan_name": "Internal Platform Superuser (Unlimited)",
                "allowed_features": all_feats,
                "can_create_users": True,
                "max_users_allowed": 999999,
                "current_workspace_users": current_active_users,
                "remaining_user_slots": 999999,
                "allowed_assignable_roles": [
                    "admin",
                    "maintainer",
                    "vice_president",
                    "senior_application_manager",
                    "application_manager",
                    "senior_account_manager",
                    "account_manager",
                    "manager",
                    "team_lead",
                    "consultant",
                    "associate",
                ],
            }

        # External user
        if not user.tenant_id:
            return {
                "user_id": user.id,
                "email": user.email,
                "user_role": user_role_str,
                "user_type": user_type_str,
                "is_internal_admin": False,
                "tenant_id": None,
                "tenant_name": None,
                "plan_tier": None,
                "plan_name": None,
                "allowed_features": [],
                "can_create_users": False,
                "max_users_allowed": 0,
                "current_workspace_users": 0,
                "remaining_user_slots": 0,
                "allowed_assignable_roles": [],
            }

        tenant = await self.get_tenant(user.tenant_id)
        tier_str = tenant.tier.value if hasattr(tenant.tier, "value") else str(tenant.tier).lower()
        plan = await self.get_plan_config(tier_str)

        # Check features
        allowed_features = []
        for feat in KNOWN_FEATURES:
            f_code = feat["code"]
            is_ok, _ = await self.repository.check_feature_access(
                tenant_id=tenant.id,
                user_role=user_role_str,
                feature_code=f_code,
                redis=self.redis,
            )
            if is_ok:
                allowed_features.append(f_code)

        creator_roles = [
            r.strip().lower() for r in plan.team_creator_roles.split(",") if r.strip()
        ]
        can_role_create = user_role_str in creator_roles
        remaining_slots = max(0, plan.max_users - current_active_users)
        can_create = (
            (plan.can_manage_team or plan.max_users > 1)
            and can_role_create
            and (remaining_slots > 0)
        )

        allowed_roles = [
            r.strip().lower() for r in plan.allowed_roles.split(",") if r.strip()
        ]

        return {
            "user_id": user.id,
            "email": user.email,
            "user_role": user_role_str,
            "user_type": user_type_str,
            "is_internal_admin": False,
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "plan_tier": tier_str,
            "plan_name": plan.name,
            "allowed_features": allowed_features,
            "can_create_users": can_create,
            "max_users_allowed": plan.max_users,
            "current_workspace_users": current_active_users,
            "remaining_user_slots": remaining_slots,
            "allowed_assignable_roles": allowed_roles,
        }
