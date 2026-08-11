# VideoBox Codex owner UI recovery closeout

작성일: 2026-08-12
브랜치: `codex/videobox-container-compatibility`

## 현재 기준

- 최신 소스: `5cf1dc34b` (자산 탭 접근성 보강)
- 공식 런타임은 `scripts/owner-ready.ps1`로 재빌드했다.
- worktree clean, origin과 divergence `0 0`.
- `owner-ready -Mode Check -Json`: VideoBox health·데이터·모델·CapCut은 pass. Hermes dashboard는 별도 서비스 미기동으로 blocked이며 VideoBox 런타임 상태와 분리한다.

## 실제 브라우저 증거

- 전용 UI QA 프로젝트: 표시명 `VideoBox UI QA 20260812ㄱ`, ID `videobox-ui-qa-20260812`.
- 브라우저에서 프로젝트 생성, 대본 승인, 파일 선택기 자산 가져오기(잘못된 경로 실패 후 올바른 경로 성공), readiness 재준비, 초안 생성, 편집 미리보기, 검토 승인, 자막·MP4·CapCut draft 출력을 순서대로 실행했다.
- `home/media/editor/review/outputs` × `1920×1080`, `1440×900`, `1366×768`, `1280×800` 총 20개 조합을 재검증했다. 오류와 가로 overflow는 없었다.
- 자체 편집기에서 원본 audition→복귀, 타임라인 선택, 캡션 저장·reload 보존, 미리보기 재생(`duration=5`, `muted=false`, `readyState=4`)을 확인했다.
- 자산 탭은 활성 패널만 `aria-controls`를 갖고 Arrow/Home/End 키로 이동한다. 실제 브라우저에서 포커스와 패널 교체를 재확인했다.

## 산출물·라인리지

- UI QA output MP4: 5초, 1920×1080 H.264/AAC, 48kHz stereo.
- UI QA subtitle SHA-256: `7F00CA7D67B702CF4CEF62058248FF75AA9BC6B9E21E7A88D18869258D6CE546`.
- UI QA final MP4 SHA-256: `EE2403E045431F1463A4A987069CBB4369484846179036E998FD1704A05AD977`.
- CapCut draft content SHA-256: `CA4C15C670394B7088412D06830549492B3F9A9A783F38EF9AE5CDDD14FACC55`.
- 별도 canonical QA lane `videobox-pc-qa-20260811153350`에서는 caption mutation으로 revision 1→2, stale review refresh·approve, subtitle/final/CapCut export까지 확인했고 CapCut Desktop import/open도 통과했다.

## 남은 운영 게이트

자동·브라우저 검증으로 대체하지 않는 owner 작업은 최종 MP4 전체 시청·청취, 자막 타이밍 확인, owner 승인이다. CapCut 컨테이너 handoff registration은 설치 감지 한계로 실패하지만, 호스트 CapCut 9.1.0.3879에서 실제 MP4 import/open과 캡션 표시를 확인했다.

상세 mutation manifest와 이전 인계의 세부 경로·스크린샷은 `artifacts/qa/desktop-owner-ui-recovery/qa-mutation-manifest.json` 및 `docs/handoffs/2026-08-11-videobox-claude-to-codex-handover.ko.md`에 있다.
