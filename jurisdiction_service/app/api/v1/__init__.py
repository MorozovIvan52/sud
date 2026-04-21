from fastapi import APIRouter

from app.api.v1.endpoints import jurisdiction, admin, verification, verification_system

api_router = APIRouter()
api_router.include_router(jurisdiction.router, prefix="")
api_router.include_router(verification.router, prefix="")
api_router.include_router(verification_system.router, prefix="")
api_router.include_router(admin.router, prefix="")
