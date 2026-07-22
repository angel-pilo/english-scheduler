from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.enums import PermissionCode
from app.models.rbac import Permission
from app.models.user import User
from app.schemas.permissions import (
    PermissionGrantIn,
    PermissionOut,
    UserAuthorizationOut,
    UserPermissionOut,
)
from app.services.authorization import (
    AuthorizationError,
    AuthorizationService,
    PermissionDeniedError,
    PermissionNotFoundError,
    TenantAccessError,
)


router = APIRouter(prefix="/admin", tags=["permissions"])


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(PermissionCode.USERS_PERMISSIONS_MANAGE)),
) -> list[Permission]:
    return list(db.scalars(select(Permission).order_by(Permission.code)))


@router.get("/users/{user_id}/permissions", response_model=UserAuthorizationOut)
def get_user_permissions(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.USERS_PERMISSIONS_MANAGE)),
) -> UserAuthorizationOut:
    target = _get_target(db, user_id)
    service = AuthorizationService(db)
    try:
        delegations = service.list_delegations(actor=actor, target=target)
    except AuthorizationError as error:
        _raise_http(error)
    return UserAuthorizationOut(
        user_id=target.id,
        role=target.role,
        effective_permissions=service.effective_permission_codes(target),
        delegations=[UserPermissionOut.model_validate(item) for item in delegations],
    )


@router.post(
    "/users/{user_id}/permissions",
    response_model=UserPermissionOut,
    status_code=status.HTTP_201_CREATED,
)
def grant_user_permission(
    user_id: int,
    payload: PermissionGrantIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.USERS_PERMISSIONS_MANAGE)),
) -> UserPermissionOut:
    target = _get_target(db, user_id)
    try:
        grant = AuthorizationService(db).grant(
            actor=actor,
            target=target,
            permission_code=payload.permission_code,
            expires_at=payload.expires_at,
        )
    except AuthorizationError as error:
        _raise_http(error)
    return UserPermissionOut.model_validate(grant)


@router.delete(
    "/users/{user_id}/permissions/{permission_code}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_user_permission(
    user_id: int,
    permission_code: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.USERS_PERMISSIONS_MANAGE)),
) -> Response:
    target = _get_target(db, user_id)
    try:
        AuthorizationService(db).revoke(
            actor=actor,
            target=target,
            permission_code=permission_code,
        )
    except AuthorizationError as error:
        _raise_http(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_target(db: Session, user_id: int) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return target


def _raise_http(error: AuthorizationError) -> NoReturn:
    if isinstance(error, TenantAccessError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if isinstance(error, PermissionNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, PermissionDeniedError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error))
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
