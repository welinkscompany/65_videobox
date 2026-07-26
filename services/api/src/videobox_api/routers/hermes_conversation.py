"""Authenticated internal Hermes runs exposed as a narrow public SSE surface."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from videobox_api.models import HermesRunCreateRequest, HermesRunCreateResponse


def build_hermes_conversation_router(run_service) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/director/conversations/{conversation_id}/hermes-runs",
        response_model=HermesRunCreateResponse,
        status_code=201,
    )
    async def create_run(
        project_id: str,
        conversation_id: str,
        body: HermesRunCreateRequest,
    ) -> HermesRunCreateResponse:
        try:
            run = await run_service.create_run(
                project_id=project_id,
                session_id=body.session_id,
                conversation_id=conversation_id,
                client_message_id=body.client_message_id,
                text=body.text,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error.args[0])) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        events_url = (
            f"/api/projects/{project_id}/director/conversations/"
            f"{conversation_id}/hermes-runs/{run.run_id}/events"
        )
        return HermesRunCreateResponse(
            run_id=run.run_id,
            conversation_id=conversation_id,
            events_url=events_url,
        )

    @router.get(
        "/api/projects/{project_id}/director/conversations/{conversation_id}/hermes-runs/{run_id}/events"
    )
    async def events(
        request: Request,
        project_id: str,
        conversation_id: str,
        run_id: str,
    ) -> StreamingResponse:
        try:
            run = run_service.get_run(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error.args[0])) from error
        if run.project_id != project_id or run.conversation_id != conversation_id:
            raise HTTPException(status_code=404, detail="director_hermes_run_missing")

        async def stream() -> AsyncIterator[str]:
            try:
                async for event in run_service.subscribe(run_id):
                    if await request.is_disconnected():
                        await run_service.cancel(run_id)
                        return
                    yield (
                        f"id: {event.event_id}\n"
                        f"event: {event.event_type}\n"
                        f"data: {event.model_dump_json()}\n\n"
                    )
            finally:
                if await request.is_disconnected():
                    await run_service.cancel(run_id)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    return router
