import json
from typing import Annotated
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from src.core.config import settings
from src.core.database import get_db
from src.core.redis import get_redis
from src.components.users.models import User, UserRole, UserStatus
from src.components.users.repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
    except (jwt.PyJWTError, ValueError):
        raise credentials_exception

    repository = UserRepository(session)
    user = await repository.get_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Check account status (support both user_status and status attributes)
    status_val = getattr(user, "user_status", getattr(user, "status", None))
    if status_val != UserStatus.ACTIVE and status_val != "active":
        display_status = status_val.value if hasattr(status_val, "value") else str(status_val)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User account is {display_status}",
        )

    return user


class RequireRole:
    """
    Dependency factory to restrict endpoints to specific roles.
    Usage: Depends(RequireRole([UserRole.ADMIN, UserRole.MANAGER]))
    """

    def __init__(self, allowed_roles: list[UserRole]):
        self.allowed_roles = allowed_roles

    def __call__(
        self, current_user: Annotated[User, Depends(get_current_user)]
    ) -> User:
        user_role = getattr(current_user, "user_role", getattr(current_user, "role", None))
        if user_role not in self.allowed_roles:
            role_names = [r.value if hasattr(r, "value") else str(r) for r in self.allowed_roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {role_names}",
            )
        return current_user


def require_internal_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dependency that strictly enforces Internal Admin (Platform Superuser) access."""
    from src.core.permissions import is_internal_admin

    if not is_internal_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Internal Admin privileges required.",
        )
    return current_user


class RequireFeatureAccess:
    """
    Dependency factory to enforce plan & role based API feature permissions.
    Internal admins bypass all feature restrictions.
    External users are checked against their workspace's subscription tier and role.
    """

    def __init__(self, feature_code: str):
        self.feature_code = feature_code

    async def __call__(
        self,
        current_user: Annotated[User, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_db)],
        redis: Annotated[Redis, Depends(get_redis)],
    ) -> User:
        from src.core.permissions import is_internal_admin
        from src.components.tenants.repository import TenantRepository

        # 1. Platform Superuser bypasses plan/feature limits
        if is_internal_admin(current_user):
            return current_user

        # 2. External users must belong to a workspace
        if not current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must belong to an active workspace to access this feature.",
            )

        # 3. Check access against database & Redis cache
        tenant_repo = TenantRepository(session)
        user_role_str = (
            current_user.user_role.value
            if hasattr(current_user.user_role, "value")
            else str(current_user.user_role).lower()
        )
        is_allowed, reason = await tenant_repo.check_feature_access(
            tenant_id=current_user.tenant_id,
            user_role=user_role_str,
            feature_code=self.feature_code,
            redis=redis,
        )

        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=reason or f"Feature '{self.feature_code}' is not permitted for your plan and role.",
            )

        return current_user

