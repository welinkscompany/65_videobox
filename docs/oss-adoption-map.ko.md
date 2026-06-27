# VideoBox OSS 반입 맵

## 1. 목적

이 문서는 VideoBox가 Phase 8 이후 구현에서 어떤 오픈소스와 기존 내부 소스를 실제로 반입할지 고정하기 위한 문서다.

이 문서의 목표는 다음 4가지를 명확히 하는 것이다.

- 어떤 소스를 그대로 쓰지 않고 선별 이식할지
- 어떤 소스를 dependency로만 사용할지
- 어떤 소스는 구조만 참고하고 재작성할지
- 어떤 소스는 명시적으로 반입 금지할지

핵심 원칙:

- `소스 복제`보다 `경계 유지`를 우선한다
- `파일 단위 판단`을 남겨서 나중에 추적 가능해야 한다
- `현재 repo 구조` 안에서 어디로 들어갈지 먼저 고정한다
- `라이선스와 의존성 리스크`를 코드 반입 전에 검토한다

## 2. 분류 기준

### `adopt as-is`

- 내부 구조와 충돌이 거의 없고
- source copy 또는 거의 무변형 이식이 가능한 경우

VideoBox에서는 이 케이스를 거의 허용하지 않는다.

### `partial port`

- 핵심 실행 로직은 유효하지만
- 입출력, 에러 처리, provider, storage, job wiring은 VideoBox 기준으로 다시 붙여야 하는 경우

VideoBox의 기본 반입 방식은 이 방식이다.

### `rewrite`

- 문제 정의와 처리 흐름은 유효하지만
- 현재 구현이 특정 UI, 특정 provider, 특정 storage 구조에 강하게 묶여 있어 새로 작성하는 편이 더 안전한 경우

### `exclude`

- 현재 제품 범위와 맞지 않거나
- 라이선스/구조/운영 리스크가 커서 지금은 반입하면 안 되는 경우

## 3. 현재 VideoBox 반입 대상 패키지 맵

| 목적 | 현재 기준 target path | 비고 |
|---|---|---|
| CapCut export adapter | `packages/capcut-export/src/videobox_capcut_export/` | CapCut 전용 변환 로직 격리 |
| 로컬 파이프라인 조정 | `packages/core-engine/src/videobox_core_engine/local_pipeline.py` | job orchestration entry |
| rough cut / auto cut | `packages/core-engine/src/videobox_core_engine/auto_cut.py` | 새 파일 생성 예정 |
| transcript alignment | `packages/core-engine/src/videobox_core_engine/transcript_alignment.py` | 새 파일 생성 예정 |
| script scene planning | `packages/core-engine/src/videobox_core_engine/script_scene_planner.py` | 새 파일 생성 예정 |
| B-roll matching/scoring | `packages/core-engine/src/videobox_core_engine/broll_matcher.py` | 새 파일 생성 예정 |
| preview artifact renderer | `packages/core-engine/src/videobox_core_engine/preview_renderer.py` | 현재 HTML preview 기반 |
| provider boundary | `packages/provider-interfaces/src/videobox_provider_interfaces/` | STT/TTS/recommender 경계 유지 |
| local persistence | `packages/storage-abstractions/src/videobox_storage/` | SQLite + local file |
| API surface | `services/api/src/videobox_api/` | dashboard/backend contract |
| operator dashboard | `apps/web/src/` | 로컬 우선 review dashboard |

## 4. BrollBox 파일 반입 판단

