from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.branch import Branch
from app.models.enums import PermissionCode, UserRole
from app.models.org import Organization
from app.models.rbac import Permission, Role, RolePermission
from app.models.user import User
from app.services.authorization import AuthorizationService, TenantAccessError


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        _seed_rbac(db)
        yield db


def _seed_rbac(db: Session) -> None:
    db.add_all(
        [
            Role(code=role.value, name=role.value.title(), description=role.value)
            for role in UserRole
        ]
    )
    permission_codes = [
        PermissionCode.USERS_PERMISSIONS_MANAGE.value,
        PermissionCode.USERS_INVITE.value,
        PermissionCode.OWN_PROFILE_VIEW.value,
    ]
    db.add_all(
        [Permission(code=code, name=code, description=code) for code in permission_codes]
    )
    db.add_all(
        [
            RolePermission(
                role_code=UserRole.ADMIN.value,
                permission_code=PermissionCode.USERS_PERMISSIONS_MANAGE.value,
            ),
            RolePermission(
                role_code=UserRole.ADMIN.value,
                permission_code=PermissionCode.USERS_INVITE.value,
            ),
            RolePermission(
                role_code=UserRole.TEACHER.value,
                permission_code=PermissionCode.OWN_PROFILE_VIEW.value,
            ),
        ]
    )
    db.commit()


def _tenant_users(db: Session, suffix: str) -> tuple[User, User]:
    organization = Organization(name=f"Academia {suffix}", slug=f"academia-{suffix.lower()}")
    branch = Branch(name="Centro", code="CENTRO", organization=organization)
    admin = User(
        name="Admin",
        email=f"admin-{suffix}@test.local",
        hashed_password="hash",
        role=UserRole.ADMIN.value,
        organization=organization,
        branch=branch,
    )
    teacher = User(
        name="Teacher",
        email=f"teacher-{suffix}@test.local",
        hashed_password="hash",
        role=UserRole.TEACHER.value,
        organization=organization,
        branch=branch,
    )
    db.add_all([admin, teacher])
    db.commit()
    return admin, teacher


def test_role_permissions_are_effective(session: Session) -> None:
    admin, teacher = _tenant_users(session, "One")
    service = AuthorizationService(session)

    assert service.has_permission(admin, PermissionCode.USERS_INVITE)
    assert not service.has_permission(teacher, PermissionCode.USERS_INVITE)
    assert service.has_permission(teacher, PermissionCode.OWN_PROFILE_VIEW)


def test_admin_can_delegate_and_revoke_permission(session: Session) -> None:
    admin, teacher = _tenant_users(session, "One")
    service = AuthorizationService(session)

    service.grant(
        actor=admin,
        target=teacher,
        permission_code=PermissionCode.USERS_INVITE.value,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert service.has_permission(teacher, PermissionCode.USERS_INVITE)

    service.revoke(
        actor=admin,
        target=teacher,
        permission_code=PermissionCode.USERS_INVITE.value,
    )
    assert not service.has_permission(teacher, PermissionCode.USERS_INVITE)


def test_expired_delegation_is_not_effective(session: Session) -> None:
    admin, teacher = _tenant_users(session, "One")
    service = AuthorizationService(session)
    grant = service.grant(
        actor=admin,
        target=teacher,
        permission_code=PermissionCode.USERS_INVITE.value,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    grant.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()

    assert not service.has_permission(teacher, PermissionCode.USERS_INVITE)


def test_cross_tenant_delegation_is_rejected(session: Session) -> None:
    admin, _ = _tenant_users(session, "One")
    _, other_teacher = _tenant_users(session, "Two")

    with pytest.raises(TenantAccessError):
        AuthorizationService(session).grant(
            actor=admin,
            target=other_teacher,
            permission_code=PermissionCode.USERS_INVITE.value,
            expires_at=None,
        )
