import { useState } from "react";

import { api, type CreationRecommendationSet, type ScriptDraft } from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { NativeSelect } from "../../components/ui/native-select";
import { Textarea } from "../../components/ui/textarea";

/** 서버가 붙여 보낸 이유를 owner가 **할 수 있는 일**로 옮긴다.
 *
 *  닿지 못한 것과 쓸 수 없는 대본이 온 것은 다음 행동이 다르다 -- 앞쪽은 그냥
 *  다시 누르면 되고, 뒤쪽은 주제를 고쳐 적어야 한다. 한 문장으로 뭉치면 owner는
 *  같은 주제로 몇 번이고 다시 누른다. */
const messageByDetail: Record<string, string> = {
  script_draft_writer_unavailable: "유진이 지금 답하지 못했어요. 잠시 뒤 다시 눌러 주세요.",
  // 같은 길이로 다시 누르면 같은 결과다. 무엇을 바꿔야 하는지를 말한다 --
  // 2026-08-21 실측으로 5분·12장면이 28.7초까지 갔다.
  script_draft_took_too_long: "대본이 제 시간에 오지 않았어요. 영상 길이나 장면 수를 줄여서 다시 부탁해 주세요.",
  script_draft_empty: "대본을 받지 못했어요. 주제를 조금 더 자세히 적고 다시 눌러 주세요.",
  script_draft_not_korean: "대본이 우리말로 오지 않았어요. 주제를 조금 더 자세히 적고 다시 눌러 주세요.",
  script_draft_topic_empty: "무엇에 대한 영상인지 먼저 적어 주세요.",
};

const UNKNOWN = "대본을 만들지 못했어요. 잠시 뒤 다시 눌러 주세요.";

function messageFor(error: unknown): string {
  const detail = (error as { detail?: string | null })?.detail ?? null;
  return (detail && messageByDetail[detail]) || UNKNOWN;
}

/** 길이는 **초로 보낸다.** 화면에는 창작자가 쓰는 말로 적는다. */
const lengthChoices = [
  { seconds: 30, label: "30초" },
  { seconds: 60, label: "1분" },
  { seconds: 180, label: "3분" },
  { seconds: 300, label: "5분" },
];

const sceneChoices = [3, 5, 8, 12];

/** 대본도 찍어 둔 영상도 없이 시작하는 길.
 *
 *  첫 화면의 세 길은 전부 **이미 가진 것**을 전제했다 -- 만들던 편집본, 써 둔 대본,
 *  찍어 둔 영상. 아무것도 없는 사람은 들어갈 문이 없었다.
 *
 *  **받은 대본을 그대로 확정하지 않는다.** 유진이도 틀린다. owner가 고친 뒤 확인해야
 *  기획으로 넘어간다 -- 승인 기록이 남기라고 못박은 사람 게이트 `대본 확정`이 여기다
 *  (`decisions/2026-08-16-autonomous-creator-loop-scope-expansion.ko.md`). */
