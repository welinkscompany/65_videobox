# 손수 만든 타임라인 시험 조사 (2026-08-24)

이 문서는 `tests/`에서 타임라인·트랙·클립을 손으로 만들어 넣는 시험을 찾고,
렌더·내보내기에 닿는 시험부터 실제
`materialize_editing_session_timeline`의 출력 모양을 쓰도록 바꾸기 위한 조사다.

## 모수

정적 검색 후보는 **48개 파일**이다.

- `tracks`를 직접 만드는 위치: **402곳**, 41개 파일
- `clips`를 직접 만드는 위치: **386곳**, 34개 파일
- `CompositionPlan.from_timeline` 직행: **90곳**, 15개 파일
- 위 항목과 `Timeline*` 직접 생성, timeline dict 대입을 합친 고유 후보: **48개 파일**

위 숫자는 서로 겹친다. 예를 들어 한 timeline dict 안의 `tracks`와 `clips`, 그 dict를
받는 `CompositionPlan.from_timeline`은 각각 한 번씩 잡힌다. 따라서 위치 수를 더해
시험 개수라고 부르지 않는다.

## 판단 기준

손수 만든 timeline이 모두 잘못된 것은 아니다.

- **바꿔야 하는 것**: 편집 세션의 눈·음소거·자막·오버레이·재배치가 렌더나 내보내기까지
  간다고 주장하면서, 완성된 timeline에 기대 필드를 손으로 꽂는 시험
- **그대로 둘 수 있는 것**: `CompositionPlan.from_timeline`, FFmpeg 필터 한 조각,
  저장소 스키마처럼 낮은 단계의 입력 계약 자체를 시험하는 단위 시험
- **이미 실제 경로인 것**: fixture는 timeline을 준비하지만 제품의 출력 진입점 안에서
  materializer를 호출하는 통합 시험

즉 이 조사의 48개는 **검토 모수**이지, 48개 전부를 일괄 변환한다는 뜻이 아니다.

## 이번에 실제로 바꾼 것 — 2개

| 파일 | 바꾸기 전 | 바꾼 뒤 | 결과 |
|---|---|---|---|
| `tests/test_pycapcut_track_states.py` | 완성 timeline에 `track_states`를 직접 삽입 | 편집 session에 상태를 넣고 materializer 출력만 실제 PyCapCut 어댑터에 전달 | 5개 통과 |
| `tests/test_capcut_export_track_states.py` | 레거시 JSON export timeline에 `track_states`를 직접 삽입 | 같은 session→materializer 모양을 레거시 어댑터에도 전달 | 8개 통과 |

두 변환 모두 기존 시험은 계속 통과했다. 이번 두 파일에서는 새 제품 결함이 나오지 않았다.
시험을 되돌리거나 제품 코드를 우회하지 않았다.

## 이미 materializer를 직접 쓰는 혼합 파일 — 9개

이 파일들은 손수 만든 fixture도 있지만, 적어도 세션 편집 결과를 주장하는 일부 시험은
이미 실제 materializer를 호출한다. 각 raw fixture가 낮은 단계 계약인지 다음 검토에서
시험별로 판단해야 한다.

- `tests/test_api_media_library.py`
- `tests/test_editing_session.py`
- `tests/test_editor_timeline_mutations.py`
- `tests/test_editor_view_model_api.py`
- `tests/test_exact_preview_artifact.py`
- `tests/test_exact_preview_remediation.py`
- `tests/test_overlay_motion.py`
- `tests/test_scene_transition_session_and_api.py`
- `tests/test_track_states.py`

## 제품 출력 진입점 안에서 이미 materialize하는 파일 — 3개

- `tests/test_local_pipeline_capcut_draft_export.py`
- `tests/test_local_pipeline_final_render.py`
- `tests/test_api_exact_preview.py`

