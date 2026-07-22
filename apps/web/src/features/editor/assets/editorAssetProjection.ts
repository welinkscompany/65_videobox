import { api, type BrollAsset, type MediaLibraryAsset } from "../../../api";

export type EditorAssetKind = "broll" | "bgm" | "sfx";
export type EditorAssetPreviewKind = "audio" | "video" | "image";
export type EditorAssetAudioPresence = "오디오 있음" | "오디오 없음" | "오디오 정보 확인 중";

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
  license: string;
  canApply: boolean;
  previewUrl: string;
  previewKind?: EditorAssetPreviewKind;
  sourceMetadata: EditorAssetSourceMetadata;
}>;

export type EditorAssetFilter = Readonly<{
  type: "all" | EditorAssetKind;
  query: string;
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
    durationLabel: durationLabel(metadata.duration_seconds),
    status: brollStatus(metadata),
    audioPresence: brollAudioPresence(metadata),
    license: "프로젝트 로컬 B-roll",
    canApply: true,
    previewUrl: api.assetContentUrl(projectId, asset.asset_id),
    previewKind: brollPreviewKind(asset.asset_type),
    sourceMetadata: {
      tags: Array.isArray(metadata.tags) ? metadata.tags.filter((tag): tag is string => typeof tag === "string") : [],
      source: "프로젝트 로컬 B-roll",
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
  const prefix = kind === "bgm" ? "BGM" : "SFX";
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

export function projectEditorAssets({ projectId, brollAssets, libraryAssets }: ProjectEditorAssetsInput): EditorAssetCard[] {
  const brollCards = brollAssets.map((asset, index) => projectBroll(projectId, asset, index));
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