export function YujinScriptStart({
  projectId,
  onReady,
  disabled = false,
}: {
  projectId: string;
  onReady: (start: { scriptText: string }) => void;
  disabled?: boolean;
}) {
  const [topic, setTopic] = useState("");
  const [durationSec, setDurationSec] = useState(60);
  const [sceneCount, setSceneCount] = useState(5);
  const [isWriting, setIsWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [written, setWritten] = useState<ScriptDraft | null>(null);
  const [scriptText, setScriptText] = useState("");
  // 주제 하나로 BGM·이미지 스타일·목소리까지 세트로 미리 본다(owner 요청
  // 2026-08-28, 필수 지정). 대본을 기다리게 하지 않는다 -- 대본이 먼저 뜨고
  // 나서 따로, 조용히 늦게 채워져도 된다. 실패해도 대본 확정은 막지 않는다.
  const [recommendations, setRecommendations] = useState<CreationRecommendationSet | null>(null);
  const [recommendationsFailed, setRecommendationsFailed] = useState(false);

  async function ask() {
    if (isWriting) return;
    if (!topic.trim()) {
      setError("무엇에 대한 영상인지 먼저 적어 주세요.");
      return;
    }
    setError(null);
    setIsWriting(true);
    setRecommendations(null);
    setRecommendationsFailed(false);
    try {
      const draft = await api.createScriptDraft(projectId, {
        topic: topic.trim(),
        duration_sec: durationSec,
        scene_count: sceneCount,
      });
      setWritten(draft);
      setScriptText(draft.script_text);
      api.createCreationRecommendationSet(projectId, { topic: topic.trim(), script_text: draft.script_text })
        .then(setRecommendations)
        .catch(() => setRecommendationsFailed(true));
    } catch (caught) {
      setError(messageFor(caught));
    } finally {
      setIsWriting(false);
    }
  }

  if (written) {
    return (
      <section aria-label="유진이 쓴 대본 확인">
        <h2>{written.title}</h2>
        <p>마음에 안 드는 곳을 고친 뒤 기획을 시작해 주세요. 유진이도 틀리니 꼭 읽어 봐 주세요.</p>
        <label htmlFor="yujin-script-text">유진이 쓴 대본</label>
        <Textarea
          id="yujin-script-text"
          rows={10}
          value={scriptText}
          onChange={(event) => setScriptText(event.target.value)}
          disabled={disabled}
        />
        {/* 이 제품이 다른 점은 자산이 아니라 **고르는 일**이다(계획서 §4.2).
            대본만 주고 장면을 감추면 유진이 한 일의 절반이 안 보인다. */}
        <p id="yujin-scene-note">대본을 고치면 장면도 달라져요. 어떤 영상을 넣을지는 기획에서 함께 정합니다.</p>
        <ul aria-label="유진이 생각한 장면" aria-describedby="yujin-scene-note">
          {written.scenes.map((scene) => (
            // 붙여 쓰면 읽어 주는 도구에서 `1번째 장면첫 캠핑...`으로 이어진다.
            <li key={scene.scene_number}>
              <strong>{`${scene.scene_number}번째 장면`}</strong>
              <p>{scene.narration}</p>
              {scene.visual ? <p>{`보여 줄 그림: ${scene.visual}`}</p> : null}
            </li>
          ))}
        </ul>
        {/* 주제 하나로 미리 본 소재 세트. 전부 이미 있는 재료 위에서 고른
            추천이다 -- BGM은 의미 기반 검색, 스타일은 낱말 매칭, 목소리는
            이미 등록한 것 중 최근 것이다(`creation_recommendations.py`). */}
        {recommendations ? (
          <section aria-label="주제로 미리 본 소재 세트">
            <h3>이 주제로 어울리는 소재</h3>
            <div>
              <strong>배경음악</strong>
              {recommendations.bgm.length ? (
                <ul>
                  {recommendations.bgm.map((track) => (
                    <li key={track.library_asset_id}>{track.description || track.library_asset_id}</li>
                  ))}
                </ul>
              ) : <p>{recommendations.bgm_semantic ? "어울리는 배경음악을 찾지 못했어요." : "지금은 뜻으로 찾을 수 없어 배경음악을 추천하지 못했어요."}</p>}
            </div>
            <div>
              <strong>이미지 스타일</strong>
              <p>{recommendations.image_style.name} -- {recommendations.image_style.reason}</p>
            </div>
            <div>
              <strong>목소리</strong>
              <p>{recommendations.voice.filename ?? recommendations.voice.note}</p>
            </div>
            <p>미디어를 모을 때 여기서 고른 대로 이어서 적용할 수 있어요.</p>
          </section>
        ) : recommendationsFailed ? <p>소재 추천을 지금 불러오지 못했어요. 미디어 단계에서 직접 골라도 괜찮아요.</p> : null}
        <Button
          type="button"
          disabled={disabled || !scriptText.trim()}
          onClick={() => onReady({ scriptText: scriptText.trim() })}
        >
          이 대본으로 기획 시작
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={disabled}
          onClick={() => { setWritten(null); setScriptText(""); }}
        >
          주제 다시 적기
        </Button>
      </section>
    );
  }

  return (
    <section aria-label="유진과 대본부터 시작">
      <h2>대본도 영상도 아직 없어요</h2>
      <p>무엇에 대한 영상인지만 알려 주면 유진이 대본 초안을 써 드릴게요.</p>
      <label htmlFor="yujin-script-topic">무엇에 대한 영상인가요</label>
      <Input
        id="yujin-script-topic"
        value={topic}
        // 서버가 500자에서 거절한다. 여기서 막지 않으면 owner는 길게 적고 나서야
        // 이유를 알 수 없는 실패를 본다.
        maxLength={500}
        placeholder="예: 집에서 라면 맛있게 끓이는 법"
        disabled={disabled || isWriting}
        onChange={(event) => { setTopic(event.target.value); setError(null); }}
      />
      <label htmlFor="yujin-script-duration">영상 길이</label>
      <NativeSelect
        id="yujin-script-duration"
        value={String(durationSec)}
        disabled={disabled || isWriting}
        onChange={(event) => setDurationSec(Number(event.target.value))}
      >
        {lengthChoices.map((choice) => (
          <option key={choice.seconds} value={choice.seconds}>{choice.label}</option>
        ))}
      </NativeSelect>
      <label htmlFor="yujin-script-scenes">장면 수</label>
      <NativeSelect
        id="yujin-script-scenes"
        value={String(sceneCount)}
        disabled={disabled || isWriting}
        onChange={(event) => setSceneCount(Number(event.target.value))}
      >
        {sceneChoices.map((count) => (
          <option key={count} value={count}>{`${count}개`}</option>
        ))}
      </NativeSelect>
      <Button type="button" disabled={disabled || isWriting} onClick={() => void ask()}>
        {isWriting ? "유진이 대본을 쓰고 있어요" : "유진에게 대본 부탁하기"}
      </Button>
      {isWriting ? <p role="status">잠깐이면 돼요. 이 화면을 열어 둔 채 기다려 주세요.</p> : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