세 파일은 `LocalPipelineRunner`의 실제 출력 진입점을 부른다. 제품 코드는 각각
`run_capcut_draft_export_job`, `run_final_render_job`, `_exact_preview_inputs` 안에서
materializer를 호출한다. `test_api_exact_preview.py`의 source timeline은 편집 세션을
적용하기 전 입력이며, pipeline이 그 둘을 합친다. 따라서 이 파일의 source timeline을
단지 dict라는 이유로 먼저 materialize해 저장하면 같은 계층을 두 번 통과시키게 된다.

2026-08-24에 `test_api_exact_preview.py` focused 실행은 4개 통과했다. 이 파일은
“손수 만든 완성 timeline을 어댑터에 직접 넣는 시험”이 아니므로 이번 전환 대상에서 뺐다.

## 렌더·내보내기 쪽 다음 검토 대상 — 9개

아래 파일은 출력에 가깝지만, 낮은 단계 계획·필터 계약과 세션 통합 계약이 섞여 있을 수
있다. 파일 전체를 바꾸지 말고, **세션 편집 결과를 주장하는 시험만** 실제 만듦새로 옮긴다.

- `tests/test_broll_dissolve.py`
- `tests/test_broll_speed_and_volume.py`
- `tests/test_ffmpeg_final_renderer.py`
- `tests/test_icon_font_overlay_render.py`
- `tests/test_overlay_text_avoids_the_caption_band.py`
- `tests/test_preview_export.py`
- `tests/test_pycapcut_adapter.py`
- `tests/test_scene_transitions.py`
- `tests/test_vertical_composition.py`

## 나머지 API·저장소·도메인 후보 — 25개

이들은 출력 우선순위보다 뒤다. API validation, migration, 저장소 round-trip처럼 raw dict가
의도된 입력인 시험이 많으므로 자동 변환하지 않는다.

- `tests/test_api_atomic_draft_bundle.py`
- `tests/test_api_capcut_draft_export_endpoint.py`
- `tests/test_api_format_templates.py`
- `tests/test_api_library_assets.py`
- `tests/test_api_media_director.py`
- `tests/test_api_output_variants.py`
- `tests/test_api.py`
- `tests/test_atomic_draft_bundle.py`
- `tests/test_director_commands.py`
- `tests/test_final_render_idempotency.py`
- `tests/test_final_render_publish_fence.py`
- `tests/test_format_template.py`
- `tests/test_hermes_run_service.py`
- `tests/test_library_asset_usage.py`
- `tests/test_output_publish_fences.py`
- `tests/test_output_source_verifier.py`
- `tests/test_owner_sample_edit_package.py`
- `tests/test_playback_delivery_contract.py`
- `tests/test_postgres_project_store.py`
- `tests/test_production_readiness_smoke_script.py`
- `tests/test_render_quality_facts.py`
- `tests/test_review_timeline.py`
- `tests/test_storage.py`
- `tests/test_timeline_placements.py`
- `tests/test_yujin_creator_context.py`

## 이번 조사에서 확인한 함정

1. 파일에 `materialize_editing_session_timeline` 문자열이 있다고 그 파일의 모든 시험이
   실제 모양인 것은 아니다. 같은 파일 안에 raw plan 단위 시험이 함께 있다.
2. 반대로 timeline dict가 있다고 모두 잘못된 시험도 아니다. 실제 출력 진입점이 내부에서
   materialize하면 source fixture를 두 번 가공하지 않아야 한다.
3. `tests/test_capcut_export_looks.py`는 timeline fixture가 아니라 어댑터 소스 문자열의
   호출 개수를 센다. 이번 48개 모수에는 들어가지 않지만, 실제 초안 결과를 검증하는 시험을
   대체할 수는 없다.
4. 이번 변환에서 RED가 나오지 않았다는 사실은 나머지 후보가 안전하다는 증거가 아니다.
   다음 대상은 한 시험씩 실제 만듦새로 바꾸고, 붉어지면 입력을 되돌리지 않고 데이터 흐름을
   추적해야 한다.
