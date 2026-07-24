import type {
  BrollAsset,
  EditingSession,
  EditingSessionSegment,
  JobRecord,
} from "../api";

export type LoadState = "idle" | "loading" | "ready" | "error";

export type EditingMutationFeedback = {
  kind: "success" | "error";
  message: string;
} | null;

export function formatEditingMutationFeedbackLabel(mutationKey: string): string {
  const mutationParts = mutationKey.split("-");
  const mutationType = mutationParts[mutationParts.length - 1];
  switch (mutationType) {
    case "caption":
      return "자막";
    case "cut":
      return "컷";
    case "broll":
      return "B롤";
    case "music":
      return "음악";
    case "explanation":
      return "설명";
    case "image":
      return "이미지";
    case "table":
      return "표";
    case "tts":
      return "TTS";
    default:
      return "변경";
  }
}
export type RestoredTargetedSegment = Record<string, unknown>;

export const reviewActions = [
  "Approve recommendation",
  "Reject recommendation",
  "Mark for manual edit",
] as const;

export function prettifyJobType(jobType: string) {
  const labels: Record<string, string> = {
    transcription: "전사",
    segment_analysis: "세그먼트",
    broll_recommendation: "B롤 추천",
    music_recommendation: "음악 추천",
    sfx: "효과음",
    timeline_build: "타임라인",
    subtitle_render: "자막",
    preview_render: "미리보기",
    capcut_export: "캡컷",
    broll: "B롤",
    music: "음악",
    manual_review: "수동 검수",
    broll_review_required: "B롤 검수",
    sfx_review_required: "효과음 검수",
    partial_regeneration: "부분 재생성",
  };
  return labels[jobType] ?? jobType.replace(/_/g, " ");
}

export function formatStatusLabel(status: string | null | undefined) {
  if (!status) {
    return "상태 없음";
  }
  const labels: Record<string, string> = {
    active: "사용",
    approved: "승인",
    blocked: "보류",
    cooldown: "대기",
    disabled: "중지",
    draft: "초안",
    error: "오류",
    failed: "실패",
    loading: "로딩",
    pending: "대기",
    ready: "준비",
    review: "검수",
    running: "진행",
    succeeded: "완료",
    "not-started": "미시작",
  };
  return labels[status] ?? status;
}

export function formatJobValue(value: string | null | undefined) {
  if (!value || value === "not-started") {
    return "미시작";
  }
  if (value === "pending") {
    return "대기";
  }
  return value;
}

export function formatSeconds(startSec: number, endSec: number) {
  return `${startSec.toFixed(1)}s - ${endSec.toFixed(1)}s`;
}

export function findLatestTimelineJob(jobs: JobRecord[]) {
  const candidates = jobs
    .filter((job) => job.job_type === "timeline_build" && job.status === "succeeded")
    .sort((left, right) =>
      getLatestJobTimestamp(right).localeCompare(getLatestJobTimestamp(left)),
    );
  return candidates.length > 0 ? candidates[0] : null;
}

export function findLatestSucceededJob(jobs: JobRecord[], jobType: string, inputRef?: string | null) {
  const candidates = jobs
    .filter(
      (job) =>
        job.job_type === jobType &&
        job.status === "succeeded" &&
        (inputRef == null || job.input_ref === inputRef),
    )
    .sort((left, right) =>
      getLatestJobTimestamp(right).localeCompare(getLatestJobTimestamp(left)),
    );
  return candidates.length > 0 ? candidates[0] : null;
}

export function findLatestJob(jobs: JobRecord[], jobType: string, inputRef?: string | null) {
  const candidates = jobs
    .filter((job) => job.job_type === jobType && (inputRef == null || job.input_ref === inputRef))
    .sort((left, right) => getLatestJobTimestamp(right).localeCompare(getLatestJobTimestamp(left)));
  return candidates.length > 0 ? candidates[0] : null;
}

export function getLatestJobTimestamp(job: JobRecord) {
  return job.finished_at ?? job.started_at ?? "";
}

export function canResumeCandidate(
  session: EditingSession,
  candidate: {
    session_id: string;
    session_updated_at?: string | null;
  },
) {
  return (
    candidate.session_id === session.session_id &&
    !!candidate.session_updated_at &&
    candidate.session_updated_at === session.updated_at
  );
}

