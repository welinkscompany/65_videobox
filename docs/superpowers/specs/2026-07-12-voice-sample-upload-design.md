# Voice Sample Upload Design

## Goal

사용자가 브라우저에서 로컬 음성 파일을 선택해 프로젝트의 voice sample asset으로 등록하고, 기존 personal-voice TTS 후보 생성과 human listening approval 흐름을 그대로 사용할 수 있게 한다.

## Decision

`multipart/form-data` upload endpoint가 파일명을 안전한 basename으로 정규화해 프로젝트 전용 임시 업로드 폴더에 저장한 뒤, 기존 `register_voice_sample_asset`를 호출한다. 등록 성공·실패와 무관하게 임시 파일은 정리한다. 기존 JSON `source_path` endpoint는 데스크톱 호환 경로로 남긴다.

브라우저 microphone recording, 외부 URL 다운로드, 다중 파일 batch upload는 이번 범위에 포함하지 않는다.

## Contracts

- 빈 파일명, 빈 파일, 허용되지 않은 확장자는 `400`으로 거부한다. 최대 128 MiB이며 서버는 1 MiB chunk로 stage한다.
- 업로드 성공은 기존 `AssetResponse`를 반환하며 asset type은 `voice_sample_audio`다.
- UI는 선택 파일명, 업로드 진행 상태, 실패 메시지를 표시한다.
- 성공한 asset ID는 TTS candidate voice-sample ID에 자동 반영되며 새로고침 후 기존 candidate API 사용에 필요한 ID를 사용자가 확인할 수 있다.
- deterministic API test는 실제 localhost LLM/TTS provider를 호출하지 않는다.
