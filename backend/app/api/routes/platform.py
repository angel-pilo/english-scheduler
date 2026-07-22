from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.platform import (
    OrganizationCreatedOut,
    OrganizationCreateIn,
    OrganizationOut,
    OrganizationStatusIn,
)
from app.services.platform import PlatformConflictError, PlatformError, PlatformService


router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/organizations", response_model=list[OrganizationOut])
def list_organizations(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.SUPER_ADMIN.value)),
) -> list[OrganizationOut]:
    return [
        OrganizationOut.model_validate(item, from_attributes=True)
        for item in PlatformService(db).list_organizations()
    ]


@router.post(
    "/organizations",
    response_model=OrganizationCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    payload: OrganizationCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.SUPER_ADMIN.value)),
) -> OrganizationCreatedOut:
    try:
        created = PlatformService(db).create_organization(
            actor=actor,
            name=payload.name,
            slug=payload.slug,
            timezone_name=payload.timezone,
            branch_name=payload.branch_name,
            branch_code=payload.branch_code,
            admin_name=payload.admin_name,
            admin_email=payload.admin_email,
        )
    except PlatformConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    except PlatformError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    return OrganizationCreatedOut(
        id=created.organization.id,
        name=created.organization.name,
        slug=created.organization.slug,
        timezone=created.organization.timezone,
        active=created.organization.active,
        branch_id=created.branch.id,
        admin_user_id=created.admin.id,
        admin_activation_url=created.activation_url,
    )


@router.patch("/organizations/{organization_id}/status", response_model=OrganizationOut)
def set_organization_status(
    organization_id: int,
    payload: OrganizationStatusIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.SUPER_ADMIN.value)),
) -> OrganizationOut:
    try:
        organization = PlatformService(db).set_organization_active(
            organization_id, payload.active
        )
    except PlatformError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    return OrganizationOut.model_validate(organization, from_attributes=True)
