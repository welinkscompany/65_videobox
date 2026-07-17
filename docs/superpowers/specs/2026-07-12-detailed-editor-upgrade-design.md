# VideoBox 상세 편집기 업그레이드 설계

## 1. 문서 목적

이 문서는 현재의 세그먼트 기반 경량 편집기를 유튜브 초안을 실질적으로 마감할 수 있는 `하이브리드 타임라인형 편집기`로 확장하는 제품·데이터·출력 계약을 정의한다. VideoBox는 CapCut 전체를 복제하지 않는다. 반복 작업이 많은 자막, 구간, B-roll, 음악, SFX, 오버레이 조정은 VideoBox에서 끝내고 키프레임, 정밀 모션, 색보정, 고급 믹싱은 실제 CapCut draft로 넘긴다.

## 2. 목표와 비목표

### 목표

1. 선택한 세그먼트와 재생 위치를 연결하는 미리보기와 간단한 타임라인을 제공한다.
2. 자막의 폰트, 크기, 색상, 외곽선, 그림자, 배경, 위치와 정렬을 편집한다.
3. 자막 스타일 프리셋, 공용/프로젝트 전용 프리셋, 즐겨찾기와 최근 사용을 제공한다.
4. 세그먼트의 순서, 시작·끝, 분할, 병합을 안전한 범위에서 편집한다.
5. B-roll, 음악, SFX와 오버레이를 검색·미리보기·교체·즐겨찾기한다.
6. 동일 editing-session SSOT에서 브라우저 미리보기, 정확한 FFmpeg 미리보기, SRT, MP4와 실제 CapCut draft를 파생한다.
7. 저장 실패, 출력 실패, 누락 폰트·미디어와 새로고침을 복구 가능한 상태로 처리한다.

### 비목표

- 임의 멀티트랙 생성과 자유 중첩
- 키프레임과 베지어 모션
- 색보정, LUT, 마스크와 크로마키
- 속도 램핑과 광학 흐름
- EQ, 컴프레서, 멀티밴드 믹싱
- CapCut 자체를 자동 조작하거나 사용자 계정에 draft를 직접 등록하는 기능

## 3. 사용자와 핵심 작업

주 사용자는 AI 초안을 검수하고 유튜브 영상을 제작하는 1인 운영자다. 핵심 흐름은 다음과 같다.

1. ingest와 자동 타임라인 생성을 완료한다.
2. 편집기에서 영상을 재생하고 문제 세그먼트로 이동한다.
3. 자막 문구와 스타일을 현재 자막, 선택 구간 또는 전체 프로젝트에 적용한다.
4. B-roll, 음악, SFX와 오버레이를 교체하고 즐겨찾기를 재사용한다.
5. 변경된 세그먼트만 정확한 미리보기로 확인한다.
6. 승인 후 SRT, MP4 또는 실제 CapCut draft를 생성한다.
7. CapCut에서는 정밀 애니메이션, 색보정과 최종 마감만 수행한다.

## 4. 시스템 경계

- `editor-domain`: timing, style, preset, favorite와 history 불변식을 검증하는 순수 도메인 계층
- `editor-storage`: project SQLite의 editing session/preset snapshot과 projects root의 `user-library/library.sqlite` 공용 favorite를 저장하는 계층
- `editor-api`: revision-aware mutation, scope preflight, preview와 output job 계약
- `web editor`: 하이브리드 타임라인, 즉시 미리보기와 속성 패널
- `render adapters`: ASS/FFmpeg와 pycapcut에 canonical style을 변환하고 호환성 경고를 반환하는 계층

프로젝트 DB와 user-library DB를 분리한다. 공용 즐겨찾기 장애가 프로젝트 editing session의 읽기·저장을 막아서는 안 된다.

## 5. 화면 정보 구조

### 상단 작업바

- 저장 상태: 저장 중, 저장됨, 저장 실패, 서버 최신 시각
- 실행 취소·다시 실행
- 정확한 구간 미리보기
- SRT, MP4, 실제 CapCut draft 출력
- 출력 전 차단 오류와 경고 개수

### 좌측 탐색 패널

- 세그먼트 목록과 검색
- 미디어 보관함: B-roll, 음악, SFX
- 프리셋: 자막, 오버레이
- 필터: 즐겨찾기, 최근 사용, 현재 프로젝트 사용 중, 누락 자산

### 중앙 작업 영역

- 상단: 재생·일시정지, 탐색, 현재 시간과 전체 시간
- 중앙: 즉시 영상 미리보기와 자막·오버레이 합성
- 하단: 고정 역할 트랙의 세그먼트 타임라인
  - video/narration
  - broll
  - caption/overlay
  - bgm
  - sfx
- 타임라인은 arbitrary clip authoring이 아니라 세그먼트 선택, 순서, 경계와 자산 배치를 표현한다.

### 우측 속성 패널

