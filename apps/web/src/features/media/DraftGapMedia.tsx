import { useState } from "react";
import { api } from "../../api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";

export function DraftGapMedia({ projectId, returnTo }: { projectId: string; returnTo: string }) {
  const [status, setStatus] = useState("장면 영상을 추가하면 초안 준비에 다시 반영할 수 있어요.");
  const [file, setFile] = useState<File | null>(null);
  async function upload() {
    if (!file) return setStatus("먼저 장면 영상을 골라 주세요.");
    setStatus("영상을 프로젝트에 추가하고 있어요.");
    try { const asset = await api.uploadDraftBroll(projectId, file); setStatus(asset.scan_status === "local_ready" ? "영상 추가를 확인했어요. 기획으로 돌아가 다시 준비해 주세요." : "영상을 추가했어요."); }
    catch { setStatus("영상을 추가하지 못했어요. 파일을 확인한 뒤 다시 시도해 주세요."); }
  }
  return <section aria-label="장면 영상 추가"><h1>장면 영상 추가</h1><p role="status">{status}</p><label htmlFor="gap-broll-file">장면 영상 파일</label><Input id="gap-broll-file" type="file" accept="video/*,.mp4,.mov,.webm,.mkv" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /><Button type="button" onClick={() => void upload()}>영상 추가</Button><Button type="button" variant="outline" onClick={() => window.location.assign(returnTo)}>기획으로 돌아가기</Button></section>;
}
