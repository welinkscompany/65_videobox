# 숏폼 장면 리플 배속 설계

## 결정과 목표

루이스 대표님이 2026-08-24에 결정했다. VideoBox는 선택한 **장면 하나**를 1.5배 또는
2배로 빠르게 만들 때 영상만 빨라지게 두지 않는다. 그 장면의 나레이션·자막·장면에 붙은
B-roll·효과음·오버레이를 함께 줄이고, 뒤 장면을 앞으로 당겨 완성본 길이도 실제로 줄인다.

이 문서의 이름을 “리플 배속”으로 고정한다. 기존 B-roll 개별 `speed`는 같은 타임라인
창 안에서 원본을 더 빨리 읽는 자산 제어값이고, 리플 배속은 편집 세션의 장면 길이와
뒤쪽 시간축을 바꾸는 명령이다. 둘을 같은 필드나 같은 화면 조작으로 섞지 않는다.

## 사용자 동작

1. 편집기에서 장면을 하나 선택한다.
2. 장면 도구막대의 `짧게 만들기`에서 `1.5배` 또는 `2배`를 고른다. `원래 길이`은
   1배로 되돌리는 명시적 선택이다.
3. 확인 문구는 “이 장면과 말·자막을 함께 줄이고, 뒤 장면을 앞으로 당깁니다.”로
   결과를 말한다. 별도 색·배치 변경은 이 기능 범위가 아니다.
4. 한 번의 저장이 성공하면 현재 장면 길이, 뒤 장면 시작 시각, 전체 길이가 갱신된다.
   undo 한 번이면 이전 시간축 전체가 돌아온다.

v1은 장면 단위만 지원한다. 여러 장면 일괄 적용, 임의 숫자 입력, 0.5배 느리게 만들기,
선택 구간의 부분 배속은 범위 밖이다.

## 시간 규칙

선택 장면의 이전 범위를 `[start, end)`라 하고 배속을 `rate`라 한다.

- `new_duration = (end - start) / rate`
- 선택 장면의 시작은 유지하고 끝은 `start + new_duration`이 된다.
- 그 장면 뒤에 있는 모든 편집 세션 segment는 `old_duration - new_duration`만큼 앞으로
  이동한다. 앞 장면은 변하지 않는다.
- 선택 장면의 나레이션 source slice는 같은 말 전체를 `rate`로 재생한다. 단순 trim으로
  끝부분을 버리지 않는다.
- 자막과 장면별 overlay의 시작·끝은 선택 장면의 새 범위에 맞춰 비율로 축소한다.
- 장면에 묶인 B-roll·SFX의 배치 범위도 비율로 축소하고, 음성·영상 재생도 같은
  segment rate를 곱한다.
- 전역 BGM은 1배 재생을 유지한다. 다만 뒤 장면이 이동한 만큼 그 이후 배치는 당기고,
  최종 출력 길이에서 자른다.

장면 B-roll에 기존 개별 `speed`가 있으면 유효 속도는 `segment_rate × broll_speed`다.
v1은 유효 값이 0.25 미만 또는 4 초과가 되면 저장을 거절하고 화면은 이유를 표시한다.
조용한 clamp나 속도 무시는 금지한다.

## 저장·명령 경계

편집 세션 segment에 별도 `ripple_playback_rate`를 저장한다. `media_controls.speed`에
저장하지 않는다. 새 서버 명령은 다음을 하나의 revision-guarded mutation으로 수행한다.

```
setEditingSessionSegmentRippleSpeed(projectId, sessionId, segmentId,
  { rate: 1 | 1.5 | 2, expected_revision })
```

서버는 현재 revision, segment 존재, 유한한 양수 rate, 유효 B-roll 속도, 바뀐 전체
경계의 비음수·비겹침을 확인한다. 성공하면 모든 변경 segment, source slice 및
placement를 하나의 undoable history record에 저장한다. 실패하면 어떤 segment도 바꾸지
않는다.

이미 저장된 세션은 `ripple_playback_rate`가 없으면 1배로 읽는다. 기존 개별 B-roll 배속
동작과 저장값은 바꾸지 않는다.

## 출력 경로

`materialize_editing_session_timeline`이 장면별 rate와 축소된 시각을 canonical timeline에
반영한다. 그 결과 하나만 다음이 함께 소비한다.

- editor playback manifest와 exact preview
- FFmpeg final render: video `setpts`, narration/SFX audio `atempo` 단계
- CapCut draft adapter: 영상·오디오 속도 및 새 target range
- subtitle render: 축소된 caption 시간

