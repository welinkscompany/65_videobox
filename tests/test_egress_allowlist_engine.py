"""Hermes egress 허용목록 판정 로직. 실제 소켓은 안 쓴다(Phase 2에서 붙인다).

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §2 Phase 1.
"""

from __future__ import annotations

from videobox_egress_gateway.allowlist import EgressAllowlist


def _allowlist() -> EgressAllowlist:
    return EgressAllowlist(entries={
        "oauth_bootstrap": frozenset({"auth.example-provider.test"}),
        "provider_runtime": frozenset({"api.example-provider.test"}),
    })


def test_exact_match_is_allowed() -> None:
    allowlist = _allowlist()
    assert allowlist.is_allowed(scope="provider_runtime", hostname="api.example-provider.test") is True


def test_unlisted_host_is_denied() -> None:
    allowlist = _allowlist()
    assert allowlist.is_allowed(scope="provider_runtime", hostname="evil.test") is False


def test_a_listed_host_under_the_wrong_scope_is_denied() -> None:
    """부트스트랩 전용 호스트를 런타임 scope로 물으면 거부돼야 한다."""
    allowlist = _allowlist()
    assert allowlist.is_allowed(scope="provider_runtime", hostname="auth.example-provider.test") is False


def test_a_subdomain_of_an_allowed_host_is_allowed() -> None:
    allowlist = _allowlist()
    assert allowlist.is_allowed(scope="provider_runtime", hostname="edge.api.example-provider.test") is True


def test_a_suffix_abuse_attempt_is_not_fooled() -> None:
    """`api.example-provider.test.attacker.test`는 허용 호스트를 '포함'하지만
    실제로는 공격자 도메인이다 -- 접미사가 아니라 전체 라벨 경계로 판단해야 한다."""
    allowlist = _allowlist()
    assert allowlist.is_allowed(
        scope="provider_runtime", hostname="api.example-provider.test.attacker.test"
    ) is False


def test_a_lookalike_host_that_merely_contains_the_allowed_name_is_denied() -> None:
    allowlist = _allowlist()
    assert allowlist.is_allowed(
        scope="provider_runtime", hostname="notapi.example-provider.test"
    ) is False


def test_matching_is_case_insensitive() -> None:
    allowlist = _allowlist()
    assert allowlist.is_allowed(scope="provider_runtime", hostname="API.EXAMPLE-PROVIDER.TEST") is True


def test_non_ascii_lookalike_hostname_is_denied_not_normalized_into_a_match() -> None:
    allowlist = _allowlist()
    # 유니코드 동형 문자(다른 'a'처럼 보이는 키릴 문자 등)를 흉내낸 예시.
    assert allowlist.is_allowed(scope="provider_runtime", hostname="аpi.example-provider.test") is False


def test_blank_or_malformed_hostname_is_denied_not_an_exception() -> None:
    allowlist = _allowlist()
    assert allowlist.is_allowed(scope="provider_runtime", hostname="") is False
    assert allowlist.is_allowed(scope="provider_runtime", hostname="   ") is False
    assert allowlist.is_allowed(scope="provider_runtime", hostname=".api.example-provider.test") is False


def test_an_unknown_scope_is_denied_by_default() -> None:
    allowlist = _allowlist()
    assert allowlist.is_allowed(scope="some_new_scope", hostname="api.example-provider.test") is False


def test_an_empty_allowlist_denies_everything() -> None:
    allowlist = EgressAllowlist()
    assert allowlist.is_allowed(scope="provider_runtime", hostname="api.example-provider.test") is False
