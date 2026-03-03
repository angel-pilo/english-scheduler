from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.api.router import api_router

from app.models.org import Organization
from app.models.branch import Branch
from app.models.user import User
from app.models.enums import UserRole
from app.core.security import hash_password

# Asegura que SQLAlchemy conozca modelos
from app.models import org, branch, user  # noqa: F401

app = FastAPI(title="English Scheduler API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/health")
def health():
    return {"status": "ok"}

def bootstrap(db: Session):
    Base.metadata.create_all(bind=engine)

    org = db.query(Organization).filter(Organization.name == settings.bootstrap_org_name).first()
    if not org:
        org = Organization(name=settings.bootstrap_org_name)
        db.add(org)
        db.commit()
        db.refresh(org)

    branch = db.query(Branch).filter(Branch.organization_id == org.id, Branch.name == settings.bootstrap_branch_name).first()
    if not branch:
        branch = Branch(organization_id=org.id, name=settings.bootstrap_branch_name)
        db.add(branch)
        db.commit()
        db.refresh(branch)

    admin = db.query(User).filter(User.email == settings.bootstrap_admin_email).first()
    if not admin:
        admin = User(
            organization_id=org.id,
            branch_id=branch.id,
            role=UserRole.ADMIN.value,
            name="Admin",
            email=settings.bootstrap_admin_email,
            hashed_password=hash_password(settings.bootstrap_admin_password),
            active=True,
        )
        db.add(admin)
        db.commit()

@app.on_event("startup")
def on_startup():
    db = SessionLocal()
    try:
        bootstrap(db)
    finally:
        db.close()
