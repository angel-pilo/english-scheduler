import argparse
from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password, validate_password_strength
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.models.user import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the initial platform SUPER_ADMIN")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Platform Owner")
    args = parser.parse_args()

    password = getpass("Password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    try:
        validate_password_strength(password)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    normalized_email = args.email.strip().lower()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == normalized_email)) is not None:
            raise SystemExit("A user with that email already exists")
        db.add(
            User(
                organization_id=None,
                branch_id=None,
                role=UserRole.SUPER_ADMIN.value,
                name=args.name.strip(),
                email=normalized_email,
                hashed_password=hash_password(password),
                active=True,
            )
        )
        db.commit()
    print("SUPER_ADMIN created successfully")


if __name__ == "__main__":
    main()
