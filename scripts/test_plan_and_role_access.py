"""
Test script to verify:
1. Signup user is always external user with role admin and auto-provisioned workspace on Free tier.
2. External admin user creation limits:
   - Free tier max_users=1 rejects adding more members.
   - Upgrading workspace allows adding members up to plan max_users.
   - External admin can only assign roles permitted by the plan.
3. Dynamic API & Feature permission checking:
   - External user permissions governed by (Plan x Role).
   - Internal Admin bypasses all plan restrictions.
4. Internal Admin APIs to manage plans and permission rules.
"""

import asyncio
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import engine, Base
from src.components.tenants.models import Tenant, SubscriptionTier, PlanConfig, ApiPermissionRule
from src.components.tenants.repository import (
    TenantRepository,
    seed_default_plan_configs,
    seed_default_api_permissions,
)
from src.components.users.models import User, UserRole, UserType, UserStatus, Gender
from src.components.users.repository import UserRepository, seed_default_lookups
from src.components.users.service import UserService
from src.components.users.schemas import UserCreate
from src.components.tenants.service import TenantService
import redis.asyncio as redis
from src.core.config import settings
from fastapi import HTTPException


async def run_tests():
    print("=" * 70)
    print("RUNNING VERIFICATION: SIGNUP, PLAN LIMITS, AND API ACCESS MATRIX")
    print("=" * 70)

    # 1. Initialize schema & seed defaults
    from sqlalchemy import text
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TYPE subscription_tier_enum ADD VALUE IF NOT EXISTS 'PLUS';"))
            await conn.execute(text("ALTER TYPE subscription_tier_enum ADD VALUE IF NOT EXISTS 'MAX';"))
        except Exception:
            pass
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        await seed_default_lookups(session)
        await seed_default_plan_configs(session)
        await seed_default_api_permissions(session)

    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async with AsyncSession(engine) as session:
        user_repo = UserRepository(session)
        tenant_repo = TenantRepository(session)
        user_service = UserService(user_repo, tenant_repo)
        tenant_service = TenantService(tenant_repo, redis_client)

        # ------------------------------------------------------------------
        # TEST 1: Signup User Is Always External User & Role Admin
        # ------------------------------------------------------------------
        print("\n[TEST 1] Verifying Signup User Creation...")
        test_uid = uuid.uuid4().hex[:6]
        signup_ws_name = f"TestCorp_{test_uid}"
        
        # Simulate signup auto-provisioning
        tenant = await tenant_repo.create({
            "name": signup_ws_name,
            "tier": SubscriptionTier.FREE,
            "is_active": True,
        })

        target_tenant_id = tenant.id

        signup_user_in = UserCreate(
            email=f"signup_admin_{test_uid}@example.com",
            password="SecurePassword123!",
            first_name="Alice",
            last_name="Owner",
            phone="+1234567890",
            gender=Gender.FEMALE,
            tenant_id=target_tenant_id,
            user_type=UserType.EXTERNAL,  # ALWAYS EXTERNAL
            user_role=UserRole.ADMIN,      # ALWAYS ADMIN
            user_status=UserStatus.ACTIVE,
        )

        signed_up_admin = await user_service.create_user(signup_user_in, creator=None)
        admin_id = signed_up_admin.id
        assert signed_up_admin.user_type == UserType.EXTERNAL, "Signup user must be EXTERNAL"
        assert signed_up_admin.user_role == UserRole.ADMIN, "Signup user must be ADMIN"
        assert signed_up_admin.tenant_id == target_tenant_id, "Signup user must have workspace tenant_id"

        print(f"  [PASS] Signup user {signed_up_admin.email} created as EXTERNAL ADMIN in workspace '{signup_ws_name}' (Tier: FREE)")

        # ------------------------------------------------------------------
        # TEST 2: Free Tier Blocks External Admin From Adding Team Members (max_users=1)
        # ------------------------------------------------------------------
        print("\n[TEST 2] Verifying Free Plan User Limit Enforcement (max_users=1)...")
        new_member_in = UserCreate(
            email=f"member1_{test_uid}@example.com",
            password="SecurePassword123!",
            first_name="Bob",
            last_name="Member",
            phone="+1987654321",
            gender=Gender.MALE,
            tenant_id=target_tenant_id,
            user_type=UserType.EXTERNAL,
            user_role=UserRole.ASSOCIATE,
            user_status=UserStatus.ACTIVE,
        )

        blocked = False
        try:
            admin_user = await user_repo.get_by_id(admin_id)
            await user_service.create_user(new_member_in, creator=admin_user)
        except HTTPException as e:
            blocked = True
            print(f"  [PASS] Successfully blocked with HTTP {e.status_code}: {e.detail}")
        assert blocked, "Free tier external admin should not be able to exceed max_users=1"

        # ------------------------------------------------------------------
        # TEST 3: Upgrade Workspace to PLUS Plan (max_users=5) & Check Allowed Roles
        # ------------------------------------------------------------------
        print("\n[TEST 3] Upgrading Workspace to PLUS (max 5 users)...")
        tenant = await tenant_repo.get_by_id(target_tenant_id)
        tenant.tier = SubscriptionTier.PLUS
        await session.commit()

        # External admin creates associate (permitted by Plus plan)
        admin_user = await user_repo.get_by_id(admin_id)
        member1 = await user_service.create_user(new_member_in, creator=admin_user)
        assert member1.id is not None
        assert member1.user_role == UserRole.ASSOCIATE
        print(f"  [PASS] Successfully created team member {member1.email} with role 'associate' on PLUS plan")

        # External admin attempts to assign 'vice_president' (disallowed by Plus plan)
        print("\n[TEST 4] Testing Role Assignment Restriction on PLUS Plan...")
        disallowed_role_in = UserCreate(
            email=f"vp_{test_uid}@example.com",
            password="SecurePassword123!",
            first_name="Charlie",
            last_name="VP",
            phone="+1555555555",
            gender=Gender.OTHER,
            tenant_id=target_tenant_id,
            user_type=UserType.EXTERNAL,
            user_role=UserRole.VICE_PRESIDENT,
            user_status=UserStatus.ACTIVE,
        )
        role_blocked = False
        try:
            admin_user = await user_repo.get_by_id(admin_id)
            await user_service.create_user(disallowed_role_in, creator=admin_user)
        except HTTPException as e:
            role_blocked = True
            print(f"  [PASS] Blocked unauthorized role assignment with HTTP {e.status_code}: {e.detail}")
        assert role_blocked, "External admin cannot assign roles not in plan's allowed_roles"

        # ------------------------------------------------------------------
        # TEST 5: Internal Admin Can Create Users Without Plan Restrictions
        # ------------------------------------------------------------------
        print("\n[TEST 5] Verifying Internal Admin Unlimited Powers...")
        internal_admin = User(
            email=f"internal_super_{test_uid}@example.com",
            hashed_password="hash",
            first_name="Super",
            last_name="Admin",
            phone="+1000000000",
            gender=Gender.OTHER,
            user_role=UserRole.ADMIN,
            user_type=UserType.INTERNAL,  # Internal platform superuser
            user_status=UserStatus.ACTIVE,
            tenant_id=None,
        )
        session.add(internal_admin)
        await session.commit()
        await session.refresh(internal_admin)

        # Internal Admin can create any role (e.g. Vice President) in any tenant
        vp_created_by_internal = await user_service.create_user(disallowed_role_in, creator=internal_admin)
        assert vp_created_by_internal.user_role == UserRole.VICE_PRESIDENT
        print(f"  [PASS] Internal Admin successfully created Vice President user ID {vp_created_by_internal.id} bypassing plan limits")

        # ------------------------------------------------------------------
        # TEST 6: Feature / API Permission Access Engine
        # ------------------------------------------------------------------
        print("\n[TEST 6] Testing Plan x Role API Permission Checks...")
        # Free associate should have documents:read, but NOT users:create
        allowed_read, _ = await tenant_repo.check_feature_access(
            tenant_id=target_tenant_id,
            user_role="associate",
            feature_code="documents:read",
            redis=redis_client,
        )
        allowed_create, _ = await tenant_repo.check_feature_access(
            tenant_id=target_tenant_id,
            user_role="associate",
            feature_code="users:create",
            redis=redis_client,
        )
        assert allowed_read is True, "Associate on Plus should have documents:read"
        assert allowed_create is False, "Associate on Plus should NOT have users:create"
        print("  [PASS] Associate correctly has 'documents:read' = True and 'users:create' = False")

        # Workspace User Quota Endpoint test
        quota = await tenant_service.get_workspace_user_quota(target_tenant_id, current_active_users=3)
        assert quota["max_users"] == 5
        assert quota["current_users"] == 3
        assert quota["remaining_slots"] == 2
        print(f"  [PASS] Workspace User Quota verified: {quota['current_users']}/{quota['max_users']} seats used, {quota['remaining_slots']} remaining")


        # Permission Matrix test
        matrix = await tenant_service.get_permission_matrix()
        assert "free" in matrix["matrix"]
        assert "plus" in matrix["matrix"]
        assert "pro" in matrix["matrix"]
        print("  [PASS] Complete Permission Matrix generated with tiers: ", list(matrix["matrix"].keys()))

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_tests())
