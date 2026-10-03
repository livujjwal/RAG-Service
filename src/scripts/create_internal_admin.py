"""
Script to create or promote an Internal Admin (Platform Superuser).
An Internal Admin has:
  - user_role: "admin"
  - user_type: "internal"
  - user_status: "active"
  - tenant_id: None (Global / cross-tenant scope)

Usage:
  # Inside Docker Container:
  docker exec rag_engine_app python src/scripts/create_internal_admin.py --email admin@ragengine.internal --password SecretPassword123!

  # On Host Machine:
  python src/scripts/create_internal_admin.py --email admin@ragengine.internal --password SecretPassword123!
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import engine
from src.core.security import get_password_hash
from src.components.users.models import User, UserRole, UserType, UserStatus, Gender


async def create_or_promote_admin(
    email: str,
    password: str,
    first_name: str = "Internal",
    last_name: str = "Admin",
    phone: str = "+1000000000",
    gender: str = "other",
) -> None:
    async with AsyncSession(engine) as session:
        # Check if user already exists
        stmt = select(User).where(User.email == email.strip().lower())
        result = await session.execute(stmt)
        user = result.scalars().first()

        hashed_pwd = get_password_hash(password)

        if user:
            print(f"[*] User '{email}' already exists. Promoting to Internal Admin...")
            user.user_role = UserRole.ADMIN
            user.user_type = UserType.INTERNAL
            user.user_status = UserStatus.ACTIVE
            user.tenant_id = None
            user.hashed_password = hashed_pwd
            user.updated_at = datetime.now(timezone.utc)
            await session.commit()
            print(f"[+] Successfully promoted user ID {user.id} ({email}) to Internal Admin!")
        else:
            print(f"[*] Creating new Internal Admin with email '{email}'...")
            try:
                gender_enum = Gender(gender.lower())
            except ValueError:
                gender_enum = Gender.OTHER

            new_user = User(
                email=email.strip().lower(),
                hashed_password=hashed_pwd,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                gender=gender_enum,
                user_role=UserRole.ADMIN,
                user_type=UserType.INTERNAL,
                user_status=UserStatus.ACTIVE,
                tenant_id=None,  # Global / un-scoped to any single tenant
            )
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            print(f"[+] Successfully created Internal Admin ID {new_user.id} ({new_user.email})!")

        print("\nInternal Admin Details:")
        print("-----------------------")
        print(f"  Email:       {email}")
        print("  Role:        admin (Weight: 100)")
        print("  Type:        internal (Platform-wide / Global)")
        print("  Status:      active")
        print("  Tenant:      Global (None - Cross-Tenant Access)")
        print("  Power:       Full authorization to edit/manage all data, tenants, lookups, and users\n")


def main():
    parser = argparse.ArgumentParser(description="Create or promote an Internal Admin user.")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--password", required=True, help="Admin password (min 8 chars)")
    parser.add_argument("--first-name", default="Internal", help="First name")
    parser.add_argument("--last-name", default="Admin", help="Last name")
    parser.add_argument("--phone", default="+1000000000", help="Phone number")
    parser.add_argument("--gender", default="other", help="Gender (male, female, other)")

    args = parser.parse_args()

    if len(args.password) < 8:
        print("[!] Error: Password must be at least 8 characters long.")
        sys.exit(1)

    asyncio.run(
        create_or_promote_admin(
            email=args.email,
            password=args.password,
            first_name=args.first_name,
            last_name=args.last_name,
            phone=args.phone,
            gender=args.gender,
        )
    )


if __name__ == "__main__":
    main()
