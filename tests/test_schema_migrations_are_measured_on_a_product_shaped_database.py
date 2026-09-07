"""스키마를 부수며 바꾸는 이관에는 **제품과 같은 방식으로 세운 DB**로 재는 시험이 붙어야 한다.

2026-08-20에 라이브러리 이관이 배포본에서 촬영본 트리거를 깨뜨렸다. 라이브러리에
그림뿐 아니라 영상·음악까지 **아무것도** 넣을 수 없게 됐다. 이관이 매번 실패하고
롤백해서 연결을 여는 모든 호출이 함께 죽었기 때문이다.

시험은 초록이었다. 시험용 DB를 `sqlite3.connect`로 새로 만들어 세웠는데, 그
DB에는 촬영본 트리거가 없었다. **제품에서는 한 sqlite 파일을 여러 저장소가
나눠 쓴다.** 그 조건이 재현되지 않으면 이관은 재지 않은 것이나 같다.

## 이 장치가 하는 일

부수는 DDL(`DROP TABLE`·`RENAME TO`·`DROP COLUMN`·`RENAME COLUMN`)을 쓰는 함수를
저장소 코드에서 전부 찾아, 아래 표에 그 함수를 재는 시험이 적혀 있는지 본다.
새 이관이 표 없이 들어오면 이 시험이 깨진다. 표에 적은 시험은 실제로 존재해야
하고, DB를 저장소 클래스로 세워야 한다.

## 이 장치가 **못** 하는 일 — 솔직히 적어 둔다

적어 낸 시험이 정말 옛 모양을 재현하는지까지는 기계가 못 본다. 저장소 클래스로
세우는지만 본다. 그 판단은 사람 몫이고, 규정은
`docs/development-fast-path.ko.md` §10.17에 있다. 이 표는 그 판단을 **하게
만드는 정지선**이지, 판단을 대신하는 장치가 아니다.
"""

from __future__ import annotations

import ast
import re
import warnings
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCANNED_TREES = ("packages", "services")

# 표를 다시 쓰지 않고는 넘어갈 수 없는 DDL. 표가 살아 있는 채로 열이 늘어나는
# `ADD COLUMN` 은 여기 없다 -- 남의 트리거를 끊지 않기 때문이다.
DESTRUCTIVE_DDL = ("DROP TABLE", "RENAME TO", "DROP COLUMN", "RENAME COLUMN")

# 시험이 DB를 제품처럼 세웠다는 표시. 저장소 클래스를 통해 열어야 그 파일을
# 함께 쓰는 다른 저장소의 표·트리거가 같이 생긴다.
_BUILDS_THROUGH_A_STORE = re.compile(r"\b[A-Z]\w*Store\(")


@dataclass(frozen=True, slots=True)
class MeasuredMigration:
    """이관 하나와, 그것을 제품 모양 DB에서 재는 시험."""

    product_shaped_test: str
    """`<파일>::<시험 이름>`."""
    why: str
    """무엇을 부수며 바꾸는가. 다음 사람이 표를 읽고 판단할 수 있게."""


# ---------------------------------------------------------------------------
# 부수는 이관과 그것을 재는 시험. **여기 한 곳에만** 적는다.
# ---------------------------------------------------------------------------
MEASURED_MIGRATIONS: dict[tuple[str, str], MeasuredMigration] = {
    (
        "packages/storage-abstractions/src/videobox_storage/library_user_asset_store.py",
        "_widen_media_type_check",
    ): MeasuredMigration(
        product_shaped_test=(
            "tests/test_library_image_assets.py"
            "::test_an_owner_library_with_footage_triggers_can_still_widen_to_images"
        ),
        why=(
            "`library_user_assets` 를 통째로 다시 만들어 그림을 받아들이게 넓힌다."
            " 같은 파일을 쓰는 촬영본 저장소의 트리거 열 개가 이 표를 이름으로 참조한다."
        ),
    ),
    (
        "packages/storage-abstractions/src/videobox_storage/_store_hermes_capability.py",
        "_ensure_hermes_capability_lifecycle_schema",
    ): MeasuredMigration(
        product_shaped_test=(
            "tests/test_hermes_yujin_capability_lifecycle.py"
            "::test_sqlite_hermes_capability_migrates_pre_c3_rows_as_non_authorizing_tombstones"
        ),
        why="`hermes_capability_ledger` 를 다시 만들어 옛 줄을 권한 없는 흔적으로 옮긴다.",
    ),
    (
        "packages/storage-abstractions/src/videobox_storage/local_project_store.py",
        "_bootstrap_database",
    ): MeasuredMigration(
        product_shaped_test=(
            "tests/test_provider_retirement_contract.py"
            "::test_project_schema_has_no_retired_credential_table"
        ),
        why="새 프로젝트에 물러난 credential 표가 남지 않게 지운다.",
    ),
    (
        "packages/storage-abstractions/src/videobox_storage/local_project_store.py",
        "_connection",
    ): MeasuredMigration(
        product_shaped_test=(
            "tests/test_provider_retirement_contract.py"
            "::test_reopening_legacy_project_erases_retired_credential_table"
        ),
        why="옛 프로젝트를 다시 열 때 물러난 credential 표를 지운다.",
    ),
}


