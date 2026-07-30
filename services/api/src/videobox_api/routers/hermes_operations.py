"""Read-only global Hermes Yujin operations surface."""

from fastapi import APIRouter

from videobox_api.models import HermesYujinStatusResponse


def build_hermes_operations_router(status_service) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/hermes-yujin/status",
        response_model=HermesYujinStatusResponse,
    )
    async def get_hermes_yujin_status() -> HermesYujinStatusResponse:
        return await status_service.get_status()

    return router