| source project/repo | source file/path | target VideoBox package/path | decision | reason | dependency / license notes | risk notes |
|---|---|---|---|---|---|---|
| `brollbox-master` | `execution/export_capcut.py` | `packages/capcut-export/src/videobox_capcut_export/adapter.py` + 추후 helper 분리 | `partial port` | 트랙 구성 방식, SRT 생성 사고방식, hook/BGM track 설계는 유효하지만 pycapcut, Google Drive 다운로드, BrollBox 상수 구조에 결합돼 있다 | 내부 소스라 라이선스 이슈는 낮지만, `pycapcut` 의존 여부는 별도 점검 필요 | CapCut 포맷 변경, pycapcut 결합, Google Drive 전제 제거 필요 |
| `brollbox-master` | `execution/auto_cut.py` | `packages/core-engine/src/videobox_core_engine/auto_cut.py` | `partial port` | scene detect, black detect, max length split, dark/static filter 기준은 재사용 가치가 높다 | FFmpeg/ffprobe 직접 호출 유지 가능 | threshold 하드코딩을 VideoBox settings로 이동해야 함 |
| `brollbox-master` | `execution/transcribe_audio.py` | `packages/provider-interfaces/src/videobox_provider_interfaces/stt.py` + `packages/core-engine/src/videobox_core_engine/transcript_alignment.py` | `rewrite` | WhisperX + forced alignment + script sync 문제 정의는 매우 좋지만 Gemini 직접 호출, singleton 전역, constants 결합이 강하다 | WhisperX는 외부 dependency로 채택, 소스 복사는 권장하지 않음 | alignment 모델 라이선스와 fallback 정책을 별도로 관리해야 함 |
| `brollbox-master` | `execution/match_script.py` | `packages/core-engine/src/videobox_core_engine/script_scene_planner.py` + `packages/core-engine/src/videobox_core_engine/broll_matcher.py` | `rewrite` | 장면 분리와 장면별 키워드 추출 흐름은 유효하지만 Gemini/Sheets/search 결합이 너무 강하다 | external LLM dependency는 provider 뒤에 숨겨야 함 | 장면 분리 품질을 LLM 하나에 과의존하면 비용/재현성 문제 발생 |
| `brollbox-master` | `execution/search_broll.py` | `packages/core-engine/src/videobox_core_engine/broll_matcher.py` | `rewrite` | 태그 기반 검색, 필터링, 점수화 사고방식은 유지 가치가 있다 | DataFrame/Sheets 구조는 제거 필요 | 개인 B-roll 메타데이터 스키마가 먼저 안정화되어야 함 |
| `brollbox-master` | `execution/shorts_clip.py` | `packages/core-engine/src/videobox_core_engine/shortform_candidates.py` | `rewrite` | SRT 파싱과 구간 추출 흐름은 좋지만 현재 Phase 8의 첫 반입 대상은 아님 | FFmpeg 활용 가능, provider 결합은 제거 필요 | shortform은 현재 MVP 주경로가 아니라 후순위 |
| `brollbox-master` | `execution/tts_engine.py` | `packages/provider-interfaces/src/videobox_provider_interfaces/tts.py` + 추후 `packages/core-engine/src/videobox_core_engine/tts_replacement_planner.py` | `rewrite` | TTS 엔진 계층은 참고 가치가 있으나 VideoBox는 `tts_replacement recommendation` 중심 구조가 필요하다 | Voicebox 또는 다른 로컬 엔진과의 연결은 provider로 추상화 | 자동 전면 대체 금지 원칙을 어기지 않도록 강제 필요 |
| `brollbox-master` | `execution/utils.py` | 필요 시 함수 단위로 각 패키지에 재배치 | `exclude` | 범용 유틸이지만 BrollBox 결합 유틸이 섞여 있어 통째 반입 가치가 낮다 | 공용 유틸을 복사하면 결합이 다시 생김 | 작은 편의 함수 때문에 숨은 결합이 유입될 수 있음 |
| `brollbox-master` | `execution/constants.py` | `packages/core-engine/src/videobox_core_engine/settings.py` | `exclude` | 상수 개념은 필요하지만 파일 자체는 BrollBox 도메인 값이 너무 많다 | 값만 참고 가능 | 하드코딩 전파 위험 |
| `brollbox-master` | `execution/pipeline_progress.py` | `services/api/src/videobox_api/` 또는 job layer에서 별도 재구성 | `exclude` | 진행률 아이디어는 좋지만 현재 구조로는 반입 가치가 낮다 | 현재 VideoBox job model로 재설계 필요 | 잘못 가져오면 UI와 엔진이 다시 결합됨 |
| `brollbox-master` | `execution/speaker_track.py` | 반입 없음 | `exclude` | 현재 VideoBox 1차 범위는 화자 추적보다 나레이션 편집이다 | dependency 증가만 유발 | scope explosion |
| `brollbox-master` | `execution/process_image.py`, `execution/generate_tags.py`, `execution/extract_frames.py`, `execution/save_metadata.py` | 향후 `packages/core-engine/src/videobox_core_engine/asset_indexing.py` 후보 | `reference only` | 자산 태깅/프레임 추출 아이디어는 참고 가능하지만 지금 바로 이식할 정도로 경계가 정리되지 않았다 | OpenCV/이미지 처리 dependency 검토 필요 | B-roll 인덱싱 스키마가 먼저 고정돼야 함 |
| `brollbox-master` | `ui/`, `app.py` | 반입 없음 | `exclude` | Streamlit UI는 VideoBox의 React dashboard 구조와 충돌한다 | Streamlit 유지보수 비용과 이중 UI 발생 | 구조 오염 위험이 큼 |
| `brollbox-master` | `directives/`, `memory/`, `docs/archive/`, `docs/04-report/`, `tests/` | 문서 참고만 | `reference only` | 제품 코드 반입 대상은 아니지만 작업 맥락과 과거 의사결정 확인에는 쓸 수 있다 | 코드 반입 아님 | 실행 코드와 운영 문서 경계 혼동 주의 |

