"""밖에서 부를 수 있게 연 문 둘 (owner 결정 2026-09-07).

1. **잡 상태를 한 모양으로** — `GET /api/projects/{id}/jobs/{job_id}`.
   이 문이 없어서 상태를 묻는 주소가 열세 가지로 갈라져 있었다.
2. **경로로 자료실에 넣기** — `POST /api/library/ingest-path`.
   바이트를 다시 올리지 않게 하려는 것이다.

두 문이 지켜야 할 것은 같다: **실패가 조용한 0이 아니라 이유가 있는 오류로
나가야 한다.** "결과 없음"과 "못 읽었음"이 같은 응답이면 그건 결함이다
(`docs/videobox-mcp-scope.ko.md` §7).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_api.routers.library_assets import _inside_any
from videobox_domain_models.jobs import JobStatus, JobType


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # 드롭 폴더를 시험이 쥔 자리로 옮긴다 -- 안 그러면 이 컴퓨터의 진짜
    # OneDrive 폴더가 받아 줄 폴더가 된다.
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", str(tmp_path / "drop"))
    (tmp_path / "drop").mkdir(parents=True, exist_ok=True)
    return TestClient(create_app(projects_root=tmp_path / "data"))


def _project(client: TestClient) -> str:
    return client.post("/api/projects", json={"name": "잡"}).json()["project_id"]


def _job(client: TestClient, project_id: str, job_type: JobType) -> str:
    """잡 행을 직접 만든다.

    **파이프라인을 실제로 돌려서 만들지 않는다.** 처음엔 전사를 시작해서 만들려
    했는데 자산이 없으면 시작이 거절돼 시험이 통째로 skip 됐다 -- skip은 초록이
    아니라 **안 돈 것**이고, 이 저장소가 이미 그것으로 데였다
    (`docs/...green-tests-were-not-guarding`). 여기서 재려는 것은 파이프라인이
    아니라 **문 하나**이므로, 행을 만들고 문을 밟는다.
    """

    store = client.app.state.store
    return str(
        store.create_job(project_id=project_id, job_type=job_type, status=JobStatus.RUNNING)["job_id"]
    )


# --------------------------------------------------------------------------
# 1. 잡 상태를 한 모양으로
# --------------------------------------------------------------------------


def test_one_door_answers_for_a_job_whatever_kind_it_is(client: TestClient) -> None:
    """**이 문이 있는 이유다.** 전사든 타임라인이든 완성본이든, 상태를 물을 때는
    같은 주소·같은 모양이어야 한다. 열세 가지를 부르는 쪽이 외우게 하지 않는다."""

    project_id = _project(client)
    # 종류가 달라도 답이 같은 모양이어야 한다 -- 그게 이 문의 전부다.
    for job_type in (JobType.TRANSCRIPTION, JobType.TIMELINE_BUILD, JobType.FINAL_RENDER):
        job_id = _job(client, project_id, job_type)
        reply = client.get(f"/api/projects/{project_id}/jobs/{job_id}")
        assert reply.status_code == 200, reply.text
        body = reply.json()
        assert body["job_id"] == job_id
        assert body["project_id"] == project_id
        assert body["job_type"] == job_type.value
        assert body["status"] == JobStatus.RUNNING.value
        # 부르는 쪽이 종류마다 다른 열쇠를 찾지 않아도 되게, 같은 이름으로 나온다.
        for field in ("progress_percent", "error_message", "started_at", "finished_at"):
            assert field in body, f"`{field}`가 빠지면 부르는 쪽이 종류별로 다시 물어야 한다"


def test_a_job_that_is_not_there_says_so_instead_of_answering_emptily(
    client: TestClient,
) -> None:
    """**조용한 0이 아니라 이유가 있는 오류.** 빈 몸통을 200으로 내면 부르는 쪽은
    "아직 안 끝났다"로 읽고 영원히 기다린다."""

    project_id = _project(client)
    reply = client.get(f"/api/projects/{project_id}/jobs/없는잡")
    assert reply.status_code == 404
    assert reply.json()["detail"] == "job_not_found"


def test_a_job_of_another_project_is_not_visible(client: TestClient) -> None:
    """잡 id는 프로젝트 안에서만 유일하다(`transcription_job_001` 꼴).
    프로젝트를 안 보고 답하면 남의 잡을 남의 이름으로 답하게 된다."""

    first = _project(client)
    second = _project(client)
    job_id = _job(client, first, JobType.TRANSCRIPTION)
    assert client.get(f"/api/projects/{first}/jobs/{job_id}").status_code == 200
    assert client.get(f"/api/projects/{second}/jobs/{job_id}").status_code == 404


# --------------------------------------------------------------------------
# 2. 경로로 자료실에 넣기
# --------------------------------------------------------------------------


def _png(path: Path) -> Path:
    # 1x1 PNG. 실제 바이트여야 한다 -- 자료실이 내용 해시로 중복을 가린다.
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return path


def test_a_file_already_on_disk_goes_in_without_uploading_it_again(
    client: TestClient, tmp_path: Path
) -> None:
    """**이 문이 있는 이유다.** 밖에서 부르는 쪽이 그림을 만들어 함께 보는 폴더에
    두고 경로만 넘긴다. 바이트를 다시 올리게 하면 그쪽이 피하려던 바로 그것이다."""

    source = _png(tmp_path / "drop" / "만든그림.png")
    reply = client.post(
        "/api/library/ingest-path",
        json={
            "media_type": "image",
            "source_path": str(source),
            "idempotency_key": "outside:1",
            "provenance": {"made_by": "바깥"},
        },
    )
    assert reply.status_code == 201, reply.text
    body = reply.json()
    assert body["library_asset_id"]
    assert body["media_type"] == "image"
    # 원본은 그 자리에 그대로 있어야 한다 -- 옮기거나 지우지 않는다.
    assert source.is_file()


def test_the_same_file_twice_is_the_same_asset(client: TestClient, tmp_path: Path) -> None:
    """재시도가 매번 새 자산을 만들면 자료실이 같은 그림으로 찬다."""

    source = _png(tmp_path / "drop" / "같은그림.png")
    body = {"media_type": "image", "source_path": str(source), "idempotency_key": "outside:2"}
    first = client.post("/api/library/ingest-path", json=body).json()
    second = client.post("/api/library/ingest-path", json=body).json()
    assert first["library_asset_id"] == second["library_asset_id"]


def test_a_path_the_container_cannot_see_is_told_apart_from_a_missing_file(
    client: TestClient, tmp_path: Path
) -> None:
    """**이 구분이 이 문에서 제일 중요하다.** 둘을 같은 오류로 내면 부르는 쪽이
    파일을 다시 만들며 헛돈다 -- 파일은 멀쩡히 있고, 컨테이너가 그 이름을 모를
    뿐이다."""

    outside = _png(tmp_path / "밖에있는그림.png")  # 드롭 폴더 **밖**
    reply = client.post(
        "/api/library/ingest-path",
        json={"media_type": "image", "source_path": str(outside), "idempotency_key": "outside:3"},
    )
    assert reply.status_code == 403
    detail = reply.json()["detail"]
    assert detail["reason"] == "source_path_not_visible"
    # 어디에 두면 되는지 같이 말해 준다 -- 안 그러면 어디에 둘지 알 수가 없다.
    assert detail["visible_roots"], "볼 수 있는 폴더를 안 알려 주면 고칠 방법이 없다"


def test_a_missing_file_inside_the_visible_folder_is_a_missing_file(
    client: TestClient, tmp_path: Path
) -> None:
    reply = client.post(
        "/api/library/ingest-path",
        json={
            "media_type": "image",
            "source_path": str(tmp_path / "drop" / "없는그림.png"),
            "idempotency_key": "outside:4",
        },
    )
    assert reply.status_code == 404
    assert reply.json()["detail"] == "source_path_not_found"


def test_a_folder_is_not_a_file(client: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "drop" / "폴더"
    folder.mkdir()
    reply = client.post(
        "/api/library/ingest-path",
        json={"media_type": "image", "source_path": str(folder), "idempotency_key": "outside:5"},
    )
    assert reply.status_code == 422
    assert reply.json()["detail"] == "source_path_not_a_file"


def test_an_unknown_media_type_is_refused(client: TestClient, tmp_path: Path) -> None:
    source = _png(tmp_path / "drop" / "종류.png")
    reply = client.post(
        "/api/library/ingest-path",
        json={"media_type": "없는종류", "source_path": str(source), "idempotency_key": "outside:6"},
    )
    assert reply.status_code == 422
    assert reply.json()["detail"] == "media_type_invalid"


def test_with_no_visible_folder_configured_nothing_is_accepted(tmp_path: Path) -> None:
    """**설정이 빠지면 닫힌 채로 있어야 한다.**

    캡컷 다리의 같은 도우미는 폴더를 안 주면 **전부 받는다** -- 이 컴퓨터에서
    손으로 켜는 서비스라 그 기본값이 맞다. 여기는 밖에서 부르는 문이라 반대여야
    한다. 배선 한 줄이 빠졌을 때 조용히 전부 열리면, 자료실이 임의 파일 읽기
    창구가 된다.

    라우터를 통째로 세우지 않고 도우미를 직접 부르는 것은, 배선이 비는 상황을
    `create_app`으로는 못 만들기 때문이다 -- 그래도 재려는 그 한 줄은 그대로 밟는다.
    """

    somewhere = tmp_path / "아무데나.png"
    somewhere.write_bytes(b"x")
    assert _inside_any(somewhere, ()) is False
    assert _inside_any(somewhere, (tmp_path,)) is True


def test_an_idempotency_key_is_required(client: TestClient, tmp_path: Path) -> None:
    """multipart 쪽은 열쇠가 없으면 만들어 준다(사람이 화면에서 끌어다 놓는
    자리라 그렇다). **여기는 기계가 부르는 문이라 필수다** -- 없으면 재시도가
    매번 새 자산을 만든다."""

    source = _png(tmp_path / "drop" / "열쇠없음.png")
    reply = client.post(
        "/api/library/ingest-path",
        json={"media_type": "image", "source_path": str(source)},
    )
    assert reply.status_code == 422
