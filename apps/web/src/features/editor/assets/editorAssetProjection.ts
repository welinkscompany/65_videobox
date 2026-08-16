import { api, type BrollAsset, type MediaLibraryAsset } from "../../../api";

export type EditorAssetKind = "broll" | "bgm" | "sfx";
export type EditorAssetPreviewKind = "audio" | "video" | "image";
export type EditorAssetAudioPresence = "오디오 있음" | "오디오 없음" | "오디오 정보 확인 중";
/** Derived from the media at intake, not a tag the owner writes. */
export type EditorAssetOrientation = "가로" | "세로" | "정사각";

export type EditorAssetSourceMetadata = Readonly<{
  tags: readonly string[];
  source: string;
  creator: string;
  officialLicenseUrl: string;
  attributionRequired: boolean;
  attributionText: string;
  brollMetadata?: Readonly<Record<string, unknown>>;
}>;

export type EditorAssetCard = Readonly<{
  id: string;
  kind: EditorAssetKind;
  assetId: string;
  libraryAssetId?: string;
  label: string;
  title: string;
  durationLabel: string;
  status: string;
  audioPresence: EditorAssetAudioPresence;
  orientation?: EditorAssetOrientation;
  /** Absent when intake produced no still, so the card keeps its text fallback. */
  thumbnailUrl?: string;
  license: string;
  canApply: boolean;
  previewUrl: string;
  previewKind?: EditorAssetPreviewKind;
  requiresBrowserPreviewPreparation?: boolean;
  sourceMetadata: EditorAssetSourceMetadata;
}>;

export type EditorAssetFilter = Readonly<{
  type: "all" | EditorAssetKind;
  query: string;
  orientation?: "all" | EditorAssetOrientation;
}>;

export type ProjectEditorAssetsInput = Readonly<{
  projectId: string;
  brollAssets: readonly BrollAsset[];
  libraryAssets: readonly MediaLibraryAsset[];
}>;

const brollLabels: Readonly<Record<string, string>> = {
  broll_video: "영상 B-roll",
  broll_image: "이미지 B-roll",
  broll_audio: "오디오 B-roll",
};

function brollPreviewKind(assetType: string): EditorAssetPreviewKind {
  if (assetType === "broll_audio") return "audio";
  if (assetType === "broll_image") return "image";
  return "video";
}

function durationLabel(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "길이 정보 없음";
  return `${Number.isInteger(value) ? value : value.toFixed(1)}초`;
}

function intakeDurationLabel(metadata: Readonly<Record<string, unknown>>): string {
  const value = metadata.duration_sec ?? metadata.duration_seconds;
  const analysis = metadata.analysis_status;
  if ((analysis === "pending" || analysis === "processing" || metadata.review_required === true)
    && (typeof value !== "number" || !Number.isFinite(value))) {
    return "길이 확인 중";
  }
  return durationLabel(value);
}

function brollStatus(metadata: Readonly<Record<string, unknown>>): string {
  const analysis = metadata.analysis_status;
  const base = analysis === "succeeded"
    ? "준비됨"
    : analysis === "pending" || analysis === "processing"
      ? "준비 중"
      : analysis === "failed"
        ? "확인 필요"
        : "확인 중";
  const reviewStatus = metadata.review_required === true
    ? "검토 필요"
    : metadata.review_required === false
      ? "검토 불필요"
      : "검토 상태 확인 중";
  return `${base} · ${reviewStatus}`;
}

function brollOrientation(
  metadata: Readonly<Record<string, unknown>>,
): EditorAssetOrientation | undefined {
  const stored = metadata.orientation;
  if (stored === "가로" || stored === "세로" || stored === "정사각") return stored;
  const width = typeof metadata.width === "number" ? metadata.width : null;
  const height = typeof metadata.height === "number" ? metadata.height : null;
  if (width === null || height === null || width <= 0 || height <= 0) return undefined;
  if (width > height) return "가로";
  if (height > width) return "세로";
  return "정사각";
}

function brollAudioPresence(metadata: Readonly<Record<string, unknown>>): EditorAssetAudioPresence {
  const values = [metadata.audio_present, metadata.has_audio].filter((value): value is boolean => typeof value === "boolean");
  if (values.length === 0 || new Set(values).size !== 1) return "오디오 정보 확인 중";
  return values[0] ? "오디오 있음" : "오디오 없음";
}

function libraryLicense(asset: MediaLibraryAsset): string {
  const license = asset.official_license_url.trim() || "라이선스 정보 없음";
  const attribution = asset.attribution_required
    ? `출처 표기 필요: ${asset.attribution_text.trim() || "표기 문구 확인 필요"}`
    : "출처 표기 불필요";
  const details = `라이선스: ${license} · ${attribution}`;
  if (asset.available && asset.verified) return details;
  if (!asset.official_license_url.trim() && !asset.attribution_required) return "검증 또는 이용 가능 상태 확인 필요";
  return `검증 또는 이용 가능 상태 확인 필요 · ${details}`;
}

function libraryStatus(asset: MediaLibraryAsset): string {
  if (asset.available && asset.verified) return "검증됨 · 이용 가능";
  if (asset.available) return "이용 가능 · 검증 필요";
  if (asset.verified) return "이용 불가 · 검증됨";
  return "이용 불가 · 검증 필요";
}

