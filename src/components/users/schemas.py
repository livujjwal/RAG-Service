from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from src.components.users.models import UserRole, UserType, UserStatus, Gender


class UserBase(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=7, max_length=30)
    gender: Gender
    user_role: UserRole = UserRole.ASSOCIATE
    user_type: UserType = UserType.EXTERNAL
    user_status: UserStatus = UserStatus.ACTIVE


# Public user signup (user_type and user_role cannot be specified by user)
class UserSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=7, max_length=30)
    gender: Gender
    workspace_name: str | None = Field(None, description="Workspace name to create upon signup")
    tenant_id: int | None = None


# Incoming request to create a user (Admin only - can select internal or external)
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)
    tenant_id: int | None = None


# Incoming request to update a user (all fields optional)
class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    gender: Gender | None = None
    user_role: UserRole | None = None
    user_status: UserStatus | None = None
    user_type: UserType | None = None
    tenant_id: int | None = None


# Admin request to change user type (Internal or External)
class UserTypeChangeRequest(BaseModel):
    user_type: UserType = Field(description="Target user type: internal or external")


# Outgoing response sent back to clients (password omitted)
class UserResponse(UserBase):
    id: int
    tenant_id: int | None
    created_by: int | None
    updated_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Dynamic System Lookups (UserRole, UserType, UserStatus, Gender)
# ==============================================================================
class LookupItemBase(BaseModel):
    category: str = Field(description="Lookup category, e.g. user_role, user_type, user_status, gender")
    code: str = Field(min_length=1, max_length=100, description="Machine-readable unique key e.g. 'contractor'")
    label: str = Field(min_length=1, max_length=100, description="Human-readable display name")
    description: str | None = None
    is_active: bool = True
    weight: int | None = Field(None, description="Hierarchical weight for RBAC (used for roles)")
    sort_order: int = 0


class LookupItemCreate(LookupItemBase):
    pass


class LookupItemUpdate(BaseModel):
    label: str | None = None
    description: str | None = None
    is_active: bool | None = None
    weight: int | None = None
    sort_order: int | None = None


class LookupItemResponse(LookupItemBase):
    id: int
    is_system: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LookupsGroupedResponse(BaseModel):
    user_role: list[LookupItemResponse]
    user_type: list[LookupItemResponse]
    user_status: list[LookupItemResponse]
    gender: list[LookupItemResponse]

