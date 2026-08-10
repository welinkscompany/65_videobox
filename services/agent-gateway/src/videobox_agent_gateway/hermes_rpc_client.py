"""Bounded, allowlisted client for Hermes Agent v0.18.2 dashboard transport."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
import json
import logging
from urllib.parse import quote
from urllib.parse import urlsplit

from videobox_agent_gateway.fault_reporting import FaultReporter

_LOGGER = logging.getLogger("uvicorn.error")


class HermesTransportError(RuntimeError):
    """A deliberately redacted Hermes transport failure."""


_MAX_RPC_FRAME_BYTES = 64_000
_HTTP_PROBE_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class HermesRpcEvent:
    event_type: str
    text: str = ""


def _default_http_client_factory(*, base_url: str, timeout: float):
    import httpx

    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
    )


def _default_websocket_factory(url: str, **kwargs):
    import websockets

    return websockets.connect(url, proxy=None, **kwargs)


class HermesRpcClient:
    """Authenticate, mint one ticket, and run one prompt on one WebSocket."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        http_client_factory: Callable = _default_http_client_factory,
        websocket_factory: Callable = _default_websocket_factory,
        # 이 값은 한 대화 전체(로그인·티켓·세션·프롬프트·스트리밍)를 덮는다.
        # 유진의 두뇌는 이 컴퓨터의 로컬 모델이라 답 하나가 30초를 넘긴다.
        # 2026-08-08 실기: 실제 대화가 255조각까지 흐르다 30초에서 잘렸다.
        timeout_seconds: float = 300.0,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "videobox-hermes-yujin"
            or parsed.port != 9120
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("hermes_url_must_be_internal")
        if not username or not password:
            raise ValueError("hermes_credentials_required")
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._http_factory = http_client_factory
        self._ws_factory = websocket_factory
        self._timeout = timeout_seconds
        self._active_runs: dict[str, tuple[object, str]] = {}
        self._active_lock = asyncio.Lock()
        self._probe_faults = FaultReporter(_LOGGER)

    async def stream_prompt(
        self, *, text: str, run_id: str | None = None
    ) -> AsyncIterator[HermesRpcEvent]:
        try:
            async with asyncio.timeout(self._timeout):
                for ticket_attempt in range(2):
                    session_id = ""
                    websocket = None
                    registered = False
                    ticket_minted = False
                    prompt_accepted = False
                    try:
                        ticket = await self._mint_ticket()
                        ticket_minted = True
                        ws_base = self._base_url.replace(
                            "http://", "ws://", 1
                        ).replace("https://", "wss://", 1)
                        ws_url = (
                            f"{ws_base}/api/ws?"
                            f"ticket={quote(ticket, safe='')}"
                        )
                        async with self._ws_factory(
                            ws_url,
                            open_timeout=self._timeout,
                            close_timeout=min(self._timeout, 5.0),
                        ) as websocket:
                            await websocket.send(
                                json.dumps(
                                    {
                                        "jsonrpc": "2.0",
                                        "id": 1,
                                        "method": "session.create",
                                        "params": {"source": "videobox"},
                                    }
                                )
                            )
                            session_id = await self._wait_for_session(websocket)
                            if run_id is not None:
                                async with self._active_lock:
                                    if run_id in self._active_runs:
                                        raise HermesTransportError(
                                            "hermes_invalid_response"
                                        )
                                    self._active_runs[run_id] = (
                                        websocket,
                                        session_id,
                                    )
                                    registered = True
                            await websocket.send(
                                json.dumps(
                                    {
                                        "jsonrpc": "2.0",
                                        "id": 2,
                                        "method": "prompt.submit",
                                        "params": {
                                            "session_id": session_id,
                                            "text": text,
                                        },
                                    }
                                )
                            )
                            await self._wait_for_prompt_acceptance(
                                websocket, session_id
                            )
                            prompt_accepted = True
                            async for event in self._read_prompt_events(
                                websocket, session_id
                            ):
                                yield event
                            return
                    except asyncio.CancelledError:
                        if websocket is not None and session_id:
                            await self._interrupt_best_effort(
                                websocket, session_id
                            )
                        raise
                    except HermesTransportError as error:
                        if (
                            str(error) == "hermes_ticket_expired"
                            and ticket_attempt == 0
                            and not prompt_accepted
                        ):
                            continue
                        raise
                    except Exception as error:
                        if (
                            ticket_minted
                            and self._is_ticket_expired(error)
                            and not prompt_accepted
                        ):
                            if ticket_attempt == 0:
                                continue
                            raise HermesTransportError(
                                "hermes_ticket_expired"
                            ) from error
                        raise HermesTransportError(
                            "hermes_unavailable"
                        ) from error
                    finally:
                        if registered and run_id is not None:
                            async with self._active_lock:
                                current = self._active_runs.get(run_id)
                                if (
                                    current is not None
                                    and current[0] is websocket
                                    and current[1] == session_id
                                ):
                                    self._active_runs.pop(run_id, None)
                raise HermesTransportError("hermes_ticket_expired")
        except asyncio.CancelledError:
            raise
        except TimeoutError as error:
            raise HermesTransportError("hermes_timeout") from error
        except HermesTransportError:
            raise
        except Exception as error:
            raise HermesTransportError("hermes_unavailable") from error

    async def _mint_ticket(self) -> str:
        async with self._http_factory(
            base_url=self._base_url, timeout=self._timeout
        ) as http:
            login = await http.post(
                "/auth/password-login",
                json={
                    "provider": "basic",
                    "username": self._username,
                    "password": self._password,
                    "next": "",
                },
            )
            login.raise_for_status()
            ticket_response = await http.post("/api/auth/ws-ticket")
            ticket_response.raise_for_status()
            ticket = str(ticket_response.json().get("ticket") or "")
            if not ticket:
                raise HermesTransportError("hermes_unavailable")
            return ticket

    async def probe_http_ready(self) -> bool:
        """Check only Hermes HTTP readiness without reading its response body."""

        timeout = min(
            max(float(self._timeout), 0.001),
            _HTTP_PROBE_TIMEOUT_SECONDS,
        )
        try:
            async with asyncio.timeout(timeout):
                async with self._http_factory(
                    base_url=self._base_url,
                    timeout=timeout,
                ) as http:
                    async with http.stream(
                        "GET",
                        "/api/status",
                    ) as response:
                        ready = response.status_code == 200
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 준비 확인은 실패해도 계속 돈다
            # 이 False가 위로 올라가면서 유진이 "안 떴다"가 된다. 이유가 여기
            # 말고는 어디에도 남지 않는다. 화면이 계속 되묻는 경로라 사유가
            # 달라질 때만 남긴다.
            self._probe_faults.report_once(
                exc,
                "헤르메스 준비 확인이 실패했습니다. 유진이 안 뜬 것으로 보입니다 (%s).",
                self._base_url,
            )
            return False
        self._probe_faults.clear()
        return ready

    async def interrupt(self, *, run_id: str) -> bool:
        async with self._active_lock:
            active = self._active_runs.get(run_id)
        if active is None:
            return False
        websocket, session_id = active
        return await self._interrupt_best_effort(websocket, session_id)

    @staticmethod
    def _is_ticket_expired(error: BaseException) -> bool:
        if (
            isinstance(error, HermesTransportError)
            and str(error) == "hermes_ticket_expired"
        ):
            return True
        status_code = getattr(error, "status_code", None)
        if status_code is None:
            status_code = getattr(
                getattr(error, "response", None), "status_code", None
            )
        return status_code in {401, 403}

    async def _wait_for_session(self, websocket) -> str:
        while True:
            message = self._decode(await websocket.recv())
            if message.get("id") != 1:
                self._validate_ignored_message(message)
                continue
            if "error" in message:
                error = message.get("error")
                if (
                    isinstance(error, dict)
                    and error.get("code") == "ticket_expired"
                ):
                    raise HermesTransportError("hermes_ticket_expired")
                raise HermesTransportError("hermes_unavailable")
            session_id = str((message.get("result") or {}).get("session_id") or "")
            if not session_id:
                raise HermesTransportError("hermes_invalid_response")
            return session_id

    async def _wait_for_prompt_acceptance(
        self, websocket, session_id: str
    ) -> None:
        while True:
            message = self._decode(await websocket.recv())
            if message.get("id") != 2:
                self._validate_ignored_message(message)
                continue
            if "error" in message:
                error = message.get("error")
                if (
                    isinstance(error, dict)
                    and error.get("code") == "ticket_expired"
                ):
                    raise HermesTransportError("hermes_ticket_expired")
                raise HermesTransportError("hermes_unavailable")
            # Hermes 0.18.2 answers prompt.submit with "streaming"; older
            # builds answered "accepted". Both mean the prompt was taken.
            # Anything else stays a hard failure -- this guard exists so an
            # unexpected reply never gets read as a running conversation.
            if message.get("result") not in (
                {"status": "accepted"},
                {"status": "streaming"},
            ):
                raise HermesTransportError("hermes_invalid_response")
            return

    async def _read_prompt_events(
        self, websocket, session_id: str
    ) -> AsyncIterator[HermesRpcEvent]:
        while True:
            message = self._decode(await websocket.recv())
            if message.get("id") == 2:
                raise HermesTransportError("hermes_invalid_response")
            if message.get("method") != "event":
                continue
            params = message.get("params")
            if not isinstance(params, dict):
                continue
            event_type = params.get("type")
            if isinstance(event_type, str) and (
                event_type.startswith("tool.")
                or event_type.startswith("approval.")
                or event_type.startswith("terminal.")
                or event_type.startswith("file.")
            ):
                raise HermesTransportError("hermes_invalid_response")
            if event_type not in {"gateway.ready", "message.delta", "message.complete"}:
                continue
            event_session = params.get("session_id")
            if event_type != "gateway.ready" and event_session != session_id:
                raise HermesTransportError("hermes_invalid_response")
            payload = params.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            if event_type == "gateway.ready":
                yield HermesRpcEvent("gateway.ready")
            elif event_type == "message.delta":
                text = payload.get("text", "")
                if not isinstance(text, str):
                    raise HermesTransportError("hermes_invalid_response")
                yield HermesRpcEvent("message.delta", text)
            else:
                if payload.get("status") == "interrupted":
                    raise HermesTransportError("hermes_interrupted")
                if payload.get("status") != "complete":
                    raise HermesTransportError("hermes_unavailable")
                text = payload.get("text", "")
                if not isinstance(text, str):
                    raise HermesTransportError("hermes_invalid_response")
                if not text.strip():
                    raise HermesTransportError("hermes_invalid_response")
                yield HermesRpcEvent(
                    "message.complete", text
                )
                return

    @staticmethod
    def _decode(raw: object) -> dict:
        if not isinstance(raw, (str, bytes)):
            raise HermesTransportError("hermes_invalid_response")
        if len(raw.encode("utf-8") if isinstance(raw, str) else raw) > _MAX_RPC_FRAME_BYTES:
            raise HermesTransportError("hermes_invalid_response")
        try:
            message = json.loads(raw)
        except Exception as error:
            raise HermesTransportError("hermes_invalid_response") from error
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise HermesTransportError("hermes_invalid_response")
        return message

    @staticmethod
    def _validate_ignored_message(message: dict) -> None:
        if message.get("method") == "event":
            params = message.get("params")
            event_type = params.get("type") if isinstance(params, dict) else None
            if event_type == "gateway.ready":
                return
            if isinstance(event_type, str) and (
                event_type.startswith("tool.")
                or event_type.startswith("approval.")
                or event_type.startswith("terminal.")
                or event_type.startswith("file.")
            ):
                raise HermesTransportError("hermes_invalid_response")
            if event_type in {"message.delta", "message.complete"}:
                raise HermesTransportError("hermes_invalid_response")

    @staticmethod
    async def _interrupt_best_effort(websocket, session_id: str) -> bool:
        try:
            await websocket.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "session.interrupt",
                        "params": {"session_id": session_id},
                    }
                )
            )
            return True
        except Exception:
            return False
