from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.admin import InvitationCreateIn, InvitationOut
from app.services.invitations import (
    InvitationConflictError,
    InvitationError,
    InvitationService,
)


router = APIRouter(prefix="/admin", tags=["admin"])


@router.post(
    "/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED
)
def create_invitation(
    payload: InvitationCreateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN.value)),
) -> InvitationOut:
    try:
        created = InvitationService(db).create(
            admin=admin,
            name=payload.name,
            email=payload.email,
            role=payload.role,
            branch_id=payload.branch_id,
        )
    except InvitationConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    except InvitationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))

    return InvitationOut(
        id=created.invitation.id,
        user_id=created.invitation.user_id,
        email=created.email,
        expires_at=created.invitation.expires_at,
        activation_url=created.activation_url,
    )
