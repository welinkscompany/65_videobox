# VideoBox 필수 미디어 팩 및 즐겨찾기 설계

## 1. 문서 목적

이 문서는 VideoBox 설치 직후 실제 BGM과 SFX를 검색·추천·미리듣기·즐겨찾기·적용할 수 있도록 하는 `Starter Media Pack`의 라이선스, 배포, 데이터, 추천과 운영 계약을 정의한다. 프로그램 Git 저장소에는 대용량 미디어를 넣지 않고 선택 설치형 content pack으로 분리한다.

## 2. 목표와 비목표

### 목표

1. 300–500MB 규모의 필수 음악·효과음 세트를 제공한다.
2. 상업적 유튜브 사용과 팩 재배포가 명확히 허용된 자산만 포함한다.
3. 파일별 출처, 제작자, 라이선스, 증빙 시각과 checksum을 보존한다.
4. 설치, 중단 복구, 업데이트, 제거와 무결성 검증을 지원한다.
5. 편집기의 공통 즐겨찾기·최근 사용·검색·미리듣기와 연결한다.
6. 실제 파일과 활성 라이선스가 없는 추천은 자동 적용하지 않는다.

### 비목표

- 무제한 온라인 음원 검색
- YouTube, 스트리밍 서비스 또는 저작권 불명 사이트에서의 추출
- 사용자가 별도로 구매한 라이선스의 법적 적합성 자동 판정
- Content ID 분쟁의 자동 해결
- 음악 생성 모델을 이용한 신규 음원 생성

## 3. 시스템 경계

- `pack-schema`: manifest와 license policy를 검증하는 독립 계약
- `pack-installer`: staging download/local archive, checksum, atomic activation, update와 remove 상태 머신
- `media-library`: 설치 pack과 user import를 index하는 `user-library/library.sqlite`
- `media-api`: pack 상태, 검색, preview, favorite와 attribution 조회
- `recommendation bridge`: active asset ID만 기존 recommendation/timeline 계약으로 전달
- `release builder`: 승인된 source와 evidence에서 versioned archive, LICENSES와 release report를 생성

팩 설치 실패는 기존 프로젝트 DB와 이미 설치된 active pack을 변경하지 않는다. recommendation bridge는 installer나 네트워크에 직접 의존하지 않고 media-library의 검증된 snapshot만 읽는다.

## 4. 팩 구성

`starter-v1` 목표는 음악 30곡과 SFX 100개다.

### 음악 카테고리

- bright/upbeat 4곡
- calm/explainer 4곡
- emotional 4곡
- tension 3곡
- technology/business 4곡
- documentary 4곡
- comedy/light 3곡
- intro/outro 4곡

권장 파일 형식은 44.1kHz 또는 48kHz WAV/FLAC 원본과 배포용 고품질 오디오다. 보컬이 있는 트랙은 기본 팩에서 제외한다.

### SFX 카테고리

- click/UI 15개
- transition/whoosh 15개
- pop/emphasis 15개
- success/failure 10개
- notification 10개
- impact 10개
- comedy 10개
- ambience 5개
- mechanical/digital 5개
- intro/outro 5개

SFX는 불필요한 무음 tail을 정리하되 원본 checksum과 변환 lineage를 함께 기록한다.

## 5. 라이선스 수용 정책

### 수용 가능

- CC0 1.0
- Public Domain으로 공식 표시된 자산
- 상업적 사용, 영상 삽입, 수정과 팩 내 재배포를 명시적으로 허용하는 원 저작자 라이선스
- attribution 조건이 있는 경우 팩과 영상 설명용 attribution text를 함께 제공할 수 있는 자산

### 제외

- 개인 사용 전용, 비상업, ND 또는 재배포 금지
- 출처·제작자·라이선스 URL이 없는 파일
- 사이트 이용약관과 파일 라이선스가 충돌하는 파일
- Content ID 등록 또는 분쟁 처리 조건이 불명확한 파일
- 로그인 세션이나 scraping 우회로만 다운로드 가능한 파일
- 라이선스가 나중에 바뀌었지만 당시 증빙을 보존하지 못한 파일

소스 선정 시 최신 공식 라이선스 페이지를 웹으로 확인한다. 검색 결과나 제3자 요약만으로 수용하지 않는다. 법적 보증을 주장하지 않으며 출시 전 운영자가 manifest를 검토한다.

