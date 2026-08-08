"""B-roll analysis has to reach LM Studio from inside the container too.

`settings.py` was widened for the chat route on 2026-08-08 (owner approved,
`docs/development-fast-path.ko.md` §10.14 clause 2-B), but the vision and
embedding transport carries its own pin to `127.0.0.1:1234`. Inside the
container that address is the container, so B-roll analysis could never reach
a model there -- the same defect, one layer over.
"""

from __future__ import annotations

import pytest

from videobox_provider_interfaces.lm_studio import (
    LMStudioHTTPTransport,
    LMStudioProviderError,
)

CONTAINER_BASE = "http://host.docker.internal:1234/v1"


def test_transport_accepts_the_docker_host_endpoint() -> None:
    transport = LMStudioHTTPTransport(base_url=CONTAINER_BASE)

    # The native inventory must follow the same host; sending it to loopback
    # from inside a container would silently talk to nothing.
    assert transport._native_models_endpoint() == (
        "http://host.docker.internal:1234/api/v1/models"
    )


def test_loopback_stays_the_default_and_still_works() -> None:
    transport = LMStudioHTTPTransport()

    assert transport.base_url == "http://127.0.0.1:1234/v1"
    assert transport._native_models_endpoint() == (
        "http://127.0.0.1:1234/api/v1/models"
    )


@pytest.mark.parametrize(
    "rejected",
    [
        "http://example.test/v1",
        "https://host.docker.internal:1234/v1",
        "http://host.docker.internal:8080/v1",
        "http://host.docker.internal:1234/v2",
        "http://host.docker.internal:1234/v1?token=unexpected",
        "http://evil.host.docker.internal:1234/v1",
    ],
)
def test_transport_still_refuses_everything_off_this_machine(rejected: str) -> None:
    transport = LMStudioHTTPTransport(base_url=rejected)

    with pytest.raises(LMStudioProviderError):
        transport._native_models_endpoint()
