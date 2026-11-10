"""api_router 汇总：每个路由文件保持薄壳，业务在 controllers/services。"""
from fastapi import APIRouter

from src.routes import auth, catalog, evaluation, governance, system

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(catalog.router)
api_router.include_router(evaluation.router)
api_router.include_router(governance.router)
api_router.include_router(system.router)

__all__ = ["api_router"]
