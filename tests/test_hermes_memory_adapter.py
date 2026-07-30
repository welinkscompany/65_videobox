from __future__ import annotations

from fastapi.testclient import TestClient

from videobox_agent_gateway.hermes_memory_adapter import create_memory_adapter_app
from videobox_agent_gateway.hermes_memory_adapter import (
    build_memory_adapter_from_environment,
    _PinnedHermesMem0Provider,
)


class _Provider:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def add(self, **kwargs):
        self.calls.append(kwargs)
        return self.result

    def get_event(self, **kwargs):
        self.calls.append(kwargs)
        return self.result

    def search(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


def _payload() -> dict[str, object]:
    return {
        "text": "빠른 컷을 선호합니다.",
        "category": "pacing",
        "external_ref": "ext-" + "a" * 64,
        "operation_id": "op-" + "b" * 64,
        "user_id": "videobox-owner-v1",
        "agent_id": "videobox-yujin-v1",
        "infer": False,
        "metadata": {
            "source": "videobox_yujin_approved_v1",
            "category": "pacing",
            "external_ref": "ext-" + "a" * 64,
        },
    }


def test_adapter_adds_only_approved_minimal_payload_without_inference() -> None:
    provider = _Provider({"results": [{"id": "durable-memory-1"}]})
    app = create_memory_adapter_app(
        provider=provider,
        service_token="adapter-service-token-with-enough-entropy-456",
    )

    with TestClient(app) as client:
        response = client.post(
            "/internal/memory/add",
            headers={
                "Authorization": (
                    "Bearer adapter-service-token-with-enough-entropy-456"
                )
            },
            json=_payload(),
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "stored",
        "memory_ref": "durable-memory-1",
        "event_ref": None,
    }
    assert provider.calls == [
        {
            "messages": [
                {"role": "user", "content": "빠른 컷을 선호합니다."}
            ],
            "user_id": "videobox-owner-v1",
            "agent_id": "videobox-yujin-v1",
            "infer": False,
            "metadata": {
                "source": "videobox_yujin_approved_v1",
                "category": "pacing",
                "external_ref": "ext-" + "a" * 64,
            },
        }
    ]


def test_adapter_keeps_event_id_distinct_from_memory_id() -> None:
    provider = _Provider({"event_id": "event-private-1"})
    app = create_memory_adapter_app(
        provider=provider,
        service_token="adapter-service-token-with-enough-entropy-456",
    )

    with TestClient(app) as client:
        response = client.post(
            "/internal/memory/add",
            headers={
                "Authorization": (
                    "Bearer adapter-service-token-with-enough-entropy-456"
                )
            },
            json=_payload(),
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "event_pending",
        "memory_ref": None,
        "event_ref": "event-private-1",
    }


def test_adapter_is_startable_without_provider_and_does_not_call_network() -> None:
    app = create_memory_adapter_app(
        provider=None,
        service_token="adapter-service-token-with-enough-entropy-456",
    )

    with TestClient(app) as client:
        health = client.get("/health")
        response = client.post(
            "/internal/memory/add",
            headers={
                "Authorization": (
                    "Bearer adapter-service-token-with-enough-entropy-456"
                )
            },
            json=_payload(),
        )

    assert health.json() == {"status": "ready", "configured": False}
    assert response.status_code == 503
    assert response.json() == {"detail": "memory_adapter_unavailable"}


def test_environment_with_key_but_invalid_token_never_constructs_provider() -> None:
    provider_calls = []

    app = build_memory_adapter_from_environment(
        environ={"MEM0_API_KEY": "private-key"},
        provider_factory=lambda _key: provider_calls.append("constructed"),
    )

    with TestClient(app) as client:
        assert client.get("/health").json() == {
            "status": "ready",
            "configured": False,
        }
    assert provider_calls == []


def test_valid_environment_is_lazy_and_startup_constructs_no_provider() -> None:
    provider_calls = []
    app = build_memory_adapter_from_environment(
        environ={
            "MEM0_API_KEY": "private-key",
            "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN": (
                "adapter-service-token-with-enough-entropy-456"
            ),
        },
        provider_factory=lambda _key: provider_calls.append("constructed"),
    )

    with TestClient(app) as client:
        assert client.get("/health").json() == {
            "status": "ready",
            "configured": True,
        }

    assert provider_calls == []


def test_reconcile_requires_exact_owned_single_result() -> None:
    text = "빠른 컷을 선호합니다."
    metadata = {
        "source": "videobox_yujin_approved_v1",
        "category": "pacing",
        "external_ref": "ext-" + "a" * 64,
    }
    request = {
        **_payload(),
        "event_ref": "event-private-1",
    }
    request.pop("infer")
    request.pop("metadata")
    outcomes = (
        (
            {
                "status": "SUCCEEDED",
                "results": [
                    {
                        "id": "memory-1",
                        "memory": text,
                        "metadata": metadata,
                    }
                ],
            },
            "stored",
        ),
        (
            {
                "status": "SUCCEEDED",
                "results": [
                    {
                        "id": "memory-1",
                        "memory": "다른 내용",
                        "metadata": metadata,
                    }
                ],
            },
            "ambiguous",
        ),
        (
            {
                "status": "SUCCEEDED",
                "results": [
                    {
                        "id": "memory-1",
                        "memory": text,
                        "metadata": metadata,
                    },
                    {
                        "id": "memory-2",
                        "memory": text,
                        "metadata": metadata,
                    },
                ],
            },
            "ambiguous",
        ),
    )
    for provider_result, expected in outcomes:
        provider = _Provider(provider_result)
        app = create_memory_adapter_app(
            provider=provider,
            service_token="adapter-service-token-with-enough-entropy-456",
        )
        with TestClient(app) as client:
            response = client.post(
                "/internal/memory/reconcile",
                headers={
                    "Authorization": (
                        "Bearer adapter-service-token-with-enough-entropy-456"
                    )
                },
                json=request,
            )
        assert response.status_code == 200
        assert response.json()["status"] == expected


def test_failed_event_with_no_owned_result_is_proven_retryable() -> None:
    class Provider:
        def get_event(self, **_kwargs):
            return {"status": "FAILED"}

        def search(self, *_args, **_kwargs):
            return {"results": []}

    app = create_memory_adapter_app(
        provider=Provider(),
        service_token="adapter-service-token-with-enough-entropy-456",
    )
    request = {**_payload(), "event_ref": "event-private-1"}
    request.pop("infer")
    request.pop("metadata")
    with TestClient(app) as client:
        response = client.post(
            "/internal/memory/reconcile",
            headers={
                "Authorization": (
                    "Bearer adapter-service-token-with-enough-entropy-456"
                )
            },
            json=request,
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "failed_retryable",
        "memory_ref": None,
        "event_ref": None,
    }


def test_search_and_delete_use_pinned_filters_and_return_no_raw_fields() -> None:
    metadata = {
        "source": "videobox_yujin_approved_v1",
        "category": "pacing",
        "external_ref": "ext-" + "a" * 64,
    }

    class Provider:
        def __init__(self):
            self.calls = []

        def search(self, query, **kwargs):
            self.calls.append(("search", query, kwargs))
            return [
                {
                    "id": "memory-private",
                    "memory": "빠른 컷을 선호합니다.",
                    "metadata": metadata,
                    "provider_raw": "must-not-leak",
                }
            ]

        def delete(self, memory_id):
            self.calls.append(("delete", memory_id))

    provider = Provider()
    app = create_memory_adapter_app(
        provider=provider,
        service_token="adapter-service-token-with-enough-entropy-456",
    )
    headers = {
        "Authorization": (
            "Bearer adapter-service-token-with-enough-entropy-456"
        )
    }
    with TestClient(app) as client:
        searched = client.post(
            "/internal/memory/search",
            headers=headers,
            json={
                "query": "편집 템포",
                "limit": 3,
                "user_id": "videobox-owner-v1",
                "agent_id": "videobox-yujin-v1",
            },
        )
        deleted = client.post(
            "/internal/memory/delete",
            headers=headers,
            json={
                "memory_ref": "memory-private",
                "external_ref": "ext-" + "a" * 64,
                "allow_absent": False,
                "user_id": "videobox-owner-v1",
                "agent_id": "videobox-yujin-v1",
            },
        )

    assert searched.status_code == 200
    assert "provider_raw" not in searched.text
    assert searched.json()["memories"][0]["memory_ref"] == "memory-private"
    search_calls = [call for call in provider.calls if call[0] == "search"]
    assert search_calls[0][2] == {
        "filters": {
            "AND": [
                {"user_id": "videobox-owner-v1"},
                {
                    "metadata": {
                        "source": "videobox_yujin_approved_v1"
                    }
                },
            ]
        },
        "top_k": 3,
        "rerank": False,
    }
    assert deleted.json() == {"deleted": True}
    assert provider.calls[-1] == ("delete", "memory-private")


def test_delete_reconciles_absent_exact_memory_as_already_deleted() -> None:
    class Provider:
        def __init__(self):
            self.calls = []

        def search(self, query, **kwargs):
            self.calls.append(("search", query, kwargs))
            return []

        def delete(self, memory_id):
            raise AssertionError(
                f"already absent memory must not be deleted again: {memory_id}"
            )

    provider = Provider()
    app = create_memory_adapter_app(
        provider=provider,
        service_token="adapter-service-token-with-enough-entropy-456",
    )
    request = {
        "memory_ref": "memory-private",
        "external_ref": "ext-" + "a" * 64,
        "allow_absent": False,
        "user_id": "videobox-owner-v1",
        "agent_id": "videobox-yujin-v1",
    }
    with TestClient(app) as client:
        first_attempt = client.post(
            "/internal/memory/delete",
            headers={
                "Authorization": (
                    "Bearer adapter-service-token-with-enough-entropy-456"
                )
            },
            json=request,
        )
        response = client.post(
            "/internal/memory/delete",
            headers={
                "Authorization": (
                    "Bearer adapter-service-token-with-enough-entropy-456"
                )
            },
            json={**request, "allow_absent": True},
        )

    assert first_attempt.status_code == 409
    assert first_attempt.json() == {
        "detail": "memory_adapter_ownership_mismatch"
    }
    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert provider.calls == [
        (
            "search",
            request["external_ref"],
            {
                "filters": {
                    "AND": [
                        {"user_id": "videobox-owner-v1"},
                        {
                            "metadata": {
                                "external_ref": request["external_ref"]
                            }
                        },
                    ]
                },
                "top_k": 2,
                "rerank": False,
            },
        ),
        (
            "search",
            request["external_ref"],
            {
                "filters": {
                    "AND": [
                        {"user_id": "videobox-owner-v1"},
                        {
                            "metadata": {
                                "external_ref": request["external_ref"]
                            }
                        },
                    ]
                },
                "top_k": 2,
                "rerank": False,
            },
        ),
    ]


def test_delete_rejects_duplicate_or_mismatched_ownership() -> None:
    metadata = {
        "source": "videobox_yujin_approved_v1",
        "category": "pacing",
        "external_ref": "ext-" + "a" * 64,
    }

    class Provider:
        def __init__(self, rows):
            self.rows = rows
            self.delete_calls = []

        def search(self, *_args, **_kwargs):
            return self.rows

        def delete(self, memory_id):
            self.delete_calls.append(memory_id)

    request = {
        "memory_ref": "memory-private",
        "external_ref": "ext-" + "a" * 64,
        "allow_absent": False,
        "user_id": "videobox-owner-v1",
        "agent_id": "videobox-yujin-v1",
    }
    for rows in (
        [
            {"id": "memory-private", "metadata": metadata},
            {"id": "memory-other", "metadata": metadata},
        ],
        [{"id": "memory-other", "metadata": metadata}],
        [
            {
                "id": "memory-private",
                "metadata": {**metadata, "unexpected": "field"},
            }
        ],
    ):
        provider = Provider(rows)
        app = create_memory_adapter_app(
            provider=provider,
            service_token=(
                "adapter-service-token-with-enough-entropy-456"
            ),
        )
        with TestClient(app) as client:
            response = client.post(
                "/internal/memory/delete",
                headers={
                    "Authorization": (
                        "Bearer "
                        "adapter-service-token-with-enough-entropy-456"
                    )
                },
                json=request,
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "memory_adapter_ownership_mismatch"
        }
        assert provider.delete_calls == []


def test_provider_add_exception_is_ambiguous_not_retryable() -> None:
    class Provider:
        def add(self, **_kwargs):
            raise TimeoutError("response lost after commit")

    app = create_memory_adapter_app(
        provider=Provider(),
        service_token="adapter-service-token-with-enough-entropy-456",
    )
    with TestClient(app) as client:
        response = client.post(
            "/internal/memory/add",
            headers={
                "Authorization": (
                    "Bearer adapter-service-token-with-enough-entropy-456"
                )
            },
            json=_payload(),
        )

    assert response.json() == {
        "status": "ambiguous",
        "memory_ref": None,
        "event_ref": None,
    }


def test_pinned_provider_polls_event_with_bounded_exact_http_contract() -> None:
    calls = []

    class Response:
        status_code = 200
        is_redirect = False
        content = b'{"status":"PENDING"}'

        def json(self):
            return {"status": "PENDING"}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, path):
            calls.append(("get", path))
            return Response()

    provider = object.__new__(_PinnedHermesMem0Provider)
    provider._api_key = "private-api-key"

    def factory(**kwargs):
        calls.append(("factory", kwargs))
        return Client()

    provider._event_http_client_factory = factory

    assert provider.get_event(event_id="event-123") == {
        "status": "PENDING"
    }
    assert calls == [
        (
            "factory",
            {
                "base_url": "https://api.mem0.ai",
                "headers": {
                    "Authorization": "Token private-api-key"
                },
                "timeout": 5.0,
                "trust_env": False,
                "follow_redirects": False,
            },
        ),
        ("get", "/v1/event/event-123/"),
    ]
