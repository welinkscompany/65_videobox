import type { ShapeOverlayMotion, ShapeOverlayShape } from "../../../api";
import type { EditorCaptionStyle, EditorControls, EditorViewModel } from "../editorViewModel";

type MediaKind = "broll" | "bgm" | "sfx";
type MediaField = "fadeInSec" | "fadeOutSec" | "inSec" | "outSec" | "speed" | "volume" | "ducking" | "preserveSourceAudio" | "gainDb" | "filter" | "fit" | "normalizeLoudness" | "denoise" | "stabilize" | "reduceNoise" | "preservePitch" | "zoom" | "positionXPercent" | "positionYPercent" | "rotationDeg";
type CaptionField = "style";
type ExplanationCardField = "title" | "body" | "text";
type ImageField = "assetId" | "text";
type TableField = "columns" | "rows" | "text";
type ShapeField = "shape" | "vertical" | "horizontal" | "size" | "motion";

// 정지 도형·아이콘("여기를 보세요")의 프리셋. 자유 좌표는 계획서 §4가 범위 밖으로
// 못박았다. 고를 수 있는 이름은 명령 포트(`api.ts`)가 정한 하나뿐이다.
export type { ShapeOverlayMotion, ShapeOverlayShape };

// 화면에 보이는 이름. 내부 이름·유니코드 이름·코드포인트·글꼴 이름은 노출하지
// 않는다(§10.13). 순서가 곧 목록에 보이는 순서다 -- 도형 먼저, 그다음 화살표
// 여덟, 그다음 표시들, 마지막이 뜻을 담은 그림들.
export const SHAPE_OVERLAY_LABELS: Readonly<Record<ShapeOverlayShape, string>> = {
  highlight_box: "강조 상자",
  underline: "밑줄",
  icon_arrow_right: "화살표(오른쪽)",
  icon_arrow_left: "화살표(왼쪽)",
  icon_arrow_up: "화살표(위)",
  icon_arrow_down: "화살표(아래)",
  icon_arrow_up_left: "화살표(왼쪽 위)",
  icon_arrow_up_right: "화살표(오른쪽 위)",
  icon_arrow_down_left: "화살표(왼쪽 아래)",
  icon_arrow_down_right: "화살표(오른쪽 아래)",
  icon_circle: "동그라미",
  icon_check: "체크",
  icon_x: "엑스",
  icon_star: "별",
  icon_warning: "경고",
  icon_pointer: "손가락",
  icon_triangle: "삼각형",
  icon_diamond: "마름모",
  icon_lightbulb: "전구",
  icon_search: "돋보기",
  icon_question: "물음표",
  icon_exclamation: "느낌표",
  icon_lock: "자물쇠",
  icon_clock: "시계",
  icon_calendar: "달력",
  icon_location: "위치",
  icon_heart: "하트",
  icon_thumb_up: "엄지척",
  icon_money: "돈",
  icon_trend_up: "오름세",
  icon_trend_down: "내림세",
  icon_cart: "장바구니",
};

export const SHAPE_OVERLAY_CHOICES = Object.keys(SHAPE_OVERLAY_LABELS) as readonly ShapeOverlayShape[];

// 표시가 어떻게 나타나고 사라지는가. 화면에 보이는 이름은 쉬운 말만 쓴다(§10.13) --
// `알파`·`페이드`·`키프레임` 같은 내부 용어는 여기 오지 않는다.
//
// 목록이 짧은 것이 실수가 아니다. 승인 범위(2026-08-20 5항)는 "오버레이 하나가
// 등장·퇴장·이동하는 정도"까지이며, 고르기 쉬운 정도로 유지하라는 조건이 붙어
// 있다. 시간이나 세기를 정하는 칸을 여기 더하면 그게 곧 범위 밖의 키프레임
// 편집기가 된다.
export const SHAPE_OVERLAY_MOTION_LABELS: Readonly<Record<ShapeOverlayMotion, string>> = {
  none: "그대로",
  fade_in: "천천히 나타나기",
  fade_out: "천천히 사라지기",
  fade_in_out: "나타났다 사라지기",
  slide_in_left: "왼쪽에서 밀려 들어오기",
  slide_in_right: "오른쪽에서 밀려 들어오기",
};

