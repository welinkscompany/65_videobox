# 화면이 부르지 않는 웹 API 분류 — 2026-08-24

## 결론

`apps/web/src/api.ts`의 `api` 객체 메서드 **196개**를 TypeScript 구문으로 다시 셌다.
테스트를 뺀 `apps/web/src` 제품 코드에서 직접 호출하거나
`Pick<typeof api, ...>`로 명시해 간접 호출하는 메서드는 **171개**, 정확한 호출이 없는
메서드는 **25개(12.8%)**다.

25개는 다음처럼 나눈다.

| 판단 | 수 | 뜻 |
|---|---:|---|
| 화면에 붙일 것 | 4 | 백엔드 능력이 있는데 현재 화면 흐름에서 복구·미리보기 기능이 실제로 비어 있음 |
| 지울 것 | 13 | 같은 일을 하는 현재 화면 경로가 이미 있거나, 화면이 의도적으로 다른 단일 저장 경로를 씀 |
| 그대로 둘 것 | 8 | 승인 경계, 호환성 계약, 의도적 읽기 전용 또는 승인된 로컬 우선 결정을 보존해야 함 |
| **합계** | **25** | **196 - 171** |

이 문서는 판단만 기록한다. 메서드를 연결하거나 삭제하지 않았다.

## 왜 기존 22개와 다른가

2026-08-23 인계의 **22개**는 이름이 다른 제품 코드에 문자열로 한 번이라도 나오는지를
센 값이다. 정확한 `api.<이름>` 호출을 센 값이 아니다. 다음 세 이름이 거짓 양성이다.

| API 메서드 | 이름 검색이 호출로 잘못 센 이유 |
|---|---|
| `applyDirectorProposal` | `EditorWorkbenchRoute.tsx`에 같은 이름의 화면 내부 함수가 있지만 실제 API 호출은 `batchApplyDirectorProposal`이다. |
| `getLibraryAsset` | 실제 호출인 `getLibraryAssetUsage`의 접두어에 이름이 들어 있다. |
| `getProject` | 실제 호출인 `getProjectWorkspaceSummary`와 `targetProjectId` 같은 더 긴 이름에 들어 있다. |

따라서 **22개는 당시 검색 방식의 결과**, **25개가 현재 정확한 호출 기준의 모수**다.
196이라는 전체 메서드 수는 그대로다.

## 화면에 붙일 것 — 4개

| 메서드 | 현재 빈칸 | 붙일 때 지켜야 할 경계 |
|---|---|---|
| `listSceneImages` | `SceneImageStudio`는 새 장면 이미지만 만들고, 프로젝트에 이미 만든 이미지 목록을 다시 불러오지 않는다. | 새 색·배치를 만들지 말고 기존 자산 선택 흐름에 재사용·이력 조회로 연결한다. |
| `getFootageProposal` | 촬영본 정리 화면은 새 제안을 만든 뒤 React 상태에만 들고 있다. 새로고침하면 제안 ID를 알아도 복구할 경로가 없다. | URL 또는 저장된 현재 제안 ID의 명확한 SSOT를 먼저 정한 뒤 복구에만 쓴다. |
| `previewEditingSessionSelectedRange` | 서버에는 선택 구간 미리보기가 있지만 화면은 현재 전체 편집본용 `startExactPreview`만 부른다. | 별도 미리보기 진실을 만들지 말고 현재 revision fence와 같은 실패·stale 규칙을 쓴다. |
| `previewEditingSessionCaptionStyleScope` | 자막 모양 변경 전에 영향 범위를 보여 주는 서버 사전 확인이 화면에 없다. 화면은 바로 `updateEditingSessionCaptionStyle`을 부른다. | 사전 확인 뒤 기존 단일 저장 경로를 호출한다. 새 자막 저장 경로를 만들지 않는다. |

## 지울 것 — 13개

여기서 “지울 것”은 우선 **`api.ts`의 사용되지 않는 웹 클라이언트 표면**을 뜻한다.
백엔드 경로 삭제는 별도 사용처·호환성 조사가 필요하며 이 문서가 승인하지 않는다.

