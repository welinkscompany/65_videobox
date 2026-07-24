import { useEffect, useRef, useState } from "react";

import {
  api,
  type AssetResponse,
  type EditingSessionSegment,
  type TtsCandidateRecord,
} from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { NativeSelect } from "../../components/ui/native-select";

type LoadState = "idle" | "loading" | "ready" | "error";
type ActionToken = { epoch: number; name: string };
type LoadToken = { epoch: number; key: string };

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
          : "청취 거부를 저장했어요. 현재 나레이션은 바뀌지 않아요.",
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

  return (
    <section aria-label="내 목소리와 읽어보기 후보" className="vb-setting-control">
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
          <label className="grid gap-2 text-sm">
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
        <label className="grid gap-2 text-sm">
          <span>음성 파일의 로컬 경로</span>
          <Input
            aria-label="음성 파일의 로컬 경로"
            className="rounded-md border bg-background px-3 py-2"
            disabled={isBusy || loadState !== "ready"}
            onChange={(event) => setLocalPath(event.target.value)}
            placeholder="예: D:\voices\my-voice.wav"
            value={localPath}
          />
        </label>
        <Button disabled={isBusy || loadState !== "ready" || !localPath.trim()} onClick={() => void registerLocalPath()} type="button">
          {actionName === "register" ? "추가하는 중" : "로컬 경로로 추가"}
        </Button>
      </div>
      <div>
        <label className="grid gap-2 text-sm">
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

      <h2>문장별 읽어보기 후보</h2>
      <p className="vb-setting-note">구간을 직접 고른 뒤 후보를 만들고 들어 보세요. 청취 결정만으로 편집본은 바뀌지 않아요.</p>
      {loadState === "ready" && segments.length === 0 ? <p className="text-sm text-muted-foreground">먼저 편집 초안을 만들어 주세요.</p> : null}
      <label className="grid gap-2 text-sm">
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
