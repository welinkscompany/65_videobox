

def test_a_timeout_is_classified_separately_from_a_hard_block() -> None:
    """Task 29: the transport collapsed every transport-level failure into
    'blocked', which the analysis worker treats as terminal. A timeout is
    transient -- LM Studio was busy -- and must stay distinguishable so it can
    be retried instead of stranding the asset."""
    from videobox_provider_interfaces.lm_studio import LMStudioHTTPTransport, LMStudioProviderError

    def timing_out(_request, **_kwargs):
        raise TimeoutError("timed out")

    transport = LMStudioHTTPTransport(http_client=timing_out)
    try:
        transport.request_json("/chat/completions", {"model": "m"}, timeout_seconds=1)
    except LMStudioProviderError as exc:
        assert exc.code == "timeout", exc.code
    else:
        raise AssertionError("a timeout must raise LMStudioProviderError")


def test_a_connection_failure_still_reports_blocked() -> None:
    from urllib.error import URLError

    from videobox_provider_interfaces.lm_studio import LMStudioHTTPTransport, LMStudioProviderError

    def refused(_request, **_kwargs):
        raise URLError("connection refused")

    transport = LMStudioHTTPTransport(http_client=refused)
    try:
        transport.request_json("/chat/completions", {"model": "m"}, timeout_seconds=1)
    except LMStudioProviderError as exc:
        assert exc.code == "blocked", exc.code
    else:
        raise AssertionError("a refused connection must raise LMStudioProviderError")
