import { useEffect, useRef, useState } from "react";

import {
  api,
  type AssetResponse,
  type EditingSessionSegment,
  type TtsCandidateRecord,
  type YoutubeReferenceImport,
} from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { NativeSelect } from "../../components/ui/native-select";

type LoadState = "idle" | "loading" | "ready" | "error";
type ActionToken = { epoch: number; name: string };
type LoadToken = { epoch: number; key: string };

// 유튜브 학습이 비동기로 바뀌면서(owner 결정 2026-08-29, 2회차) 화면이 결과를
// 직접 기다리지 않고 물어서 받는다. 2초 간격 300회 = 최대 10분 -- 백엔드
// 다운로드 한도(600초)와 맞춘다.
const YOUTUBE_IMPORT_POLL_INTERVAL_MS = 2000;
const YOUTUBE_IMPORT_POLL_MAX_ATTEMPTS = 300;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function pollYoutubeImportUntilDone(
  projectId: string,
  jobId: string,
  isStillRelevant: () => boolean,
): Promise<YoutubeReferenceImport> {
  for (let attempt = 0; attempt < YOUTUBE_IMPORT_POLL_MAX_ATTEMPTS; attempt += 1) {
    if (!isStillRelevant()) throw new Error("youtube_import_cancelled");
    const current = await api.getYoutubeReferenceStyleImportStatus(projectId, jobId);
    if (current.status === "succeeded" && current.result) return current.result;
    if (current.status === "failed") throw new Error(current.error_detail ?? "youtube_import_failed");
    await delay(YOUTUBE_IMPORT_POLL_INTERVAL_MS);
  }
  throw new Error("youtube_import_timed_out");
}

function candidateStatus(candidate: TtsCandidateRecord) {
  if (candidate.technical_status !== "accepted") return "사용할 수 없음";
  if (candidate.operator_review_status === "approved") return "청취 승인됨";
  if (candidate.operator_review_status === "rejected") return "청취 거부됨";
  return "청취 확인 필요";
}

