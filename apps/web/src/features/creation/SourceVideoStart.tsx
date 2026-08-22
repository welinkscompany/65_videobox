import { useState } from "react";

import { api } from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";

/** 서버가 붙여 보낸 이유를 owner가 **할 수 있는 일**로 옮긴다.
 *
 *  이유를 구분하지 않으면 "다시 시도해 주세요" 하나로 뭉치는데, 소리가 없는
 *  영상은 몇 번을 다시 올려도 같은 결과다. 무엇을 바꿔야 하는지를 말한다. */
const messageByDetail: Record<string, string> = {
  source_video_has_no_speech: "이 영상에는 말소리가 없어요. 사람이 말하는 영상을 골라 주세요. 말이 없는 영상이라면 대본을 직접 붙여넣고 시작해 주세요.",
  source_video_upload_invalid: "열 수 없는 형식이에요. MP4, MOV, WEBM, MKV, M4V 영상을 골라 주세요.",
  source_video_upload_too_large: "영상이 너무 커요. 128MB보다 작게 줄이거나 잘라서 올려 주세요.",
};

/** 상태 코드만 남고 이유가 없을 때. 여기서 갈리는 것은 **긴 영상**이다 --
 *  받아쓰기가 요청 안에서 끝나야 하는데 중간 프록시가 330초에서 끊는다
 *  (`docker/workspace-nginx.conf`). "다시 시도"라고 하면 owner는 같은 영상을
 *  몇 번이고 다시 올린다. */
const TOO_LONG = "영상이 길어서 받아쓰기를 제 시간에 마치지 못했어요. 절반쯤으로 잘라서 올려 주세요.";
const TOO_BIG = "영상이 너무 커요. 128MB보다 작게 줄이거나 잘라서 올려 주세요.";
const UNKNOWN = "영상에서 대본을 만들지 못했어요. 잠시 뒤 다시 눌러 주세요.";

function messageFor(error: unknown): string {
  const detail = (error as { detail?: string | null })?.detail ?? null;
  if (detail && messageByDetail[detail]) return messageByDetail[detail];
  const status = (error as { status?: number })?.status;
  if (status === 504 || status === 408) return TOO_LONG;
  if (status === 413) return TOO_BIG;
  return UNKNOWN;
}

/** 찍어 둔 영상으로 시작하는 길.
 *
 *  지금까지는 대본이 있어야만 첫 걸음을 뗄 수 있었다. "영상은 찍어 뒀는데 대본은
 *  없다"가 가장 흔한 상황인데도 들어갈 문이 없었다.
 *
 *  **받아쓴 글을 그대로 확정하지 않는다.** 받아쓰기는 틀린다 -- 사람 이름과 숫자가
 *  특히 그렇다. owner가 고친 뒤 확인해야 기획으로 넘어간다.
 *
 *  올린 영상은 버려지지 않고 프로젝트 자산으로 남는다. 그 영상이 곧 본편이라
 *  부모가 `assetId`를 받아 내레이션으로도 이어야 한다. */
export function SourceVideoStart({
  projectId,
  onReady,
  disabled = false,
}: {
  projectId: string;
  onReady: (start: { assetId: string; scriptText: string }) => void;
  disabled?: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [isReading, setIsReading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [heard, setHeard] = useState<{ assetId: string; scriptText: string } | null>(null);
  const [scriptText, setScriptText] = useState("");

  async function read() {
    if (isReading) return;
    if (!file) {
      setError("영상을 먼저 골라 주세요.");
      return;
    }
    setError(null);
    setIsReading(true);
    try {
      const start = await api.uploadSourceVideo(projectId, file);
      setHeard({ assetId: start.asset_id, scriptText: start.script_text });
      setScriptText(start.script_text);
    } catch (caught) {
      setError(messageFor(caught));
    } finally {
      setIsReading(false);
    }
  }

  if (heard) {
    return (
      <section aria-label="영상에서 받아쓴 대본 확인">
        <h2>영상에서 이렇게 들었어요</h2>
        <p>잘못 들은 곳을 고친 뒤 기획을 시작해 주세요. 사람 이름과 숫자는 특히 자주 틀려요.</p>
        <label htmlFor="source-video-script">영상에서 받아쓴 대본</label>
        <Textarea
          id="source-video-script"
          rows={10}
          value={scriptText}
          onChange={(event) => setScriptText(event.target.value)}
          disabled={disabled}
        />
        <Button
          type="button"
          disabled={disabled || !scriptText.trim()}
          onClick={() => onReady({ assetId: heard.assetId, scriptText: scriptText.trim() })}
        >
          이 대본으로 기획 시작
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={disabled}
          onClick={() => { setHeard(null); setScriptText(""); setFile(null); }}
        >
          다른 영상 고르기
        </Button>
      </section>
    );
  }

  return (
    <section aria-label="찍어 둔 영상으로 시작">
      <h2>찍어 둔 영상이 있어요</h2>
      <p>영상에서 말을 받아써 대본을 만들어 드릴게요. 올린 영상은 그대로 본편으로 씁니다.</p>
      <label htmlFor="source-video-file">찍어 둔 영상 선택</label>
      {/* 길이 안내는 **재서** 적었다. 2026-08-21 실측으로 3분 20초짜리가 24초에
          끝났다(대략 8배속). 중간에서 끊는 벽이 330초이므로 길이만 보면 20분도
          넉넉하지만, 재 본 것은 잡음 없는 한 사람 목소리다 -- 실제 촬영본은
          더 느리므로 여유를 두고 말한다. 128MB는 서버가 정한 상한이다. */}
      {/* 조건을 문장으로 늘어놓으면 읽지 않는다. 셋 다 **고르기 전에 알아야 하는
          사실**이라 빼지 않고, 키워드로 줄여서 한눈에 들어오게 한다. */}
      <p id="source-video-file-help">MP4 · MOV · WEBM · MKV · M4V · 128MB 이하 · 20분 이내</p>
      <Input
        id="source-video-file"
        type="file"
        accept="video/*,.mp4,.mov,.webm,.mkv,.m4v"
        aria-describedby="source-video-file-help"
        disabled={disabled || isReading}
        onChange={(event) => { setFile(event.target.files?.[0] ?? null); setError(null); }}
      />
      <Button type="button" disabled={disabled || isReading} onClick={() => void read()}>
        {isReading ? "영상에서 말을 받아쓰고 있어요" : "영상에서 대본 만들기"}
      </Button>
      {isReading ? <p role="status">영상 길이에 따라 몇 분 걸릴 수 있어요. 이 화면을 열어 둔 채 기다려 주세요.</p> : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
