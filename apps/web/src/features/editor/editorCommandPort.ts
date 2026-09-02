import { api, type BrollOverrideRequest, type CaptionOverrideRequest, type CaptionStyleMutationRequest, type CaptionStyleScopePreflight, type EditingSession, type ExplanationCardRequest, type ImageOverlayRequest, type MusicOverrideRequest, type ShapeOverlayMotion, type ShapeOverlayShape, type TableOverlayRequest, type TtsReplacementRequest } from "../../api";
import type { EditorCaptionStyle, EditorControls } from "./editorViewModel";

type Context = Readonly<{ projectId: string; sessionId: string; expectedRevision: number }>;
type MediaKind = "broll" | "bgm" | "sfx";
type MediaCommand = Readonly<{ kind: MediaKind; segmentId: string; assetId: string; controls?: EditorControls }>;
type CandidateAttestation = Readonly<{ proposalId: string; candidateId: string }>;
type OverlayApply =
  | Readonly<{ kind: "explanation-card"; segmentId: string; title: string; body: string; text: string; attestation?: CandidateAttestation }>
  | Readonly<{ kind: "image"; segmentId: string; assetId: string; text: string; attestation?: CandidateAttestation }>
  | Readonly<{ kind: "table"; segmentId: string; columns: string[]; rows: string[][]; text: string; attestation?: CandidateAttestation }>
  // 정지 도형과 아이콘. 유진 attestation 경로는 이번 범위에서 열지 않는다(화면 수동 얹기만).
  | Readonly<{ kind: "shape"; segmentId: string; shape: ShapeOverlayShape; vertical: "top" | "middle" | "bottom"; horizontal: "left" | "center" | "right"; size: "small" | "medium" | "large"; motion: ShapeOverlayMotion }>;
type OverlayClear = Readonly<{ kind: OverlayApply["kind"]; segmentId: string }>;

export type EditorCommandApi = Pick<typeof api,
  "splitEditingSessionSegment" | "mergeEditingSessionSegments" | "updateEditingSessionSegmentBounds" | "updateEditingSessionSegmentRipplePlaybackRate" | "reorderEditingSessionSegments" |
  "updateEditingSessionTimelinePlacements" | "updateEditingSessionTrackStates" | "undoEditingSession" | "redoEditingSession" | "updateEditingSessionCutAction" |
  "updateEditingSessionBroll" | "clearEditingSessionBrollOverride" | "updateEditingSessionMusicOverride" | "clearEditingSessionMusicOverride" |
  "updateEditingSessionSfxOverride" | "clearEditingSessionSfxOverride" | "updateEditingSessionExplanationCard" | "removeEditingSessionExplanationCard" |
  "updateEditingSessionImageOverlay" | "removeEditingSessionImageOverlay" | "updateEditingSessionTableOverlay" | "removeEditingSessionTableOverlay" |
  "updateEditingSessionShapeOverlay" | "removeEditingSessionShapeOverlay" |
  "updateEditingSessionTtsReplacement" | "clearEditingSessionTtsReplacement" |
  "updateEditingSessionCaption" | "updateEditingSessionCaptionStyle" | "previewEditingSessionCaptionStyleScope" | "updateEditingSessionSegmentTransition" |
  "translateEditingSessionCaptions" | "updateEditingSessionCaptionLanguage"
>;