export function formatDisplayText(value: string | null | undefined) {
  if (!value) {
    return "";
  }
  const normalized = value.trim();
  if (
    normalized.includes("://") ||
    /^\d{4}-\d{2}-\d{2}T/.test(normalized) ||
    /\b[a-z]+_[a-z0-9_]+_\d+\b/i.test(normalized) ||
    /\b(asset|clip|job|rec|seg|timeline|editing_session)_[a-z0-9_]+\b/i.test(normalized)
  ) {
    return normalized;
  }
  const labels: Record<string, string> = {
    "B-roll Smoke Test": "B롤 검수 테스트",
    "Operator Review Demo": "작업자 검수 데모",
    "Office overview": "사무실 개요",
    "Office overview.": "사무실 개요",
    "Team meeting overview": "팀 회의 개요",
    "Team meeting restart.": "팀 회의 재시작",
    "Team meeting overview refreshed": "팀 회의 개요 갱신",
    "Office lobby pan": "사무실 로비 패닝",
    "Office team smoke pan": "사무실 팀 검수 패닝",
    "smoke-office-pan": "사무실 패닝 검수본",
    "Team whiteboard": "팀 화이트보드",
    "team-whiteboard": "팀 화이트보드",
    "factory-line": "공장 라인",
    "Primary routing key": "기본 라우팅 키",
    "Primary routing key v2": "기본 라우팅 키 v2",
    "Fallback cooldown key": "대기 예비 키",
    "Burst quota key": "긴급 할당 키",
    "429 quota exceeded": "429 할당량 초과",
    "Mock CapCut payload written for local post-editing handoff.": "캡컷 초안 생성",
    playable_html_preview: "HTML 미리보기",
    capcut: "캡컷",
  };
  return labels[normalized] ?? formatDisplayTokens(normalized);
}

export function formatDisplayTag(tag: string) {
  const labels = getDisplayTokenLabels();
  return labels[tag] ?? formatDisplayTokens(tag);
}

export function getDisplayTokenLabels(): Record<string, string> {
  return {
    office: "사무실",
    overview: "개요",
    lobby: "로비",
    team: "팀",
    meeting: "회의",
    planning: "기획",
    smoke: "검수",
    "live-smoke": "실사용 검수",
    "live-smoke-final": "최종 실사용 검수",
    "folder-import": "폴더 가져오기",
    broll: "B롤",
    roll: "롤",
    video: "영상",
    pan: "패닝",
    whiteboard: "화이트보드",
    factory: "공장",
    line: "라인",
  };
}

export function formatDisplayTokens(value: string) {
  const labels = getDisplayTokenLabels();
  return value
    .split(/([\s_-]+)/)
    .map((part) => {
      if (/^[\s_-]+$/.test(part)) {
        return " ";
      }
      return labels[part.toLowerCase() as keyof ReturnType<typeof getDisplayTokenLabels>] ?? part;
    })
    .join("")
    .replace(/\s+/g, " ")
    .trim();
}

export function formatBrollAssetTitle(asset: BrollAsset) {
  const title = asset.metadata.title;
  return typeof title === "string" && title.trim() ? formatDisplayText(title) : asset.asset_id;
}

export function formatBrollAssetTags(asset: BrollAsset) {
  const tags = asset.metadata.tags;
  return Array.isArray(tags)
    ? tags.map((tag) => formatDisplayTag(String(tag).trim())).filter(Boolean).join(", ")
    : "";
}

export function formatBrollAssetLabel(asset: BrollAsset) {
  const tags = formatBrollAssetTags(asset);
  return `${formatBrollAssetTitle(asset)} - ${asset.asset_id}${tags ? ` - ${tags}` : ""}`;
}

export function formatStringList(value: unknown) {
  return Array.isArray(value)
    ? value
        .map((item) => String(item).trim())
        .filter(Boolean)
        .map((item) => formatDisplayTag(item))
        .join(", ")
    : "";
}

export type EditingSegmentDraft = {
  captionText: string;
  cutAction: string;
  brollAssetId: string;
  musicAssetId: string;
  sfxAssetId: string;
  explanationTitle: string;
  explanationBody: string;
  explanationText: string;
  imageAssetId: string;
  imageText: string;
  tableColumns: string;
  tableRows: string;
  tableText: string;
  ttsRecommendationId: string;
  ttsAssetId: string;
};

export function readOverlay(segment: EditingSessionSegment, overlayType: string) {
  const overlayTypeAliases: Record<string, string[]> = {
    visual_overlay: ["visual_overlay", "hook_title"],
    image_overlay: ["image_overlay", "image_card", "image"],
    table_overlay: ["table_overlay", "table_card"],
  };
  const acceptedTypes = overlayTypeAliases[overlayType] ?? [overlayType];
  return (
    segment.visual_overlays.find(
      (overlay) => acceptedTypes.includes(String(overlay.overlay_type ?? "")),
    ) ?? null
  );
}

