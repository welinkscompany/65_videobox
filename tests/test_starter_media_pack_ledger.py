"""스타터 미디어팩 원장의 저작자 상속이 표 경계를 넘지 않는지 지킨다.

`sfx-rpg-door`·`sfx-rpg-grass`·`sfx-rpg-steps` 셋이 `Delta12 Studio /
RPG Sound Effect Pack`이어야 하는데, 2026-09-06에 RPG 표의 앞 줄들을
지우면서 `sfx-rpg-door`가 `same page/hash`로 그 위 표(`sfx-pop10`,
`cogitollc / pop-sounds`)를 물려받게 됐다. 원장의 `same page/hash`는
표 경계를 안 가리고 문서 순서로 물려받으므로, 어떤 표든 첫 줄을 지우면
이 사고가 재발한다 -- `docs/handoffs/2026-09-07-full-audit-docs-tests-boundaries.ko.md`
§1-2.
"""

from __future__ import annotations

from pathlib import Path
import sys

SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

LEDGER = Path(__file__).resolve().parents[1] / "docs" / "starter-media-pack-license-research.ko.md"


def test_rpg_sfx_inherit_delta12_not_pop_sounds() -> None:
    from build_starter_media_pack import load_approved_candidates

    candidates = {candidate.asset_id: candidate for candidate in load_approved_candidates(LEDGER)}

    for asset_id in ("sfx-rpg-door", "sfx-rpg-grass", "sfx-rpg-steps"):
        candidate = candidates[asset_id]
        assert candidate.creator == "Delta12 Studio", asset_id
        assert "rpg-sound-effect-pack" in candidate.official_url, asset_id
        # cogitollc / pop-sounds(위 표)를 물려받으면 안 된다.
        assert "pop-sounds" not in candidate.official_url, asset_id