export type EditorCommandPort = Readonly<{
  undo(): Promise<EditingSession>;
  redo(): Promise<EditingSession>;
  setCutAction(input: { segmentId: string; cutAction: "keep" | "remove" }): Promise<EditingSession>;
  /** 앞 장면에서 이 장면으로 넘어오는 방법. `null`이면 끈다.
   *  `chosenBy`를 안 주면 서버가 `owner`로 채운다 -- owner가 직접 고르는
   *  경로는 이 값을 몰라도 되고, 유진 추천을 적용하는 경로만 명시로 넘긴다. */
  setSceneTransition(input: { segmentId: string; transition: { type: string; durationSec: number; chosenBy?: string } | null }): Promise<EditingSession>;
  splitNarration(input: { segmentId: string; splitSec: number }): Promise<EditingSession>;
  mergeNarration(input: { leftSegmentId: string; rightSegmentId: string }): Promise<EditingSession>;
  setNarrationBounds(input: { segmentId: string; startSec: number; endSec: number }): Promise<EditingSession>;
  setSegmentRippleSpeed(input: { segmentId: string; rate: 1 | 1.5 | 2 }): Promise<EditingSession>;
  reorderNarration(input: { segmentIds: string[]; boundsById: Record<string, { startSec: number; endSec: number }> }): Promise<EditingSession>;
  setTimelinePlacements(input: { changes: Array<{ placementId: string; kind: "broll" | "bgm" | "sfx" | "overlay" | "caption"; startSec: number; endSec: number }> }): Promise<EditingSession>;
  /** 트랙 눈·음소거. 보낸 것이 곧 전체 상태다(조각 병합 아님). */
  setTrackStates(states: Record<string, { hidden?: boolean; muted?: boolean }>): Promise<EditingSession>;
  applyMedia(input: MediaCommand): Promise<EditingSession>;
  updateMediaControls(input: MediaCommand): Promise<EditingSession>;
  clearMedia(input: { kind: MediaKind; segmentId: string }): Promise<EditingSession>;
  applyOverlay(input: OverlayApply): Promise<EditingSession>;
  clearOverlay(input: OverlayClear): Promise<EditingSession>;
  applyTtsCandidate(input: { segmentId: string; candidateId: string; assetId: string; attestation?: CandidateAttestation }): Promise<EditingSession>;
  clearTtsCandidate(input: { segmentId: string }): Promise<EditingSession>;
  /** `language`를 주면 **그 번역을 고치고 원본은 안 건드린다.** 화면이 영어를
   *  보여 주는 중이면 반드시 넘겨야 한다 -- 안 넘기면 한국어 원본이 덮인다. */
  setCaptionText(input: { segmentId: string; text: string; language?: string | null; attestation?: CandidateAttestation }): Promise<EditingSession>;
  setCaptionStyle(input: { segmentIds: string[]; scope: CaptionStyleMutationRequest["scope"]; style: EditorCaptionStyle; attestation?: CandidateAttestation }): Promise<EditingSession>;
  previewCaptionStyle(input: { segmentIds: string[]; scope: CaptionStyleMutationRequest["scope"]; style: EditorCaptionStyle }): Promise<CaptionStyleScopePreflight>;
  /** 자막을 그 언어로 옮겨 원본 옆에 쌓고, 그 언어로 내보내게 고른다. */
  translateCaptions(input: { language: string }): Promise<EditingSession>;
  /** 어느 자막으로 내보낼지 고른다. `null`이면 원본. */
  setCaptionLanguage(input: { language: string | null }): Promise<EditingSession>;
}>;

function mediaControls(value: EditorControls | undefined): BrollOverrideRequest["media_controls"] {
  if (!value) return undefined;
  return Object.fromEntries(Object.entries({
    volume: value.volume,
    crop: value.crop,
    speed: value.speed,
    gain_db: value.gainDb,
    fade_in_sec: value.fadeInSec,
    fade_out_sec: value.fadeOutSec,
    ducking: value.ducking,
    fit: value.fit,
    // Task 24: the source window. Read back from the server since Task 18 but
    // never sent, so an inspector edit had nowhere to go.
    in_sec: value.inSec,
    out_sec: value.outSec,
    // **여기 없는 키는 저장할 때마다 사라진다.** 서버는 안 온 키를 기본값으로
    // 되돌리므로, 배속만 고쳐 저장해도 `자체 소리 살리기`가 꺼지고 앞부분
    // 잘라내기가 0으로 돌아간다(2026-08-18 확인). 새 제어를 만들면 반드시
    // 이 목록에도 넣는다 -- 화면에 붙이는 것만으로는 절반이다.
    preserve_source_audio: value.preserveSourceAudio,
    // 색감(`filters.py`). 위 경고를 읽고도 2026-08-23에 여기를 빠뜨려서,
    // 화면에서 고르고 "저장했어요"까지 떴는데 값이 이 자리에서 조용히
    // 버려졌다. 실제 화면에서 눌러 보고 찾았다.
    filter: value.filter,
    loop: value.loop,
    pad: value.pad,
    trim_start_sec: value.trimStartSec,
    // 소리 정리(오디오)와 손떨림 보정(영상). 캡컷 대조로 2026-09-01에 들어왔다 --
    // 위 경고대로 여기 안 넣으면 켜 두고 다른 값을 저장하는 순간 꺼진다.
    normalize_loudness: value.normalizeLoudness,
    denoise: value.denoise,
    stabilize: value.stabilize,
    reduce_noise: value.reduceNoise,
    preserve_pitch: value.preservePitch,
    zoom: value.zoom,
    position_x_percent: value.positionXPercent,
    position_y_percent: value.positionYPercent,
    rotation_deg: value.rotationDeg,
  }).filter(([, item]) => item !== undefined));
}
function captionStyle(style: EditorCaptionStyle): CaptionStyleMutationRequest["style"] {
  return { font_family: style.fontFamily, font_size_px: style.fontSizePx, text_color: style.textColor, outline_color: style.outlineColor, outline_width_px: style.outlineWidthPx, background_color: style.backgroundColor, position_x_percent: style.positionXPercent, position_y_percent: style.positionYPercent, horizontal_align: style.horizontalAlign, safe_area_enabled: style.safeAreaEnabled, shadow_blur_px: style.shadowBlurPx };
}

