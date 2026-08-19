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
        { clipId: "table-1", segmentId: "segment-1", type: "overlay", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: "table_overlay", overlayPayload: { columns: ["항목", "값"], rows: [["길이", "10초"]], text: "요약표" } },
        { clipId: "unsupported-overlay", segmentId: "segment-1", type: "overlay", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {}, overlayType: null },
      ],
    },
  ],
  captions: [{ segmentId: "segment-1", captionId: "caption-1", text: "연결 자막", startSec: 0, endSec: 1, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0 } }],
  gaps: [], source: { status: "current" }, playback: { auditionUrls: {}, exactPreview: { status: "unavailable" } }, local: { selectedSegmentId: null, seekSec: 0 },
} satisfies EditorViewModel;

describe("projectInspectorTargets", () => {
  it("projects only port-representable controls that the current runtime honors", () => {
    const targets = projectInspectorTargets({ view, selectedSegmentId: "segment-1" });

    expect(targets).toContainEqual({
      id: "clip:broll-1",
      kind: "media",
      label: "B-roll",
      segmentId: "segment-1",
      mediaKind: "broll",
      // Task 24: B-roll gets the source window, not the audio fades. Which
      // part of a ten-minute take to use is the one thing the owner adjusts by
      // hand after the recommendation picks a scene.
      // 장면이 바뀔 때 부드럽게 넘어가려면 **화면** 페이드가 필요하다. 예전에는
      // "B-roll에는 소리가 없으니 페이드도 의미 없다"고 뺐는데, 그건 소리 페이드
      // 이야기였다. 겹쳐 놓은 두 클립에서 위에 걸면 아래가 비친다.
      // `소리 크기`는 자체 소리를 살려 둘 때만 뜻이 있으므로 그 스위치를 같이 준다.
      fields: ["inSec", "outSec", "speed", "volume", "preserveSourceAudio", "fadeInSec", "fadeOutSec"],
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
      fields: ["fadeInSec", "fadeOutSec", "ducking", "gainDb"],
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
      fields: ["fadeInSec", "fadeOutSec", "gainDb"],
      assetId: "asset-sfx",
      controls: { fadeInSec: 0.25, fadeOutSec: 0.5, gainDb: -4, ducking: true },
      clearOnly: false,
    });
    expect(targets).toContainEqual({
      id: "caption:caption-1",
      kind: "caption",
      label: "연결 자막",
      segmentId: "segment-1",
      fields: ["style"],
      style: view.captions[0].style,
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
      fields: ["assetId", "text"],
      value: { assetId: "asset-image", text: "이미지 설명" },
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
    // 이미지는 고를 자산 없이 저장할 수 없으므로 빈 이미지 항목은 주지 않는다.
    // 이미지는 자산 목록의 `화면에 얹기`로 만든다 -- 죽은 저장 단추를 두지 않는다.
    expect(targets.filter((target) => target.kind === "overlay" && target.overlayKind === "image")).toEqual([]);
  });

  it("does not duplicate an overlay target the segment already has", () => {
    const targets = projectInspectorTargets({ view, selectedSegmentId: "segment-1" });

    expect(targets.filter((target) => target.id.startsWith("overlay-new:"))).toEqual([]);
  });
});
