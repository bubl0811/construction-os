from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.health.router import router as health_router
from app.modules.projects.members_router import router as project_members_router
from app.modules.projects.router import router as projects_router
from app.modules.structures.router import router as structures_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(project_members_router)
api_router.include_router(structures_router)