export function VoiceTtsSettings({ projectId }: { projectId: string }) {
  const [samples, setSamples] = useState<AssetResponse[]>([]);
  const [segments, setSegments] = useState<EditingSessionSegment[]>([]);
  const [candidates, setCandidates] = useState<TtsCandidateRecord[]>([]);
  const [selectedSampleId, setSelectedSampleId] = useState("");
  const [selectedSegmentId, setSelectedSegmentId] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadInputVersion, setUploadInputVersion] = useState(0);
  // 본인 유튜브 영상으로 목소리·스타일 배우기(owner 요청 2026-08-29).
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [youtubeImportResult, setYoutubeImportResult] = useState<YoutubeReferenceImport | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [candidateLoadState, setCandidateLoadState] = useState<LoadState>("idle");
  const [actionName, setActionName] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const epochRef = useRef(0);
  const currentProjectRef = useRef(projectId);
  const initialLoadRef = useRef<LoadToken | null>(null);
  const candidateLoadRef = useRef<LoadToken | null>(null);
  const actionRef = useRef<ActionToken | null>(null);
  const selectedSegmentRef = useRef("");
  currentProjectRef.current = projectId;

  const isCurrent = (epoch: number, expectedProjectId = projectId) => (
    epochRef.current === epoch && currentProjectRef.current === expectedProjectId
  );

  async function loadSettings(expectedProjectId: string, epoch: number) {
    if (initialLoadRef.current?.epoch === epoch && initialLoadRef.current.key === expectedProjectId) return;
    const loadToken = { epoch, key: expectedProjectId };
    initialLoadRef.current = loadToken;
    setLoadState("loading");
    setActionError(null);
    try {
      const [nextSamples, session] = await Promise.all([
        api.listVoiceSamples(expectedProjectId),
        api.getLatestEditingSession(expectedProjectId),
      ]);
      if (!isCurrent(epoch, expectedProjectId)) return;
      const activeSegments = (session?.segments ?? []).filter(
        (segment) => segment.cut_action.trim().toLowerCase() !== "remove",
      );
      setSamples(nextSamples);
      setSegments(activeSegments);
      setSelectedSampleId((current) => (
        nextSamples.some((sample) => sample.asset_id === current)
          ? current
          : (nextSamples[0]?.asset_id ?? "")
      ));
      const nextSelectedSegmentId = activeSegments.some(
        (segment) => segment.segment_id === selectedSegmentRef.current,
      ) ? selectedSegmentRef.current : "";
      selectedSegmentRef.current = nextSelectedSegmentId;
      setSelectedSegmentId(nextSelectedSegmentId);
      setLoadState("ready");
    } catch {
      if (isCurrent(epoch, expectedProjectId)) setLoadState("error");
    } finally {
      if (initialLoadRef.current === loadToken) initialLoadRef.current = null;
    }
  }

  async function refreshSamples(expectedProjectId: string, epoch: number) {
    const nextSamples = await api.listVoiceSamples(expectedProjectId);
    if (!isCurrent(epoch, expectedProjectId)) return;
    setSamples(nextSamples);
    setSelectedSampleId((current) => (
      nextSamples.some((sample) => sample.asset_id === current)
        ? current
        : (nextSamples[0]?.asset_id ?? "")
    ));
    setLoadState("ready");
  }

  async function loadCandidates(expectedProjectId: string, segmentId: string, epoch: number) {
    const loadKey = `${expectedProjectId}:${segmentId}`;
    if (candidateLoadRef.current?.epoch === epoch && candidateLoadRef.current.key === loadKey) return;
    const loadToken = { epoch, key: loadKey };
    candidateLoadRef.current = loadToken;
    setCandidateLoadState("loading");
    try {
      const result = await api.listTtsCandidates(expectedProjectId, segmentId);
      if (
        candidateLoadRef.current !== loadToken
        || !isCurrent(epoch, expectedProjectId)
        || selectedSegmentRef.current !== segmentId
      ) return;
      setCandidates(result.candidates);
      setCandidateLoadState("ready");
    } catch {
      if (
        candidateLoadRef.current === loadToken
        && isCurrent(epoch, expectedProjectId)
        && selectedSegmentRef.current === segmentId
      ) {
        setCandidateLoadState("error");
      }
    } finally {
      if (candidateLoadRef.current === loadToken) candidateLoadRef.current = null;
    }
  }

  useEffect(() => {
    const epoch = epochRef.current + 1;
    epochRef.current = epoch;
    initialLoadRef.current = null;
    candidateLoadRef.current = null;
    actionRef.current = null;
    selectedSegmentRef.current = "";
    setSamples([]);
    setSegments([]);
    setCandidates([]);
    setSelectedSampleId("");
    setSelectedSegmentId("");
    setLoadState("idle");
    setCandidateLoadState("idle");
    setActionName(null);
    setMessage(null);
    setActionError(null);
    setYoutubeUrl("");
    setYoutubeImportResult(null);
    void loadSettings(projectId, epoch);
  }, [projectId]);

  function beginAction(name: string) {
    if (actionRef.current) return null;
    const token = { epoch: epochRef.current, name };
    actionRef.current = token;
    setActionName(name);
    setMessage(null);
    setActionError(null);
    return token;
  }

  function finishAction(token: ActionToken) {
    if (actionRef.current !== token) return;
    actionRef.current = null;
    if (isCurrent(token.epoch)) setActionName(null);
  }

  async function registerLocalPath() {
    const sourcePath = localPath.trim();
    if (loadState !== "ready" || !sourcePath) return;
    const token = beginAction("register");
    if (!token) return;
    const expectedProjectId = projectId;
    try {
      try {
        await api.registerVoiceSample(expectedProjectId, { source_path: sourcePath });
      } catch {
        if (isCurrent(token.epoch, expectedProjectId)) {
          setActionError("내 목소리를 추가하지 못했어요. 다시 시도해 주세요.");
        }
        return;
      }
      if (!isCurrent(token.epoch, expectedProjectId)) return;
      setLocalPath("");
      try {
        await refreshSamples(expectedProjectId, token.epoch);
      } catch {
        if (isCurrent(token.epoch, expectedProjectId)) {
          setActionError("내 목소리는 저장됐지만 목록을 새로 불러오지 못했어요. 목록 새로고침으로 확인해 주세요.");
        }
        return;
      }
      if (isCurrent(token.epoch, expectedProjectId)) {
        setMessage("내 목소리를 추가했어요.");
      }
    } finally {
      finishAction(token);
    }
  }

  async function uploadSelectedFile() {
    if (loadState !== "ready" || !uploadFile) return;
    const token = beginAction("upload");
    if (!token) return;
    const expectedProjectId = projectId;
    try {
      try {
        await api.uploadVoiceSample(expectedProjectId, uploadFile);
      } catch {
        if (isCurrent(token.epoch, expectedProjectId)) {
          setActionError("내 목소리 파일을 추가하지 못했어요. 다시 시도해 주세요.");
        }
        return;
      }
      if (!isCurrent(token.epoch, expectedProjectId)) return;
      setUploadFile(null);
      setUploadInputVersion((current) => current + 1);
      try {
        await refreshSamples(expectedProjectId, token.epoch);
      } catch {
        if (isCurrent(token.epoch, expectedProjectId)) {
          setActionError("내 목소리는 저장됐지만 목록을 새로 불러오지 못했어요. 목록 새로고침으로 확인해 주세요.");
        }
        return;
      }
      if (isCurrent(token.epoch, expectedProjectId)) {
        setMessage("내 목소리 파일을 추가했어요.");
      }
    } finally {
      finishAction(token);
    }
  }

  async function importFromYoutube() {
    const url = youtubeUrl.trim();
    if (loadState !== "ready" || !url) return;
    const token = beginAction("youtube-import");
    if (!token) return;
    const expectedProjectId = projectId;
    setYoutubeImportResult(null);
    try {
      let result: YoutubeReferenceImport;
      try {
        // 비동기로 바뀌었다(owner 결정 2026-08-29, 2회차) -- 다운로드·오디오
        // 추출·컷/색감 분석을 합치면 긴 영상에서 nginx 330초 타임아웃보다
        // 오래 걸릴 수 있어, 요청 자체는 바로 돌아오고 여기서 상태를 물어본다.
        const started = await api.startYoutubeReferenceStyleImport(expectedProjectId, url);
        if (isCurrent(token.epoch, expectedProjectId)) setMessage("영상을 내려받고 분석하는 중이에요. 시간이 걸릴 수 있어요…");
        result = await pollYoutubeImportUntilDone(expectedProjectId, started.job_id, () => isCurrent(token.epoch, expectedProjectId));
      } catch {
        if (isCurrent(token.epoch, expectedProjectId)) {
          setActionError("이 링크에서 목소리를 가져오지 못했어요. 본인이 올린 유튜브 영상 주소가 맞는지 확인해 주세요.");
        }
        return;
      }
      if (!isCurrent(token.epoch, expectedProjectId)) return;
      setYoutubeUrl("");
      setYoutubeImportResult(result);
      try {
        await refreshSamples(expectedProjectId, token.epoch);
      } catch {
        if (isCurrent(token.epoch, expectedProjectId)) {
          setActionError("목소리는 저장됐지만 목록을 새로 불러오지 못했어요. 목록 새로고침으로 확인해 주세요.");
        }
        return;
      }
      if (isCurrent(token.epoch, expectedProjectId)) {
        setMessage("유튜브 영상에서 목소리를 가져왔어요.");
      }
    } finally {
      finishAction(token);
    }
  }

  async function reloadSamples() {
    if (loadState !== "ready") return;
    const token = beginAction("reload-samples");
    if (!token) return;
    const expectedProjectId = projectId;
    try {
      await refreshSamples(expectedProjectId, token.epoch);
      if (isCurrent(token.epoch, expectedProjectId)) setMessage("목소리 목록을 새로 불러왔어요.");
    } catch {
      if (isCurrent(token.epoch, expectedProjectId)) {
        setActionError("목소리 목록을 불러오지 못했어요. 다시 시도해 주세요.");
      }
    } finally {
      finishAction(token);
    }
  }

  function selectSegment(segmentId: string) {
    const activeSegmentId = segments.some((segment) => segment.segment_id === segmentId)
      ? segmentId
      : "";
    selectedSegmentRef.current = activeSegmentId;
    setSelectedSegmentId(activeSegmentId);
    setCandidates([]);
    setCandidateLoadState(activeSegmentId ? "loading" : "idle");
    setMessage(null);
    setActionError(null);
    if (activeSegmentId) void loadCandidates(projectId, activeSegmentId, epochRef.current);
  }

  async function generateCandidate() {
    const segment = segments.find((item) => item.segment_id === selectedSegmentId);
    if (!segment || !selectedSampleId) return;
    const token = beginAction("generate");
    if (!token) return;
    const expectedProjectId = projectId;
    const targetDuration = segment.end_sec - segment.start_sec;
    try {
      await api.generateTtsCandidate(expectedProjectId, {
        segment_text: segment.caption_text,
        voice_sample_asset_id: selectedSampleId,
        segment_id: segment.segment_id,
        ...(targetDuration > 0 ? { target_duration_sec: targetDuration } : {}),
      });
      if (!isCurrent(token.epoch, expectedProjectId)) return;
      setMessage("후보를 만들었어요. 들어 보고 결정해 주세요.");
      await loadCandidates(expectedProjectId, segment.segment_id, token.epoch);
    } catch {
      if (isCurrent(token.epoch, expectedProjectId)) {
        setActionError("목소리 후보를 만들지 못했어요. 다시 시도해 주세요.");
      }
    } finally {
      finishAction(token);
    }
  }

  async function reviewCandidate(candidate: TtsCandidateRecord, decision: "approved" | "rejected") {
    const token = beginAction(`review-${candidate.candidate_id}`);
    if (!token) return;
    const expectedProjectId = projectId;
    try {
      const reviewed = await api.reviewTtsCandidate(expectedProjectId, candidate.candidate_id, decision);
      if (!isCurrent(token.epoch, expectedProjectId)) return;
      setCandidates((current) => current.map((item) => (
        item.candidate_id === reviewed.candidate_id ? reviewed : item
      )));
      setMessage(
        decision === "approved"
          ? "청취 승인을 저장했어요. 편집본 적용은 편집 화면에서 따로 진행해 주세요."
          : "청취 거부를 저장했어요. 현재 내레이션은 바뀌지 않아요.",
      );
    } catch {
      if (isCurrent(token.epoch, expectedProjectId)) {
        setActionError("청취 결정을 저장하지 못했어요. 다시 시도해 주세요.");
      }
    } finally {
      finishAction(token);
    }
  }

  const selectedSegment = segments.find((segment) => segment.segment_id === selectedSegmentId) ?? null;
  const isBusy = actionName !== null;

  // 루트가 `vb-setting-control`이었다 -- 설정 화면의 **한 줄짜리 행** 스타일
  // (`display:flex; align-items:center`)이다. 화면 전체가 그 한 줄에 눌려 제목
  // 글자가 세로로 한 자씩 쌓였다. 자산 단계로 옮기고 **캡처해 보고서야** 보였다:
  // 글자·제목 단계·가로 넘침을 다 재도 이건 안 잡힌다.
  //
  // 폭도 정해 준다. 설정 화면은 `.vb-settings`가 42rem으로 잡아 줬는데 자산 화면은
  // 1440px까지 넓어서, 입력과 단추가 화면 끝까지 늘어나 읽기 어려웠다.
  // `justify-items-start`가 없으면 grid가 자식을 열 폭에 맞춰 전부 늘린다.
  return (
    <section aria-label="내 목소리와 읽어보기 후보" className="vb-voice-workspace grid gap-4 justify-items-start">
      <h2>내 목소리 샘플</h2>
      <p className="vb-setting-note">이 기기에 있는 본인 음성만 추가해 주세요.</p>
      {loadState === "loading" || loadState === "idle" ? <p className="text-sm text-muted-foreground">음성 설정을 불러오는 중이에요.</p> : null}
      {loadState === "error" ? (
        <div>
          <p className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">음성 설정을 불러오지 못했어요.</p>
          <Button disabled={initialLoadRef.current?.key === projectId} onClick={() => void loadSettings(projectId, epochRef.current)} type="button">
            다시 불러오기
          </Button>
        </div>
      ) : null}
      {loadState === "ready" ? (
        <>
          <p>{`저장한 내 목소리 ${samples.length}개`}</p>
          <Button disabled={isBusy} onClick={() => void reloadSamples()} type="button">목록 새로고침</Button>
          {samples.length === 0 ? <p className="text-sm text-muted-foreground">아직 저장한 목소리가 없어요.</p> : (
            <ul>
              {samples.map((sample, index) => <li key={sample.asset_id}>{`내 목소리 ${index + 1}`}</li>)}
            </ul>
          )}
          <label className="grid w-full gap-2 text-sm">
            <span>후보에 사용할 목소리</span>
            <NativeSelect
              aria-label="후보에 사용할 목소리"
              disabled={isBusy || samples.length === 0}
              onChange={(event) => setSelectedSampleId(event.target.value)}
              value={selectedSampleId}
            >
              {samples.length === 0 ? <option value="">먼저 목소리를 추가해 주세요</option> : null}
              {samples.map((sample, index) => <option key={sample.asset_id} value={sample.asset_id}>{`내 목소리 ${index + 1}`}</option>)}
            </NativeSelect>
          </label>
        </>
      ) : null}
      <div>
        <label className="grid w-full gap-2 text-sm">
          <span>음성 파일이 있는 곳</span>
          <Input
            aria-label="음성 파일이 있는 곳"
            className="rounded-md border bg-background px-3 py-2"
            disabled={isBusy || loadState !== "ready"}
            onChange={(event) => setLocalPath(event.target.value)}
            placeholder="예: D:\voices\my-voice.wav"
            value={localPath}
          />
        </label>
        <Button disabled={isBusy || loadState !== "ready" || !localPath.trim()} onClick={() => void registerLocalPath()} type="button">
          {actionName === "register" ? "추가하는 중" : "이 위치로 추가"}
        </Button>
      </div>
      <div>
        <label className="grid w-full gap-2 text-sm">
          <span>음성 파일 업로드</span>
          <Input
            key={uploadInputVersion}
            accept="audio/*"
            aria-label="음성 파일 업로드"
            className="rounded-md border bg-background px-3 py-2"
            disabled={isBusy || loadState !== "ready"}
            onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
            type="file"
          />
        </label>
        <Button disabled={isBusy || loadState !== "ready" || !uploadFile} onClick={() => void uploadSelectedFile()} type="button">
          {actionName === "upload" ? "업로드하는 중" : "파일 업로드"}
        </Button>
      </div>
      {/* owner 요청(2026-08-29): "내 유튜브 영상 있는걸로 학습은 안돼?" 본인이
          올린 본인 영상만 대상이라는 전제를 문구로 분명히 한다 -- 확인할 방법이
          없어서 화면 문구가 그 책임을 owner에게 남긴다. */}
      <div>
        <label className="grid w-full gap-2 text-sm">
          <span>내 유튜브 영상 링크</span>
          <Input
            aria-label="내 유튜브 영상 링크"
            className="rounded-md border bg-background px-3 py-2"
            disabled={isBusy || loadState !== "ready"}
            onChange={(event) => setYoutubeUrl(event.target.value)}
            placeholder="본인이 올린 유튜브 영상 주소만 입력해 주세요"
            value={youtubeUrl}
          />
        </label>
        <Button disabled={isBusy || loadState !== "ready" || !youtubeUrl.trim()} onClick={() => void importFromYoutube()} type="button">
          {actionName === "youtube-import" ? "영상에서 가져오는 중" : "유튜브 링크로 배우기"}
        </Button>
        <p className="vb-setting-note">목소리는 바로 후보 만들기에 쓸 수 있어요. 컷 빠르기·색감은 참고용으로 보여만 드려요 -- 실제 편집에 자동으로 입히지 않아요.</p>
        {youtubeImportResult ? (
          <section aria-label="유튜브 영상에서 배운 스타일">
            <p>{`컷 빠르기: 평균 ${youtubeImportResult.pacing.average_clip_duration_sec.toFixed(1)}초마다 전환 (장면 ${youtubeImportResult.pacing.clip_count}개, 가장 짧은 구간 ${youtubeImportResult.pacing.shortest_clip_sec.toFixed(1)}초 · 가장 긴 구간 ${youtubeImportResult.pacing.longest_clip_sec.toFixed(1)}초)`}</p>
            <p>{`색감: 밝기 ${youtubeImportResult.color.average_brightness.toFixed(0)}/255, ${youtubeImportResult.color.warm_cool_bias > 0 ? "따뜻한" : youtubeImportResult.color.warm_cool_bias < 0 ? "차가운" : "중립적인"} 톤`}</p>
          </section>
        ) : null}
      </div>

      <h2>문장별 읽어보기 후보</h2>
      <p className="vb-setting-note">구간을 직접 고른 뒤 후보를 만들고 들어 보세요. 청취 결정만으로 편집본은 바뀌지 않아요.</p>
      {loadState === "ready" && segments.length === 0 ? <p className="text-sm text-muted-foreground">먼저 편집 초안을 만들어 주세요.</p> : null}
      <label className="grid w-full gap-2 text-sm">
        <span>후보를 만들 구간</span>
        <NativeSelect
          aria-label="후보를 만들 구간"
          disabled={isBusy || loadState !== "ready" || segments.length === 0}
          onChange={(event) => selectSegment(event.target.value)}
          value={selectedSegmentId}
        >
          <option value="">구간을 선택해 주세요</option>
          {segments.map((segment, index) => (
            <option key={segment.segment_id} value={segment.segment_id}>
              {`${index + 1}번 구간 · ${segment.caption_text}`}
            </option>
          ))}
        </NativeSelect>
      </label>
      <Button
        disabled={isBusy || candidateLoadState === "loading" || !selectedSegment || !selectedSampleId || !selectedSegment.caption_text.trim()}
        onClick={() => void generateCandidate()}
        type="button"
      >
        {actionName === "generate" ? "후보 만드는 중" : "내 목소리 후보 만들기"}
      </Button>
      {selectedSegment ? (
        <section aria-label="선택한 구간의 읽어보기 후보">
          {candidateLoadState === "loading" ? <p className="text-sm text-muted-foreground">이 구간의 후보를 불러오는 중이에요.</p> : null}
          {candidateLoadState === "error" ? (
            <div>
              <p className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">이 구간의 후보를 불러오지 못했어요.</p>
              <Button
                disabled={candidateLoadRef.current?.key === `${projectId}:${selectedSegment.segment_id}`}
                onClick={() => void loadCandidates(projectId, selectedSegment.segment_id, epochRef.current)}
                type="button"
              >
                후보 다시 불러오기
              </Button>
            </div>
          ) : null}
          {candidateLoadState === "ready" && candidates.length === 0 ? <p className="text-sm text-muted-foreground">이 구간에는 아직 후보가 없어요.</p> : null}
          {candidates.map((candidate, index) => {
            const label = `후보 ${index + 1}`;
            const reviewable = candidate.technical_status === "accepted" && candidate.operator_review_status === "pending";
            return (
              <article aria-label={label} key={candidate.candidate_id}>
                <strong>{label}</strong>
                <p>{`${label} · ${candidateStatus(candidate)}`}</p>
                <p className="text-sm text-muted-foreground">{candidate.source_text}</p>
                <audio
                  aria-label={`${label} 들어보기`}
                  controls
                  src={api.assetContentUrl(projectId, candidate.asset_id)}
                />
                {reviewable ? (
                  <div>
                    <Button
                      disabled={isBusy}
                      onClick={() => void reviewCandidate(candidate, "approved")}
                      type="button"
                    >
                      {`${label} 청취 승인`}
                    </Button>
                    <Button
                      disabled={isBusy}
                      onClick={() => void reviewCandidate(candidate, "rejected")}
                      type="button"
                    >
                      {`${label} 청취 거부`}
                    </Button>
                  </div>
                ) : null}
              </article>
            );
          })}
        </section>
      ) : null}
      {message ? <p aria-live="polite" className="text-sm text-muted-foreground">{message}</p> : null}
      {actionError ? <p aria-live="polite" className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{actionError}</p> : null}
    </section>
  );
}