따라서 화면에서만 시간을 당기거나, 출력별로 별도 계산을 만들지 않는다. 모든 결과물은
현재 revision을 다시 확인하고, 기존 exact-preview/final/CapCut freshness 규칙으로 stale이
된다.

## 오류와 복구

| 상황 | 결과 |
|---|---|
| 선택 장면 없음 | 버튼을 비활성화한다. |
| 오래된 revision | 기존 충돌 안내를 보여 주고 최신 세션을 다시 읽는다. |
| 기존 B-roll 속도와 합쳐 유효 범위 초과 | 저장하지 않고 어떤 B-roll의 유효 배속이 범위를 넘는지 말한다. |
| 나레이션·자막 source가 없거나 손상 | 저장하지 않는다. 말·자막 없이 영상만 줄이는 대체는 금지한다. |
| 출력 중 세션 변경 | 기존 freshness fence로 preview·MP4·CapCut 결과를 stale 처리한다. |

## 범위 밖

- B-roll 한 클립만 빠르게 읽는 기존 `재생 속도` 기능 변경
- 0.5배 슬로모션, 임의 수치·키프레임·부분 구간 배속
- 대본 문장 생성·삭제·재작성 또는 음성 합성
- 승인된 팔레트·배치 변경, 외부 게시, 컨테이너 네트워크 변경
- 실제 화면 품질·말의 자연스러움·CapCut Desktop 사용성의 자동 완료 주장

## 검증 순서

TDD를 적용한다. 첫 RED는 세 장면 세션에서 가운데 장면을 2배로 할 때 다음을 함께
기대한다.

1. 가운데 장면·나레이션·자막의 길이가 절반이다.
2. 마지막 장면의 시작과 전체 duration이 줄어든 길이만큼 당겨진다.
3. undo/redo가 이전·다음 시간축 전체를 복원한다.
4. 4배 B-roll이 있는 장면에 2배 리플을 요청하면 저장 전 실패하고 세션은 불변이다.
5. materializer, exact preview, FFmpeg MP4, CapCut draft가 같은 장면 경계와 유효 배속을
   받는다.

각 RED/GREEN 뒤 해당 focused 시험을 실행한다. 구현 단위 종료 시 관련 백엔드·웹 시험을
실행하고, 전체 pytest는 단독 실행한다. 화면 문구·배치와 실제 PC/모바일 사용성은 별도
브라우저·대표님 확인으로 남긴다.

## 대안 검토

| 대안 | 장점 | 버린 이유 |
|---|---|---|
| 영상만 빠르게 | 기존 B-roll 속도와 구현이 비슷함 | 나레이션·자막이 어긋나고 대표님 요구와 다름 |
| 전체 프로젝트를 한 번에 빠르게 | 구현 표면이 작음 | 설명 장면·BGM·전환까지 의도 없이 바뀌어 편집 제어를 잃음 |
| **선택 장면 리플 배속** | 말·자막·뒤 시간축을 일관되게 보존하며 되돌릴 수 있음 | session·renderer·CapCut까지 함께 바꿔야 함. 이 문서의 선택 |

## Claude/Codex 전환 시 해야 할 일

도구가 Claude에서 Codex로 바뀌어도 다음 SSOT와 경계는 같다.

1. canonical worktree와 branch, HEAD, `git status --short`, upstream divergence를 확인한다.
2. `CLAUDE.md`, `docs/development-fast-path.ko.md` §10, `CLAUDE.md`가 가리키는 최신
   handoff를 읽는다.
3. UI를 건드리면 `docs/decisions/` 승인 기록을 먼저 읽는다.
4. 이 기능의 spec과 구현 계획을 읽고, RED → GREEN → 관련 회귀 순으로 한 작업 단위만
   진행한다.
5. 전체 pytest는 `.venv\Scripts\python.exe -m pytest`로 단독 실행한다. 웹은
   `apps/web`에서 `npx vitest run`, `npx tsc --noEmit`을 쓴다.
6. 인계 시 실제로 한 일, 검증했지만 끝나지 않은 것, 사람·브라우저 확인이 필요한 것을
   나눠 적고 `CLAUDE.md`의 최신 handoff 포인터를 같이 옮긴다.
7. push, 외부 게시, provider/네트워크 경계 변경은 이 기능 승인에 포함되지 않는다.
