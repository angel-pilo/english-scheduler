from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import PermissionCode, UserRole
from app.models.rbac import Permission, RolePermission, UserPermission
from app.models.user import User


class AuthorizationError(Exception):
    pass


class PermissionDeniedError(AuthorizationError):
    pass


class TenantAccessError(AuthorizationError):
    pass


class PermissionNotFoundError(AuthorizationError):
    pass


class AuthorizationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def has_permission(self, user: User, permission_code: str | PermissionCode) -> bool:
        code = self._code(permission_code)
        if user.role == UserRole.SUPER_ADMIN.value:
            return True

        role_permission = self.db.scalar(
            select(RolePermission).where(
                RolePermission.role_code == user.role,
                RolePermission.permission_code == code,
            )
        )
        if role_permission is not None:
            return True

        now = datetime.now(timezone.utc)
        delegated = self.db.scalar(
            select(UserPermission).where(
                UserPermission.user_id == user.id,
                UserPermission.organization_id == user.organization_id,
                UserPermission.permission_code == code,
                UserPermission.active.is_(True),
                UserPermission.revoked_at.is_(None),
            )
        )
        return delegated is not None and (
            delegated.expires_at is None or self._as_utc(delegated.expires_at) > now
        )

    def effective_permission_codes(self, user: User) -> list[str]:
        if user.role == UserRole.SUPER_ADMIN.value:
            return list(self.db.scalars(select(Permission.code).order_by(Permission.code)))

        codes = set(
            self.db.scalars(
                select(RolePermission.permission_code).where(
                    RolePermission.role_code == user.role
                )
            )
        )
        now = datetime.now(timezone.utc)
        delegations = self.db.scalars(
            select(UserPermission).where(
                UserPermission.user_id == user.id,
                UserPermission.organization_id == user.organization_id,
                UserPermission.active.is_(True),
                UserPermission.revoked_at.is_(None),
            )
        )
        codes.update(
            grant.permission_code
            for grant in delegations
            if grant.expires_at is None or self._as_utc(grant.expires_at) > now
        )
        return sorted(codes)

    def grant(
        self,
        *,
        actor: User,
        target: User,
        permission_code: str,
        expires_at: datetime | None,
    ) -> UserPermission:
        self._assert_can_manage(actor, target)
        permission = self.db.get(Permission, permission_code)
        if permission is None:
            raise PermissionNotFoundError("Permiso inexistente")
        if not self.has_permission(actor, permission_code):
            raise PermissionDeniedError("No puedes delegar un permiso que no posees")
        if expires_at is not None:
            expires_at = self._as_utc(expires_at)
            if expires_at <= datetime.now(timezone.utc):
                raise AuthorizationError("La expiración debe estar en el futuro")

        grant = self.db.scalar(
            select(UserPermission).where(
                UserPermission.user_id == target.id,
                UserPermission.permission_code == permission_code,
            )
        )
        if grant is None:
            grant = UserPermission(
                organization_id=target.organization_id,
                user_id=target.id,
                permission_code=permission_code,
                granted_by_user_id=actor.id,
            )
            self.db.add(grant)
        grant.organization_id = target.organization_id
        grant.granted_by_user_id = actor.id
        grant.expires_at = expires_at
        grant.revoked_at = None
        grant.active = True
        self.db.commit()
        self.db.refresh(grant)
        return grant

    def revoke(self, *, actor: User, target: User, permission_code: str) -> None:
        self._assert_can_manage(actor, target)
        grant = self.db.scalar(
            select(UserPermission).where(
                UserPermission.user_id == target.id,
                UserPermission.permission_code == permission_code,
                UserPermission.organization_id == target.organization_id,
            )
        )
        if grant is None or not grant.active:
            raise PermissionNotFoundError("Delegación inexistente")
        grant.active = False
        grant.revoked_at = datetime.now(timezone.utc)
        self.db.commit()

    def list_delegations(self, *, actor: User, target: User) -> list[UserPermission]:
        self._assert_same_tenant(actor, target)
        return list(
            self.db.scalars(
                select(UserPermission)
                .where(UserPermission.user_id == target.id)
                .order_by(UserPermission.permission_code)
            )
        )

    def _assert_can_manage(self, actor: User, target: User) -> None:
        self._assert_same_tenant(actor, target)
        if target.role == UserRole.SUPER_ADMIN.value:
            raise PermissionDeniedError("Los permisos de SUPER_ADMIN no son delegables")
        if not self.has_permission(actor, PermissionCode.USERS_PERMISSIONS_MANAGE):
            raise PermissionDeniedError("No tienes permiso para administrar delegaciones")

    @staticmethod
    def _assert_same_tenant(actor: User, target: User) -> None:
        if actor.role == UserRole.SUPER_ADMIN.value:
            return
        if actor.organization_id is None or actor.organization_id != target.organization_id:
            raise TenantAccessError("El usuario no pertenece a tu organización")

    @staticmethod
    def _code(permission_code: str | PermissionCode) -> str:
        return permission_code.value if isinstance(permission_code, PermissionCode) else permission_code

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
