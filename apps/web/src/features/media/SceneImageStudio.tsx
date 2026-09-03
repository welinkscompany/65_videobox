import { useEffect, useState } from "react";

import { api, type SceneVideoQuality } from "../../api";
import { Button } from "../../components/ui/button";
import { NativeSelect } from "../../components/ui/native-select";
import { Textarea } from "../../components/ui/textarea";
import { pollJobUntilTerminal } from "../../lib/pollJob";

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
  // 취소 버튼(owner 요청 2026-08-29 3회차) -- 실패가 아니라 owner의 명시적 선택이다.
  scene_video_cancelled: "취소했어요.",
};

// 실측(2026-08-29, RTX 5090): 1920x1080 기본값이 약 18분 걸렸다. 2초 간격
// 700회 = 최대 약 23분 -- 실측치에 여유를 둔다.
const SCENE_VIDEO_POLL_INTERVAL_MS = 2000;
const SCENE_VIDEO_POLL_MAX_ATTEMPTS = 700;

// owner 요청(2026-08-29 3회차): 20분 가까이 걸리는 작업인데 화면 상태에만
// job_id가 있으면 새로고침하거나 다른 화면에 갔다 오는 순간 진행 상황을
// 놓친다 -- 실제 생성 자체는 서버에서 계속 도는데 화면만 그 사실을 모르게
// 된다. `readActiveDrawer`(편집기 도크)와 같은 방어적 패턴 -- 저장이 막혀도
// (사생활 모드 등) 조용히 새로 시작한다.
function sceneVideoJobStorageKey(gapSlotId: string): string {
  return `videobox.scene-video-job.${gapSlotId}`;
}
function readPendingSceneVideoJob(gapSlotId: string): { projectId: string; jobId: string } | null {
  try {
    const raw = window.localStorage.getItem(sceneVideoJobStorageKey(gapSlotId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { projectId?: unknown; jobId?: unknown };
    if (typeof parsed.projectId !== "string" || typeof parsed.jobId !== "string") return null;
    return { projectId: parsed.projectId, jobId: parsed.jobId };
  } catch {
    return null;
  }
}
function writePendingSceneVideoJob(gapSlotId: string, projectId: string, jobId: string): void {
  try {
    window.localStorage.setItem(sceneVideoJobStorageKey(gapSlotId), JSON.stringify({ projectId, jobId }));
  } catch {
    // 이 화면 전용 편의 기능이다. 저장이 막혀도 최선만 한다.
  }
}
function clearPendingSceneVideoJob(gapSlotId: string): void {
  try {
    window.localStorage.removeItem(sceneVideoJobStorageKey(gapSlotId));
  } catch {
    // 위와 같은 이유.
  }
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
  //: 만든 그림을 **상업적으로 써도 되는지.** `null`이면 모른다는 뜻이다.
  //: 지금 쓰는 그림 모델(`flux1-dev`)은 상업 이용이 막혀 있는데, 서버는 그걸
  //: 알고 보내 주면서 화면은 한 번도 안 보여 주고 있었다(2026-09-03 확인).
  //: 대표님 채널은 수익이 나므로 **모르고 쓰면 안 되는 정보다.**
  const [commercialUseOk, setCommercialUseOk] = useState<boolean | null | undefined>(undefined);
  const fieldId = `scene-image-${gap.gapSlotId}`;
  // 진짜 동영상(Wan)은 그림과 **같은 설명 칸을 공유한다** -- 같은 장면을
  // 묘사하는 말이라 owner가 두 번 쓸 이유가 없다. 만드는 방식·시간만 다르다
  // (owner 결정 2026-08-29 2회차, "원래 만든거외에 별도로 만들자").
  const [makeGif, setMakeGif] = useState(false);
  // 빠른 미리보기(owner 요청 2026-08-29, 3회차) -- 실측: preview 약 12초,
  // full(고화질) 약 18~23분. 매번 20분을 기다리지 않고 먼저 가늠해 볼 수 있다.
  const [quality, setQuality] = useState<SceneVideoQuality>("preview");
  const [isMakingVideo, setIsMakingVideo] = useState(false);
  const [videoStatus, setVideoStatus] = useState<string | null>(null);
  const [madeVideoAssetId, setMadeVideoAssetId] = useState<string | null>(null);
  const [madeGifAssetId, setMadeGifAssetId] = useState<string | null>(null);
  // 취소 버튼(owner 요청 2026-08-29 3회차)이 어느 job을 멈출지 알아야 한다.
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
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
      setCommercialUseOk(made.commercial_use_is_unrestricted ?? null);
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

  // 새로고침·화면 이동 복귀(owner 요청 2026-08-29 3회차) -- 페이지가 다시
  // 뜰 때 이 장면에 아직 처리 중인 작업이 남아 있으면 새로 만들지 않고
  // 그 job_id를 이어서 지켜본다. 서버는 이미 계속 돌고 있었다.
  useEffect(() => {
    const pending = readPendingSceneVideoJob(gap.gapSlotId);
    if (!pending || pending.projectId !== projectId) return;
    setIsMakingVideo(true);
    setVideoStatus("이어서 확인하는 중이에요…");
    void pollSceneVideoJob(pending.jobId);
    // 장면(gapSlotId)이 바뀔 때만 다시 확인한다 -- 매 렌더마다 새로 걸면 안 된다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gap.gapSlotId, projectId]);

  async function pollSceneVideoJob(jobId: string) {
    setActiveJobId(jobId);
    try {
      const outcome = await pollJobUntilTerminal(
        () => api.getSceneVideoStatus(projectId, jobId),
        { intervalMs: SCENE_VIDEO_POLL_INTERVAL_MS, maxAttempts: SCENE_VIDEO_POLL_MAX_ATTEMPTS, delayFirst: true },
      );
      if (outcome.kind === "succeeded") {
        setMadeVideoAssetId(outcome.result.scene_asset_id);
        setMadeGifAssetId(outcome.result.gif_asset_id);
        // owner 요청(2026-08-29 3회차): "이렇게 생성된것도 우리 자산으로
        // 들어가도록". 자료실 등록은 실패해도 위 프로젝트 자산은 그대로라
        // 따로 알려 주되 실패를 오류로 다루지 않는다.
        setVideoStatus(
          outcome.result.library_asset_id
            ? "영상을 만들었어요. 자료실에도 저장했어요."
            : "영상을 만들었어요.",
        );
        clearPendingSceneVideoJob(gap.gapSlotId);
        // 그림 쪽과 같은 이유 -- 자산이 생긴 것과 장면이 채워진 것은 다른 일이다.
        onGenerated?.();
        return;
      }
      if (outcome.kind === "failed") {
        const detail = outcome.error_detail;
        setVideoStatus((detail && videoMessageByDetail[detail]) ?? "영상을 만들지 못했어요. 잠시 뒤 다시 눌러 주세요.");
        clearPendingSceneVideoJob(gap.gapSlotId);
        return;
      }
      // "cancelled"는 이 자리에서 안 쓴다(isStillRelevant를 안 넘겼다) --
      // 남는 건 "timed_out"뿐이다.
      setVideoStatus("영상이 제 시간에 안 나왔어요. 잠시 뒤 다시 눌러 주세요.");
      clearPendingSceneVideoJob(gap.gapSlotId);
    } catch {
      setVideoStatus("진행 상황을 확인하지 못했어요. 잠시 뒤 다시 눌러 주세요.");
      clearPendingSceneVideoJob(gap.gapSlotId);
    } finally {
      setIsMakingVideo(false);
      setActiveJobId(null);
    }
  }

  async function cancelVideo() {
    if (!activeJobId) return;
    setIsCancelling(true);
    try {
      await api.cancelSceneVideo(projectId, activeJobId);
      // 실제로 멈췄다는 확인은 폴링 쪽(`pollSceneVideoJob`)이 그대로 이어받는다
      // -- 취소 요청을 보낸 자리와 최종 상태를 쓰는 자리를 하나로 유지한다.
      setVideoStatus("취소하는 중이에요…");
    } catch {
      // 이미 끝났거나(409) 요청 자체가 실패한 것이다 -- 폴링이 곧 실제 결과를 보여준다.
    } finally {
      setIsCancelling(false);
    }
  }

  async function makeVideo() {
    if (!description.trim()) return setVideoStatus("어떤 영상을 원하는지 먼저 적어 주세요.");
    setIsMakingVideo(true);
    setVideoStatus(
      quality === "preview"
        ? "빠르게 미리 만들고 있어요. 15초 정도 걸려요…"
        : quality === "standard"
          ? "표준 화질로 만들고 있어요. 3분 정도 걸려요…"
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
      writePendingSceneVideoJob(gap.gapSlotId, projectId, started.job_id);
      await pollSceneVideoJob(started.job_id);
    } catch (error) {
      const detail = (error as { detail?: string | null })?.detail ?? null;
      setVideoStatus((detail && videoMessageByDetail[detail]) ?? "영상을 만들지 못했어요. 잠시 뒤 다시 눌러 주세요.");
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
      {/* 만든 그림을 어디까지 쓸 수 있는지 **그림 옆에서** 말한다. 나중에
          알면 이미 영상에 넣은 뒤다. 모르면 모른다고 말하고 아는 척하지
          않는다 -- 괜찮다고 잘못 말하는 쪽이 훨씬 나쁘다. */}
      {madeAssetId && commercialUseOk === false ? (
        <p role="status">
          이 그림은 <strong>수익 내는 영상에는 쓸 수 없어요.</strong> 지금 쓰는 그림
          모델이 그렇게 정해 두었어요. 연습용·비공개 영상에는 괜찮아요.
        </p>
      ) : null}
      {madeAssetId && commercialUseOk === null ? (
        <p role="status">
          이 그림을 수익 내는 영상에 써도 되는지 <strong>확인되지 않았어요.</strong>
          쓰시기 전에 한 번 확인해 주세요.
        </p>
      ) : null}
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
          onChange={(event) => setQuality(event.target.value as SceneVideoQuality)}
        >
          <option value="preview">빠르게 (약 15초)</option>
          <option value="standard">표준 (약 3분)</option>
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
          {isMakingVideo ? "영상 생성 중" : madeVideoAssetId ? "다시 만들기" : "AI 영상 생성"}
        </Button>
        {isMakingVideo && activeJobId ? (
          <Button type="button" variant="ghost" disabled={isCancelling} onClick={() => void cancelVideo()}>
            {isCancelling ? "취소하는 중" : "취소"}
          </Button>
        ) : null}
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
