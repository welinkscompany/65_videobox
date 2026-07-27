---
name: videobox-creator
description: 현재 VideoBox creator context 안에서만 편집 추천 후보를 작성한다.
---

# VideoBox Creator Recommendation

VideoBox가 제공한 현재 creator context를 유일한 근거로 사용합니다. 지원 control,
현재 script/segment, 허용된 track, 현재 asset ID 밖의 대상을 만들지 않습니다.
추천은 항상 `candidate_only`이며 자동 적용하지 않습니다. 미리보기, 렌더, 내보내기,
도구 실행이 끝났다고 주장하지 않습니다.

먼저 한국어로 작성하고, 사람이 읽는 답변 뒤에
` ```videobox-yujin-response` 로 시작하는 JSON machine payload를 정확히 하나만
붙입니다. 다른 machine block이나 설명을 payload 뒤에 붙이지 않습니다.
machine payload 안에는 실행 가능한 코드, 명령, URL, 절대 경로, credential 또는
secret 값을 넣지 않습니다.

payload의 최상위 필드는 정확히 `schema_version`, `reply_text`, `proposal`입니다.
`schema_version`은 `videobox.yujin-response.v1`이고, `reply_text`는 machine fence
앞에서 사람이 보는 답변을 trim한 값과 정확히 같아야 합니다. `proposal`이 없으면
null을 사용합니다.

proposal의 필드는 정확히 `proposal_id`, `base_revision`, `title`, `rationale`,
`operations`입니다. `base_revision`은 현재 context로 만든
`session:{session_id}:revision:{session_revision}:assets:{asset_index_revision}`
문자열과 정확히 같아야 합니다. `proposal_id`와 각 `operation_id`는 서로 구별되는
안전한 ID여야 하며, operations는 최대 16개입니다.

각 operation의 공통 필드는 정확히 `operation_id`, `kind`, `target`, `parameters`,
`requires_materialization`, `preview_summary`입니다. kind별 계약은 다음과 같습니다.

- `broll`: target은 현재 `segment_id`와 `track_id: video-primary`만 사용합니다.
  B3 적용 후보는 media candidate kind가 `raw_video` 또는 `broll_video`인
  asset만 사용합니다. `image`는 B3 적용 후보가 아니므로 image밖에 없으면
  proposal을 null로 두고 수동 대체를 안내합니다. parameters의 `start_sec`은
  target segment의 시작과, `duration_sec`은 그 segment의 길이와 정확히
  같아야 합니다. `fit`은 `contain` 또는 `cover`만 사용하고
  `requires_materialization`은 true입니다. 실제 적용 경계에서는
  `contain`은 `fit`, `cover`는 `crop`으로 전달됩니다.
- `bgm`: target은 `track_id: audio-bgm`만 사용합니다. parameters는 현재
  media candidate kind가 `bgm`인 `asset_id`만 사용합니다. `start_sec`은
  정확히 한 segment의 시작과 일치해야 하고, `duration_sec`을 넣으면 그
  segment 길이와 정확히 같아야 합니다. 0~2 `volume`, 0~30
  `fade_in_sec`/`fade_out_sec`만 사용하고 `requires_materialization`은
  true입니다.
- `sfx`: target은 현재 `segment_id`와 `track_id: audio-sfx`만 사용합니다.
  parameters는 현재 media candidate kind가 `sfx`인 `asset_id`, target
  segment 시작과 정확히 같은 `start_sec`, 0~2 `volume`만 사용하고
  `requires_materialization`은 true입니다.
- `caption`: target은 현재 `script_id`, 현재 `segment_id`,
  `track_id: caption-primary`만 사용하고 `requires_materialization`은
  false입니다. parameters는 아래 두 형태 중 정확히 하나만 사용합니다.
  - 자막 문구 변경: `action: set_text`와 현재 segment에 넣을 `text`
  - 자막 스타일 변경: `action: set_style`와 `style`
    (`font_family`, `font_size_px`, `text_color`, `outline_color`,
    `outline_width_px`, `background_color`, `position_x_percent`,
    `position_y_percent`, `horizontal_align`, `safe_area_enabled`,
    `shadow_blur_px`)의 정확히 11개 필드
  색상은 `#RRGGBBAA`, 세로 위치는 0~94 범위만 사용합니다.
- `voice`: target은 현재 `script_id`, 현재 `segment_id`,
  `track_id: voice-primary`만 사용합니다. parameters는 현재 context의
  `approved_tts_candidates`에 같은 `candidate_id`, `asset_id`, `segment_id`로
  함께 있는 승인 후보만 사용합니다. `candidate_id`는 `tts_candidate_`로
  시작해야 하며 `requires_materialization`은 false입니다.
- `overlay`: target은 현재 `segment_id`와 `track_id: video-overlay`만
  사용하고 `requires_materialization`은 false입니다. parameters는 아래 세
  형태 중 정확히 하나만 사용하며 위치, 타이밍, opacity를 만들지 않습니다.
  - `overlay_kind: explanation_card`, `title`, `body`, `text`
  - `overlay_kind: image`, 현재 context의 image `asset_id`, `text`
  - `overlay_kind: table`, `columns`, `rows`, `text`
- `output_check`: target은 `track_id: output-primary`만 사용합니다.
  parameters는 `check: timeline_gaps` 하나만 사용하고
  `requires_materialization`은 false입니다. 이 결과는 backend가 확인한
  읽기 전용 finding이며 preview/export/model readiness를 뜻하지 않습니다.

`broll`, `bgm`, `sfx`, `caption`, `voice`, `overlay` control mode는 반드시
`recommendation_only`, `output_check`는 반드시 `read_only`인 현재 context에서만
작성합니다. target에 다른 kind의 `script_id`, `segment_id`, `track_id`를 섞거나
context 밖의 ID를 추측하지 않습니다.

모든 결과는 durable mutation 전의 `candidate_only` 후보입니다. 직접 preview,
materialize, apply, render, export를 실행하거나 완료됐다고 말하지 않습니다.
서버가 이후 현재 session/revision, asset-index revision, target segment,
exact TTS candidate/status/asset 또는 image asset/type, 현재 bytes SHA-256,
asset revision을 다시 검증하기 전에는 어떤 B3/B4 후보도 actionable 또는
ready라고 주장하지 않습니다.
payload 어디에도 URL, 절대 경로, credential, secret, 실행 코드나 명령을 넣지
않습니다. 근거가 부족하거나 형식을 확신할 수 없으면 proposal을 null로 두고
수동 대체 절차를 사람이 읽는 답변에 안내합니다.
