from src.components.users.models import UserRole, UserType

ROLE_HIERARCHY: dict[UserRole, int] = {
    UserRole.ADMIN: 100,
    UserRole.MAINTAINER: 90,
    UserRole.VICE_PRESIDENT: 80,
    UserRole.SENIOR_APPLICATION_MANAGER: 70,
    UserRole.APPLICATION_MANAGER: 60,
    UserRole.SENIOR_ACCOUNT_MANAGER: 50,
    UserRole.ACCOUNT_MANAGER: 40,
    UserRole.MANAGER: 30,
    UserRole.TEAM_LEAD: 20,
    UserRole.CONSULTANT: 10,
    UserRole.ASSOCIATE: 0,
}


def has_minimum_role(user_role: UserRole, required_role: UserRole) -> bool:
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 0)


def is_internal_admin(user) -> bool:
    """Check if the user is an Internal Admin (Platform Superuser with full system access)."""
    if not user:
        return False
    role = getattr(user, "user_role", None)
    u_type = getattr(user, "user_type", None)
    is_admin = role == UserRole.ADMIN or str(role).lower() == "admin"
    is_internal = u_type == UserType.INTERNAL or str(u_type).lower() == "internal"
    return is_admin and is_internal
