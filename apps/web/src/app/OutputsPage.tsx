import { useCallback, useEffect, useState } from "react";

import {
  api,
  type CapCutDraftExportJob,
  type CapCutHandoffDiagnostics,
  type FinalRenderJob,
  type JobRecord,
} from "../api";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";

type OutputState = {
  finalRender: FinalRenderJob | null;
  capcutDraft: CapCutDraftExportJob | null;
  diagnostics: CapCutHandoffDiagnostics | null;
};

function mostRecentJob(jobs: JobRecord[], jobType: string) {
  return jobs.filter((job) => job.job_type === jobType).reduce<JobRecord | null>((latest, job) => {
    if (!latest) return job;
    const timestamp = job.finished_at ?? job.started_at ?? "";
    const latestTimestamp = latest.finished_at ?? latest.started_at ?? "";
    return timestamp > latestTimestamp ? job : latest;
  }, null);
}

export function OutputsPage({ projectId, onOpenEditor }: { projectId: string; onOpenEditor: () => void }) {
  const [state, setState] = useState<OutputState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(false);
    try {
      const jobs = await api.listJobs(projectId);
      const finalJob = mostRecentJob(jobs, "final_render");
      const capcutJob = mostRecentJob(jobs, "capcut_draft_export");
      const [finalRender, capcutDraft, diagnostics] = await Promise.all([
        finalJob ? api.getFinalRender(projectId, finalJob.job_id) : Promise.resolve(null),
        capcutJob ? api.getCapcutDraftExport(projectId, capcutJob.job_id) : Promise.resolve(null),
        api.getCapcutHandoffDiagnostics().catch(() => null),
      ]);
      setState({ finalRender, capcutDraft, diagnostics });
    } catch {
      setState(null);
      setError(true);
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => { void refresh(); }, [refresh]);

  if (isLoading && !state && !error) return <section className="vb-outputs" aria-live="polite"><p>출력 상태를 불러오는 중이에요.</p></section>;
  if (error) return <section className="vb-outputs" aria-live="polite" data-testid="outputs-page"><h1>출력</h1><p>출력 상태를 불러오지 못했어요.</p><p>잠시 후 상태를 다시 확인하거나 편집 화면에서 작업을 이어가세요.</p><Button variant="outline" onClick={() => void refresh()}>상태 다시 확인</Button><Button onClick={onOpenEditor}>편집 열기</Button></section>;

  const finalRender = state?.finalRender;
  const currentFinal = finalRender?.status === "succeeded" && finalRender.render?.is_current === true;
  const staleFinal = finalRender?.status === "succeeded" && Boolean(finalRender.render) && !currentFinal;
  const capcutHandoff = state?.capcutDraft?.export?.handoff;
  const capcutReady = state?.capcutDraft?.status === "succeeded" && capcutHandoff?.status === "ready";

  return <section className="vb-outputs" aria-live="polite" data-testid="outputs-page">
    <div><p className="vb-eyebrow">출력</p><h1>완성본과 CapCut 초안</h1><p>여기서는 현재 결과만 확인할 수 있어요. 새 출력은 편집 화면에서 시작해 주세요.</p></div>
    <div className="vb-home-grid">
      <Card>
        <CardHeader><CardTitle>완성본</CardTitle><CardDescription>{currentFinal ? "완성본을 확인할 수 있어요." : staleFinal ? "완성본이 최신 편집본과 달라요." : finalRender?.status === "failed" ? "완성본을 만들지 못했어요." : "아직 완성본이 없어요."}</CardDescription></CardHeader>
        <CardContent>
          {currentFinal ? <video aria-label="완성본 재생" controls preload="metadata" src={`/api/projects/${encodeURIComponent(projectId)}/final-renders/${encodeURIComponent(finalRender.job_id)}/content`}>이 브라우저에서는 완성본을 재생할 수 없어요.</video> : null}
          {staleFinal ? <p>편집에서 새 완성본 만들기를 실행해 주세요.</p> : null}
          {finalRender?.status === "failed" ? <p>편집 화면에서 원인을 확인한 뒤 다시 시도해 주세요.</p> : null}
          {!finalRender ? <p>편집을 마친 뒤 완성본을 만들면 여기에서 확인할 수 있어요.</p> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>CapCut 초안</CardTitle><CardDescription>{capcutReady ? "CapCut에서 초안을 열 수 있어요." : state?.capcutDraft?.status === "failed" || capcutHandoff?.status === "failed" ? "CapCut 초안 준비를 완료하지 못했어요." : state?.capcutDraft?.export ? "CapCut 초안의 연결 준비가 필요해요." : "아직 CapCut 초안이 없어요."}</CardDescription></CardHeader>
        <CardContent>
          {state?.capcutDraft?.export?.notes.length ? <p>일부 효과는 CapCut에서 확인해 주세요.</p> : null}
          {state?.capcutDraft?.status === "failed" || capcutHandoff?.status === "failed" ? <p>편집 화면에서 상태를 확인한 뒤 다시 진행해 주세요.</p> : null}
          {state?.diagnostics && !state.diagnostics.is_supported ? <p>이 기기의 CapCut 연결 상태를 확인해 주세요.</p> : null}
          {!state?.diagnostics ? <p>CapCut 연결 상태는 지금 확인할 수 없어요. 잠시 후 다시 확인해 주세요.</p> : null}
        </CardContent>
      </Card>
    </div>
    <div className="vb-home-grid"><Button variant="outline" onClick={() => void refresh()}>상태 다시 확인</Button><Button onClick={onOpenEditor}>편집 열기</Button></div>
  </section>;
}