## 5. 외부 OSS 반입 판단

여기서 중요한 원칙은 `외부 OSS는 source copy보다 dependency 우선`이다.

| source project/repo | source file/path | target VideoBox package/path | decision | reason | dependency / license notes | risk notes |
|---|---|---|---|---|---|---|
| `m-bain/whisperX` | repo 전체를 dependency로 사용 | `packages/provider-interfaces/src/videobox_provider_interfaces/stt.py` + runner wiring | `partial port` | STT와 forced alignment의 핵심 dependency다. 소스 복사보다 provider integration이 맞다 | GitHub 기준 BSD-2-Clause. 다만 alignment 모델/weights는 별도 확인 필요 | GPU/VRAM 요구량, alignment 모델별 라이선스 검토 필요 |
| `Breakthrough/PySceneDetect` | repo 전체를 dependency로 사용 | `packages/core-engine/src/videobox_core_engine/auto_cut.py` | `partial port` | 장면 감지 로직을 FFmpeg 직접 호출보다 더 구조적으로 붙일 수 있다 | GitHub 기준 BSD-3-Clause | semantic scene이 아니라 shot detection 수준이라는 한계 명시 필요 |
| `huggingface/sentence-transformers` | repo 전체를 dependency로 사용 | `packages/core-engine/src/videobox_core_engine/broll_matcher.py` | `partial port` | 텍스트 기반 추천 랭킹과 script/B-roll 유사도에 가장 현실적이다 | GitHub 기준 Apache-2.0 | embedding model 선택과 모델별 라이선스 구분 필요 |
| `jamiepine/voicebox` | repo 전체를 source copy하지 않음 | `packages/provider-interfaces/src/videobox_provider_interfaces/tts.py` + 추후 `packages/core-engine/src/videobox_core_engine/tts_replacement_planner.py` | `reference only` | 로컬 우선 TTS studio 방향은 매우 좋지만 VideoBox는 음성 스튜디오가 아니라 제한적 나레이션 대체가 목적이다 | GitHub 기준 MIT. 실제 사용 모델/weights/voice cloning policy는 별도 검토 필요 | 품질 편차, 로컬 리소스, 동의/윤리 리스크 |
| `mlfoundations/open_clip` | repo 전체를 dependency로만 검토 | 추후 `packages/core-engine/src/videobox_core_engine/multimodal_retrieval.py` | `reference only` | 장기적으로 B-roll 추천 품질 개선 가능성이 있으나 Phase 8 첫 반입 대상은 아니다 | repo는 오픈소스지만 pretrained model 라이선스가 checkpoint마다 다르다 | 모델 선택 실수 시 비상업/혼합 라이선스 리스크 발생 |
| `remotion-dev/remotion` | 반입 없음 | 반입 없음 | `exclude` | 설명형 시각화 가능성은 높지만 현재 범위에 비해 무겁고 license 검토가 필요하다 | 공식 저장소 설명 기준, 특정 규모 이상의 회사는 별도 라이선스 검토 필요 | 범위 증가 + 라이선스 검토 비용 발생 |
| `tauri-apps/tauri` | 반입 없음 | `apps/desktop/` 장기 후보 | `reference only` | 데스크톱 패키징 방향은 유효하지만 지금은 web dashboard + local API 검증이 우선이다 | 공식 생태계는 MIT/Apache-2.0 계열이나 배포 번들 dependency는 별도 확인 필요 | 패키징 문제에 시간 소모 가능 |