| 메서드 | 현재 화면의 대체 경로 또는 삭제 근거 |
|---|---|
| `listDirectorMessages` | 편집 화면은 `reloadDirectorSession` 응답의 메시지를 복구해 쓴다. |
| `prepareDirectorMessage` | 화면은 고정된 `client_message_id`로 `sendDirectorMessage`를 다시 호출해 재시도한다. 별도 준비 래퍼가 필요 없다. |
| `applyDirectorProposal` | 화면은 사전 확인 뒤 `batchApplyDirectorProposal` 하나로 적용한다. |
| `getDirectorProposal` | 새 제안은 `createDirectorProposal`, 오래된 제안은 `refreshDirectorProposal`, 세션 복구는 `reloadDirectorSession`이 맡는다. |
| `listMediaLibraryFavorites` | 현재 자산 화면은 프로젝트 범위의 `listProjectMediaLibraryFavorites`를 쓴다. |
| `listRecentMediaLibraryAssetIds` | 현재 자산 화면은 프로젝트 범위의 `listProjectRecentMediaLibraryAssetIds`를 쓴다. |
| `setMediaLibraryFavorite` | 현재 자산 화면은 프로젝트 범위의 `setProjectMediaLibraryFavorite`를 쓴다. |
| `getLibraryAsset` | 현재 목록 응답이 카드·미리보기에 필요한 자산 본문을 주고, 추가 조회는 `getLibraryAssetUsage`만 쓴다. |
| `getProject` | 프로젝트 선택은 `listProjects`, 화면 작업 상태는 `getProjectWorkspaceSummary`가 맡는다. |
| `registerNarrationAudio` | 화면 파일 입력은 업로드 경로를 쓴다. 호스트 `source_path`를 받는 등록 래퍼는 화면 경계와 맞지 않는다. |
| `registerScriptDocument` | 현재 새 영상 흐름은 업로드·초안 경로를 쓴다. 호스트 `source_path` 등록 래퍼는 화면에서 쓰지 않는다. |
| `importBrollBatch` | 현재 자산 화면은 파일을 받는 `ingestLibraryAssets`와 초안 B-roll 업로드 경로를 쓴다. |
| `applyFormatTemplate` | `SavedFormatPicker`는 자막 모양만 화면 값에 넣고 기존 `updateEditingSessionCaptionStyle` 저장 경로를 쓴다. 주석도 이 단일 경로를 의도적으로 고정한다. |

## 그대로 둘 것 — 8개

| 메서드 | 지금 보존해야 하는 이유 | 다시 결정할 조건 |
|---|---|---|
| `createHermesRun` | 승인된 로컬 우선 결정 때문에 현재 화면이 동기식 `sendDirectorMessage`를 쓰는 것이며, 스트리밍 계약 자체를 폐기한 결정은 아니다. | 외부/스트리밍 경로를 다시 열기로 대표가 승인할 때 네 개를 함께 재평가한다. |
| `openHermesRunEvents` | 위와 같다. | 위와 같다. |
| `cancelHermesRun` | 위와 같다. | 위와 같다. |
| `retryHermesRun` | 위와 같다. | 위와 같다. |
| `approveReviewRecommendation` | 검토 화면은 의도적으로 읽기 전용이고 현행 초안은 보류 추천을 만들지 않는다. 다만 다른 경로가 보류 추천을 만들면 내보내기가 막히므로 삭제도 안전하지 않다. | 보류 추천의 제품 생성 경로를 허용할지, 화면에서 승인·거절할지 함께 결정한다. |
| `permanentDeleteLibraryAsset` | 휴지통·복원은 화면에 있지만 영구 삭제는 되돌릴 수 없다. 명시적 대표 결정 없이 버튼을 붙이거나 경로를 없애지 않는다. | 보존 기간, 확인 문구, 사용 중 자산 차단 규칙이 정해질 때 연결 여부를 정한다. |
| `getPreview` | `task22-parity-owners.test.ts`가 저장된 옛 미리보기의 읽기 호환 경로를 의도적으로 보존한다. | 이전 데이터 이관과 호환 종료를 별도 승인할 때만 삭제한다. |
| `getExport` | 같은 시험이 저장된 옛 내보내기의 읽기 호환 경로를 의도적으로 보존한다. | 이전 데이터 이관과 호환 종료를 별도 승인할 때만 삭제한다. |

## 다음 결정 순서

1. 먼저 연결 가치가 분명한 `listSceneImages`와 `getFootageProposal`의 화면 SSOT를 정한다.
2. 선택 구간·자막 영향 범위 미리보기는 현재 exact-preview revision fence를 재사용하는 설계를 먼저 만든다.
3. 삭제 13개는 `api.ts` 래퍼 삭제 시험을 한 묶음씩 RED/GREEN으로 진행한다. 백엔드 삭제와 섞지 않는다.
4. 영구 삭제와 보류 추천 처리는 대표 결정 전까지 그대로 둔다.

## 확인 근거

- 현재 호출 구조: `apps/web/src/api.ts`, `apps/web/src/features/editor/editorCommandPort.ts`
- 현재 화면 경로: `SceneImageStudio.tsx`, `FootageOrganizerPage.tsx`,
  `EditorWorkbenchRoute.tsx`, `MediaLibraryBrowser.tsx`, `TimelineReviewPage.tsx`,
  `SavedFormatPicker.tsx`
- 호환성 가드: `apps/web/src/task22-parity-owners.test.ts`
- 로컬 우선 승인: `docs/decisions/2026-08-05-local-first-assistant-decision.ko.md`
- 기존 조사와 위험 기록: `docs/superpowers/plans/2026-08-10-videobox-consolidated-priorities.md`

이 분류는 정적 소스 조사다. 실제 브라우저에서 버튼을 눌러 본 근거나 대표 인수 결과가 아니다.