export function createEditorCommandPort(context: Context, commandApi: EditorCommandApi = api): EditorCommandPort {
  const { projectId, sessionId, expectedRevision } = context;
  const revise = { expected_revision: expectedRevision };
  const applyMedia = (input: MediaCommand) => {
    const payload = { asset_id: input.assetId, media_controls: mediaControls(input.controls), ...revise };
    if (input.kind === "broll") return commandApi.updateEditingSessionBroll(projectId, sessionId, input.segmentId, payload);
    if (input.kind === "bgm") return commandApi.updateEditingSessionMusicOverride(projectId, sessionId, input.segmentId, payload as MusicOverrideRequest);
    return commandApi.updateEditingSessionSfxOverride(projectId, sessionId, input.segmentId, payload);
  };
  return {
    undo: () => commandApi.undoEditingSession(projectId, sessionId, expectedRevision),
    redo: () => commandApi.redoEditingSession(projectId, sessionId, expectedRevision),
    setCutAction: ({ segmentId, cutAction }) => commandApi.updateEditingSessionCutAction(
      projectId,
      sessionId,
      segmentId,
      { cut_action: cutAction, ...revise },
    ),
    setSceneTransition: ({ segmentId, transition }) => commandApi.updateEditingSessionSegmentTransition(
      projectId,
      sessionId,
      segmentId,
      {
        transition: transition ? { type: transition.type, duration_sec: transition.durationSec, ...(transition.chosenBy ? { chosen_by: transition.chosenBy } : {}) } : null,
        ...revise,
      },
    ),
    splitNarration: ({ segmentId, splitSec }) => commandApi.splitEditingSessionSegment(projectId, sessionId, segmentId, { split_sec: splitSec, ...revise }),
    mergeNarration: ({ leftSegmentId, rightSegmentId }) => commandApi.mergeEditingSessionSegments(projectId, sessionId, { left_segment_id: leftSegmentId, right_segment_id: rightSegmentId, ...revise }),
    setNarrationBounds: ({ segmentId, startSec, endSec }) => commandApi.updateEditingSessionSegmentBounds(projectId, sessionId, segmentId, { start_sec: startSec, end_sec: endSec, ...revise }),
    setSegmentRippleSpeed: ({ segmentId, rate }) => commandApi.updateEditingSessionSegmentRipplePlaybackRate(projectId, sessionId, segmentId, { rate, ...revise }),
    reorderNarration: ({ segmentIds, boundsById }) => commandApi.reorderEditingSessionSegments(projectId, sessionId, {
      segment_ids: segmentIds,
      bounds_by_id: Object.fromEntries(Object.entries(boundsById).map(([segmentId, bounds]) => [segmentId, { start_sec: bounds.startSec, end_sec: bounds.endSec }])),
      ...revise,
    }),
    setTimelinePlacements: ({ changes }) => commandApi.updateEditingSessionTimelinePlacements(projectId, sessionId, {
      changes: changes.map((change) => ({ placement_id: change.placementId, kind: change.kind, start_sec: change.startSec, end_sec: change.endSec })),
      ...revise,
    }),
    setTrackStates: (states) => commandApi.updateEditingSessionTrackStates(projectId, sessionId, { track_states: states, ...revise }),
    applyMedia,
    updateMediaControls: applyMedia,
    clearMedia: ({ kind, segmentId }) => kind === "broll" ? commandApi.clearEditingSessionBrollOverride(projectId, sessionId, segmentId, expectedRevision) : kind === "bgm" ? commandApi.clearEditingSessionMusicOverride(projectId, sessionId, segmentId, expectedRevision) : commandApi.clearEditingSessionSfxOverride(projectId, sessionId, segmentId, expectedRevision),
    applyOverlay: (input) => input.kind === "explanation-card" ? commandApi.updateEditingSessionExplanationCard(projectId, sessionId, input.segmentId, { title: input.title, body: input.body, text: input.text, ...(input.attestation ? { proposal_id: input.attestation.proposalId, candidate_id: input.attestation.candidateId } : {}), ...revise } as ExplanationCardRequest) : input.kind === "image" ? commandApi.updateEditingSessionImageOverlay(projectId, sessionId, input.segmentId, { asset_id: input.assetId, text: input.text, ...(input.attestation ? { proposal_id: input.attestation.proposalId, candidate_id: input.attestation.candidateId } : {}), ...revise } as ImageOverlayRequest) : input.kind === "shape" ? commandApi.updateEditingSessionShapeOverlay(projectId, sessionId, input.segmentId, { shape: input.shape, vertical: input.vertical, horizontal: input.horizontal, size: input.size, motion: input.motion, ...revise }) : commandApi.updateEditingSessionTableOverlay(projectId, sessionId, input.segmentId, { columns: input.columns, rows: input.rows, text: input.text, ...(input.attestation ? { proposal_id: input.attestation.proposalId, candidate_id: input.attestation.candidateId } : {}), ...revise } as TableOverlayRequest),
    clearOverlay: (input) => input.kind === "explanation-card" ? commandApi.removeEditingSessionExplanationCard(projectId, sessionId, input.segmentId, expectedRevision) : input.kind === "image" ? commandApi.removeEditingSessionImageOverlay(projectId, sessionId, input.segmentId, expectedRevision) : input.kind === "shape" ? commandApi.removeEditingSessionShapeOverlay(projectId, sessionId, input.segmentId, expectedRevision) : commandApi.removeEditingSessionTableOverlay(projectId, sessionId, input.segmentId, expectedRevision),
    applyTtsCandidate: ({ segmentId, candidateId, assetId, attestation }) => commandApi.updateEditingSessionTtsReplacement(projectId, sessionId, segmentId, { recommendation_id: candidateId, asset_id: assetId, ...(attestation ? { proposal_id: attestation.proposalId, candidate_id: attestation.candidateId } : {}), ...revise } as TtsReplacementRequest),
    clearTtsCandidate: ({ segmentId }) => commandApi.clearEditingSessionTtsReplacement(projectId, sessionId, segmentId, expectedRevision),
    setCaptionText: ({ segmentId, text, language, attestation }) => commandApi.updateEditingSessionCaption(projectId, sessionId, segmentId, { caption_text: text, ...(language ? { language } : {}), ...(attestation ? { proposal_id: attestation.proposalId, candidate_id: attestation.candidateId } : {}), ...revise } as CaptionOverrideRequest),
    setCaptionStyle: ({ segmentIds, scope, style, attestation }) => commandApi.updateEditingSessionCaptionStyle(projectId, sessionId, { segment_ids: segmentIds, scope, style: captionStyle(style), ...(attestation ? { proposal_id: attestation.proposalId, candidate_id: attestation.candidateId } : {}), ...revise } as CaptionStyleMutationRequest),
    previewCaptionStyle: ({ segmentIds, scope, style }) => commandApi.previewEditingSessionCaptionStyleScope(projectId, sessionId, { segment_ids: segmentIds, scope, style: captionStyle(style), ...revise } as CaptionStyleMutationRequest),
    translateCaptions: ({ language }) => commandApi.translateEditingSessionCaptions(projectId, sessionId, { language, ...revise }),
    setCaptionLanguage: ({ language }) => commandApi.updateEditingSessionCaptionLanguage(projectId, sessionId, { language, ...revise }),
  };
}
