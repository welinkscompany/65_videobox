import { useEffect, useRef, useState } from "react";

import { api, type AssetResponse } from "../../api";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";

/** 프로젝트가 지금 들고 있는 내레이션을 보여 주고, 바꿀 수 있게 한다.
 *
 * 2026-08-16까지 내레이션은 **넣을 수만 있고 볼 수가 없었다.** 넣는 곳도 프로젝트를
 * 만들 때 파일 경로를 타이핑하는 화면 하나뿐이었다. 그래서 완성본이 완전 무음(-91dB)으로
 * 나갔는데도 내레이션이 무음 파일이라는 것을 확인할 방법이 없었다.
 *
 * **듣기가 이 화면의 핵심이다.** 목록만 보여 주면 파일이 있다는 것만 알 뿐,
 * 그 안이 비었는지는 여전히 모른다.
 */
export function NarrationAudioSection({ projectId }: { projectId: string }) {
  const [assets, setAssets] = useState<readonly AssetResponse[]>([]);
  const [ready, setReady] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function load(activeProjectId: string) {
    try {
      setAssets(await api.listNarrationAudio(activeProjectId));
    } catch {
      setMessage("내레이션 목록을 불러오지 못했어요.");
    } finally {
      setReady(true);
    }
  }

  useEffect(() => {
    setReady(false);
    setAssets([]);
    setMessage(null);
    void load(projectId);
  }, [projectId]);

  async function upload(file: File) {
    setBusy(true);
    setMessage(null);
    try {
      await api.uploadNarrationAudio(projectId, file);
      await load(projectId);
      setMessage("내레이션을 넣었어요. 들어 보고 소리가 맞는지 확인해 주세요.");
    } catch {
      setMessage("내레이션을 넣지 못했어요. 소리가 들어 있는 오디오 파일인지 확인해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="narration-audio-heading">
      {/* 다른 탭과 같은 평면(h2)을 쓴다. 여기만 h3였을 때 화면 낭독기에서
          목차가 거꾸로 올라갔다 -- 뒤따르는 목소리 화면이 h2로 시작하기 때문이다. */}
      <h2 id="narration-audio-heading">이 영상의 내레이션</h2>
      {message ? <p role="status">{message}</p> : null}
      {ready && assets.length === 0
        ? <p>아직 내레이션이 없어요. 녹음한 파일을 넣거나, 아래에서 내 목소리로 만들 수 있어요.</p>
        : null}
      {/* 항목은 카드로 묶는다. 다른 탭이 재료 하나를 카드 하나로 보여 준다. */}
      {assets.length ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {assets.map((asset) => (
            <Card key={asset.asset_id} role="article" aria-label={`${asset.asset_id} 내레이션`}>
              <CardHeader><CardTitle>{asset.asset_id}</CardTitle></CardHeader>
              <CardContent>
                {/* 들어 봐야 무음인지 안다. 목록만으로는 파일이 있다는 것밖에 모른다. */}
                <audio controls preload="metadata" src={api.assetContentUrl(projectId, asset.asset_id)} />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
      <label htmlFor="narration-audio-file">내레이션 파일 넣기</label>
      <input
        id="narration-audio-file"
        data-native-control="narration-audio-input"
        ref={fileRef}
        type="file"
        accept="audio/*"
        hidden
        disabled={busy}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void upload(file);
        }}
      />
      <Button type="button" variant="outline" disabled={busy} onClick={() => fileRef.current?.click()}>
        {busy ? "넣는 중" : "내레이션 파일 넣기"}
      </Button>
    </section>
  );
}