- 선택 대상에 따라 자막, 구간, B-roll, 음악, SFX 또는 오버레이 편집기를 표시한다.
- 변경 적용 범위와 영향받는 항목 수를 저장 전에 표시한다.
- 지원하지 않는 CapCut 속성은 해당 입력 옆에 호환성 경고를 표시한다.

## 6. 세그먼트 편집 계약

지원 동작은 선택, 다중 선택, 순서 변경, 시작·끝 조절, 분할, 인접 병합, 삭제, 음소거, 복제와 원본 복원이다.

### 불변식

- `start_sec < end_sec`
- 최소 세그먼트 길이는 0.2초다.
- 동일 역할 트랙의 활성 세그먼트는 중첩할 수 없다.
- 소스 사용 구간은 실제 미디어 길이를 초과할 수 없다.
- 순서 변경은 caption, B-roll, music, SFX, TTS와 overlay의 segment identity를 함께 이동한다.
- 짧은 B-roll/TTS는 기존 loop/pad/trim 계약을 사용한다.
- 병합은 인접한 세그먼트만 허용한다. 스타일과 자산 충돌이 있으면 사용자가 유지 대상을 선택한다.
- 분할은 원본 lineage와 부모 segment ID를 기록한다.

## 7. 자막 데이터 모델

프로젝트는 하나의 기본 스타일을 갖고 각 세그먼트는 선택적 override를 갖는다.

```json
{
  "caption_style": {
    "font_family": "Noto Sans KR",
    "font_size_px": 54,
    "font_weight": 700,
    "italic": false,
    "text_color": "#FFFFFFFF",
    "outline_color": "#000000FF",
    "outline_width_px": 3,
    "shadow_color": "#00000099",
    "shadow_offset_x_px": 2,
    "shadow_offset_y_px": 2,
    "shadow_blur_px": 2,
    "background_color": "#00000000",
    "background_padding_px": 12,
    "background_radius_px": 8,
    "position_x_percent": 50,
    "position_y_percent": 88,
    "horizontal_align": "center",
    "line_height": 1.2,
    "letter_spacing_px": 0,
    "max_width_percent": 84,
    "safe_area_enabled": true
  },
  "caption_style_source": {
    "preset_id": null,
    "has_manual_overrides": false
  }
}
```

### 허용 범위

- size: 12–160px
- outline: 0–12px
- shadow offset: -30–30px
- background padding: 0–80px
- position: 0–100%, safe area 사용 시 출력 해상도 기준 내부로 clamp
- max width: 20–100%
- color: `#RRGGBBAA`
- font family: 설치된 폰트 registry의 canonical ID

모든 pixel 값은 1920×1080 canonical canvas 기준이다. 즉시 미리보기, 다른 해상도의 FFmpeg 출력과 CapCut draft는 가로·세로 비율에 따라 동일 비율로 scaling한다. 세로 영상은 별도 project canvas를 사용하고 1920×1080 값을 그대로 재사용하지 않는다.

스타일 계산 우선순위는 `프로젝트 기본값 → 프리셋 snapshot → 세그먼트 manual override`다. 프리셋을 수정하거나 삭제해도 이미 적용된 세그먼트는 저장된 snapshot으로 동일하게 출력된다.

## 8. 자막 스타일 적용 범위

지원 범위는 `current_caption`, `selected_captions`, `from_current`, `whole_project`, `project_default`다. 저장 요청은 scope와 대상 segment ID를 명시한다. 기존 manual override를 덮어쓰는 경우 서버가 영향 항목 수와 ID를 preflight로 반환하고 사용자가 확인한 뒤 mutation을 실행한다.

## 9. 프리셋과 즐겨찾기

### 프리셋

- `caption_style`과 `overlay`만 설정 묶음으로 저장한다.
- scope는 `global` 또는 `project`다.
- 기본 제공 프리셋은 immutable이며 복제 후 수정한다.
- 이름은 동일 scope 안에서 대소문자와 양끝 공백을 정규화해 중복을 막는다.
- 삭제 후에도 적용된 segment snapshot은 유지한다.

### 공통 즐겨찾기

지원 resource type은 `caption_style_preset`, `overlay_preset`, `broll_asset`, `music_asset`, `sfx_asset`이다.

```text
favorite_id, resource_type, resource_id, display_name,
tags_json, sort_order, created_at, last_used_at, usage_count
```

- 즐겨찾기는 VideoBox 설치 전체에 적용되는 user-library DB에 저장한다.
- 프로젝트 전용 프리셋은 프로젝트가 열릴 때만 즐겨찾기에 노출한다.
- 즐겨찾기 해제는 원본이나 프리셋을 삭제하지 않는다.
- 누락 자산은 `missing`으로 표시하고 추천·자동 적용·출력을 차단한다.
- 최근 사용은 명시적 즐겨찾기와 분리하고 최대 30개를 유지한다.

## 10. 미디어 편집 범위

### B-roll

검색, 태그·길이·해상도 필터, 썸네일, 미리보기, 즐겨찾기, 교체·해제, 소스 시작점, `crop|fit|loop` 채우기, scale과 중심 위치를 지원한다.

