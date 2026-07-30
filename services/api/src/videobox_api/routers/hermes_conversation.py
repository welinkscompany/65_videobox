"""Authenticated internal Hermes runs exposed as a narrow public SSE surface."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from videobox_api.models import HermesRunCreateRequest, HermesRunCreateResponse
from videobox_api.agent_gateway_client import AgentGatewayUnavailable
from videobox_api.hermes_capabilities import HermesCapabilityError
from videobox_api.hermes_run_service import HermesCapacityUnavailable


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
                expected_session_revision=body.expected_session_revision,
                selected_segment_id=body.selected_segment_id,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error.args[0])) from error
        except HermesCapabilityError as error:
            raise HTTPException(
                status_code=503,
                detail="hermes_context_preparation_unavailable",
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except HermesCapacityUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except AgentGatewayUnavailable as error:
            raise HTTPException(
                status_code=503, detail="hermes_context_preparation_unavailable"
            ) from error
        events_url = (
            f"/api/projects/{project_id}/director/conversations/"
            f"{conversation_id}/hermes-runs/{run.run_id}/events"
        )
        return HermesRunCreateResponse(
            run_id=run.run_id,
            conversation_id=conversation_id,
            events_url=events_url,
        )

    @router.post(
        "/api/projects/{project_id}/director/conversations/{conversation_id}/hermes-runs/{run_id}/cancel",
        status_code=204,
        response_class=Response,
    )
    async def cancel_run(
        project_id: str,
        conversation_id: str,
        run_id: str,
    ) -> Response:
        try:
            await run_service.cancel(
                run_id,
                project_id=project_id,
                conversation_id=conversation_id,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail=str(error.args[0])
            ) from error
        return Response(status_code=204)

    @router.post(
        "/api/projects/{project_id}/director/conversations/{conversation_id}/hermes-runs/{run_id}/retry",
        response_model=HermesRunCreateResponse,
        status_code=201,
    )
    async def retry_run(
        project_id: str,
        conversation_id: str,
        run_id: str,
    ) -> HermesRunCreateResponse:
        try:
            run = await run_service.retry(
                run_id,
                project_id=project_id,
                conversation_id=conversation_id,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail=str(error.args[0])
            ) from error
        except HermesCapabilityError as error:
            raise HTTPException(
                status_code=503,
                detail="hermes_context_preparation_unavailable",
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except HermesCapacityUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except AgentGatewayUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail="hermes_context_preparation_unavailable",
            ) from error
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
        raw_cursor = request.headers.get("last-event-id")
        if raw_cursor is None:
            after_event_id = 0
        elif (
            len(raw_cursor) > 19
            or re.fullmatch(r"[0-9]+", raw_cursor) is None
        ):
            raise HTTPException(
                status_code=400, detail="hermes_run_cursor_invalid"
            )
        else:
            after_event_id = int(raw_cursor)
        try:
            await asyncio.to_thread(
                run_service.store.list_director_hermes_run_events,
                project_id=project_id,
                conversation_id=conversation_id,
                run_id=run_id,
                after_event_id=after_event_id,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error.args[0])) from error
        except ValueError as error:
            detail = str(error)
            if detail == "hermes_run_events_expired":
                raise HTTPException(status_code=410, detail=detail) from error
            status_code = (
                400 if detail == "hermes_run_cursor_invalid" else 409
            )
            raise HTTPException(status_code=status_code, detail=detail) from error

        async def stream() -> AsyncIterator[str]:
            async for event in run_service.subscribe(
                run_id,
                project_id=project_id,
                conversation_id=conversation_id,
                after_event_id=after_event_id,
            ):
                if await request.is_disconnected():
                    return
                yield (
                    f"id: {event.event_id}\n"
                    f"event: {event.event_type}\n"
                    f"data: {event.model_dump_json()}\n\n"
                )

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    return router
