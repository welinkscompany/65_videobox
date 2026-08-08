from __future__ import annotations

from fastapi.testclient import TestClient

from videobox_agent_gateway.main import create_app
from videobox_agent_gateway.memory_gateway import MemoryWriteOutcome
from videobox_agent_gateway.memory_gateway import (
    AdapterMemorySearch,
    AdapterMemoryWrite,
    HermesMemoryAdapterClient,
    MemoryDeleteResult,
    MemorySearchResult,
    RetrievedMemory,
)
import asyncio
import pytest


class _MemoryAdapter:
    def __init__(self) -> None:
        self.requests = []

    async def add_approved(self, request):
        self.requests.append(request)
        return MemoryWriteOutcome(status="stored", memory_ref="memory-private")

    async def search(self, request):
        self.requests.append(request)
        return MemorySearchResult(
            memories=(
                RetrievedMemory(
                    memory_ref="memory-private",
                    text="빠른 컷을 선호합니다.",
                    category="pacing",
                    external_ref="ext-" + "a" * 64,
                ),
            )
        )

    async def delete(self, request):
        self.requests.append(request)
        return MemoryDeleteResult(deleted=True)


def test_gateway_exposes_only_authenticated_narrow_memory_add() -> None:
    adapter = _MemoryAdapter()
    app = create_app(
        service_token="gateway-service-token-with-enough-entropy-123",
        memory_gateway=adapter,
    )

    with TestClient(app) as client:
        unauthorized = client.post(
            "/internal/hermes/memory/add",
            json={
                "text": "빠른 컷을 선호합니다.",
                "category": "pacing",
                "external_ref": "ext-" + "a" * 64,
                "operation_id": "op-" + "b" * 64,
            },
        )
        accepted = client.post(
            "/internal/hermes/memory/add",
            headers={
                "Authorization": (
                    "Bearer gateway-service-token-with-enough-entropy-123"
                )
            },
            json={
                "text": "빠른 컷을 선호합니다.",
                "category": "pacing",
                "external_ref": "ext-" + "a" * 64,
                "operation_id": "op-" + "b" * 64,
            },
        )

    assert unauthorized.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json() == {
        "status": "stored",
        "memory_ref": "memory-private",
        "event_ref": None,
    }
    assert len(adapter.requests) == 1
    request = adapter.requests[0]
    assert request.user_id == "videobox-owner-v1"
    assert request.agent_id == "videobox-yujin-v1"
    assert request.infer is False
    assert request.metadata == {
        "source": "videobox_yujin_approved_v1",
        "category": "pacing",
        "external_ref": "ext-" + "a" * 64,
    }
    assert not hasattr(request, "project_id")


