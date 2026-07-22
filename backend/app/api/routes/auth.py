from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginIn, MeOut, RefreshIn, TokenOut
from app.services.auth import (
    AccountLockedError,
    AuthService,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    try:
        tokens = AuthService(db).login(
            email=data.email,
            password=data.password,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except AccountLockedError:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Cuenta bloqueada temporalmente")
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )
    return TokenOut(**tokens.__dict__)


@router.post("/refresh", response_model=TokenOut)
def refresh(data: RefreshIn, db: Session = Depends(get_db)) -> TokenOut:
    try:
        tokens = AuthService(db).refresh(data.refresh_token)
    except InvalidRefreshTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado",
        )
    return TokenOut(**tokens.__dict__)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
) -> Response:
    AuthService(db).logout(context.session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