export function createEditingSegmentDraft(segment: EditingSessionSegment): EditingSegmentDraft {
  const explanationCard = readOverlay(segment, "explanation_card");
  const imageOverlay = readOverlay(segment, "image_overlay");
  const tableOverlay = readOverlay(segment, "table_overlay");
  const tableRows = Array.isArray(tableOverlay?.rows)
    ? (tableOverlay.rows as unknown[][])
        .map((row) => row.map((cell) => String(cell ?? "")).join(", "))
        .join("\n")
    : "";
  return {
    captionText: segment.caption_text,
    cutAction: segment.cut_action,
    brollAssetId: String(segment.broll_override?.asset_id ?? ""),
    musicAssetId: String(segment.music_override?.asset_id ?? ""),
    sfxAssetId: String(segment.sfx_override?.asset_id ?? ""),
    explanationTitle: String(explanationCard?.title ?? ""),
    explanationBody: String(explanationCard?.body ?? ""),
    explanationText: String(explanationCard?.text ?? ""),
    imageAssetId: String(imageOverlay?.asset_id ?? ""),
    imageText: String(imageOverlay?.text ?? ""),
    tableColumns: Array.isArray(tableOverlay?.columns)
      ? (tableOverlay.columns as unknown[]).map((column) => String(column ?? "")).join(", ")
      : "",
    tableRows,
    tableText: String(tableOverlay?.text ?? ""),
    ttsRecommendationId: String(segment.tts_replacement?.recommendation_id ?? ""),
    ttsAssetId: String(segment.tts_replacement?.asset_id ?? ""),
  };
}

export function buildEditingDrafts(session: EditingSession) {
  return Object.fromEntries(
    session.segments.map((segment) => [segment.segment_id, createEditingSegmentDraft(segment)]),
  ) as Record<string, EditingSegmentDraft>;
}

export function buildDefaultRegenerationFields(segment: EditingSessionSegment | null) {
  if (!segment) {
    return [] as string[];
  }
  const defaultFields: string[] = [];
  if (segment.broll_override) {
    defaultFields.push("broll");
  }
  if (segment.music_override) {
    defaultFields.push("music");
  }
  if (segment.sfx_override) {
    defaultFields.push("sfx");
  }
  if (readOverlay(segment, "visual_overlay")) {
    defaultFields.push("visual_overlay");
  }
  if (readOverlay(segment, "explanation_card")) {
    defaultFields.push("explanation_card");
  }
  if (readOverlay(segment, "image_overlay")) {
    defaultFields.push("image_overlay");
  }
  if (readOverlay(segment, "table_overlay")) {
    defaultFields.push("table_overlay");
  }
  if (segment.tts_replacement) {
    defaultFields.push("tts_replacement");
  }
  return defaultFields.length > 0 ? defaultFields : ["caption"];
}

export function buildDefaultEditingSelection(session: EditingSession) {
  const selectedSegment =
    session.segments.find(
      (segment) =>
        segment.broll_override ||
        segment.music_override ||
        segment.sfx_override ||
        segment.tts_replacement ||
        segment.visual_overlays.length > 0 ||
        segment.review_required,
    ) ?? session.segments[0] ?? null;
  if (!selectedSegment) {
    return { segmentId: null, fields: [] as string[] };
  }
  return {
    segmentId: selectedSegment.segment_id,
    fields: buildDefaultRegenerationFields(selectedSegment),
  };
}

export function formatFieldLabel(field: string) {
  const labels: Record<string, string> = {
    caption: "자막",
    cut_action: "컷",
    broll: "B롤",
    music: "음악",
    sfx: "효과음",
    visual_overlay: "화면",
    explanation_card: "설명 카드",
    image_overlay: "이미지",
    table_overlay: "표",
    tts_replacement: "TTS",
    timeline_structure: "타임라인 구조",
  };
  return labels[field] ?? field.replace(/_/g, " ");
}

export function mapRecommendationTypeToEditingField(recommendationType: string) {
  if (recommendationType === "tts_replacement") {
    return "tts_replacement";
  }
  if (recommendationType === "broll") {
    return "broll";
  }
  if (recommendationType === "sfx") {
    return "sfx";
  }
  return null;
}

export function haveSameMembers(left: string[], right: string[]) {
  const leftSet = new Set(left);
  const rightSet = new Set(right);
  return (
    left.length === right.length &&
    leftSet.size === rightSet.size &&
    [...leftSet].every((item) => rightSet.has(item))
  );
}

export function findEditingSessionSegmentById(session: EditingSession, segmentId: string) {
  return session.segments.find((item) => item.segment_id === segmentId) ?? null;
}