### 음악

장르·분위기·BPM·길이 검색, 미리듣기, 즐겨찾기, 구간·전체 적용, 소스 시작점, -60–0dB gain, 0–10초 fade, loop와 narration ducking을 지원한다.

### SFX

카테고리·분위기·길이 검색, 미리듣기, 즐겨찾기, 타임라인 위치, -60–6dB gain과 0–3초 fade를 지원한다. loop 기본값은 false이며 동일 SFX 반복 사용을 경고한다.

## 11. 오버레이

제목, 설명 카드, 이미지, 표, 로고·워터마크를 지원한다. 공통 속성은 시작·끝, 위치, 크기, 여백, 배경, 투명도와 정렬이다. 자막과 동일한 preset snapshot 원칙을 사용한다. 키프레임·모션 템플릿은 범위 밖이다.

## 12. 미리보기와 출력 SSOT

editing session을 유일한 편집 truth로 사용한다.

```text
editing session
  -> browser instant preview
  -> FFmpeg selected-range preview
  -> SRT (text + timing)
  -> styled MP4 (ASS or equivalent FFmpeg path)
  -> real CapCut draft
```

- 즉시 미리보기는 브라우저 CSS/canvas로 스타일과 배치를 반영하지만 final equivalence를 주장하지 않는다.
- 정확한 미리보기는 선택 구간만 FFmpeg로 렌더링한다.
- SRT는 text와 timing만 보존한다.
- MP4는 ASS 또는 동일 결과를 내는 FFmpeg 필터로 스타일을 burn-in한다.
- CapCut draft는 font, size, color, outline, background, position과 alignment 중 pycapcut/CapCut이 표현할 수 있는 subset을 기록한다.
- 지원하지 않는 속성은 `capcut_compatibility_warnings`로 반환하고 silent drop하지 않는다.

## 13. 저장, 이력과 동시성

- mutation은 SQLite transaction과 append-only history event를 함께 기록한다.
- 클라이언트는 `session_revision`을 전송한다. 서버 revision과 다르면 409와 최신 snapshot을 반환한다.
- autosave는 입력 종료 800ms 후 배치하고 페이지 이탈 시 pending 상태를 경고한다.
- 저장 실패 시 로컬 draft를 유지하고 명시적 재시도를 제공한다.
- undo/redo는 최근 100개의 reversible mutation을 지원한다. output generation과 asset import는 undo 대상이 아니다.
- 새로고침은 최신 persisted session과 선택 segment, timeline viewport를 복원한다.

## 14. 오류와 복구

- 누락 폰트: fallback 폰트를 표시하고 출력 전 경고한다.
- 누락·손상 미디어: 자동 적용과 출력 차단, 원본 narration 유지.
- 잘못된 시간 범위: 422와 field error, 저장 상태 미변경.
- preview 실패: 마지막 성공 artifact 유지, nullable failure result 표시.
- final/CapCut 실패: 기존 nullable artifact와 UI error boundary 계약 유지.
- autosave 충돌: 사용자 변경을 폐기하지 않고 서버/로컬 차이를 표시한다.
- CapCut 미지원 스타일: draft는 호환 subset으로 생성하고 경고 목록을 제공한다.

## 15. 출시 단계

### Phase 1: 자막 스타일과 공통 즐겨찾기

자막 모델, 스타일 패널, 적용 범위, 프리셋, 즐겨찾기, instant preview, SRT/MP4/CapCut 계약을 완성한다.

### Phase 2: 하이브리드 타임라인

순서·경계 조절, 분할·병합, 다중 선택, undo/redo, 선택 구간 정확한 preview를 완성한다.

### Phase 3: 미디어와 오버레이 상세 편집

B-roll crop/fit/loop, 음악·SFX gain/fade/ducking, 오버레이 preset과 공통 검색을 완성한다.

각 phase는 독립적으로 배포 가능하고 기존 경량 편집 경로를 깨지 않아야 한다.

## 16. 검증과 완료 기준

- 모든 mutation은 RED contract/API test 후 구현한다.
- frontend는 저장 실패·복구·새로고침·409 충돌·undo/redo를 포함한다.
- style scope별 대상과 override 보존을 property/contract test로 검증한다.
- 폰트 누락, asset missing과 invalid timing을 역방향으로 검증한다.
- 동일 sample에서 instant preview 경고, FFmpeg preview, SRT, MP4와 CapCut mapping을 확인한다.
- 600초 한국어 sample로 style, timing, B-roll, music, SFX, overlay를 변경하고 SRT·MP4·real CapCut draft smoke를 실행한다.
- Phase 1 완료 조건은 사용자가 자막 스타일을 저장·즐겨찾기·범위 적용하고 MP4와 CapCut draft에서 유지하는 것이다.
- 전체 완료 조건은 세 phase가 모두 통과하고 실제 프로젝트 3건의 human open/edit/export UX 검수가 끝나는 것이다.
