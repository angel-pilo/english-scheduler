from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.enums import PermissionCode
from app.models.user import User
from app.schemas.locations import (
    BranchCreateIn,
    BranchOut,
    BranchUpdateIn,
    RoomCreateIn,
    RoomOut,
    RoomUpdateIn,
)
from app.services.locations import (
    BranchService,
    LocationConflictError,
    LocationError,
    LocationNotFoundError,
    RoomService,
)


router = APIRouter(prefix="/admin", tags=["locations"])


@router.get("/branches", response_model=list[BranchOut])
def list_branches(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BRANCHES_MANAGE)),
):
    return BranchService(db).list(actor, include_inactive=include_inactive)


@router.post("/branches", response_model=BranchOut, status_code=status.HTTP_201_CREATED)
def create_branch(
    payload: BranchCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BRANCHES_MANAGE)),
):
    try:
        return BranchService(db).create(
            actor,
            name=payload.name,
            code=payload.code,
            timezone_name=payload.timezone,
        )
    except LocationError as error:
        _raise_location(error)


@router.get("/branches/{branch_id}", response_model=BranchOut)
def get_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BRANCHES_MANAGE)),
):
    try:
        return BranchService(db).get(actor, branch_id)
    except LocationError as error:
        _raise_location(error)


@router.patch("/branches/{branch_id}", response_model=BranchOut)
def update_branch(
    branch_id: int,
    payload: BranchUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BRANCHES_MANAGE)),
):
    try:
        return BranchService(db).update(
            actor, branch_id, payload.model_dump(exclude_unset=True)
        )
    except LocationError as error:
        _raise_location(error)


@router.delete("/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BRANCHES_MANAGE)),
) -> Response:
    try:
        BranchService(db).deactivate(actor, branch_id)
    except LocationError as error:
        _raise_location(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/rooms", response_model=list[RoomOut])
def list_rooms(
    branch_id: int | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.ROOMS_MANAGE)),
):
    try:
        return RoomService(db).list(
            actor,
            branch_id=branch_id,
            include_inactive=include_inactive,
        )
    except LocationError as error:
        _raise_location(error)


@router.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(
    payload: RoomCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.ROOMS_MANAGE)),
):
    try:
        return RoomService(db).create(actor, **payload.model_dump())
    except LocationError as error:
        _raise_location(error)


@router.get("/rooms/{room_id}", response_model=RoomOut)
def get_room(
    room_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.ROOMS_MANAGE)),
):
    try:
        return RoomService(db).get(actor, room_id)
    except LocationError as error:
        _raise_location(error)


@router.patch("/rooms/{room_id}", response_model=RoomOut)
def update_room(
    room_id: int,
    payload: RoomUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.ROOMS_MANAGE)),
):
    try:
        return RoomService(db).update(
            actor, room_id, payload.model_dump(exclude_unset=True)
        )
    except LocationError as error:
        _raise_location(error)


@router.delete("/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_room(
    room_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.ROOMS_MANAGE)),
) -> Response:
    try:
        RoomService(db).deactivate(actor, room_id)
    except LocationError as error:
        _raise_location(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _raise_location(error: LocationError) -> NoReturn:
    if isinstance(error, LocationNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, LocationConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
