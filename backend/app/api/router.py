from fastapi import APIRouter
from app.api.routes.auth import router as auth_router
from app.api.routes.permissions import router as permissions_router
from app.api.routes.platform import router as platform_router
from app.api.routes.locations import router as locations_router
from app.api.routes.students import router as students_router
from app.api.routes.teachers import router as teachers_router
from app.api.routes.curriculum import router as curriculum_router
from app.api.routes.schedules import router as schedules_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.bookings import router as bookings_router
from app.api.routes.waitlists import router as waitlists_router
from app.api.routes.attendance import router as attendance_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(permissions_router)
api_router.include_router(platform_router)
api_router.include_router(locations_router)
api_router.include_router(students_router)
api_router.include_router(teachers_router)
api_router.include_router(curriculum_router)
api_router.include_router(schedules_router)
api_router.include_router(sessions_router)
api_router.include_router(bookings_router)
api_router.include_router(waitlists_router)
api_router.include_router(attendance_router)
