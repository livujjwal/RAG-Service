import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.auth.schemas import Token
from src.components.auth.service import AuthService
from src.components.tenants.models import SubscriptionTier
from src.components.tenants.repository import TenantRepository
from src.components.users.models import UserRole, UserStatus, UserType
from src.components.users.repository import UserRepository
from src.components.users.schemas import UserCreate, UserResponse, UserSignup
from src.components.users.service import UserService
from src.core.database import get_db
from src.core.security import create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_auth_service(session: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(session))


def get_user_service(session: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(UserRepository(session), TenantRepository(session))


@router.post("/login", response_model=Token)
async def login_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: AuthService = Depends(get_auth_service),
):
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    # form_data.username maps to our email field
    user = await service.authenticate_user(
        email=form_data.username, password=form_data.password
    )

    # Generate the JWT
    access_token = create_access_token(subject=user.id)

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    signup_in: UserSignup,
    service: UserService = Depends(get_user_service),
    session: AsyncSession = Depends(get_db),
):
    """
    Public self-registration endpoint for new users.
    - Signup user is ALWAYS created as:
        user_type = EXTERNAL
        user_role = ADMIN
        user_status = ACTIVE
    - Automatically provisions a dedicated workspace for the new External Admin
      on the default Free tier if no tenant_id is specified.
    - API access and team creation quotas are subsequently governed by this plan.
    """
    tenant_repo = TenantRepository(session)
    target_tenant_id = signup_in.tenant_id

    # If user did not provide a tenant_id, automatically create a new workspace
    if not target_tenant_id:
        base_name = (
            signup_in.workspace_name.strip()
            if signup_in.workspace_name and signup_in.workspace_name.strip()
            else f"{signup_in.first_name}'s Workspace"
        )
        ws_name = base_name

        # Ensure workspace name is unique
        existing_tenant = await tenant_repo.get_by_name(ws_name)
        if existing_tenant:
            ws_name = f"{base_name} ({uuid.uuid4().hex[:6]})"

        new_tenant = await tenant_repo.create(
            {
                "name": ws_name,
                "tier": SubscriptionTier.FREE,
                "is_active": True,
            }
        )
        target_tenant_id = new_tenant.id
    else:
        # Verify specified tenant exists and is active
        tenant = await tenant_repo.get_by_id(target_tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace with ID {target_tenant_id} not found.",
            )
        if not tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Workspace is currently inactive or suspended.",
            )

    user_in = UserCreate(
        email=signup_in.email,
        password=signup_in.password,
        first_name=signup_in.first_name,
        last_name=signup_in.last_name,
        phone=signup_in.phone,
        gender=signup_in.gender,
        tenant_id=target_tenant_id,
        user_type=UserType.EXTERNAL,  # ALWAYS EXTERNAL
        user_role=UserRole.ADMIN,      # ALWAYS ADMIN
        user_status=UserStatus.ACTIVE,
    )
    return await service.create_user(user_in, created_by=None)
