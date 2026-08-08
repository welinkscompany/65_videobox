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


_VALID_TOKEN = "adapter-service-token-with-enough-entropy-456"


def test_local_mode_needs_no_api_key_and_stays_on_this_computer() -> None:
    """MEM0_API_KEY 없이 이 컴퓨터 안에서만 기억을 돌리는 길.

    Hermes 의 OSS 백엔드를 쓰면 기억 생성·검색을 로컬 모델과 파일 기반
    벡터 저장소가 처리한다. 밖으로 나가는 것이 하나도 없다.
    """
    captured = {}

    def local_factory(config):
        captured.update(config)
        return object()

    app = build_memory_adapter_from_environment(
        environ={
            "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN": _VALID_TOKEN,
            "MEM0_API_KEY": "",
            "VIDEOBOX_MEM0_MODE": "local",
        },
        local_provider_factory=local_factory,
    )

    with TestClient(app) as client:
        assert client.get("/health").json() == {
            "status": "ready",
            "configured": True,
        }
    # 지연 생성이므로 기동만으로는 아무것도 만들지 않는다.
    assert captured == {}


def test_local_mode_defaults_point_at_this_computer_only() -> None:
    """기본값은 전부 이 컴퓨터를 가리켜야 한다. 외부 주소가 새면 안 된다."""
    from videobox_agent_gateway.hermes_memory_adapter import (
        local_mem0_config_from_environment,
    )

    config = local_mem0_config_from_environment(
        {"VIDEOBOX_MEM0_MODE": "local"}
    )

    assert config["llm"]["provider"] == "openai"
    assert config["embedder"]["provider"] == "openai"
    assert config["vector_store"]["provider"] == "qdrant"
    # 파일 경로 방식이라 벡터 저장소 서버가 필요 없다.
    assert config["vector_store"]["config"]["path"]
    assert "host" not in config["vector_store"]["config"]

    for block in (config["llm"], config["embedder"]):
        base_url = block["config"]["openai_base_url"]
        assert base_url.startswith("http://host.docker.internal:")

    # 임베딩 차원이 틀리면 저장소가 조용히 어긋난다.
    assert config["embedder"]["config"]["embedding_dims"] == 1024


def test_api_key_still_wins_so_an_existing_setup_does_not_change() -> None:
    """호스팅 키가 들어 있으면 그대로 호스팅 경로를 쓴다."""
    picked = []

    app = build_memory_adapter_from_environment(
        environ={
            "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN": _VALID_TOKEN,
            "MEM0_API_KEY": "private-key",
            "VIDEOBOX_MEM0_MODE": "local",
        },
        provider_factory=lambda _key: picked.append("platform"),
        local_provider_factory=lambda _config: picked.append("local"),
    )

    with TestClient(app) as client:
        assert client.get("/health").json()["configured"] is True
    assert picked == []


class _FakeOssBackend:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search(self, query, *, filters, top_k=10, rerank=False):
        self.calls.append(dict(filters=filters, top_k=top_k))
        if not ({"user_id", "agent_id", "run_id"} & set(filters)):
            raise ValueError(
                "filters must contain at least one of: user_id, agent_id, run_id"
            )
        return list(self.rows)


def _local_provider_with(rows):
    from videobox_agent_gateway.hermes_memory_adapter import _LocalMem0Provider

    provider = _LocalMem0Provider.__new__(_LocalMem0Provider)
    backend = _FakeOssBackend(rows)
    provider._backend = backend
    return provider, backend


def test_local_search_translates_the_hosted_filter_shape() -> None:
    """자체 호스팅 Mem0 는 호스팅 쪽 필터 문법을 모른다.

    2026-08-08 실기: {"AND": [...]} 를 그대로 넘기면
    "filters must contain at least one of: user_id, agent_id, run_id" 로
    거절당해 검색이 전부 503 이 됐다.
    """
    approved = {
        "id": "m-1",
        "memory": "저는 빠른 컷 편집을 선호합니다.",
        "metadata": {
            "source": "videobox_yujin_approved_v1",
            "category": "pacing",
            "external_ref": "ext-" + "a" * 64,
        },
    }
    provider, backend = _local_provider_with([approved])

    rows = provider.search(
        "편집 속도",
        filters={
            "AND": [
                {"user_id": "videobox-owner-v1"},
                {"metadata": {"source": "videobox_yujin_approved_v1"}},
            ]
        },
        top_k=5,
        rerank=False,
    )

    assert backend.calls[0]["filters"] == {"user_id": "videobox-owner-v1"}
    assert rows == [approved]


def test_local_search_still_applies_the_metadata_constraint() -> None:
    """소유자 필터만 남기면 승인하지 않은 기억까지 돌아온다.

    벡터 저장소는 소유자 단위로만 걸러 주므로, metadata 조건은 여기서
    다시 적용해야 한다.
    """
    approved = {
        "id": "m-1",
        "memory": "승인된 기억",
        "metadata": {
            "source": "videobox_yujin_approved_v1",
            "category": "pacing",
            "external_ref": "ext-" + "a" * 64,
        },
    }
    other = {
        "id": "m-2",
        "memory": "다른 경로로 들어온 기억",
        "metadata": {"source": "somewhere_else"},
    }
    provider, _ = _local_provider_with([other, approved])

    rows = provider.search(
        "편집 속도",
        filters={
            "AND": [
                {"user_id": "videobox-owner-v1"},
                {"metadata": {"source": "videobox_yujin_approved_v1"}},
            ]
        },
        top_k=5,
        rerank=False,
    )

    assert rows == [approved]


def test_local_search_keeps_the_external_ref_constraint_for_reconcile() -> None:
    """되맞춤은 external_ref 로 정확히 한 건을 찾아야 한다.

    이 조건을 흘리면 엉뚱한 기억을 "이미 저장됨"으로 판정한다.
    """
    wanted_ref = "ext-" + "b" * 64
    wanted = {
        "id": "m-1",
        "memory": "찾는 기억",
        "metadata": {
            "source": "videobox_yujin_approved_v1",
            "category": "pacing",
            "external_ref": wanted_ref,
        },
    }
    sibling = {
        "id": "m-2",
        "memory": "다른 기억",
        "metadata": {
            "source": "videobox_yujin_approved_v1",
            "category": "pacing",
            "external_ref": "ext-" + "c" * 64,
        },
    }
    provider, _ = _local_provider_with([sibling, wanted])

    rows = provider.search(
        "찾는 기억",
        filters={
            "AND": [
                {"user_id": "videobox-owner-v1"},
                {"metadata": {"external_ref": wanted_ref}},
            ]
        },
        top_k=2,
        rerank=False,
    )

    assert rows == [wanted]