function projectBroll(projectId: string, asset: BrollAsset, index: number): EditorAssetCard {
  const metadata = asset.metadata ?? {};
  const metadataTitle = typeof metadata.title === "string" ? metadata.title.trim() : "";
  return {
    id: `broll:${asset.asset_id}`,
    kind: "broll",
    assetId: asset.asset_id,
    label: brollLabels[asset.asset_type] ?? "기타 B-roll",
    title: metadataTitle || `B-roll ${index + 1}`,
    // Intake writes `duration_sec`.  `duration_seconds` is the media-pack
    // field and never appears on project b-roll, so reading it always
    // produced "길이 정보 없음".
    durationLabel: intakeDurationLabel(metadata),
    status: brollStatus(metadata),
    audioPresence: brollAudioPresence(metadata),
    orientation: brollOrientation(metadata),
    thumbnailUrl: typeof metadata.thumbnail_uri === "string" && metadata.thumbnail_uri.trim()
      ? api.assetThumbnailUrl(projectId, asset.asset_id)
      : undefined,
    license: "내 영상",
    canApply: metadata.review_required !== true && metadata.analysis_status !== "pending" && metadata.analysis_status !== "processing",
    previewUrl: api.assetContentUrl(projectId, asset.asset_id),
    previewKind: brollPreviewKind(asset.asset_type),
    requiresBrowserPreviewPreparation: asset.asset_type === "broll_video",
    sourceMetadata: {
      tags: Array.isArray(metadata.tags) ? metadata.tags.filter((tag): tag is string => typeof tag === "string") : [],
      source: "내 영상",
      creator: "",
      officialLicenseUrl: "",
      attributionRequired: false,
      attributionText: "",
      brollMetadata: metadata,
    },
  };
}

function projectLibrary(asset: MediaLibraryAsset, index: number): EditorAssetCard {
  const kind = asset.media_type === "music" ? "bgm" : "sfx";
  const prefix = kind === "bgm" ? "배경 음악" : "효과음";
  const availableForUse = asset.available && asset.verified;
  return {
    id: `library:${asset.library_asset_id}`,
    kind,
    assetId: asset.asset_id,
    libraryAssetId: asset.library_asset_id,
    label: prefix,
    title: `${prefix} ${index + 1}`,
    durationLabel: durationLabel(asset.duration_seconds),
    status: libraryStatus(asset),
    audioPresence: "오디오 있음",
    license: libraryLicense(asset),
    canApply: availableForUse,
    previewUrl: api.mediaLibraryPreviewUrl(asset.library_asset_id),
    previewKind: "audio",
    requiresBrowserPreviewPreparation: false,
    sourceMetadata: {
      tags: asset.tags,
      source: asset.source,
      creator: asset.creator,
      officialLicenseUrl: asset.official_license_url,
      attributionRequired: asset.attribution_required,
      attributionText: asset.attribution_text,
    },
  };
}

/**
 * 초안이 빈 자리를 표시하려고 넣는 자산은 고를 수 있는 재료가 아니다.
 * 저장소가 `in_app_only`로 표시하고 합성 계획도 렌더 입력에서 빼는데, 이
 * 목록에만 남아 "B-roll 1"·0초짜리 재료처럼 보였다.
 */
function isInAppPlaceholder(asset: BrollAsset): boolean {
  return (asset.metadata ?? {}).in_app_only === true;
}

export function projectEditorAssets({ projectId, brollAssets, libraryAssets }: ProjectEditorAssetsInput): EditorAssetCard[] {
  // 번호는 걸러낸 뒤에 매긴다. 앞의 것을 숨긴 채 원래 순번을 쓰면 "B-roll 2"로
  // 시작해 owner가 하나를 잃어버렸다고 읽는다.
  const brollCards = brollAssets
    .filter((asset) => !isInAppPlaceholder(asset))
    .map((asset, index) => projectBroll(projectId, asset, index));
  const libraryIndexes = { music: 0, sfx: 0 };
  const libraryCards = libraryAssets.map((asset) => {
    const index = libraryIndexes[asset.media_type];
    libraryIndexes[asset.media_type] += 1;
    return projectLibrary(asset, index);
  });
  return [...brollCards, ...libraryCards];
}

export function filterEditorAssets(cards: readonly EditorAssetCard[], filter: EditorAssetFilter): EditorAssetCard[] {
  const term = filter.query.trim().toLocaleLowerCase();
  return cards.filter((card) => {
    if (filter.type !== "all" && card.kind !== filter.type) return false;
    if (filter.orientation && filter.orientation !== "all" && card.orientation !== filter.orientation) {
      return false;
    }
    if (!term) return true;
    const searchable = [
      card.title,
      card.label,
      card.status,
      card.license,
      card.assetId,
      card.libraryAssetId ?? "",
      ...card.sourceMetadata.tags,
      card.sourceMetadata.source,
      card.sourceMetadata.creator,
      card.sourceMetadata.officialLicenseUrl,
      card.sourceMetadata.attributionText,
      JSON.stringify(card.sourceMetadata.brollMetadata ?? {}),
    ].join(" ").toLocaleLowerCase();
    return searchable.includes(term);
  });
}
