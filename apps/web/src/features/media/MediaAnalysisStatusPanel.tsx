import { useEffect, useRef, useState } from "react";

import { api, type BrollAsset, type MediaAnalysis } from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";

/** 프로젝트 단계의 독립 "미디어" 화면(`MediaWorkspacePage`)이 편집기 도크로
 *  접히면서(owner 승인 2026-09-01, 2026-08-27 결정 §순서 2 실행) 그 화면의
 *  "분석 상태" 절만 옮겨 온 조각이다. 편집기 어디에도 없던 유일한 고유
 *  기능이라 그대로 옮겼다 — 나머지 네 탭(음악·효과음·내레이션·가져오기)은
 *  편집기 도크가 이미 같은 컴포넌트·같은 API로 갖고 있어 통째로 버렸다.
 *
 *  좁은 도크(약 300~400px)에 맞춰 원본의 `Card` 레이아웃 대신 압축형으로
 *  다시 그렸다(`.vb-yujin-panel__candidate`와 같은 밀도 관행). 확인할 분석이
 *  없으면 `null`을 반환한다 — 상시 노출되는 빈 문구는 좁은 패널에서 소음이다.
 *
 *  **이름에 "Status"를 넣은 이유**: `MediaAnalysisPanel`이라는 더 짧은 이름이
 *  `task22-parity-owners.test.ts`의 `retiredFiles`에 이미 있었다 -- 예전에
 *  없앤 다른 컴포넌트가 그 이름을 썼고, 되살아나지 않게 지키는 회귀 시험이다.
 *  같은 이름을 다시 쓰면 그 시험이 깨진다. */

const analysisStatusCopy: Record<string, string> = {
  queued: "분석을 기다리고 있어요",
  running: "미디어를 살펴보고 있어요",
  succeeded: "준비가 끝났어요",
  needs_review: "확인이 필요해요",
  failed: "분석을 마치지 못했어요",
  blocked: "분석을 진행할 수 없어요",
  cancelled: "분석을 멈췄어요",
};

function assetTitle(asset: BrollAsset | undefined, index: number) {
  const title = asset?.metadata?.title;
  return typeof title === "string" && title.trim() ? title.trim() : `미디어 ${index + 1}`;
}

export function MediaAnalysisStatusPanel({ projectId }: { projectId: string }) {
  const [analyses, setAnalyses] = useState<MediaAnalysis[]>([]);
  const [assets, setAssets] = useState<BrollAsset[]>([]);
  const [preview, setPreview] = useState<{ assetId: string; durationSec?: number } | null>(null);
  const [tags, setTags] = useState<Record<string, string>>({});
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const generation = useRef(0);

  const load = async (currentGeneration: number) => {
    try {
      const [analysisResponse, brollAssets] = await Promise.all([
        api.listMediaAnalysis(projectId),
        api.listBrollAssets(projectId),
      ]);
      if (generation.current !== currentGeneration) return;
      setAnalyses(analysisResponse.items);
      setAssets(brollAssets);
    } catch {
      if (generation.current !== currentGeneration) return;
      setAnalyses([]);
    }
  };

  useEffect(() => {
    generation.current += 1;
    const currentGeneration = generation.current;
    setAnalyses([]);
    setAssets([]);
    setPreview(null);
    setTags({});
    setBusyKey(null);
    void load(currentGeneration);
  }, [projectId]);

  async function runAction(key: string, mutation: () => Promise<unknown>) {
    if (busyKey !== null) return;
    const currentGeneration = generation.current;
    setBusyKey(key);
    try {
      await mutation();
      if (generation.current === currentGeneration) await load(currentGeneration);
    } catch {
      if (generation.current === currentGeneration) await load(currentGeneration);
    } finally {
      if (generation.current === currentGeneration) setBusyKey(null);
    }
  }

  async function showPreview(item: MediaAnalysis) {
    const currentGeneration = generation.current;
    setBusyKey(`preview:${item.analysis_id}`);
    try {
      const response = await api.mediaAnalysisPreview(projectId, item.asset_id);
      if (generation.current !== currentGeneration) return;
      const raw = response.preview as { duration_sec?: unknown } | null;
      setPreview({
        assetId: item.asset_id,
        durationSec: typeof raw?.duration_sec === "number" ? raw.duration_sec : undefined,
      });
    } catch {
      if (generation.current === currentGeneration) setPreview(null);
    } finally {
      if (generation.current === currentGeneration) setBusyKey(null);
    }
  }

  if (analyses.length === 0) return null;

  const assetById = new Map(assets.map((item) => [item.asset_id, item]));

  return <section className="vb-media-analysis-panel" aria-labelledby="media-analysis-panel-heading">
    <h3 id="media-analysis-panel-heading">분석 상태</h3>
    <div className="vb-media-analysis-panel__list">
      {analyses.map((item, index) => {
        const label = assetTitle(assetById.get(item.asset_id), index);
        const actionDisabled = busyKey !== null;
        return (
          <article key={item.analysis_id} className="vb-media-analysis-panel__item" aria-label={`${label} 분석`}>
            <p className="vb-media-analysis-panel__title">{label}</p>
            <p className="vb-media-analysis-panel__status">
              {analysisStatusCopy[item.status] ?? "상태를 확인하고 있어요"} · {item.progress_percent}%
            </p>
            {item.error_message ? <p className="vb-media-analysis-panel__error">분석을 마치지 못했어요. 직접 선택하거나 다시 시도해 주세요.</p> : null}
            {(item.status === "succeeded" || item.status === "needs_review") ? (
              <Button type="button" variant="outline" disabled={actionDisabled} onClick={() => void showPreview(item)}>
                미리보기
              </Button>
            ) : null}
            {preview?.assetId === item.asset_id ? (
              <p className="vb-media-analysis-panel__preview">{preview.durationSec === undefined ? "미리보기가 준비됐어요." : `미리보기 길이 ${preview.durationSec}초`}</p>
            ) : null}
            {(item.status === "queued" || item.status === "running") ? (
              <Button type="button" variant="outline" disabled={actionDisabled} onClick={() => void runAction(
                `cancel:${item.analysis_id}`,
                () => api.cancelMediaAnalysis(projectId, item.analysis_id),
              )}>
                분석 멈추기
              </Button>
            ) : null}
            {(item.status === "failed" || item.status === "blocked") ? (
              <Button type="button" variant="outline" disabled={actionDisabled} onClick={() => void runAction(
                `retry:${item.analysis_id}`,
                () => api.retryMediaAnalysis(projectId, item.analysis_id),
              )}>
                다시 분석하기
              </Button>
            ) : null}
            {item.status === "needs_review" ? (
              <form onSubmit={(event) => {
                event.preventDefault();
                const place = (tags[item.analysis_id] ?? "").split(",").map((tag) => tag.trim()).filter(Boolean);
                void runAction(
                  `review:${item.analysis_id}`,
                  () => api.reviewMediaAnalysis(projectId, item.analysis_id, { place }),
                );
              }}>
                <label>
                  {`${label} 태그`}
                  <Input
                    aria-label={`${label} 태그`}
                    value={tags[item.analysis_id] ?? ""}
                    onChange={(event) => setTags((current) => ({ ...current, [item.analysis_id]: event.target.value }))}
                  />
                </label>
                <Button type="submit" disabled={actionDisabled}>태그 확인</Button>
              </form>
            ) : null}
          </article>
        );
      })}
    </div>
  </section>;
}
