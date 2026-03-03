from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import require_role
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.admin import UserCreateIn, UserOut
from app.core.security import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/users", response_model=UserOut)
def create_user(payload: UserCreateIn, db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.ADMIN.value))):
    if payload.role not in (UserRole.TEACHER.value, UserRole.STUDENT.value):
        raise HTTPException(status_code=400, detail="role debe ser TEACHER o STUDENT")

    exists = db.query(User).filter(User.email == payload.email).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email ya registrado")

    user = User(
        organization_id=admin.organization_id,
        branch_id=payload.branch_id,
        role=payload.role,
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
