# VideoBox Exact Preview Vertical Slice Design

## 결정

Task 12와 Task 13을 하나의 수직 slice로 구현한다. `편집본 미리보기`는 현재 editing-session revision과 source fingerprint에 묶인 FFmpeg proxy만 재생한다. `선택한 클립 보기`는 source audition이며 exact preview와 URL, 상태, 플레이어를 공유하지 않는다.

기존 `FfmpegFinalRenderer`의 timeline/ASS/audio composition을 유일한 합성 truth로 사용한다. exact proxy는 720p H.264/AAC faststart profile과 선택 range의 zero-based PTS만 다르다. 별도 browser compositor, OpenCut renderer, provider, mutation, review approval 또는 CapCut 우회 경로는 만들지 않는다.

## 사용자 경험

PreviewStage는 항상 현재 상태를 보인다: `준비 중`, `만들기`, `편집본 미리보기`, `최신 편집본이 아님`, `만들지 못했어요`. `PreviewCoordinator` 하나가 discriminated `exact`/`audition` mode와 active media를 소유하므로 document에는 언제나 하나의 `<video>` 또는 `<audio>`만 mount한다. URL·freshness·사용자 문구는 두 mode가 분리하지만 player shell은 공유한다. stale/failed/pending 중에는 이전 MP4를 유지하거나 current라고 부르지 않고 recovery action만 보인다. 재생 시간은 `timelineStartSec + media.currentTime`으로 표시하며 burned caption을 다시 화면에 그리지 않는다. transcript/ARIA 상태만 별도로 동기화한다. hover는 metadata/poster만 준비하고 autoplay하지 않으며, scroll/unmount/mode change는 active player를 정지한다.

## durable contract

`ExactPreviewRequest`는 project, session, expected revision, optional `[start,end]`, fixed `proxy_720p_h264_aac_v1` profile을 받는다. proxy/final은 먼저 같은 `CompositionPlan`을 소비한다. plan은 timeline 교차 clip, source in/out, B-roll/overlay visibility, narration/BGM/SFX offset·gain·fade·ducking, canvas/fps/SAR/rotation, clipped ASS cue를 canonical timeline seconds로 가진다. selected range는 plan을 한번만 transform하고 모든 output PTS를 0으로 정규화한다.

fingerprint는 canonical CompositionPlan JSON, session caption payload, 실제 사용 asset SHA와 overlay input, canvas/fps/SAR/rotation, renderer composition version, proxy profile의 SHA-256이다. renderer 직전과 publish 직전에 current session revision/fingerprint를 재검증한다. durable record는 cache key, generation id, fingerprint, range, profile, pending/running/succeeded/failed/obsolete status, artifact URI, claim/created/invalidated time을 보관한다. 동일 current key는 coalesce하고, 새 generation은 이전 generation을 obsolete로 만든다. late worker는 generation/fingerprint fence가 맞을 때만 current artifact pointer를 쓸 수 있다. process restart는 stale running claim을 recover해 새 generation retry 또는 failed state로 전환한다. publication은 temporary file → atomic rename → fenced DB pointer 순서이며 failure/orphan는 cleanup한다. bounded retention은 obsolete/failed artifact를 보존 기간 뒤 제거한다. session/source change는 같은 SQLite transaction에서 즉시 stale로 만든다.

status/content GET도 delivery 직전에 record의 revision/fingerprint와 current CompositionPlan fingerprint를 다시 비교한다. 다르면 한 SQLite transition으로 stale 처리하고 URL 없이 recovery state를 반환하며 Range delivery를 거부한다. profile은 longest edge 720, aspect-ratio-preserving scale/pad, canonical fps/SAR/rotation, `yuv420p`, AAC, `-movflags +faststart`를 고정하고 별도 mov_text subtitle stream은 만들지 않는다. gap/placeholder draft는 read-only proxy를 만들 수 있지만 final/CapCut gate를 변경하지 않으며, unsupported/missing source는 explicit failed/recovery state가 된다.

session ASS cue는 LocalPipelineRunner가 current editing session에서 canonical caption input으로 만들고 CompositionPlan에 전달한다. final render와 proxy는 동일 plan/caption input을 사용한다. audition input은 immutable manifest track clip의 project-scoped content URL, typed `video|audio`, timeline range로만 만들며 coordinator가 exact player를 정지한 뒤 같은 shared player shell에 audition mode를 mount한다; audition 종료/return은 exact state label로만 돌아간다.

## 비목표와 완료 기준

timeline mutation, multi-player coordination beyond PreviewStage, waveform, audition redesign, provider/Hermes, real CapCut acceptance는 이 slice 밖이다. selected range와 full session proxy 모두 실제 ffprobe 가능한 MP4를 만들어야 하며, stale/late completion/isolation/Range와 browser interaction을 계약으로 검증한다. 로컬 acceptance fixture의 10-second 720p cold render <=20s와 warm lookup <=500ms는 실제 값으로 기록하며 초과하면 완료로 주장하지 않는다.
