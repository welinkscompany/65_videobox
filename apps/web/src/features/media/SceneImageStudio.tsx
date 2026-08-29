import { useState } from "react";

import { api } from "../../api";
import { Button } from "../../components/ui/button";
import { NativeSelect } from "../../components/ui/native-select";
import { Textarea } from "../../components/ui/textarea";

/** 장면 하나에 얹을 그림을 만드는 자리.
 *
 *  빈 칸으로 두지 않는다 — 그 장면에서 무슨 말을 하는지는 이미 대본이 알고 있고,
 *  owner가 매번 처음부터 쓰게 만들 이유가 없다. 자막을 그대로 깔아 두고 고치게 한다. */
export type SceneImageGap = {
  gapSlotId: string;
  segmentId: string;
  sceneNumber: number;
  sceneText: string;
  durationSec: number;
};

// 서버가 붙여 보낸 이유를 owner의 말로 옮긴다. **꺼진 것과 고장 난 것은 다른 말이다** —
// 2026-08-20에 이 둘이 같은 문구로 보여 켜지지 않은 기능을 결함으로 볼 뻔했다.
const messageByDetail: Record<string, string> = {
  scene_image_generation_unavailable: "그림 만들기가 아직 켜져 있지 않아요.",
  scene_image_generation_blocked: "그림 만드는 프로그램에 닿지 않았어요. 켜져 있는지 확인한 뒤 다시 눌러 주세요.",
  scene_image_generation_timeout: "그림이 제 시간에 안 나왔어요. 잠시 뒤 다시 눌러 주세요.",
  scene_image_prompt_empty: "어떤 그림을 원하는지 먼저 적어 주세요.",
  // 그림 만드는 쪽은 영어로만 알아듣는다. 한국어를 그대로 넣으면 거절하는 게 아니라
  // **전혀 다른 그림**이 나온다 -- 그래서 유진이 먼저 영어로 옮겨 적는다.
  scene_image_prompt_writer_unavailable: "유진이 지금 답하지 못해서 그림 설명을 옮기지 못했어요. 잠시 뒤 다시 눌러 주세요.",
  scene_image_prompt_still_korean: "그림 설명을 옮기지 못했어요. 잠시 뒤 다시 눌러 주세요.",
  scene_image_prompt_needs_english: "그림 설명을 옮길 수 없어요. 잠시 뒤 다시 눌러 주세요.",
  scene_image_ffmpeg_missing: "그림을 장면에 넣지 못했어요. 다시 눌러 주세요.",
};

// 진짜 동영상(Wan) 쪽 오류 문구. `scene_video_` 코드로 온다(owner 결정 2026-08-29 2회차).
const videoMessageByDetail: Record<string, string> = {
  scene_video_generation_unavailable: "AI 영상 만들기가 아직 켜져 있지 않아요.",
  scene_video_generation_blocked: "영상 만드는 프로그램에 닿지 않았어요. 켜져 있는지 확인한 뒤 다시 눌러 주세요.",
  scene_video_generation_timeout: "영상이 제 시간에 안 나왔어요. 잠시 뒤 다시 눌러 주세요.",
  scene_video_prompt_empty: "어떤 영상을 원하는지 먼저 적어 주세요.",
  scene_video_prompt_writer_unavailable: "유진이 지금 답하지 못해서 영상 설명을 옮기지 못했어요. 잠시 뒤 다시 눌러 주세요.",
  scene_video_prompt_needs_english: "영상 설명을 옮길 수 없어요. 잠시 뒤 다시 눌러 주세요.",
  scene_video_ffmpeg_missing: "영상을 장면에 넣지 못했어요. 다시 눌러 주세요.",
};