export const SHAPE_OVERLAY_MOTION_CHOICES = Object.keys(SHAPE_OVERLAY_MOTION_LABELS) as readonly ShapeOverlayMotion[];

export type ShapeOverlayVertical = "top" | "middle" | "bottom";
export type ShapeOverlayHorizontal = "left" | "center" | "right";
export type ShapeOverlaySize = "small" | "medium" | "large";
export type ShapeOverlayValue = Readonly<{
  shape: ShapeOverlayShape;
  vertical: ShapeOverlayVertical;
  horizontal: ShapeOverlayHorizontal;
  size: ShapeOverlaySize;
  motion: ShapeOverlayMotion;
}>;

export type InspectorTarget =
  | Readonly<{ id: string; kind: "media"; label: string; segmentId: string; mediaKind: MediaKind; fields: readonly MediaField[]; assetId: string; controls: EditorControls; clearOnly: boolean }>
  | Readonly<{ id: string; kind: "caption"; label: string; segmentId: string; fields: readonly CaptionField[]; style: EditorCaptionStyle }>
  // `isNew`: 이 장면에 아직 없는 오버레이의 빈 편집 자리다. 저장은 백엔드
  // upsert가 그대로 만들어 주고, 아직 없는 것에는 `지우기`를 보이지 않는다.
  | Readonly<{ id: string; kind: "overlay"; label: string; segmentId: string; overlayKind: "explanation-card"; fields: readonly ExplanationCardField[]; value: Readonly<{ title: string; body: string; text: string }>; isNew?: boolean }>
  | Readonly<{ id: string; kind: "overlay"; label: string; segmentId: string; overlayKind: "image"; fields: readonly ImageField[]; value: Readonly<{ assetId: string; text: string }>; isNew?: boolean }>
  | Readonly<{ id: string; kind: "overlay"; label: string; segmentId: string; overlayKind: "table"; fields: readonly TableField[]; value: Readonly<{ columns: string[]; rows: string[][]; text: string }>; isNew?: boolean }>
  | Readonly<{ id: string; kind: "overlay"; label: string; segmentId: string; overlayKind: "shape"; fields: readonly ShapeField[]; value: ShapeOverlayValue; isNew?: boolean }>;

// 2026-08-19: `소리 크기`(gainDb)가 화면에 들어왔다. 예전에는 "입력 자리를 주면
// owner가 정하지 않은 값이 저장마다 실린다"고 뺐는데, 슬라이더는 저장된 값에서
// 시작하므로 손대지 않은 저장이 값을 옮기지 않는다. 렌더러는 처음부터 클립별
// gain_db를 반영하고 있었다(`ffmpeg_final_renderer`) -- 화면에 자리만 없었다.
// 소리 정리 둘(`normalizeLoudness`·`denoise`)은 **소리가 있는 클립 전부**에
// 붙는다 -- 캡컷 오디오 탭 대조(2026-09-01). 캡컷은 유료 클라우드 AI로 파는데
// 우리는 FFmpeg 필터 하나씩이면 된다(`loudnorm`·`afftdn`).
const mediaFields = ["fadeInSec", "fadeOutSec", "gainDb", "normalizeLoudness", "denoise"] as const;
// 배경 음악만 내레이션 밑으로 비켜설 수 있다. 렌더러가 사이드체인 압축을
// **bgm에만** 걸기 때문이다(`ffmpeg_final_renderer`) -- 효과음에 스위치를 주면
// 눌러도 아무 일이 없는 단추가 된다.
const bgmFields = ["fadeInSec", "fadeOutSec", "ducking", "gainDb", "normalizeLoudness", "denoise"] as const;
// Task 24: B-roll carries no audio by default, so fades are meaningless for it.
// What the owner actually corrects is which slice of a long take gets used --
// the recommendation picks a scene window, this is where that is overridden.
// Phone B-roll is routinely too long and too loud, so the clip carries a
// source window, a rate, and its own loudness.
//
// 2026-08-18: 페이드가 다시 들어왔다. 위 문장은 **소리** 페이드 이야기였고,
// 여기 것은 **화면** 페이드다 -- 겹쳐 놓은 두 클립에서 위에 걸면 아래가 비쳐
// 장면이 부드럽게 바뀐다(디졸브). 렌더러가 알파를 태워 실제로 그렇게 그린다.
//
// 2026-08-18: `소리 크기` 옆에 **자체 소리를 살릴지**가 함께 있어야 한다. 렌더러는
// 그 스위치가 켜져 있을 때만 이 클립의 소리를 섞는데, 켜는 자리가 없어서 음량이
// 영영 아무 일도 하지 못했다. 순서도 소리 크기 바로 뒤에 둔다 -- 떨어뜨려 놓으면
// 둘이 한 벌이라는 게 보이지 않는다.
// 색감은 **화면이 있는 클립에만**. 음악·효과음에는 칠할 그림이 없다.
// `stabilize`(손떨림 보정)는 화면이 있는 클립에만. 캡컷 동영상 탭 대조로
// 2026-09-01에 들어왔다 -- FFmpeg `deshake`(단일 패스)라 렌더가 안 느려진다.
const brollFields = ["inSec", "outSec", "speed", "volume", "preserveSourceAudio", "fadeInSec", "fadeOutSec", "filter", "fit", "stabilize", "reduceNoise", "preservePitch", "zoom", "positionXPercent", "positionYPercent", "rotationDeg"] as const;
const mediaLabels = { broll: "B-roll", bgm: "배경 음악", sfx: "효과음" } as const;

