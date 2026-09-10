import { describe, expect, it } from "vitest";
import type { EditorViewModel } from "../editorViewModel";
import { projectInspectorTargets } from "./inspectorRegistry";

const view = {
  projectId: "project-1", sessionId: "session-1", timelineId: "timeline-1", timelineVersion: "v1", expectedRevision: 1, timebase: "seconds",
  fps: { num: 30, den: 1 },
  output: { width: 1080, height: 1920, sampleAspectRatio: "1:1", rotation: 0, durationSec: 10 },
  tracks: [
    { trackId: "narration", role: "narration", clips: [{ clipId: "narration-1", segmentId: "segment-unsupported", type: "narration", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {} }] },
    ...(["broll", "bgm", "sfx"] as const).map((role) => ({
      trackId: role,
      role,
      clips: [{
        clipId: `${role}-1`,
        segmentId: "segment-1",
        type: role,
        assetId: `asset-${role}`,
        assetUri: null,
        startSec: 0,
        endSec: 1,
        controls: {
          fadeInSec: 0.25,
          fadeOutSec: 0.5,
          gainDb: -4,
          ducking: true,
        },
      }],
    })),
    {
      trackId: "overlay", role: "overlay", clips: [
        { clipId: "explanation-1", segmentId: "segment-1", type: "overlay", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: "explanation_card", overlayPayload: { title: "제목", body: "본문", text: "설명" } },
        { clipId: "image-1", segmentId: "segment-1", type: "overlay", assetId: "asset-image", assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: "image_overlay", overlayPayload: { asset_id: "stale-asset", text: "이미지 설명" } },
        // 프리셋을 고른 사진. 안 고른 사진(`image-1`)과 나란히 둔다 -- 둘을 같은
        // 값으로 읽으면 화면에서 "안 고름"이 사라진다.
        { clipId: "image-2", segmentId: "segment-2", type: "overlay", assetId: "asset-image-2", assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: "image_overlay", overlayPayload: { asset_id: "asset-image-2", text: "", vertical: "top", horizontal: "left", size: "small", motion: "slide_in_left" } },
        // 얹은 자산이 사진이 아니라 영상인 경우. 절 이름이 "이미지"로 남아 있으면
        // 방금 얹은 영상을 조정하려는 창작자가 "이미지"를 찾아야 한다.
        { clipId: "image-video-1", segmentId: "segment-3", type: "overlay", assetId: "asset-video", assetUri: "local://projects/p1/assets/clip_1.mp4", startSec: 0, endSec: 1, controls: {}, overlayType: "image_overlay", overlayPayload: { asset_id: "asset-video", text: "" } },
        // 같은 종류(`image_overlay`)라도 사진이면 예전 이름 그대로여야 한다.
        { clipId: "image-photo-1", segmentId: "segment-4", type: "overlay", assetId: "asset-photo", assetUri: "local://projects/p1/assets/photo_1.jpg", startSec: 0, endSec: 1, controls: {}, overlayType: "image_overlay", overlayPayload: { asset_id: "asset-photo", text: "" } },
        { clipId: "table-1", segmentId: "segment-1", type: "overlay", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: "table_overlay", overlayPayload: { columns: ["항목", "값"], rows: [["길이", "10초"]], text: "요약표" } },
        { clipId: "shape-1", segmentId: "segment-1", type: "overlay", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: "shape_overlay", overlayPayload: { shape: "underline", vertical: "bottom", horizontal: "center", size: "large" } },
        { clipId: "unsupported-overlay", segmentId: "segment-1", type: "overlay", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: null },
      ],
    },
  ],
  captions: [{ segmentId: "segment-1", captionId: "caption-1", text: "연결 캡션", startSec: 0, endSec: 1, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0, bold: false, italic: false, letterSpacingPx: 0 } }],
  gaps: [], source: { status: "current" }, playback: { auditionUrls: {}, exactPreview: { status: "unavailable" } }, local: { selectedSegmentId: null, seekSec: 0 },
} satisfies EditorViewModel;

