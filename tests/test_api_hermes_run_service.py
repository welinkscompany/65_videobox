

def test_limits_fit_a_token_streaming_local_model() -> None:
    """로컬 모델은 글자 단위로 흘려보낸다.

    2026-08-08 실기: 실제 유진 대화가 매번 정확히 256번째 이벤트에서 잘렸다.
    분량 자체는 max_text_bytes 가 따로 막으므로 이벤트 개수 상한만 올린다.
    """
    import inspect

    from videobox_api.hermes_run_service import HermesRunService

    defaults = inspect.signature(HermesRunService.__init__).parameters
    assert defaults["max_events"].default >= 4096
    # 게이트웨이가 한 대화에 최대 300초를 쓴다. 이쪽이 더 짧으면 먼저 끊는다.
    assert defaults["timeout_seconds"].default >= 300.0
