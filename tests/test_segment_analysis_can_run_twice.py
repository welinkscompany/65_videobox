"""대본을 고치고 다시 분석하면 500이 났다 — 실측 2026-09-06.

```
duplicate key value violates unique constraint "segments_pkey"
DETAIL:  Key (project_id, segment_id)=(5-089c45a5, seg_001) already exists.
```

장면 id는 매번 `seg_001`부터 다시 세는데(`script_scene_planner`) 저장은 순수
`INSERT`였다. **재분석을 막으려던 것이 아니다** -- 파일 산출물 쪽은 오히려
재실행을 전제한다(`segment_analysis_002.json`처럼 실행마다 새 파일을 만든다).
run은 여러 번 도는 설계인데 segment 행만 단일 실행을 가정하고 있었다.

**덮어쓰고, 이번 분석에 없는 옛 장면은 지운다.** 대본을 고쳐 장면이 다섯 개에서
셋으로 줄면 `seg_004`·`seg_005`가 남아 다음 타임라인에 옛 대사가 섞인다.
"""

from __future__ import annotations

from pathlib import Path

from videobox_storage.local_project_store import LocalProjectStore


def _analysis(*texts: str) -> list[dict[str, object]]:
    return [
        {
            "segment_id": f"seg_{index + 1:03d}",
            "text": text,
            "start_sec": float(index * 2),
            "end_sec": float(index * 2 + 2),
        }
        for index, text in enumerate(texts)
    ]


def test_analysing_the_same_project_twice_does_not_explode(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("재분석")

    store.save_segment_analysis(transcript_id="t1", script_asset_id="s1", project_id=project.project_id, segments=_analysis("첫 문장", "둘째 문장"))
    store.save_segment_analysis(transcript_id="t1", script_asset_id="s1", project_id=project.project_id, segments=_analysis("고친 첫 문장", "둘째 문장"))

    segments = {str(item["segment_id"]): str(item.get("text") or "") for item in store.list_segments(project_id=project.project_id)}
    assert segments["seg_001"] == "고친 첫 문장", "덮어쓰지 않았다"


def test_a_shorter_script_leaves_no_stale_scenes(tmp_path: Path) -> None:
    """장면이 줄면 남은 옛 장면을 지운다 -- 안 지우면 다음 타임라인에 섞인다."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("짧아진 대본")

    store.save_segment_analysis(transcript_id="t1", script_asset_id="s1", project_id=project.project_id, segments=_analysis("하나", "둘", "셋"))
    store.save_segment_analysis(transcript_id="t1", script_asset_id="s1", project_id=project.project_id, segments=_analysis("하나", "둘"))

    ids = {str(item["segment_id"]) for item in store.list_segments(project_id=project.project_id)}
    assert ids == {"seg_001", "seg_002"}, f"옛 장면이 남았다: {sorted(ids)}"


def test_another_project_is_untouched(tmp_path: Path) -> None:
    """같은 `seg_001`을 쓰는 다른 프로젝트를 건드리면 안 된다."""
    store = LocalProjectStore(tmp_path)
    keep = store.bootstrap_project("건드리지 마라")
    other = store.bootstrap_project("다시 분석")
    store.save_segment_analysis(transcript_id="t1", script_asset_id="s1", project_id=keep.project_id, segments=_analysis("남아야 한다"))
    store.save_segment_analysis(transcript_id="t1", script_asset_id="s1", project_id=other.project_id, segments=_analysis("가", "나"))

    store.save_segment_analysis(transcript_id="t1", script_asset_id="s1", project_id=other.project_id, segments=_analysis("다"))

    kept = [str(item.get("text") or "") for item in store.list_segments(project_id=keep.project_id)]
    assert kept == ["남아야 한다"]
