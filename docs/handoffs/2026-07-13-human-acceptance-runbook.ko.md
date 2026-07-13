# VideoBox Human Acceptance Runbook

## 목적

자동 테스트가 대신할 수 없는 두 운영 acceptance를 실제 사용자 판단으로 수행한다.

1. 본인 동의가 있는 실제 한국어 음성으로 personal-voice TTS 후보를 청취하고 승인 또는 거부한다.
2. 개발 PC와 다른 Windows 사용자 PC에서 CapCut handoff를 진단부터 Desktop open까지 확인한다.

## 시작 전 판정

현재 `artifacts/`의 `task5-korean-600.wav`, project snapshot의 `inputs/voice_samples/*.wav`, `tts_candidate.wav`는 모두 production smoke가 만든 합성 음성이다. 기술 pipeline 증거로는 보존하지만 human listening acceptance 입력으로 사용하지 않는다.

기본 `scripts/run_api.py`는 TTS provider를 활성화하지 않는다. 실제 personal-voice candidate 생성 전에는 아래 중 하나가 준비되어야 한다.

- `local_xtts`와 local XTTS model/runtime
- 사용자 동의를 받은, 사전 clone된 ElevenLabs voice ID와 API key

gTTS는 voice cloning provider가 아니므로 대체 수단이 아니다.

## A. Personal-voice TTS listening approval

### 입력과 안전 경계

- 사용자 본인이 동의한 10–30초 한국어 WAV/MP3/M4A/WebM/Ogg/FLAC, 128 MiB 이하를 사용한다.
- 음성 파일, API key, voice ID를 Git, `artifacts/`, 상태 문서에 저장하지 않는다.
- 후보가 거부되거나 provider가 실패하면 기존 narration을 유지한다. generic-voice fallback을 사용하지 않는다.

### 절차

1. TTS provider를 명시적으로 설정한 API와 web app을 시작한다.
2. **설정 → 음성 샘플**에서 파일을 업로드·등록한다.
3. **편집** 탭에서 검수할 세그먼트를 선택하고 **TTS 후보 생성 (음성 클로닝)**을 실행한다.
4. 후보가 `기술 검증 통과 · 청취 승인 대기`인지 확인하고, audio control로 실제 청취한다.
5. 자연스러움, 한국어 발음, 무음/끊김, 톤이 원문 의도에 맞는지 사용자가 판단한다.
6. 적합하면 **청취 승인**, 부적합하면 **청취 거부**를 선택한다. 거부 시 기존 narration 유지 문구를 확인한다.
7. 승인된 후보만 **이 후보 선택**으로 적용하고, timeline → preview → SRT → final render/CapCut draft까지 output 반영 여부를 확인한다.

### Pass / Fail 증거

| 판정 | 증거 |
| --- | --- |
| Pass | 실제 사용자 청취 후 approved 상태, 적용된 candidate ID, output에 반영된 timeline/SRT/final 또는 CapCut draft 경로 |
| Fail | provider 실패, technical rejection, 청취 거부, 기존 narration 유지 확인 |

## B. External Windows CapCut handoff smoke

### 절차

1. 다른 Windows 사용자 PC에 supported CapCut Desktop `8.7.x` 또는 `8.9.x`를 설치하고 한 번 실행한다.
2. VideoBox의 **CapCut 연결 진단**에서 `준비 완료`, `지원됨`, project root 존재, 쓰기 `확인됨`을 확인한다.
3. 승인된 timeline에서 **CapCut 초안(실제)**을 생성한 뒤 **CapCut에 등록**을 실행한다.
4. ready registered path와 `draft_content.json` 존재를 확인한다.
5. 사용자가 CapCut Desktop을 직접 열어 등록 프로젝트에서 타임라인, 한국어 자막, overlay, audio track과 missing media 유무를 확인한다. 가능하면 짧은 MP4 export도 실행한다.

### 안전 경계와 실패 처리

- VideoBox source draft를 수동 복사·이동·삭제·덮어쓰기하지 않는다.
- `videobox-<export_id>` 충돌은 ownership marker가 없으면 안전 실패한다. 기존 CapCut 폴더를 먼저 확인하거나 이름을 바꾼 뒤 재시도한다.
- `failed`/`미지원` 진단, handoff failed, project 미표시, open 실패, missing media는 모두 fail로 기록한다.

## 현재 차단 상태 (2026-07-13)

- 실제 사용자 음성 입력: 없음.
- local XTTS Python package와 Torch는 이 PC에 설치되어 있지만, XTTS-v2 model download(약 2GB)와 Coqui license acceptance는 아직 수행하지 않았다. 사용자 동의 없이 이 다운로드나 license acceptance를 실행하지 않는다.
- ElevenLabs SDK/credential/사전 clone voice ID: 없음.
- 개발 PC와 다른 Windows 사용자 PC: 현재 접근 권한 없음.
- 개발 PC CapCut은 사용자가 강제 종료한 상태이며, 이 runbook은 자동 재실행하지 않는다.

따라서 현재는 preparation만 완료됐다. 실제 사용자 음성 파일과 provider 준비, 외부 PC 접근이 제공된 뒤 A/B를 실행하고 `development-status`와 release audit protocol의 relevant gate를 갱신한다.