## 6. 라이선스와 파일 manifest

팩 최상위 `manifest.json`은 pack metadata와 asset rows를 포함한다.

```json
{
  "schema_version": "1.0",
  "pack_id": "videobox-starter-media",
  "pack_version": "1.0.0",
  "published_at": "ISO-8601",
  "assets": [
    {
      "asset_id": "music_starter_001",
      "asset_type": "music",
      "original_filename": "source.wav",
      "pack_path": "music/calm/source.wav",
      "display_name": "Calm Explainer 01",
      "creator": "Creator name",
      "source_url": "https://official-source.example/item",
      "license_name": "CC0-1.0",
      "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
      "attribution_required": false,
      "attribution_text": "",
      "commercial_use_allowed": true,
      "modification_allowed": true,
      "redistribution_allowed": true,
      "content_id_policy": "not_declared",
      "downloaded_at": "ISO-8601",
      "verified_at": "ISO-8601",
      "source_sha256": "hex",
      "distributed_sha256": "hex",
      "derivation": null,
      "metadata": {}
    }
  ]
}
```

모든 필수 필드가 채워지고 checksum이 일치해야 자산을 `active`로 index한다. `not_declared` Content ID는 별도 사용자 경고를 표시하며, 더 안전한 대체 자산이 있으면 기본 추천 점수를 낮춘다.

## 7. 자산 메타데이터

### 음악

`genre`, `moods`, `bpm`, `duration_sec`, `energy`(1–5), `loop_suitable`, `intro_outro_role`, `vocal=false`, `recommended_use_cases`를 기록한다.

### SFX

`category`, `moods`, `duration_sec`, `intensity`(1–5), `loop_suitable`, `recommended_use_cases`, `has_silence_tail`을 기록한다.

태그는 canonical lower snake_case를 사용하고 display label은 UI locale에서 변환한다.

## 8. 배포와 설치 구조

미디어 팩은 프로그램 release와 독립된 versioned archive와 signed index로 배포한다.

```text
VideoBox Media Library/
  packs/
    starter-v1/
      music/
      sfx/
      manifest.json
      LICENSES/
      install-state.json
  user-imports/
  index/
    media-library.sqlite
  staging/
```

- 다운로드는 staging에 저장한다.
- archive checksum과 asset checksum을 모두 검사한다.
- 검증이 끝난 뒤 atomic rename으로 활성화한다.
- 중단 시 기존 active version은 유지하고 staging만 재개 또는 제거한다.
- 프로그램 업데이트는 user-imports를 수정하지 않는다.
- 디스크 여유 공간이 archive 압축 크기와 설치 후 크기의 합보다 부족하면 시작하지 않는다.

## 9. 설치·업데이트·제거 상태

상태는 `not_installed`, `downloading`, `verifying`, `installed`, `update_available`, `degraded`, `removal_blocked`, `failed`다.

- 설치 진행률, 다운로드 크기와 예상 설치 크기를 UI에 표시한다.
- update는 stable asset ID를 유지한다.
- checksum 또는 manifest가 바뀐 동일 asset ID는 breaking pack validation error다.
- 제거 전 사용 중인 프로젝트와 세그먼트를 표시한다.
- 사용 중 자산이 있으면 기본 동작은 `removal_blocked`다.
- 사용자가 강제 제거하면 프로젝트 선택은 `missing`으로 남고 자동 fallback하지 않는다.

## 10. 라이브러리와 공통 즐겨찾기

팩 asset은 user-library SQLite index에 등록하고 상세 편집기 설계의 공통 즐겨찾기 테이블을 사용한다.

- 별표 설정·해제
- 즐겨찾기만 보기
- 최근 사용 30개
- 사용 횟수와 마지막 사용 시각 정렬
- 현재 프로젝트 사용 중 표시
- 팩 업데이트 후 동일 favorite 유지
- 제거된 asset은 missing 상태 유지
- 사용자 대체 파일을 연결하면 새 user asset ID를 만들고 프로젝트 선택을 명시적으로 migration한다.

즐겨찾기는 추천 점수에 약한 가산점만 준다. mood/category 불일치나 반복 사용 패널티를 무시하지 않는다.

## 11. 검색과 미리듣기

