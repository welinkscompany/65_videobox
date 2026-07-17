# VideoBox Creator Workspace 시각 승인 자료

이 폴더는 Slice 0 Task 2의 정적 승인 자료다. 제품 UI나 런타임은 포함하지 않는다.

## 한 페이지 실행 계획

1. `tests/test_ui_prototype_artifacts.py`로 3 화면 × 5 viewport, PNG 해시, 승인 레코드를 요구한다.
2. Pillow 12 major 호환 정책과 로컬 Windows Noto Sans KR Variable 글꼴로 같은 PNG를 결정적으로 생성한다. patch 버전 차이는 provenance 실패 사유가 아니며, PNG SHA와 font SHA가 artifact 자체를 고정한다.
3. manifest가 viewport, RGB mode, 파일 SHA/bytes, 한글 라벨, 측정값과 renderer/font provenance를 기록한다.
4. 사람이 세 화면의 흐름과 편집기 밀도를 보고 승인 또는 거절한다. 승인이 전까지 Task 2 완료와 Task 4 진행은 막힌다.

## 관찰한 RED

`py -m pytest -q tests/test_ui_prototype_artifacts.py` 실행 시 `expected committed prototype manifest`로 1건 실패했다. 이는 산출물 부재를 직접 검증한 의도된 RED다.

리뷰 보강 RED에서는 같은 명령이 create-interview 산출물의 필수 문구(`대본 맥락`, `유진 질문`, `2 / 4`, 응답 보조 행동) 누락으로 실패했다. 이후 manifest의 화면별 필수 라벨 계약을 강화하고 PNG를 재생성했다.

화이트 톤/유진 전환으로 이전 다크 톤/루미 artifact의 시각 의견은 승인을 대신하지 않았다. 현재 manifest aggregate SHA는 2026-07-17 사용자의 명시적 방향 승인으로 **approved**다. artifact aggregate SHA가 바뀌면 새 시안에 대한 명시적 인간 승인이 다시 필요하다.

## 화면과 viewport

- `home-empty`: 프로젝트가 없는 홈과 새 영상 시작점
- `create-interview`: 대본/유진 인터뷰와 승인 전 초안
- `editor-populated`: 자산이 채워진 편집 작업판
- viewport: 1920×1080, 1440×900, 1280×800, 768×1024, 390×844

편집기 규칙은 manifest `measurements`에 선언한다. 1920에서는 양쪽 작업 도구와 720px 이상 미리보기를 보이고, 1280–1599에서는 정확히 하나의 작업 도구와 `max(640px, content의 50%)` 이상 미리보기를 보장한다. 1280 미만에서는 작업 도구로 전환한다.

색상 계약은 manifest `design_tokens`에 고정한다: 따뜻한 white canvas `#FAFAF9`, panel `#FFFFFF`, 부드러운 warm-gray border `#E7E5E4`, charcoal primary `#292524`, secondary `#57534E`, muted indigo accent `#4F46E5`, 그리고 영상 판단을 위한 dark preview `#18181B`. 영상 canvas만 dark로 유지하고 나머지 작업 공간은 white tone으로 둔다.

## 참조 주석과 범위

구조 참조만 기록한다: shadcn-admin은 shell/sidebar 조합, OpenCut classic은 panel/preview/timeline의 기하, Opencast는 transcript/caption 작업 흐름, Supabase Studio는 project/settings/mobile IA의 reference-only다. 이 PNG와 문서는 어느 upstream source도 복사하지 않았고, 주석은 production UI에 들어가지 않는다.

정적 문서 범위만 다룬다. runtime, dependency 설치, provider 호출, Hermes/container, Tailwind/shadcn/router/OpenCut 코드는 시작하지 않는다.

## 검증

`py scripts/build_ui_prototype_artifacts.py --output docs/prototypes/2026-07-17-creator-workspace --verify`는 무결성만 확인한다. `--require-approved`는 `pending` 또는 `rejected` 상태에서 실패하며, 현재의 `approved` record에서는 성공해야 한다. 이 명령은 completion/Task 4 gate에 사용한다.

작업 종료 시 `git diff --check` 및 `git status --short`를 확인한다.
