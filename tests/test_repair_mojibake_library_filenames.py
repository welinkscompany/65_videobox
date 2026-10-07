"""깨진 자료실 이름 일괄 복구 (2026-10-02, 점검 후속 A4).

소켓은 안 연다(`tests/conftest.py`). `send`(메서드, 경로, 본문 → 답)를 손으로 준다.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "repair_mojibake_library_filenames.py"
_spec = importlib.util.spec_from_file_location("videobox_repair_mojibake_under_test", _PATH)
assert _spec is not None and _spec.loader is not None
repair = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(repair)


@pytest.mark.parametrize(
    ("broken", "fixed"),
    [
        ("\xb3\xec\xc0\xbd 2026-02-07 163617.mp4", "녹음 2026-02-07 163617.mp4"),
        ("\xc8\xad\xb8\xe9 \xb3\xec\xc8\xad \xc1\xdf 2025-07-24 233828.mp4", "화면 녹화 중 2025-07-24 233828.mp4"),
        ("\xbf\xcf\xbc\xba\xba\xbb.mp4", "완성본.mp4"),
    ],
)
def test_names_read_as_latin1_come_back_as_korean(broken: str, fixed: str) -> None:
    assert repair.repaired_name(broken) == fixed


@pytest.mark.parametrize(
    "name",
    [
        "walk.mp4",            # 고칠 것이 없다
        "녹음 2026-02-07.mp4",  # 이미 한국어다
        "café.mp3",            # 진짜 라틴 문자. cp949로 안 풀린다
        "naïve résumé.wav",    # 진짜 라틴 문자
        "\xa1\xa1.mp4",        # 풀리지만(전각 공백) 한글이 안 나온다
    ],
)
def test_names_that_are_not_broken_korean_are_left_alone(name: str) -> None:
    assert repair.repaired_name(name) is None


class _FakeApi:
    def __init__(self, assets_by_type: dict[str, list[dict]], *, total_bonus: int = 0, fail_ids: set[str] | None = None) -> None:
        self.assets_by_type = assets_by_type
        self.total_bonus = total_bonus
        self.fail_ids = fail_ids or set()
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, path: str, body: dict | None) -> dict:
        self.calls.append((method, path, body))
        if method == "GET":
            media_type = path.split("media_type=")[1].split("&")[0]
            assets = self.assets_by_type.get(media_type, [])
            return {"assets": assets, "total": len(assets) + self.total_bonus}
        asset_id = path.split("/api/library/assets/")[1].split("/")[0]
        if asset_id in self.fail_ids:
            raise OSError("connection reset")
        return {"asset": {"library_asset_id": asset_id, "user_metadata": {"filename": body["filename"]}}}


def _asset(asset_id: str, name: str, origin: str = "user") -> dict:
    return {"library_asset_id": asset_id, "origin": origin, "user_metadata": {"filename": name}}


BROKEN = "\xb3\xec\xc0\xbd 2026-02-07 163617.mp4"


def test_the_plan_lists_only_own_broken_names_across_every_kind() -> None:
    api = _FakeApi({
        "broll": [_asset("user_1", BROKEN), _asset("user_2", "walk.mp4"), _asset("pack:1", BROKEN, origin="builtin")],
        "music": [_asset("user_3", "café.mp3")],
    })
    plans = repair.plan_repairs(api)
    assert plans == [{"library_asset_id": "user_1", "media_type": "broll", "before": BROKEN, "after": "녹음 2026-02-07 163617.mp4"}]
    assert [path for method, path, _ in api.calls if method == "GET"] == [
        f"/api/library/assets?media_type={kind}&include_trashed=true&limit=500" for kind in ("broll", "image", "music", "sfx")
    ]


def test_the_plan_stops_when_one_page_cannot_hold_everything() -> None:
    with pytest.raises(SystemExit):
        repair.plan_repairs(_FakeApi({"broll": [_asset("user_1", BROKEN)]}, total_bonus=1))


def test_a_dry_run_changes_nothing(tmp_path: Path, capsys) -> None:
    api = _FakeApi({"broll": [_asset("user_1", BROKEN)]})
    assert repair.main(["--revert-file", str(tmp_path / "r.json")], send=api) == 0
    assert all(method == "GET" for method, _, _ in api.calls)
    assert not (tmp_path / "r.json").exists()
    assert "고칠 이름 1개" in capsys.readouterr().out


def test_apply_writes_the_revert_list_before_renaming(tmp_path: Path) -> None:
    revert = tmp_path / "revert.json"
    seen_on_first_patch: list[bool] = []
    api = _FakeApi({"broll": [_asset("user_1", BROKEN)]})

    def send(method: str, path: str, body: dict | None) -> dict:
        if method == "PATCH" and not seen_on_first_patch:
            seen_on_first_patch.append(revert.exists())
        return api(method, path, body)

    code = repair.main(["--apply", "--revert-file", str(revert)], send=send, now=datetime(2026, 10, 2, tzinfo=timezone.utc))

    assert code == 0
    assert seen_on_first_patch == [True]
    saved = json.loads(revert.read_text(encoding="utf-8"))
    assert saved["renamed"] == [{"library_asset_id": "user_1", "media_type": "broll", "before": BROKEN, "after": "녹음 2026-02-07 163617.mp4"}]
    assert ("PATCH", "/api/library/assets/user_1/filename", {"filename": "녹음 2026-02-07 163617.mp4"}) in api.calls


def test_one_failure_does_not_hide_the_others_and_the_exit_code_says_so(tmp_path: Path, capsys) -> None:
    api = _FakeApi({"broll": [_asset("user_1", BROKEN), _asset("user_2", BROKEN)]}, fail_ids={"user_1"})
    code = repair.main(["--apply", "--revert-file", str(tmp_path / "r.json")], send=api)
    assert code == 1
    assert ("PATCH", "/api/library/assets/user_2/filename", {"filename": "녹음 2026-02-07 163617.mp4"}) in api.calls
    assert "user_1" in capsys.readouterr().out


def test_a_second_apply_after_success_does_nothing(tmp_path: Path) -> None:
    """다시 돌려도 안전해야 한다. 이미 고친 이름은 계획에 안 들고, 되돌릴 목록도 새로 안 쓴다."""
    api = _FakeApi({"broll": [_asset("user_1", "녹음 2026-02-07 163617.mp4")]})
    assert repair.main(["--apply", "--revert-file", str(tmp_path / "again.json")], send=api) == 0
    assert all(method == "GET" for method, _, _ in api.calls)
    assert not (tmp_path / "again.json").exists()


def test_an_existing_revert_list_is_never_overwritten(tmp_path: Path) -> None:
    revert = tmp_path / "revert.json"
    revert.write_text('{"renamed": [{"library_asset_id": "user_0", "before": "원본"}]}', encoding="utf-8")
    api = _FakeApi({"broll": [_asset("user_1", BROKEN)]})
    assert repair.main(["--apply", "--revert-file", str(revert)], send=api) == 2
    assert all(method == "GET" for method, _, _ in api.calls)
    assert "user_0" in revert.read_text(encoding="utf-8")


def test_undo_puts_the_old_names_back(tmp_path: Path) -> None:
    revert = tmp_path / "revert.json"
    revert.write_text(json.dumps({"renamed": [{"library_asset_id": "user_1", "media_type": "broll", "before": BROKEN, "after": "녹음.mp4"}]}, ensure_ascii=False), encoding="utf-8")
    api = _FakeApi({})
    assert repair.main(["--undo", str(revert)], send=api) == 0
    assert api.calls == [("PATCH", "/api/library/assets/user_1/filename", {"filename": BROKEN})]


@pytest.mark.parametrize("content", ["not json", '{"other": 1}', '{"renamed": [1]}'])
def test_undo_with_a_bad_file_exits_cleanly(tmp_path: Path, content: str, capsys) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(content, encoding="utf-8")
    api = _FakeApi({})
    assert repair.main(["--undo", str(bad)], send=api) == 2
    assert repair.main(["--undo", str(tmp_path / "missing.json")], send=api) == 2
    assert api.calls == []