- music: category, mood, BPM range, duration, energy, loop, favorite
- SFX: category, mood, duration, intensity, favorite
- 검색 결과는 active, checksum-valid, license-active 자산만 기본 노출한다.
- missing/degraded 자산은 문제 해결 필터에서 별도로 표시한다.
- 미리듣기는 원본 gain을 변경하지 않고 UI preview gain만 사용한다.
- 한 번에 하나만 재생하고 다른 항목 재생 시 기존 preview를 정지한다.

## 12. 추천 계약

추천기는 파일명이 아닌 `asset_id`를 반환한다.

```text
segment analysis
  -> installed + active + checksum-valid + license-active filter
  -> category/mood/use-case match
  -> duration/loop suitability
  -> favorite and recency weak boost
  -> same-project repetition penalty
  -> diversity tie-break
  -> actual file existence recheck
  -> recommendation
```

- asset row와 실제 파일이 모두 없으면 recommendation은 informational only이며 timeline 적용을 금지한다.
- music은 동일 곡의 연속 재사용을 기본 억제한다.
- SFX는 동일 segment에 같은 category를 과다 배치하지 않는다.
- 사용자가 직접 선택한 asset은 추천보다 우선하지만 출력 전 유효성 검사를 통과해야 한다.

## 13. attribution 출력

attribution_required asset을 사용하면 프로젝트별 `ATTRIBUTION.md`와 UI의 복사 가능한 YouTube 설명문을 생성한다. MP4 metadata에만 기록하고 사용자에게 숨기는 방식은 허용하지 않는다. attribution text가 비어 있으면 해당 asset의 출력 승인을 차단한다.

## 14. 오류와 복구

- download 실패: partial staging을 보존하고 range resume 가능 시 재개한다.
- checksum 실패: 세 번까지 새로 다운로드한 뒤 failed로 표시한다.
- manifest schema 실패: 팩 전체 활성화 금지.
- license 필드 누락: 해당 asset 비활성, 팩은 degraded.
- 파일 누락: favorite와 프로젝트 reference를 missing으로 유지하고 자동 적용 금지.
- index DB 실패: 파일은 유지하고 index rebuild를 제공한다.
- update 실패: 마지막 installed version 유지.
- 제거 실패: active pack을 유지하고 실패 원인을 표시한다.

## 15. 보안과 공급망

- archive path traversal을 차단한다.
- 허용 확장자와 MIME/signature를 검증한다.
- archive 해제 크기와 파일 수 상한을 둔다.
- manifest 외 파일을 index하지 않는다.
- source URL과 license evidence는 텍스트로 보존하되 실행 파일과 HTML을 팩에 포함하지 않는다.
- signed index가 준비되기 전에는 사용자가 명시적으로 확인한 local pack 설치만 허용한다.

## 16. 출시 단계

### Media Phase 1: pack contract와 local installer

manifest schema, validation, local archive install/remove, library index와 favorite를 구현한다. 실제 자산은 소규모 검증 fixture만 사용한다.

### Media Phase 2: curated starter-v1

공식 출처 조사, 라이선스 증빙, 30곡/100 SFX 선별, metadata 정규화와 archive 생성·검증을 수행한다.

### Media Phase 3: updater와 추천 품질

원격 signed index, resume/update, attribution output, diversity와 favorite weighting을 완성한다.

## 17. 검증과 완료 기준

- manifest schema의 필수 필드, license policy와 checksum을 contract test로 검증한다.
- path traversal, zip bomb 성격의 크기 초과, 미허용 파일과 checksum mismatch를 역방향 검증한다.
- 중단 설치, update 실패, 제거 차단과 index rebuild를 E2E로 검증한다.
- favorite의 성공·실패·새로고침·pack update·missing 상태를 검증한다.
- assetless/license-inactive/checksum-invalid recommendation이 timeline에 적용되지 않는지 검증한다.
- 실제 music/SFX를 선택해 600초 한국어 MP4와 real CapCut draft에 포함되는지 smoke한다.
- 공식 출처와 라이선스 URL의 human audit checklist를 pack release artifact에 포함한다.
- Phase 1 완료 조건은 검증된 local pack을 설치·검색·즐겨찾기·제거할 수 있는 것이다.
- 전체 완료 조건은 starter-v1 30곡/100 SFX가 라이선스 audit를 통과하고 실제 프로젝트에서 추천·출력되는 것이다.
