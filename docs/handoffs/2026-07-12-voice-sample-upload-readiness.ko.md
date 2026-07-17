# 개인 음성 파일 입력 readiness handoff

## 완료

- 설정 화면에서 로컬 음성 파일을 선택해 업로드·등록할 수 있다.
- `POST /api/projects/{project_id}/assets/voice-sample/upload`은 multipart 파일을 project-owned temp path에 chunk 단위로 stage하고 기존 voice-sample registration을 재사용한다.
- `GET /api/projects/{project_id}/assets/voice-sample`로 등록 asset을 복원하므로 새로고침 뒤 TTS candidate에 쓸 ID가 다시 채워진다.
- 기존 `source_path` JSON 등록 endpoint는 데스크톱 호환을 위해 유지한다.

## 검증

- frontend: 86 passed, build success.
- backend Python 3.12: 633 passed (API 389 + non-API 244 split run).
- Korean 600-second smoke: voice sample upload부터 pending-listening TTS, SRT, final MP4, real CapCut까지 13 checks true.

## 남은 사람 작업

1. 실제 본인 음성 파일을 선택·업로드한다.
2. 생성된 TTS 후보를 청취해 승인 또는 거부한다.
3. 이후 별도 slice로 실제 10분 프로젝트 3건의 CapCut open/edit/export UX QA를 수행한다.