def test_gateway_rejects_browser_internal_ids_and_never_calls_adapter() -> None:
    adapter = _MemoryAdapter()
    app = create_app(
        service_token="gateway-service-token-with-enough-entropy-123",
        memory_gateway=adapter,
    )

    with TestClient(app) as client:
        response = client.post(
            "/internal/hermes/memory/add",
            headers={
                "Authorization": (
                    "Bearer gateway-service-token-with-enough-entropy-123"
                )
            },
            json={
                "text": "빠른 컷을 선호합니다.",
                "category": "pacing",
                "external_ref": "ext-" + "a" * 64,
                "operation_id": "op-" + "b" * 64,
                "project_id": "project-private",
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "gateway_request_invalid"}
    assert adapter.requests == []


@pytest.mark.parametrize(
    "url",
    [
        "https://videobox-hermes-memory-adapter:8082",
        "http://evil.example:8082",
        "http://user:pass@videobox-hermes-memory-adapter:8082",
        "http://videobox-hermes-memory-adapter:8081",
        "http://videobox-hermes-memory-adapter:8082/path",
        "http://videobox-hermes-memory-adapter:8082?next=evil",
    ],
)
def test_adapter_client_rejects_non_internal_urls(url: str) -> None:
    with pytest.raises(ValueError, match="internal"):
        HermesMemoryAdapterClient(
            base_url=url,
            service_token="adapter-service-token-with-enough-entropy-456",
        )


@pytest.mark.parametrize(
    "token,timeout",
    [
        ("a" * 32, 1),
        ("replace_me-adapter-service-token-123456", 1),
        ("adapter-service-token-with-enough-entropy-456", 0),
        ("adapter-service-token-with-enough-entropy-456", 11),
        ("adapter-service-token-with-enough-entropy-456", float("inf")),
    ],
)
def test_adapter_client_rejects_weak_credentials_and_timeouts(
    token, timeout
) -> None:
    with pytest.raises(ValueError):
        HermesMemoryAdapterClient(
            base_url="http://videobox-hermes-memory-adapter:8082",
            service_token=token,
            timeout_seconds=timeout,
        )


def test_adapter_client_bounds_and_maps_internal_responses() -> None:
    class Response:
        def __init__(
            self, *, status_code=200, redirect=False, oversized=False
        ):
            self.status_code = status_code
            self.is_redirect = redirect
            self.content = b"x" * (16_385 if oversized else 2)

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("private response")

        def json(self):
            return {
                "status": "stored",
                "memory_ref": "memory-private",
                "event_ref": None,
            }

    class Http:
        def __init__(self, response):
            self.response = response

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return self.response

    request = AdapterMemoryWrite(
        text="빠른 컷을 선호합니다.",
        category="pacing",
        external_ref="ext-" + "a" * 64,
        operation_id="op-" + "b" * 64,
        metadata={
            "source": "videobox_yujin_approved_v1",
            "category": "pacing",
            "external_ref": "ext-" + "a" * 64,
        },
    )
    outcomes = []
    for response in (
        Response(status_code=503),
        Response(redirect=True),
        Response(oversized=True),
        Response(),
    ):
        client = HermesMemoryAdapterClient(
            base_url="http://videobox-hermes-memory-adapter:8082",
            service_token="adapter-service-token-with-enough-entropy-456",
            http_client_factory=lambda **_kwargs: Http(response),
        )
        outcomes.append(asyncio.run(client.add_approved(request)))

    assert [item.status for item in outcomes] == [
        "failed_retryable",
        "ambiguous",
        "ambiguous",
        "stored",
    ]


def test_gateway_search_and_delete_are_narrow_authenticated_routes() -> None:
    adapter = _MemoryAdapter()
    app = create_app(
        service_token="gateway-service-token-with-enough-entropy-123",
        memory_gateway=adapter,
    )
    headers = {
        "Authorization": (
            "Bearer gateway-service-token-with-enough-entropy-123"
        )
    }
    with TestClient(app) as client:
        searched = client.post(
            "/internal/hermes/memory/search",
            headers=headers,
            json={"query": "편집 템포", "limit": 3},
        )
        deleted = client.post(
            "/internal/hermes/memory/delete",
            headers=headers,
            json={
                "memory_ref": "memory-private",
                "external_ref": "ext-" + "a" * 64,
                "allow_absent": False,
            },
        )

    assert searched.status_code == 200
    assert searched.json() == {
        "memories": [
            {
                "memory_ref": "memory-private",
                "text": "빠른 컷을 선호합니다.",
                "category": "pacing",
                "external_ref": "ext-" + "a" * 64,
            }
        ]
    }
    assert deleted.json() == {"deleted": True}
    assert all(not hasattr(request, "project_id") for request in adapter.requests)


def test_adapter_client_decodes_a_real_json_search_body() -> None:
    """The adapter answers over HTTP, so `memories` arrives as a JSON array."""

    body = (
        '{"memories":[{"memory_ref":"memory-private",'
        '"text":"\ube60\ub978 \ucef7\uc744 \uc120\ud638\ud569\ub2c8\ub2e4.",'
        '"category":"pacing","external_ref":"ext-' + "a" * 64 + '"}]}'
    ).encode("utf-8")

    class Response:
        status_code = 200
        is_redirect = False
        content = body

        def raise_for_status(self):
            return None

        def json(self):
            import json

            return json.loads(body)

    class Http:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return Response()

    client = HermesMemoryAdapterClient(
        base_url="http://videobox-hermes-memory-adapter:8082",
        service_token="adapter-service-token-with-enough-entropy-456",
        http_client_factory=lambda **_kwargs: Http(),
    )
    result = asyncio.run(
        client.search(AdapterMemorySearch(query="편집 템포", limit=5))
    )

    assert result == MemorySearchResult(
        memories=(
            RetrievedMemory(
                memory_ref="memory-private",
                text="빠른 컷을 선호합니다.",
                category="pacing",
                external_ref="ext-" + "a" * 64,
            ),
        )
    )