// 실측(2026-08-29, RTX 5090): 1920x1080 기본값이 약 18분 걸렸다. 2초 간격
// 700회 = 최대 약 23분 -- 실측치에 여유를 둔다.
const SCENE_VIDEO_POLL_INTERVAL_MS = 2000;
const SCENE_VIDEO_POLL_MAX_ATTEMPTS = 700;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function SceneImageStudio({
  projectId,
  gap,
  vertical = false,
  onGenerated,
}: {
  projectId: string;
  gap: SceneImageGap;
  vertical?: boolean;
  onGenerated?: () => void;
}) {
  const [description, setDescription] = useState(gap.sceneText);
  const [isMaking, setIsMaking] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [madeAssetId, setMadeAssetId] = useState<string | null>(null);
  const fieldId = `scene-image-${gap.gapSlotId}`;
  // 진짜 동영상(Wan)은 그림과 **같은 설명 칸을 공유한다** -- 같은 장면을
  // 묘사하는 말이라 owner가 두 번 쓸 이유가 없다. 만드는 방식·시간만 다르다
  // (owner 결정 2026-08-29 2회차, "원래 만든거외에 별도로 만들자").
  const [makeGif, setMakeGif] = useState(false);
  // 빠른 미리보기(owner 요청 2026-08-29, 3회차) -- 실측: preview 약 12초,
  // full(고화질) 약 18~23분. 매번 20분을 기다리지 않고 먼저 가늠해 볼 수 있다.
  const [quality, setQuality] = useState<"preview" | "full">("preview");
  const [isMakingVideo, setIsMakingVideo] = useState(false);
  const [videoStatus, setVideoStatus] = useState<string | null>(null);
  const [madeVideoAssetId, setMadeVideoAssetId] = useState<string | null>(null);
  const [madeGifAssetId, setMadeGifAssetId] = useState<string | null>(null);
  const videoFieldId = `scene-video-gif-${gap.gapSlotId}`;
  const qualityFieldId = `scene-video-quality-${gap.gapSlotId}`;

  async function make() {
    if (!description.trim()) return setStatus("어떤 그림을 원하는지 먼저 적어 주세요.");
    setIsMaking(true);
    setStatus(null);
    try {
      const made = await api.createSceneImage(projectId, {
        prompt: description.trim(),
        segment_id: gap.segmentId,
        gap_slot_id: gap.gapSlotId,
        duration_sec: gap.durationSec,
        vertical,
      });
      setMadeAssetId(made.image_asset_id);
      setStatus("그림을 만들었어요.");
      // 자산이 생긴 것과 그 장면이 채워진 것은 다른 일이다. 초안 준비를 다시
      // 돌려야 공백 목록이 바뀌므로, 만든 쪽이 그 사실을 부모에게 알린다 —
      // 안 알리면 owner는 아무 일도 안 일어난 줄 안다.
      onGenerated?.();
    } catch (error) {
      const detail = (error as { detail?: string | null })?.detail ?? null;
      setStatus((detail && messageByDetail[detail]) ?? "그림을 만들지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    } finally {
      setIsMaking(false);
    }
  }

  async function makeVideo() {
    if (!description.trim()) return setVideoStatus("어떤 영상을 원하는지 먼저 적어 주세요.");
    setIsMakingVideo(true);
    setVideoStatus(
      quality === "preview"
        ? "빠르게 미리 만들고 있어요. 15초 정도 걸려요…"
        : "고화질로 만들고 있어요. 20분 정도 걸릴 수 있어요…",
    );
    setMadeVideoAssetId(null);
    setMadeGifAssetId(null);
    try {
      const started = await api.startSceneVideo(projectId, {
        prompt: description.trim(),
        segment_id: gap.segmentId,
        gap_slot_id: gap.gapSlotId,
        vertical,
        make_gif: makeGif,
        quality,
      });
      for (let attempt = 0; attempt < SCENE_VIDEO_POLL_MAX_ATTEMPTS; attempt += 1) {
        await delay(SCENE_VIDEO_POLL_INTERVAL_MS);
        const current = await api.getSceneVideoStatus(projectId, started.job_id);
        if (current.status === "succeeded" && current.result) {
          setMadeVideoAssetId(current.result.scene_asset_id);
          setMadeGifAssetId(current.result.gif_asset_id);
          setVideoStatus("영상을 만들었어요.");
          // 그림 쪽과 같은 이유 -- 자산이 생긴 것과 장면이 채워진 것은 다른 일이다.
          onGenerated?.();
          return;
        }
        if (current.status === "failed") {
          const detail = current.error_detail;
          setVideoStatus((detail && videoMessageByDetail[detail]) ?? "영상을 만들지 못했어요. 잠시 뒤 다시 눌러 주세요.");
          return;
        }
      }
      setVideoStatus("영상이 제 시간에 안 나왔어요. 잠시 뒤 다시 눌러 주세요.");
    } catch (error) {
      const detail = (error as { detail?: string | null })?.detail ?? null;
      setVideoStatus((detail && videoMessageByDetail[detail]) ?? "영상을 만들지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    } finally {
      setIsMakingVideo(false);
    }
  }

  return (
    <div>
      <label htmlFor={fieldId}>{`${gap.sceneNumber}번째 장면 그림·영상 설명`}</label>
      <Textarea
        id={fieldId}
        rows={2}
        value={description}
        onChange={(event) => setDescription(event.target.value)}
      />
      <Button type="button" disabled={isMaking} onClick={() => void make()}>
        {isMaking ? "이미지 생성 중" : "AI 이미지 생성"}
      </Button>
      {status ? <p role="status">{status}</p> : null}
      {madeAssetId ? (
        <img
          src={api.assetContentUrl(projectId, madeAssetId)}
          alt={`${gap.sceneNumber}번째 장면 그림`}
          width={320}
        />
      ) : null}

      {/* 진짜 동영상(Wan) -- 그림·zoompan과는 별개 자리다(owner 결정
          2026-08-29 2회차). 실측(RTX 5090)으로 고화질이 약 18분 걸려서
          "빈 장면 모두 채우기"에는 안 넣고, 여기서 장면 하나씩 owner가
          직접 고를 때만 쓴다. */}
      <div>
        <label htmlFor={qualityFieldId}>화질</label>
        <NativeSelect
          id={qualityFieldId}
          value={quality}
          onChange={(event) => setQuality(event.target.value as "preview" | "full")}
        >
          <option value="preview">빠르게 (약 15초)</option>
          <option value="full">고화질 (약 20분)</option>
        </NativeSelect>
        <label>
          <input
            type="checkbox"
            id={videoFieldId}
            data-native-control="scene-video-make-gif"
            checked={makeGif}
            onChange={(event) => setMakeGif(event.target.checked)}
          />
          {" "}GIF로 저장
        </label>
        <Button type="button" variant="outline" disabled={isMakingVideo} onClick={() => void makeVideo()}>
          {isMakingVideo ? "영상 생성 중" : "AI 영상 생성"}
        </Button>
        {videoStatus ? <p role="status">{videoStatus}</p> : null}
        {madeVideoAssetId ? (
          <video
            controls
            src={api.assetContentUrl(projectId, madeVideoAssetId)}
            width={320}
            aria-label={`${gap.sceneNumber}번째 장면 영상`}
          />
        ) : null}
        {madeGifAssetId ? (
          <img
            src={api.assetContentUrl(projectId, madeGifAssetId)}
            alt={`${gap.sceneNumber}번째 장면 GIF`}
            width={320}
          />
        ) : null}
      </div>
    </div>
  );
}
