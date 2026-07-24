import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api, type EditingSession } from "../../api";
import { VoiceTtsSettings } from "./VoiceTtsSettings";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function editingSession(
  projectId: string,
  segments = [
    {
      segment_id: "segment_secret_one",
      caption_text: "첫 문장을 소개합니다",
      start_sec: 0,
      end_sec: 2,
      cut_action: "keep",
      review_required: false,
      broll_override: null,
      visual_overlays: [],
      music_override: null,
      tts_replacement: null,
    },
    {
      segment_id: "segment_secret_two",
      caption_text: "두 번째 문장을 이어갑니다",
      start_sec: 2,
      end_sec: 5,
      cut_action: "keep",
      review_required: false,
      broll_override: null,
      visual_overlays: [],
      music_override: null,
      tts_replacement: null,
    },
  ],
): EditingSession {
  return {
    session_id: `session-${projectId}`,
    project_id: projectId,
    timeline_id: `timeline-${projectId}`,
    session_revision: 1,
    history: [],
    segments,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((next, fail) => {
    resolve = next;
    reject = fail;
  });
  return { promise, reject, resolve };
}

function candidate(candidateId: string, segmentId: string, sourceText: string) {
  return {
    candidate_id: candidateId,
    project_id: "project-a",
    segment_id: segmentId,
    asset_id: `asset-${candidateId}`,
    source_text: sourceText,
    technical_status: "accepted",
    operator_review_status: "pending",
    created_at: "2026-07-24T00:00:00Z",
  };
}

describe("VoiceTtsSettings", () => {
  it("keeps removed editing segments out of selection and generation", async () => {
    vi.spyOn(api, "listVoiceSamples").mockResolvedValue([
      { asset_id: "sample_active", asset_type: "voice_sample_audio", storage_uri: "local://voice/active.wav" },
    ]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(editingSession("project-a", [
      {
        segment_id: "segment_active",
        caption_text: "남겨 둘 문장",
        start_sec: 0,
        end_sec: 2,
        cut_action: "keep",
        review_required: false,
        broll_override: null,
        visual_overlays: [],
        music_override: null,
        tts_replacement: null,
      },
      {
        segment_id: "segment_removed",
        caption_text: "삭제할 문장",
        start_sec: 2,
        end_sec: 4,
        cut_action: "remove",
        review_required: false,
        broll_override: null,
        visual_overlays: [],
        music_override: null,
        tts_replacement: null,
      },
    ]));
    const listCandidates = vi.spyOn(api, "listTtsCandidates").mockResolvedValue({ candidates: [] });
    const generate = vi.spyOn(api, "generateTtsCandidate");

    render(<VoiceTtsSettings projectId="project-a" />);

    await screen.findByText("저장한 내 목소리 1개");
    expect(screen.getByRole("option", { name: /남겨 둘 문장/ })).toBeVisible();
    expect(screen.queryByRole("option", { name: /삭제할 문장/ })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("삭제할 문장");

    fireEvent.change(screen.getByLabelText("후보를 만들 구간"), { target: { value: "segment_removed" } });
    fireEvent.click(screen.getByRole("button", { name: "내 목소리 후보 만들기" }));
    expect(listCandidates).not.toHaveBeenCalled();
    expect(generate).not.toHaveBeenCalled();
  });

  it("blocks sample mutations and reload until the initial project read is ready", async () => {
    const initialSamples = deferred<Awaited<ReturnType<typeof api.listVoiceSamples>>>();
    const initialSession = deferred<Awaited<ReturnType<typeof api.getLatestEditingSession>>>();
    const listSamples = vi.spyOn(api, "listVoiceSamples").mockReturnValue(initialSamples.promise);
    vi.spyOn(api, "getLatestEditingSession").mockReturnValue(initialSession.promise);
    const register = vi.spyOn(api, "registerVoiceSample");
    const upload = vi.spyOn(api, "uploadVoiceSample");

    render(<VoiceTtsSettings projectId="project-a" />);

    expect(screen.getByText("음성 설정을 불러오는 중이에요.")).toBeVisible();
    expect(screen.getByLabelText("음성 파일의 로컬 경로")).toBeDisabled();
    expect(screen.getByLabelText("음성 파일 업로드")).toBeDisabled();
    expect(screen.getByRole("button", { name: "로컬 경로로 추가" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "파일 업로드" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "목록 새로고침" })).not.toBeInTheDocument();
    expect(listSamples).toHaveBeenCalledTimes(1);
    expect(register).not.toHaveBeenCalled();
    expect(upload).not.toHaveBeenCalled();

    await act(async () => {
      initialSamples.resolve([]);
      initialSession.resolve(editingSession("project-a"));
    });

    expect(await screen.findByText("저장한 내 목소리 0개")).toBeVisible();
    expect(screen.getByLabelText("음성 파일의 로컬 경로")).toBeEnabled();
    expect(screen.getByLabelText("음성 파일 업로드")).toBeEnabled();
  });

  it("registers a local path, uploads a file, and reloads the creator-facing sample list", async () => {
    const listVoiceSamples = vi.spyOn(api, "listVoiceSamples")
      .mockResolvedValueOnce([
        { asset_id: "sample_secret_one", asset_type: "voice_sample_audio", storage_uri: "local://voice/one.wav" },
      ])
      .mockResolvedValueOnce([
        { asset_id: "sample_secret_one", asset_type: "voice_sample_audio", storage_uri: "local://voice/one.wav" },
        { asset_id: "sample_secret_two", asset_type: "voice_sample_audio", storage_uri: "local://voice/two.wav" },
      ])
      .mockResolvedValueOnce([
        { asset_id: "sample_secret_one", asset_type: "voice_sample_audio", storage_uri: "local://voice/one.wav" },
        { asset_id: "sample_secret_two", asset_type: "voice_sample_audio", storage_uri: "local://voice/two.wav" },
        { asset_id: "sample_secret_three", asset_type: "voice_sample_audio", storage_uri: "local://voice/three.wav" },
      ])
      .mockResolvedValue([
        { asset_id: "sample_secret_one", asset_type: "voice_sample_audio", storage_uri: "local://voice/one.wav" },
        { asset_id: "sample_secret_two", asset_type: "voice_sample_audio", storage_uri: "local://voice/two.wav" },
        { asset_id: "sample_secret_three", asset_type: "voice_sample_audio", storage_uri: "local://voice/three.wav" },
      ]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(editingSession("project-a"));
    const register = vi.spyOn(api, "registerVoiceSample").mockResolvedValue(
      { asset_id: "sample_secret_two", asset_type: "voice_sample_audio", storage_uri: "local://voice/two.wav" },
    );
    const upload = vi.spyOn(api, "uploadVoiceSample").mockResolvedValue(
      { asset_id: "sample_secret_three", asset_type: "voice_sample_audio", storage_uri: "local://voice/three.wav" },
    );

    render(<VoiceTtsSettings projectId="project-a" />);

    expect(await screen.findByText("저장한 내 목소리 1개")).toBeVisible();
    fireEvent.change(screen.getByLabelText("음성 파일의 로컬 경로"), {
      target: { value: "  D:\\voices\\mine.wav  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "로컬 경로로 추가" }));
    await waitFor(() => expect(register).toHaveBeenCalledWith("project-a", { source_path: "D:\\voices\\mine.wav" }));
    expect(await screen.findByText("저장한 내 목소리 2개")).toBeVisible();

    const file = new File(["voice"], "my-voice.wav", { type: "audio/wav" });
    fireEvent.change(screen.getByLabelText("음성 파일 업로드"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "파일 업로드" }));
    await waitFor(() => expect(upload).toHaveBeenCalledWith("project-a", file));
    expect(await screen.findByText("저장한 내 목소리 3개")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "목록 새로고침" }));
    await waitFor(() => expect(listVoiceSamples).toHaveBeenCalledTimes(4));
    expect(screen.getAllByText("내 목소리 1").length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(/sample_secret|segment_secret|session-project/);
  });

  it("keeps the newest A candidate read when an older A success arrives after A to B to A", async () => {
    vi.spyOn(api, "listVoiceSamples").mockResolvedValue([
      { asset_id: "sample_active", asset_type: "voice_sample_audio", storage_uri: "local://voice/active.wav" },
    ]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(editingSession("project-a"));
    const firstA = deferred<Awaited<ReturnType<typeof api.listTtsCandidates>>>();
    const readB = deferred<Awaited<ReturnType<typeof api.listTtsCandidates>>>();
    const newestA = deferred<Awaited<ReturnType<typeof api.listTtsCandidates>>>();
    const listCandidates = vi.spyOn(api, "listTtsCandidates")
      .mockReturnValueOnce(firstA.promise)
      .mockReturnValueOnce(readB.promise)
      .mockReturnValueOnce(newestA.promise);

    render(<VoiceTtsSettings projectId="project-a" />);
    await screen.findByText("저장한 내 목소리 1개");
    const segmentSelect = screen.getByLabelText("후보를 만들 구간");

    fireEvent.change(segmentSelect, { target: { value: "segment_secret_one" } });
    fireEvent.change(segmentSelect, { target: { value: "segment_secret_two" } });
    fireEvent.change(segmentSelect, { target: { value: "segment_secret_one" } });
    expect(listCandidates).toHaveBeenCalledTimes(3);

    await act(async () => newestA.resolve({
      candidates: [candidate("candidate-newest", "segment_secret_one", "가장 최근에 불러온 후보")],
    }));
    expect(await screen.findByText("가장 최근에 불러온 후보")).toBeVisible();

    await act(async () => {
      readB.resolve({ candidates: [] });
      firstA.resolve({
        candidates: [candidate("candidate-old", "segment_secret_one", "늦게 도착한 오래된 후보")],
      });
    });

    expect(screen.getByText("가장 최근에 불러온 후보")).toBeVisible();
    expect(screen.queryByText("늦게 도착한 오래된 후보")).not.toBeInTheDocument();
  });

  it("keeps the newest A candidate read ready when an older A error arrives late", async () => {
    vi.spyOn(api, "listVoiceSamples").mockResolvedValue([
      { asset_id: "sample_active", asset_type: "voice_sample_audio", storage_uri: "local://voice/active.wav" },
    ]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(editingSession("project-a"));
    const firstA = deferred<Awaited<ReturnType<typeof api.listTtsCandidates>>>();
    const readB = deferred<Awaited<ReturnType<typeof api.listTtsCandidates>>>();
    const newestA = deferred<Awaited<ReturnType<typeof api.listTtsCandidates>>>();
    vi.spyOn(api, "listTtsCandidates")
      .mockReturnValueOnce(firstA.promise)
      .mockReturnValueOnce(readB.promise)
      .mockReturnValueOnce(newestA.promise);

    render(<VoiceTtsSettings projectId="project-a" />);
    await screen.findByText("저장한 내 목소리 1개");
    const segmentSelect = screen.getByLabelText("후보를 만들 구간");
    fireEvent.change(segmentSelect, { target: { value: "segment_secret_one" } });
    fireEvent.change(segmentSelect, { target: { value: "segment_secret_two" } });
    fireEvent.change(segmentSelect, { target: { value: "segment_secret_one" } });

    await act(async () => newestA.resolve({
      candidates: [candidate("candidate-newest", "segment_secret_one", "오류보다 최신인 후보")],
    }));
    expect(await screen.findByText("오류보다 최신인 후보")).toBeVisible();

    await act(async () => {
      readB.resolve({ candidates: [] });
      firstA.reject(new Error("late stale error"));
    });

    expect(screen.getByText("오류보다 최신인 후보")).toBeVisible();
    expect(screen.queryByText("이 구간의 후보를 불러오지 못했어요.")).not.toBeInTheDocument();
  });

  it("preserves a rejected local path POST for an explicit retry", async () => {
    vi.spyOn(api, "listVoiceSamples")
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { asset_id: "sample-saved", asset_type: "voice_sample_audio", storage_uri: "local://voice/saved.wav" },
      ]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    const register = vi.spyOn(api, "registerVoiceSample")
      .mockRejectedValueOnce(new Error("post failed"))
      .mockResolvedValueOnce({
        asset_id: "sample-saved",
        asset_type: "voice_sample_audio",
        storage_uri: "local://voice/saved.wav",
      });

    render(<VoiceTtsSettings projectId="project-a" />);
    await screen.findByText("저장한 내 목소리 0개");
    const path = screen.getByLabelText("음성 파일의 로컬 경로");
    fireEvent.change(path, { target: { value: "  D:\\voices\\retry.wav  " } });
    fireEvent.click(screen.getByRole("button", { name: "로컬 경로로 추가" }));

    expect(await screen.findByText("내 목소리를 추가하지 못했어요. 다시 시도해 주세요.")).toBeVisible();
    expect(path).toHaveValue("  D:\\voices\\retry.wav  ");
    fireEvent.click(screen.getByRole("button", { name: "로컬 경로로 추가" }));
    await waitFor(() => expect(register).toHaveBeenCalledTimes(2));
    expect(register).toHaveBeenNthCalledWith(1, "project-a", { source_path: "D:\\voices\\retry.wav" });
    expect(register).toHaveBeenNthCalledWith(2, "project-a", { source_path: "D:\\voices\\retry.wav" });
    expect(await screen.findByText("저장한 내 목소리 1개")).toBeVisible();
    expect(path).toHaveValue("");
  });

  it("preserves a rejected upload POST and clears the file only after a committed retry", async () => {
    vi.spyOn(api, "listVoiceSamples")
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { asset_id: "sample-uploaded", asset_type: "voice_sample_audio", storage_uri: "local://voice/uploaded.wav" },
      ]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    const upload = vi.spyOn(api, "uploadVoiceSample")
      .mockRejectedValueOnce(new Error("post failed"))
      .mockResolvedValueOnce({
        asset_id: "sample-uploaded",
        asset_type: "voice_sample_audio",
        storage_uri: "local://voice/uploaded.wav",
      });

    render(<VoiceTtsSettings projectId="project-a" />);
    await screen.findByText("저장한 내 목소리 0개");
    const fileInput = screen.getByLabelText("음성 파일 업로드") as HTMLInputElement;
    const file = new File(["voice"], "retry.wav", { type: "audio/wav" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "파일 업로드" }));

    expect(await screen.findByText("내 목소리 파일을 추가하지 못했어요. 다시 시도해 주세요.")).toBeVisible();
    expect(fileInput.files?.[0]).toBe(file);
    fireEvent.click(screen.getByRole("button", { name: "파일 업로드" }));
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
    expect(upload).toHaveBeenNthCalledWith(1, "project-a", file);
    expect(upload).toHaveBeenNthCalledWith(2, "project-a", file);
    expect(await screen.findByText("저장한 내 목소리 1개")).toBeVisible();
    expect(screen.getByRole("button", { name: "파일 업로드" })).toBeDisabled();
    expect(
      (screen.getByLabelText("음성 파일 업로드") as HTMLInputElement).files,
    ).toHaveLength(0);
  });

  it("does not repeat a committed local-path POST when its refresh fails", async () => {
    vi.spyOn(api, "listVoiceSamples")
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce(new Error("refresh failed"))
      .mockResolvedValueOnce([
        { asset_id: "sample-saved", asset_type: "voice_sample_audio", storage_uri: "local://voice/saved.wav" },
      ]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    const register = vi.spyOn(api, "registerVoiceSample").mockResolvedValue({
      asset_id: "sample-saved",
      asset_type: "voice_sample_audio",
      storage_uri: "local://voice/saved.wav",
    });

    render(<VoiceTtsSettings projectId="project-a" />);
    await screen.findByText("저장한 내 목소리 0개");
    const path = screen.getByLabelText("음성 파일의 로컬 경로");
    fireEvent.change(path, { target: { value: "D:\\voices\\saved.wav" } });
    const add = screen.getByRole("button", { name: "로컬 경로로 추가" });
    fireEvent.click(add);

    expect(await screen.findByText("내 목소리는 저장됐지만 목록을 새로 불러오지 못했어요. 목록 새로고침으로 확인해 주세요.")).toBeVisible();
    expect(path).toHaveValue("");
    expect(add).toBeDisabled();
    fireEvent.click(add);
    expect(register).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "목록 새로고침" }));
    expect(await screen.findByText("저장한 내 목소리 1개")).toBeVisible();
    expect(register).toHaveBeenCalledTimes(1);
  });

  it("does not repeat a committed upload POST when its refresh fails", async () => {
    vi.spyOn(api, "listVoiceSamples")
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce(new Error("refresh failed"))
      .mockResolvedValueOnce([
        { asset_id: "sample-uploaded", asset_type: "voice_sample_audio", storage_uri: "local://voice/uploaded.wav" },
      ]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    const upload = vi.spyOn(api, "uploadVoiceSample").mockResolvedValue({
      asset_id: "sample-uploaded",
      asset_type: "voice_sample_audio",
      storage_uri: "local://voice/uploaded.wav",
    });

    render(<VoiceTtsSettings projectId="project-a" />);
    await screen.findByText("저장한 내 목소리 0개");
    const fileInput = screen.getByLabelText("음성 파일 업로드") as HTMLInputElement;
    const file = new File(["voice"], "saved.wav", { type: "audio/wav" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    const uploadButton = screen.getByRole("button", { name: "파일 업로드" });
    fireEvent.click(uploadButton);

    expect(await screen.findByText("내 목소리는 저장됐지만 목록을 새로 불러오지 못했어요. 목록 새로고침으로 확인해 주세요.")).toBeVisible();
    expect(uploadButton).toBeDisabled();
    expect(
      (screen.getByLabelText("음성 파일 업로드") as HTMLInputElement).files,
    ).toHaveLength(0);
    fireEvent.click(uploadButton);
    expect(upload).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "목록 새로고침" }));
    expect(await screen.findByText("저장한 내 목소리 1개")).toBeVisible();
    expect(upload).toHaveBeenCalledTimes(1);
  });

  it("creates and reviews candidates for the explicitly selected segment without applying TTS", async () => {
    vi.spyOn(api, "listVoiceSamples").mockResolvedValue([
      { asset_id: "sample_secret_one", asset_type: "voice_sample_audio", storage_uri: "local://voice/one.wav" },
    ]);
    const getLatest = vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(editingSession("project-a"));
    const listCandidates = vi.spyOn(api, "listTtsCandidates")
      .mockResolvedValueOnce({ candidates: [{
        candidate_id: "candidate_secret_one",
        project_id: "project-a",
        segment_id: "segment_secret_two",
        asset_id: "asset_secret_one",
        source_text: "두 번째 문장을 이어갑니다",
        technical_status: "accepted",
        operator_review_status: "pending",
        created_at: "2026-07-24T00:00:00Z",
      }] })
      .mockResolvedValueOnce({ candidates: [{
        candidate_id: "candidate_secret_one",
        project_id: "project-a",
        segment_id: "segment_secret_two",
        asset_id: "asset_secret_one",
        source_text: "두 번째 문장을 이어갑니다",
        technical_status: "accepted",
        operator_review_status: "pending",
        created_at: "2026-07-24T00:00:00Z",
      }, {
        candidate_id: "candidate_secret_two",
        project_id: "project-a",
        segment_id: "segment_secret_two",
        asset_id: "asset_secret_two",
        source_text: "두 번째 문장을 이어갑니다",
        technical_status: "accepted",
        operator_review_status: "pending",
        created_at: "2026-07-24T00:01:00Z",
      }] });
    const generate = vi.spyOn(api, "generateTtsCandidate").mockResolvedValue({
      candidate_id: "candidate_secret_two",
      segment_id: "segment_secret_two",
      asset_id: "asset_secret_two",
      asset_type: "generated_tts_audio",
      storage_uri: "local://tts/two.wav",
      source_text: "두 번째 문장을 이어갑니다",
      technical_status: "accepted",
      operator_review_status: "pending",
    });
    const review = vi.spyOn(api, "reviewTtsCandidate")
      .mockResolvedValueOnce({
        candidate_id: "candidate_secret_one",
        project_id: "project-a",
        segment_id: "segment_secret_two",
        asset_id: "asset_secret_one",
        source_text: "두 번째 문장을 이어갑니다",
        technical_status: "accepted",
        operator_review_status: "approved",
        created_at: "2026-07-24T00:00:00Z",
      })
      .mockResolvedValueOnce({
        candidate_id: "candidate_secret_two",
        project_id: "project-a",
        segment_id: "segment_secret_two",
        asset_id: "asset_secret_two",
        source_text: "두 번째 문장을 이어갑니다",
        technical_status: "accepted",
        operator_review_status: "rejected",
        created_at: "2026-07-24T00:01:00Z",
      });
    const apply = vi.spyOn(api, "updateEditingSessionTtsReplacement");

    render(<VoiceTtsSettings projectId="project-a" />);

    await screen.findByText("저장한 내 목소리 1개");
    expect(listCandidates).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("후보를 만들 구간"), { target: { value: "segment_secret_two" } });
    await waitFor(() => expect(listCandidates).toHaveBeenCalledWith("project-a", "segment_secret_two"));
    expect(screen.getByText("후보 1")).toBeVisible();
    expect(screen.getByLabelText("후보 1 들어보기")).toHaveAttribute(
      "src",
      "/api/projects/project-a/assets/asset_secret_one/content",
    );

    fireEvent.click(screen.getByRole("button", { name: "내 목소리 후보 만들기" }));
    await waitFor(() => expect(generate).toHaveBeenCalledWith("project-a", {
      segment_text: "두 번째 문장을 이어갑니다",
      voice_sample_asset_id: "sample_secret_one",
      segment_id: "segment_secret_two",
      target_duration_sec: 3,
    }));
    expect(await screen.findByText("후보 2")).toBeVisible();

    const approve = screen.getByRole("button", { name: "후보 1 청취 승인" });
    fireEvent.click(approve);
    fireEvent.click(approve);
    await waitFor(() => expect(review).toHaveBeenCalledTimes(1));
    expect(review).toHaveBeenCalledWith("project-a", "candidate_secret_one", "approved");
    expect(await screen.findByText("후보 1 · 청취 승인됨")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "후보 2 청취 거부" }));
    await waitFor(() => expect(review).toHaveBeenCalledWith("project-a", "candidate_secret_two", "rejected"));
    expect(await screen.findByText("후보 2 · 청취 거부됨")).toBeVisible();
    expect(getLatest).toHaveBeenCalledTimes(1);
    expect(apply).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /적용/ })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/candidate_secret|asset_secret|segment_secret|sample_secret/);
  });

  it("shows recoverable load errors and keeps list requests single-flight", async () => {
    const pendingSamples = deferred<Awaited<ReturnType<typeof api.listVoiceSamples>>>();
    const listSamples = vi.spyOn(api, "listVoiceSamples")
      .mockRejectedValueOnce(new Error("local read failed"))
      .mockReturnValueOnce(pendingSamples.promise)
      .mockResolvedValue([]);
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(editingSession("project-a"));
    const pendingCandidates = deferred<Awaited<ReturnType<typeof api.listTtsCandidates>>>();
    const listCandidates = vi.spyOn(api, "listTtsCandidates")
      .mockReturnValueOnce(pendingCandidates.promise)
      .mockResolvedValueOnce({ candidates: [] });

    render(<VoiceTtsSettings projectId="project-a" />);

    expect(await screen.findByText("음성 설정을 불러오지 못했어요.")).toBeVisible();
    const retry = screen.getByRole("button", { name: "다시 불러오기" });
    fireEvent.click(retry);
    fireEvent.click(retry);
    expect(listSamples).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "다시 불러오기" })).not.toBeInTheDocument();
    expect(screen.getByText("음성 설정을 불러오는 중이에요.")).toBeVisible();
    await act(async () => pendingSamples.resolve([
      { asset_id: "sample_retry", asset_type: "voice_sample_audio", storage_uri: "local://voice/retry.wav" },
    ]));
    expect(await screen.findByText("저장한 내 목소리 1개")).toBeVisible();

    fireEvent.change(screen.getByLabelText("후보를 만들 구간"), { target: { value: "segment_secret_one" } });
    expect(screen.getByRole("button", { name: "내 목소리 후보 만들기" })).toBeDisabled();
    await act(async () => pendingCandidates.reject(new Error("candidate read failed")));
    expect(await screen.findByText("이 구간의 후보를 불러오지 못했어요.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "후보 다시 불러오기" }));
    await waitFor(() => expect(listCandidates).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("이 구간에는 아직 후보가 없어요.")).toBeVisible();
  });

  it("fences late project A responses after switching to project B", async () => {
    const samplesA = deferred<Awaited<ReturnType<typeof api.listVoiceSamples>>>();
    const sessionA = deferred<Awaited<ReturnType<typeof api.getLatestEditingSession>>>();
    vi.spyOn(api, "listVoiceSamples").mockImplementation((projectId) => (
      projectId === "project-a"
        ? samplesA.promise
        : Promise.resolve([{ asset_id: "sample_b", asset_type: "voice_sample_audio", storage_uri: "local://voice/b.wav" }])
    ));
    vi.spyOn(api, "getLatestEditingSession").mockImplementation((projectId) => (
      projectId === "project-a"
        ? sessionA.promise
        : Promise.resolve(editingSession("project-b", [{
          segment_id: "segment_b",
          caption_text: "B 프로젝트 문장",
          start_sec: 0,
          end_sec: 1,
          cut_action: "keep",
          review_required: false,
          broll_override: null,
          visual_overlays: [],
          music_override: null,
          tts_replacement: null,
        }]))
    ));

    const view = render(<VoiceTtsSettings projectId="project-a" />);
    view.rerender(<VoiceTtsSettings projectId="project-b" />);

    expect(await screen.findByText("저장한 내 목소리 1개")).toBeVisible();
    expect(screen.getByRole("option", { name: /B 프로젝트 문장/ })).toBeVisible();

    await act(async () => {
      samplesA.resolve([
        { asset_id: "sample_a_1", asset_type: "voice_sample_audio", storage_uri: "local://voice/a1.wav" },
        { asset_id: "sample_a_2", asset_type: "voice_sample_audio", storage_uri: "local://voice/a2.wav" },
      ]);
      sessionA.resolve(editingSession("project-a", [{
        segment_id: "segment_a",
        caption_text: "늦게 도착한 A 프로젝트 문장",
        start_sec: 0,
        end_sec: 1,
        cut_action: "keep",
        review_required: false,
        broll_override: null,
        visual_overlays: [],
        music_override: null,
        tts_replacement: null,
      }]));
    });

    expect(screen.getByText("저장한 내 목소리 1개")).toBeVisible();
    expect(screen.getByRole("option", { name: /B 프로젝트 문장/ })).toBeVisible();
    expect(screen.queryByRole("option", { name: /늦게 도착한 A 프로젝트 문장/ })).not.toBeInTheDocument();
  });
});
