# CapCut Handoff Diagnostics Design

## Goal

사용자가 CapCut draft handoff를 시도하기 전에 현재 Windows PC의 지원 여부와 복구 방법을 확인할 수 있게 한다.

## Decision

기존 `CapCutHandoffService`에 read-only `diagnose()`를 추가한다. 결과는 현재 handoff 상태와 섞지 않는 별도 API response로 제공하며, 프로젝트 생성이나 draft export가 없어도 조회할 수 있다.

## Diagnostic contract

`CapCutHandoffDiagnostics`는 다음 값을 반환한다.

- `status`: `ready` 또는 `failed`
- `installation_path`: 선택된 `CapCut.exe`의 절대 경로 또는 null
- `detected_version`: 선택된 설치 디렉터리 이름 또는 null
- `project_root_path`: 예상 CapCut local project root 절대 경로
- `project_root_exists`: root 존재 여부
- `write_access`: root에 파일을 만들고 즉시 삭제할 수 있는지
- `recovery_message`: failed 상태의 한글 복구 안내 또는 null
- `checked_at`: UTC ISO-8601 시각

`%LOCALAPPDATA%\\CapCut\\Apps`의 versioned `CapCut.exe` 중 가장 높은 숫자 버전을 선택한다. versioned directory가 없으면 root-level `CapCut.exe`를 fallback으로 사용한다. CapCut app 자체를 실행하지 않으며, copy/move/registration도 하지 않는다. 쓰기 판단은 OS ACL만으로 신뢰할 수 없으므로 root에 즉시 삭제되는 임시 file probe를 사용한다.

## Failure boundaries

| Condition | Status | Korean recovery |
| --- | --- | --- |
| `CapCut.exe` 없음 | failed | CapCut 설치를 확인한 뒤 다시 진단 |
| local project root 없음 | failed | CapCut을 한 번 실행해 프로젝트 폴더 생성 후 다시 진단 |
| write probe 실패 | failed | 프로젝트 폴더 권한·디스크 공간 확인 후 다시 진단 |

진단은 실제 handoff를 시도하지 않으므로 source draft 존재 여부, export artifact 상태, CapCut draft content 완전성은 검사하지 않는다.

## API and UI

`GET /api/capcut/handoff-diagnostics`는 diagnostics object를 반환한다. `create_app`의 injected `CapCutHandoffService(local_app_data=...)`를 그대로 사용해 tests가 localhost LLM이나 실제 PC 상태를 호출하지 않게 한다.

웹 출력 패널은 `CapCut 연결 진단` 카드를 표시한다. ready는 설치 버전, 설치 경로, 프로젝트 경로, 쓰기 가능 표시를 보여준다. failed는 검사한 경로와 한글 복구 안내를 보여주고 `다시 진단` 버튼을 제공한다. 프로젝트 또는 export 상태와 무관한 machine-level information이므로 최초 dashboard load 및 button click에서 refresh한다.

## Verification

- backend RED/GREEN: version 선택, 미설치, missing root, denied write, API serialization/injection.
- frontend RED/GREEN: ready display, failed recovery/retry, page reload recovery.
- live: 현재 Windows installation에서 API-equivalent service diagnostics를 실행해 path, version, root, write result를 확인한다.
- full: Python 3.12 pytest, frontend Vitest, production build, SSOT and Git closeout.
