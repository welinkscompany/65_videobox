import { useState } from "react";

import { api } from "../../api";
import { Button } from "../../components/ui/button";
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
  scene_image_ffmpeg_missing: "그림을 장면에 넣지 못했어요. 다시 눌러 주세요.",
};

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

  return (
    <div>
      <label htmlFor={fieldId}>{`${gap.sceneNumber}번째 장면 그림 설명`}</label>
      <Textarea
        id={fieldId}
        rows={2}
        value={description}
        onChange={(event) => setDescription(event.target.value)}
      />
      <Button type="button" disabled={isMaking} onClick={() => void make()}>
        {isMaking ? "그림을 만들고 있어요" : "그림 만들기"}
      </Button>
      {status ? <p role="status">{status}</p> : null}
      {madeAssetId ? (
        <img
          src={api.assetContentUrl(projectId, madeAssetId)}
          alt={`${gap.sceneNumber}번째 장면 그림`}
          width={320}
        />
      ) : null}
    </div>
  );
}