## 6. 명시적 반입 금지 규칙

아래는 Phase 8 시작 전에 명시적으로 금지한다.

1. BrollBox `ui/` 전체를 VideoBox `apps/web/`에 복사하는 것
2. BrollBox의 Google Sheets/Drive 접근 코드를 VideoBox storage layer에 직접 이식하는 것
3. Gemini 직접 호출 코드를 `core-engine` 안에 박아 넣는 것
4. Voicebox 소스를 통째로 vendoring 하는 것
5. open_clip 체크포인트 라이선스를 확인하지 않고 바로 추천 경로에 넣는 것
6. Remotion을 preview 기본 경로로 교체하는 것
7. CapCut payload 생성을 `core-engine` 안으로 다시 섞는 것

## 7. Phase 8 intake set

### 7.1 먼저 이식할 것

| 우선순위 | source | target | 방식 |
|---|---|---|---|
| 1 | `brollbox-master/execution/export_capcut.py` | `packages/capcut-export/src/videobox_capcut_export/` | `partial port` |
| 2 | `brollbox-master/execution/auto_cut.py` | `packages/core-engine/src/videobox_core_engine/auto_cut.py` | `partial port` |
| 3 | `brollbox-master/execution/transcribe_audio.py`의 alignment 흐름 | `packages/core-engine/src/videobox_core_engine/transcript_alignment.py` | `rewrite` |
| 4 | `brollbox-master/execution/match_script.py`의 scene split 사고방식 | `packages/core-engine/src/videobox_core_engine/script_scene_planner.py` | `rewrite` |
| 5 | `brollbox-master/execution/search_broll.py`의 scoring 축 | `packages/core-engine/src/videobox_core_engine/broll_matcher.py` | `rewrite` |

### 7.2 참고만 할 것

| source | 이유 |
|---|---|
| `brollbox-master/execution/shorts_clip.py` | shortform은 후순위이므로 지금은 구조 참고만 |
| `brollbox-master/execution/tts_engine.py` | TTS provider 경계 설계 참고용 |
| `jamiepine/voicebox` | local-first TTS studio 방향 참고용 |
| `mlfoundations/open_clip` | 추후 multimodal retrieval 검증용 |
| `tauri-apps/tauri` | 추후 desktop wrapper 검토용 |

### 7.3 명시적으로 막을 것

| source | 이유 |
|---|---|
| `brollbox-master/ui/*` | Streamlit UI 구조 충돌 |
| `brollbox-master/app.py` | 앱 구조 전체 복제 금지 |
| `brollbox-master/execution/export_sheet.py` | Google Sheets 구조 유입 차단 |
| `brollbox-master/execution/detect_drive.py` | Google Drive 결합 구조 차단 |
| `remotion-dev/remotion` 직접 반입 | 현재 범위와 라이선스 판단 미확정 |

## 8. 문서 정합성 판단

이번 반입 맵 기준으로 현재 문서와의 정합성을 점검한 결과는 다음과 같다.

### 정렬이 필요한 항목

1. 구현 계획서의 `preview mp4` 표현
2. 아키텍처 계획서의 `apps/web 비필수` 표현
3. 아키텍처 계획서의 preview layer를 `mp4 전용`처럼 읽히는 표현

### 그대로 유지 가능한 항목

1. `product-plan.ko.md`의 local-first + CapCut export 중심 방향
2. `oss-research-and-scope-cut.ko.md`의 BrollBox 재사용 우선순위
3. TTS를 review 기반 대체로 제한하는 원칙

## 9. 결론

VideoBox의 Phase 8 반입 전략은 다음 한 문장으로 요약할 수 있다.

`BrollBox와 외부 OSS에서 검증된 실행 로직과 dependency만 선별 반입하고, UI/Sheets/provider 하드코딩 구조는 명시적으로 차단한다.`

이 원칙을 지키면:

- 구현 속도를 높일 수 있고
- 구조 오염을 줄일 수 있으며
- Phase 8 이후 기능 확장을 해도 repo 경계가 무너지지 않는다