def _string_literals(node: ast.AST) -> str:
    return " ".join(
        item.value.upper()
        for item in ast.walk(node)
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    )


def _functions_using_destructive_ddl() -> dict[tuple[str, str], list[str]]:
    found: dict[tuple[str, str], list[str]] = {}
    for tree in SCANNED_TREES:
        for path in (ROOT / tree).rglob("*.py"):
            if "tests" in path.parts or "node_modules" in path.parts:
                continue
            try:
                # 훑기가 남의 파일 경고까지 끌고 오면 이 시험의 출력이 지저분해진다.
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", SyntaxWarning)
                    module = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - 파싱 못 하는 파일은 다른 시험이 잡는다
                continue
            relative = path.relative_to(ROOT).as_posix()
            for node in ast.walk(module):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                literals = _string_literals(node)
                marks = [mark for mark in DESTRUCTIVE_DDL if mark in literals]
                if marks:
                    found[(relative, node.name)] = marks
    return found


def _test_function_source(node_id: str) -> str | None:
    file_part, _, name = node_id.partition("::")
    path = ROOT / file_part
    if not path.is_file():
        return None
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node)
    return None


def test_the_scan_still_finds_the_migrations_we_know_about() -> None:
    """그물이 찢어졌는지부터 본다. 아무것도 못 찾으면 이 파일은 지키는 게 없다."""
    assert _functions_using_destructive_ddl() != {}


def test_every_destructive_migration_is_listed_with_the_test_that_measures_it() -> None:
    found = _functions_using_destructive_ddl()
    unlisted = sorted(key for key in found if key not in MEASURED_MIGRATIONS)

    assert unlisted == [], (
        "표를 부수며 바꾸는데 재는 시험이 적혀 있지 않다:"
        f" {[(path, name, found[(path, name)]) for path, name in unlisted]}."
        " 빈 DB가 아니라 **저장소 클래스로 세운** DB에서 재는 시험을 먼저 쓰고,"
        " 이 파일의 `MEASURED_MIGRATIONS` 에 그 시험을 적어라."
        " 제품에서는 한 sqlite 파일을 여러 저장소가 나눠 쓴다 -- 새로 만든 시험용"
        " DB는 그 조건을 재현하지 않는다."
    )


def test_the_list_does_not_keep_migrations_that_are_gone() -> None:
    found = _functions_using_destructive_ddl()
    stale = sorted(key for key in MEASURED_MIGRATIONS if key not in found)

    assert stale == [], f"이제 없는 이관을 적어 두고 있다: {stale}"


def test_every_listed_test_exists_and_builds_the_database_the_way_the_product_does() -> None:
    missing: list[str] = []
    shallow: list[str] = []
    for (path, name), entry in MEASURED_MIGRATIONS.items():
        source = _test_function_source(entry.product_shaped_test)
        if source is None:
            missing.append(f"{path}::{name} -> {entry.product_shaped_test}")
        elif not _BUILDS_THROUGH_A_STORE.search(source):
            shallow.append(f"{path}::{name} -> {entry.product_shaped_test}")

    assert missing == [], f"적어 둔 시험이 없다: {missing}"
    assert shallow == [], (
        f"적어 둔 시험이 저장소 클래스로 DB를 세우지 않는다: {shallow}."
        " 빈 파일에 `sqlite3.connect` 로 표만 만들면 다른 저장소의 트리거가 없어서"
        " 제품에서 깨지는 이관이 초록으로 지나간다."
    )


def test_every_entry_says_what_it_breaks() -> None:
    assert all(len(entry.why.strip()) > 20 for entry in MEASURED_MIGRATIONS.values())
