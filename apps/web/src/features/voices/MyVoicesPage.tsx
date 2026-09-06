/**
 * `내 자산 > 내 목소리` — 프로젝트에 흩어진 내 녹음을 한자리에서.
 *
 * **목소리는 프로젝트에 묶여 있다.** 자료실에는 목소리 종류가 아예 없어서,
 * 지금까지 내 목소리를 한눈에 볼 방법이 없었다(2026-09-07에 `GET /api/voices`를
 * 만들었다). 그래서 이 화면은 자료실을 갈래로 여는 `내 영상`·`음악·효과음`과
 * 달리 **자기 화면**이다.
 *
 * 줄마다 어느 프로젝트 것인지 들고 있다 -- 이름 바꾸기가 그 프로젝트 경로로
 * 가야 하기 때문이다.
 */

import { useCallback, useEffect, useState } from "react";

import { api, type MyVoice } from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";

/** 이름을 안 붙인 녹음도 목록에 남는다. 안 보이면 **있는데 없는 것**이 되고,
 *  그 목소리는 영영 이름을 못 받는다. */
const UNNAMED = "이름 없는 목소리";

function spokenLength(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "";
  const whole = Math.round(seconds);
  return whole >= 60 ? `${Math.floor(whole / 60)}분 ${whole % 60}초` : `${whole}초`;
}

function recordedOn(value: string | null | undefined): string {
  if (!value) return "";
  const when = new Date(value);
  return Number.isNaN(when.getTime()) ? "" : when.toLocaleDateString("ko-KR");
}

export function MyVoicesPage({
  listVoices = () => api.listMyVoices(),
  renameVoice = api.renameVoiceSample,
}: {
  listVoices?: () => Promise<MyVoice[]>;
  renameVoice?: (projectId: string, assetId: string, displayName: string) => Promise<unknown>;
} = {}) {
  const [voices, setVoices] = useState<MyVoice[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");

  const reload = useCallback(async () => {
    try {
      setFailed(false);
      setVoices(await listVoices());
    } catch {
      // **조용히 비우지 않는다.** 빈 목록과 "못 읽었다"는 다르다 -- 창작자가
      // 녹음이 사라진 줄 안다.
      setFailed(true);
      setVoices([]);
    }
  }, [listVoices]);

  useEffect(() => { void reload(); }, [reload]);

  const save = async (voice: MyVoice) => {
    const name = draftName.trim();
    if (!name) return;
    await renameVoice(voice.project_id, voice.asset_id, name);
    setEditing(null);
    await reload();
  };

  return <main className="vb-my-voices" data-testid="my-voices-page">
    <header className="vb-my-voices__header">
      <h1>내 목소리</h1>
      <p>프로젝트마다 녹음한 목소리를 한자리에 모았어요. 들어 보고 이름을 붙일 수 있어요.</p>
    </header>
    {failed ? <p role="alert">목소리 목록을 지금 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.</p> : null}
    {voices === null ? <p role="status">목소리를 불러오는 중이에요.</p> : null}
    {voices !== null && voices.length === 0 && !failed
      ? <p>아직 녹음한 목소리가 없어요. 편집기 왼쪽 `오디오`에서 녹음하면 여기에 모여요.</p>
      : null}
    <ul className="vb-my-voices__list">
      {(voices ?? []).map((voice) => <li className="vb-my-voices__item" key={`${voice.project_id}:${voice.asset_id}`}>
        <div className="vb-my-voices__title">
          <strong>{voice.display_name || UNNAMED}</strong>
          <small>{[voice.project_name, recordedOn(voice.created_at), spokenLength(voice.duration_sec)].filter(Boolean).join(" · ")}</small>
        </div>
        <audio controls preload="none" src={voice.content_url} />
        {editing === voice.asset_id
          ? <div className="vb-my-voices__rename">
              <label>
                <span className="sr-only">목소리 이름</span>
                <Input
                  aria-label="목소리 이름"
                  onChange={(event) => setDraftName(event.target.value)}
                  type="text"
                  value={draftName}
                />
              </label>
              <Button onClick={() => void save(voice)} type="button">저장</Button>
              <Button onClick={() => setEditing(null)} type="button" variant="ghost">그만두기</Button>
            </div>
          : <Button
              onClick={() => { setEditing(voice.asset_id); setDraftName(voice.display_name || ""); }}
              type="button"
              variant="ghost"
            >이름 바꾸기</Button>}
      </li>)}
    </ul>
  </main>;
}
