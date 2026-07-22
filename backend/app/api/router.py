from fastapi import APIRouter
from app.api.routes.auth import router as auth_router
from app.api.routes.admin import router as admin_router
from app.api.routes.permissions import router as permissions_router
from app.api.routes.platform import router as platform_router
from app.api.routes.locations import router as locations_router
from app.api.routes.students import router as students_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(permissions_router)
api_router.include_router(platform_router)
api_router.include_router(locations_router)
api_router.include_router(students_router)