export function readRecordValue(value: unknown) {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

export function restoredTargetedSegmentsMatch(
  restoredSegments: RestoredTargetedSegment[],
  session: EditingSession,
  matcher: (restoredSegment: RestoredTargetedSegment, currentSegment: EditingSessionSegment) => boolean,
) {
  return restoredSegments.every((segment) => {
    const restoredSegmentId = String(segment.segment_id ?? "");
    if (!restoredSegmentId) {
      return false;
    }
    const currentSessionSegment = findEditingSessionSegmentById(session, restoredSegmentId);
    return !!currentSessionSegment && matcher(segment, currentSessionSegment);
  });
}

export function formatAffectedOutputArea(area: string) {
  const labels: Record<string, string> = {
    "b-roll track": "B롤 트랙",
    "narration track": "내레이션 트랙",
    "overlay track": "화면 표시 트랙",
    "visual overlays": "화면 표시",
    "timeline preview": "타임라인 미리보기",
    "subtitle render": "자막 생성",
    "capcut export": "캡컷 전달",
    "segment copy": "세그먼트 문구",
  };
  return labels[area] ?? area;
}

export function formatWorkflowStep(step: string) {
  const labels: Record<string, string> = {
    broll_refresh: "B롤 갱신",
    overlay_refresh: "화면 표시 갱신",
    segment_refresh: "세그먼트 갱신",
    timeline_build: "타임라인 생성",
  };
  return labels[step] ?? step;
}

export function formatOperatorNote(note: string) {
  const matchedKeywords = note.match(/^Matched keywords:\s*(.+)$/i);
  if (matchedKeywords) {
    return matchedKeywords[1]
      .split(",")
      .map((item) => formatDisplayTag(item.trim()))
      .filter(Boolean)
      .join(" · ");
  }
  const labels: Record<string, string> = {
    "Matched office overview keywords": "사무실 개요",
    "Matched meeting keywords.": "회의",
    "Narration replacement still requires operator confirmation.": "내레이션 확인",
    "Operator should confirm the suggested B-roll pick.": "B롤 확인",
    "Operator should inspect this segment manually.": "수동 확인",
    "Pronunciation restart detected": "재시작 감지",
    "Segment requires operator review before export.": "내보내기 전 확인",
    "source timeline already has unresolved review blockers that rerun will preserve": "기존 보류 유지",
    "selected segments already require operator review, so rerun output stays blocked": "선택 구간 보류",
    "b-roll asset replaced with regenerated recommendation": "B롤 교체",
    "explanation card text refreshed": "설명 카드 갱신",
  };
  return labels[note] ?? note;
}

export function formatReviewFlagCode(code: string) {
  const labels: Record<string, string> = {
    broll_review_required: "B롤 검수",
    segment_review_required: "세그먼트 검수",
    tts_replacement_review_required: "TTS 검수",
  };
  return labels[code] ?? prettifyJobType(code);
}

export function formatSegmentReviewReason(reason: string) {
  const labels: Record<string, string> = {
    restart_keyword: "재촬영 발화 감지",
    low_confidence: "STT 신뢰도 낮음",
    script_mismatch: "대본 불일치",
    narration_silence_gap: "무음 구간 감지",
    narration_retake_duplicate: "반복(재촬영) 구간 감지",
  };
  return labels[reason] ?? prettifyJobType(reason);
}

export function formatTrackLabel(trackType: string) {
  if (trackType === "broll") {
    return "B롤 트랙";
  }
  if (trackType === "narration") {
    return "내레이션 트랙";
  }
  if (trackType === "sfx") {
    return "효과음 트랙";
  }
  if (trackType === "bgm") {
    return "배경음악 트랙";
  }
  if (trackType === "overlay") {
    return "화면 표시 트랙";
  }
  return `${trackType} 트랙`;
}

export function formatPredictedReviewStatusLabel(status: string) {
  if (status === "blocked") {
    return "재검수 보류";
  }
  if (status === "draft") {
    return "재생성 초안";
  }
  return "상태 미확인";
}

export function formatPredictedReviewStatusDescription(status: string) {
  if (status === "blocked") {
    return "보류 · 확인 필요";
  }
  if (status === "draft") {
    return "초안 · 승인 필요";
  }
  return "범위 · 확인 필요";
}

export function formatReviewActionLabel(action: (typeof reviewActions)[number]) {
  if (action === "Approve recommendation") {
    return "추천 승인";
  }
  if (action === "Reject recommendation") {
    return "추천 거절";
  }
  return "수동 편집";
}