describe("projectInspectorTargets", () => {
  it("projects only port-representable controls that the current runtime honors", () => {
    const targets = projectInspectorTargets({ view, selectedSegmentId: "segment-1" });

    expect(targets).toContainEqual({
      id: "clip:broll-1",
      kind: "media",
      label: "영상",
      segmentId: "segment-1",
      mediaKind: "broll",
      // Task 24: B-roll gets the source window, not the audio fades. Which
      // part of a ten-minute take to use is the one thing the owner adjusts by
      // hand after the recommendation picks a scene.
      // 장면이 바뀔 때 부드럽게 넘어가려면 **화면** 페이드가 필요하다. 예전에는
      // "B-roll에는 소리가 없으니 페이드도 의미 없다"고 뺐는데, 그건 소리 페이드
      // 이야기였다. 겹쳐 놓은 두 클립에서 위에 걸면 아래가 비친다.
      // `소리 크기`는 자체 소리를 살려 둘 때만 뜻이 있으므로 그 스위치를 같이 준다.
      // 갱신 이유(2026-08-23): 색감(`filter`)이 붙었다. 화면이 있는 클립에만
      // 붙으므로 아래 음악·효과음 목록은 그대로다.
      // 갱신 이유(2026-09-01): 손떨림 보정(`stabilize`)이 붙었다. 캡컷 동영상
      // 탭 대조로 들어왔고, 색감과 같은 이유로 화면이 있는 클립에만 붙는다.
      // 같은 날 음조 유지(`preservePitch`)도 붙었다 -- 캡컷 속도 탭 대조.
      // 배속을 걸 수 있는 클립에만 뜻이 있으므로 아래 소리 목록에는 없다.
      // 같은 날 변형 넷(`zoom`/`positionXPercent`/`positionYPercent`/`rotationDeg`)도
      // 붙었다 -- 캡컷 동영상 탭의 `확대·위치·회전`. 클립 전체에 한 번 걸리는
      // 고정 값이고, 임의 키프레임은 계획서가 범위 밖으로 못박은 항목이다.
      fields: ["inSec", "outSec", "speed", "volume", "preserveSourceAudio", "fadeInSec", "fadeOutSec", "filter", "fit", "stabilize", "reduceNoise", "preservePitch", "zoom", "positionXPercent", "positionYPercent", "rotationDeg"],
      assetId: "asset-broll",
      controls: { fadeInSec: 0.25, fadeOutSec: 0.5, gainDb: -4, ducking: true },
      clearOnly: false,
    });
    expect(targets).toContainEqual({
      id: "clip:bgm-1",
      kind: "media",
      label: "배경 음악",
      segmentId: "segment-1",
      mediaKind: "bgm",
      // 덕킹은 **배경 음악에만** 붙는다. 렌더러도 bgm에만 사이드체인을 건다 --
      // 효과음에 스위치를 주면 눌러도 아무 일이 없다.
      // `소리 크기`(gainDb)는 렌더러가 처음부터 읽고 있었다 -- 화면에 자리만 없었다.
      // 갱신 이유(2026-09-01): 소리 정리 둘이 붙었다(캡컷 오디오 탭 대조).
      // 소리가 있는 클립 전부에 붙으므로 아래 효과음 목록에도 같이 들어간다.
      fields: ["fadeInSec", "fadeOutSec", "ducking", "gainDb", "normalizeLoudness", "denoise"],
      assetId: "asset-bgm",
      controls: { fadeInSec: 0.25, fadeOutSec: 0.5, gainDb: -4, ducking: true },
      clearOnly: false,
    });
    expect(targets).toContainEqual({
      id: "clip:sfx-1",
      kind: "media",
      label: "효과음",
      segmentId: "segment-1",
      mediaKind: "sfx",
      fields: ["fadeInSec", "fadeOutSec", "gainDb", "normalizeLoudness", "denoise"],
      assetId: "asset-sfx",
      controls: { fadeInSec: 0.25, fadeOutSec: 0.5, gainDb: -4, ducking: true },
      clearOnly: false,
    });
    expect(targets).toContainEqual({
      id: "caption:caption-1",
      kind: "caption",
      label: "연결 캡션",
      segmentId: "segment-1",
      fields: ["style"],
      style: view.captions[0].style,
    });
  });

  // 사진 오버레이의 자리·크기·움직임(owner 요청 2026-09-06). 도형과 **같은 어휘**를
  // 쓴다 -- 백엔드도 `overlay_shapes`의 목록을 그대로 본떴다.
  it("reads the picture overlay presets the owner already chose", () => {
    const targets = projectInspectorTargets({ view, selectedSegmentId: "segment-2" });

    expect(targets).toContainEqual({
      id: "overlay:image-2",
      kind: "overlay",
      label: "이미지",
      segmentId: "segment-2",
      overlayKind: "image",
      fields: ["assetId", "text", "vertical", "horizontal", "size", "motion"],
      value: { assetId: "asset-image-2", text: "", vertical: "top", horizontal: "left", size: "small", motion: "slide_in_left" },
      bodyNoun: "사진",
    });
  });

  it("projects only the three supported overlay variants with their typed fields", () => {
    const targets = projectInspectorTargets({ view, selectedSegmentId: "segment-1" });

    expect(targets).toContainEqual({
      id: "overlay:explanation-1",
      kind: "overlay",
      label: "설명 카드",
      segmentId: "segment-1",
      overlayKind: "explanation-card",
      fields: ["title", "body", "text"],
      value: { title: "제목", body: "본문", text: "설명" },
    });
    expect(targets).toContainEqual({
      id: "overlay:image-1",
      kind: "overlay",
      label: "이미지",
      segmentId: "segment-1",
      overlayKind: "image",
      fields: ["assetId", "text", "vertical", "horizontal", "size", "motion"],
      // 안 고른 프리셋은 `null`이다. 기본값으로 좁히면 화면이 owner가 고르지도
      // 않은 자리·크기·움직임을 저장마다 실어 보낸다.
      value: { assetId: "asset-image", text: "이미지 설명", vertical: null, horizontal: null, size: null, motion: null },
      bodyNoun: "사진",
    });
    expect(targets).toContainEqual({
      id: "overlay:table-1",
      kind: "overlay",
      label: "표",
      segmentId: "segment-1",
      overlayKind: "table",
      fields: ["columns", "rows", "text"],
      value: { columns: ["항목", "값"], rows: [["길이", "10초"]], text: "요약표" },
    });
    // 정지 도형("여기를 보세요")도 같은 오버레이 체계를 탄다.
    expect(targets).toContainEqual({
      id: "overlay:shape-1",
      kind: "overlay",
      label: "강조 표시",
      segmentId: "segment-1",
      overlayKind: "shape",
      fields: ["shape", "vertical", "horizontal", "size", "motion"],
      // 이 표시는 움직임이 생기기 전에 저장된 것이라 `motion`이 아예 없다.
      // 화면은 그것을 `그대로`로 읽어야 한다 -- 편집기를 여는 것만으로 이미
      // 만들어 둔 표시가 움직이기 시작하면 안 된다.
      value: { shape: "underline", vertical: "bottom", horizontal: "center", size: "large", motion: "none" },
    });
    expect(targets.find((target) => target.id === "overlay:unsupported-overlay")).toBeUndefined();
  });

  it("never projects unsupported voice, effect, or independent caption timing controls", () => {
    const fields = projectInspectorTargets({ view, selectedSegmentId: "segment-1" }).flatMap((target) => target.fields);

    expect(fields).not.toEqual(expect.arrayContaining(["voice", "effect", "keyframe", "mask", "transition", "captionStartSec", "captionEndSec"]));
  });

  it("does not project a media target without the asset required by the command port", () => {
    const assetlessView = {
      ...view,
      tracks: view.tracks.map((track) => track.role === "bgm" ? { ...track, clips: track.clips.map((clip) => ({ ...clip, assetId: null })) } : track),
    } as EditorViewModel;

    expect(projectInspectorTargets({ view: assetlessView, selectedSegmentId: "segment-1" })).not.toContainEqual(expect.objectContaining({ id: "clip:bgm-1" }));
  });

  it("returns no targets without a selection or for a segment the view does not contain", () => {
    expect(projectInspectorTargets({ view, selectedSegmentId: null })).toEqual([]);
    expect(projectInspectorTargets({ view, selectedSegmentId: "segment-not-in-view" })).toEqual([]);
  });

  // 백엔드는 처음부터 upsert였다 -- 없는 오버레이에 저장하면 만들어진다.
  // 화면에만 부르는 자리가 없어서 owner는 설명 카드·표를 새로 얹을 수 없었다.
  it("offers new explanation-card and table targets on a segment that has none", () => {
    const targets = projectInspectorTargets({ view, selectedSegmentId: "segment-unsupported" });

    expect(targets).toContainEqual({
      id: "overlay-new:explanation-card:segment-unsupported",
      kind: "overlay",
      label: "설명 카드",
      segmentId: "segment-unsupported",
      overlayKind: "explanation-card",
      fields: ["title", "body", "text"],
      value: { title: "", body: "", text: "" },
      isNew: true,
    });
    expect(targets).toContainEqual({
      id: "overlay-new:table:segment-unsupported",
      kind: "overlay",
      label: "표",
      segmentId: "segment-unsupported",
      overlayKind: "table",
      fields: ["columns", "rows", "text"],
      value: { columns: [], rows: [], text: "" },
      isNew: true,
    });
    // 정지 도형도 빈 편집 자리를 준다 -- 프리셋뿐이라 자산 없이도 저장이 된다.
    expect(targets).toContainEqual({
      id: "overlay-new:shape:segment-unsupported",
      kind: "overlay",
      label: "강조 표시",
      segmentId: "segment-unsupported",
      overlayKind: "shape",
      fields: ["shape", "vertical", "horizontal", "size", "motion"],
      value: { shape: "highlight_box", vertical: "middle", horizontal: "center", size: "medium", motion: "none" },
      isNew: true,
    });
    // 이미지는 고를 자산 없이 저장할 수 없으므로 빈 이미지 항목은 주지 않는다.
    // 이미지는 자산 목록의 `화면에 얹기`로 만든다 -- 죽은 저장 단추를 두지 않는다.
    expect(targets.filter((target) => target.kind === "overlay" && target.overlayKind === "image")).toEqual([]);
  });

  it("does not duplicate an overlay target the segment already has", () => {
    const targets = projectInspectorTargets({ view, selectedSegmentId: "segment-1" });

    expect(targets.filter((target) => target.id.startsWith("overlay-new:"))).toEqual([]);
  });

  // 사진 움직임은 **사진 한 장짜리 클립에만** 붙는다. 영상에 붙이면 아무 일도
  // 안 하는 칸이 되고, 창작자는 "골랐는데 왜 안 되지"를 본다.
  it("offers photo motion only where a photo is actually placed", () => {
    const withClip = (assetUri: string | null, controls: Record<string, unknown> = {}) => ({
      ...view,
      tracks: view.tracks.map((track) => track.role === "broll"
        ? { ...track, clips: track.clips.map((clip) => ({ ...clip, assetUri, controls })) }
        : track),
    }) as EditorViewModel;
    const brollFieldsOf = (candidate: EditorViewModel) => {
      const target = projectInspectorTargets({ view: candidate, selectedSegmentId: "segment-1" })
        .find((item) => item.id === "clip:broll-1");
      return target && target.kind === "media" ? [...target.fields] : [];
    };

    expect(brollFieldsOf(withClip("/library/aurora-01.JPG"))).toContain("photoMotion");
    expect(brollFieldsOf(withClip("/library/seaside.mp4"))).not.toContain("photoMotion");
    // 원본을 영상으로 바꿔도 **이미 고른 값이 있으면** 칸이 남는다 -- 아니면
    // 되돌릴 자리가 없어진다.
    expect(brollFieldsOf(withClip("/library/seaside.mp4", { photoMotion: "pan_up" }))).toContain("photoMotion");
  });

  // owner 승인 2026-09-06: 조정 칸 이름이 전부 `B-roll ...`로 떠 있었다. 이 저장소는
  // 같은 트랙을 자료실·타임라인·유진 요약에서 이미 `영상`이라 부른다
  // (`TimelineDock.tsx`, `EditorAssetBrowser.tsx`, `EditorWorkbenchRoute.tsx`).
  // `development-fast-path.ko.md` §10.13 -- 화면 글자에 개발 용어를 쓰지 않는다.
  it("names the b-roll clip 영상 on screen, not B-roll", () => {
    const target = projectInspectorTargets({ view, selectedSegmentId: "segment-1" })
      .find((item) => item.id === "clip:broll-1");

    expect(target?.label).toBe("영상");
  });

  // 타임라인 막대는 얹은 영상을 이미 "영상"이라 부른다(`clipNames.ts`,
  // `isVideoAssetUri`). 인스펙터 절 이름이 "이미지"로 남아 있으면 방금 얹은
  // 영상을 조정하려는 창작자가 "이미지"라는 이름을 찾아야 했다.
  // 재검증(2026-09-10)에서 "영상"이 자체 b-roll 클립 라벨과 같은 장면에서
  // 겹치는 것이 실기로 확인돼 "얹은 영상"으로 바꿨다 -- 아래 충돌 테스트 참고.
  it("얹은 것이 영상이면 절 이름이 얹은 영상이다", () => {
    // 영상을 얹어 놓고 조정하려면 "이미지"를 찾아야 했다.
    // 종류(`overlayKind`)와 조절 칸은 그대로다 -- 자리·크기·움직임은 영상에도 같다.
    const targets = projectInspectorTargets({ view, selectedSegmentId: "segment-3" });

    expect(targets).toContainEqual({
      id: "overlay:image-video-1",
      kind: "overlay",
      label: "얹은 영상",
      segmentId: "segment-3",
      overlayKind: "image",
      fields: ["assetId", "text", "vertical", "horizontal", "size", "motion"],
      value: { assetId: "asset-video", text: "", vertical: null, horizontal: null, size: null, motion: null },
      bodyNoun: "영상",
    });
  });

  it("얹은 것이 사진이면 절 이름은 예전 그대로 이미지다", () => {
    const targets = projectInspectorTargets({ view, selectedSegmentId: "segment-4" });

    expect(targets).toContainEqual({
      id: "overlay:image-photo-1",
      kind: "overlay",
      label: "이미지",
      segmentId: "segment-4",
      overlayKind: "image",
      fields: ["assetId", "text", "vertical", "horizontal", "size", "motion"],
      value: { assetId: "asset-photo", text: "", vertical: null, horizontal: null, size: null, motion: null },
      bodyNoun: "사진",
    });
  });

  // 실제 화면 재검증(2026-09-10)에서 발견: 장면이 자기 자신의 b-roll 영상과
  // 그 위에 얹은 영상을 동시에 갖고 있으면 편집 대상 드롭다운에 "영상"이
  // 둘 나왔다 -- 어느 쪽인지 창작자가 구별할 수 없었다. 기존 단위 테스트는
  // 각 대상을 따로따로만 확인해서(장면을 분리해 둔 fixture) 이 조립 결과의
  // 충돌을 못 잡았다. 이 테스트는 한 장면에 둘 다 있는 조립 결과를 만들어
  // 라벨이 겹치지 않는지 직접 본다 -- 특정 문자열이 아니라 "겹치지 않음"을
  // 확인해야 같은 종류의 충돌을 다른 조합에서도 잡는다.
  it("장면에 자체 b-roll 영상과 얹은 영상이 함께 있어도 편집 대상 라벨이 겹치지 않는다", () => {
    const collidingView = {
      ...view,
      tracks: view.tracks.map((track) => {
        if (track.role === "broll") {
          return {
            ...track,
            clips: [{
              clipId: "broll-collide-1", segmentId: "segment-collide", type: "broll" as const, assetId: "asset-broll-collide",
              assetUri: null, startSec: 0, endSec: 1, controls: {},
            }],
          };
        }
        if (track.role === "overlay") {
          return {
            ...track,
            clips: [{
              clipId: "image-video-collide-1", segmentId: "segment-collide", type: "overlay" as const, assetId: "asset-video-collide",
              assetUri: "local://projects/p1/assets/clip_collide.mp4", startSec: 0, endSec: 1, controls: {},
              overlayType: "image_overlay" as const, overlayPayload: { asset_id: "asset-video-collide", text: "" },
            }],
          };
        }
        return track;
      }),
    } satisfies EditorViewModel;

    const targets = projectInspectorTargets({ view: collidingView, selectedSegmentId: "segment-collide" });
    const labels = targets.map((target) => target.label);

    expect(new Set(labels).size).toBe(labels.length);
  });
});