function isMediaKind(role: EditorViewModel["tracks"][number]["role"]): role is MediaKind {
  return role === "broll" || role === "bgm" || role === "sfx";
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function stringRows(value: unknown): string[][] {
  return Array.isArray(value)
    ? value.filter(Array.isArray).map((row) => row.filter((item): item is string => typeof item === "string"))
    : [];
}

// 저장된 값이 프리셋 밖이면 조용히 기본값으로 좁힌다 -- 백엔드가 프리셋만
// 저장하므로 실제로는 방어선일 뿐이다.
export function shapeValue(value: unknown): ShapeOverlayShape {
  return SHAPE_OVERLAY_CHOICES.find((choice) => choice === value) ?? "highlight_box";
}

function shapeVertical(value: unknown): ShapeOverlayVertical {
  return value === "top" || value === "bottom" ? value : "middle";
}

function shapeHorizontal(value: unknown): ShapeOverlayHorizontal {
  return value === "left" || value === "right" ? value : "center";
}

function shapeSize(value: unknown): ShapeOverlaySize {
  return value === "small" || value === "large" ? value : "medium";
}

// 이 기능이 생기기 전에 저장된 표시에는 이 값이 **아예 없다.** 그때 `그대로`로
// 읽어야 편집기를 여는 것만으로 이미 만들어 둔 표시가 움직이기 시작하지 않는다.
export function shapeMotion(value: unknown): ShapeOverlayMotion {
  return SHAPE_OVERLAY_MOTION_CHOICES.find((choice) => choice === value) ?? "none";
}

export function projectInspectorTargets({ view, selectedSegmentId }: Readonly<{ view: EditorViewModel; selectedSegmentId: string | null }>): readonly InspectorTarget[] {
  if (!selectedSegmentId) return [];

  const mediaTargets = view.tracks.flatMap((track) => {
    const mediaKind = track.role;
    if (!isMediaKind(mediaKind)) return [];
    return track.clips
      .filter((clip) => clip.segmentId === selectedSegmentId && clip.type === mediaKind && clip.assetId !== null)
      .map((clip) => ({
        id: `clip:${clip.clipId}`,
        kind: "media" as const,
        label: mediaLabels[mediaKind],
        segmentId: selectedSegmentId,
        mediaKind,
        fields: mediaKind === "broll" ? brollFields : mediaKind === "bgm" ? bgmFields : mediaFields,
        assetId: clip.assetId!,
        controls: clip.controls,
        clearOnly: false,
      }));
  });
  const captionTargets = view.captions
    .filter((caption) => caption.segmentId === selectedSegmentId)
    .map((caption) => ({
      id: `caption:${caption.captionId ?? caption.segmentId}`,
      kind: "caption" as const,
      label: "연결 자막",
      segmentId: selectedSegmentId,
      fields: ["style"] as const,
      style: caption.style,
    }));
  const overlayTargets = view.tracks
    .filter((track) => track.role === "overlay")
    .flatMap((track) => track.clips.filter((clip) => clip.segmentId === selectedSegmentId && clip.type === "overlay"))
    .flatMap((clip): readonly InspectorTarget[] => {
      const payload = clip.overlayPayload ?? {};
      if (clip.overlayType === "explanation_card") return [{
        id: `overlay:${clip.clipId}`, kind: "overlay", label: "설명 카드", segmentId: selectedSegmentId, overlayKind: "explanation-card", fields: ["title", "body", "text"],
        value: { title: stringValue(payload.title), body: stringValue(payload.body), text: stringValue(payload.text) },
      }];
      if (clip.overlayType === "image_overlay") return [{
        id: `overlay:${clip.clipId}`, kind: "overlay", label: "이미지", segmentId: selectedSegmentId, overlayKind: "image", fields: ["assetId", "text"],
        value: { assetId: clip.assetId ?? stringValue(payload.asset_id), text: stringValue(payload.text) },
      }];
      if (clip.overlayType === "table_overlay") return [{
        id: `overlay:${clip.clipId}`, kind: "overlay", label: "표", segmentId: selectedSegmentId, overlayKind: "table", fields: ["columns", "rows", "text"],
        value: { columns: stringList(payload.columns), rows: stringRows(payload.rows), text: stringValue(payload.text) },
      }];
      if (clip.overlayType === "shape_overlay") return [{
        id: `overlay:${clip.clipId}`, kind: "overlay", label: "강조 표시", segmentId: selectedSegmentId, overlayKind: "shape", fields: ["shape", "vertical", "horizontal", "size", "motion"],
        value: { shape: shapeValue(payload.shape), vertical: shapeVertical(payload.vertical), horizontal: shapeHorizontal(payload.horizontal), size: shapeSize(payload.size), motion: shapeMotion(payload.motion) },
      }];
      return [];
    });

  // 2026-08-20: 없는 오버레이를 얹을 자리. 백엔드 upsert는 처음부터 만들 수
  // 있었는데("부품은 있는데 부르는 자리가 없다") 화면에는 이미 있는 오버레이의
  // 편집 자리만 있었다. 이미지는 여기 넣지 않는다 -- 고를 자산 없이는 저장이
  // 영영 잠긴 죽은 자리가 되므로, 이미지는 자산 목록의 `화면에 얹기`로 만든다.
  const segmentExists = view.tracks.some((track) => track.clips.some((clip) => clip.segmentId === selectedSegmentId));
  const presentOverlayKinds = new Set(
    overlayTargets.flatMap((target) => (target.kind === "overlay" ? [target.overlayKind] : [])),
  );
  const newOverlayTargets: InspectorTarget[] = [];
  if (segmentExists && !presentOverlayKinds.has("explanation-card")) newOverlayTargets.push({
    id: `overlay-new:explanation-card:${selectedSegmentId}`, kind: "overlay", label: "설명 카드", segmentId: selectedSegmentId, overlayKind: "explanation-card", fields: ["title", "body", "text"],
    value: { title: "", body: "", text: "" }, isNew: true,
  });
  if (segmentExists && !presentOverlayKinds.has("table")) newOverlayTargets.push({
    id: `overlay-new:table:${selectedSegmentId}`, kind: "overlay", label: "표", segmentId: selectedSegmentId, overlayKind: "table", fields: ["columns", "rows", "text"],
    value: { columns: [], rows: [], text: "" }, isNew: true,
  });
  // 정지 도형은 프리셋뿐이라 자산 없이도 저장이 되므로 빈 자리를 준다.
  if (segmentExists && !presentOverlayKinds.has("shape")) newOverlayTargets.push({
    id: `overlay-new:shape:${selectedSegmentId}`, kind: "overlay", label: "강조 표시", segmentId: selectedSegmentId, overlayKind: "shape", fields: ["shape", "vertical", "horizontal", "size", "motion"],
    value: { shape: "highlight_box", vertical: "middle", horizontal: "center", size: "medium", motion: "none" }, isNew: true,
  });

  return [...mediaTargets, ...captionTargets, ...overlayTargets, ...newOverlayTargets];
}
