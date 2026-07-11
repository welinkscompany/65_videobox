import { useState } from "react";

import { api, type Project } from "./api";

type ProjectOnboardingProps = {
  onProjectCreated: (project: Project) => void;
};

export function ProjectOnboarding({ onProjectCreated }: ProjectOnboardingProps) {
  const [name, setName] = useState("");
  const [narrationPath, setNarrationPath] = useState("");
  const [scriptPath, setScriptPath] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [narrationComplete, setNarrationComplete] = useState(false);
  const [scriptComplete, setScriptComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim() || !narrationPath.trim() || !scriptPath.trim()) {
      setError("프로젝트 이름, 나레이션 경로, 스크립트 경로를 모두 입력하세요.");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    setNarrationComplete(false);
    setScriptComplete(false);
    try {
      const project = await api.createProject({ name: name.trim() });
      onProjectCreated(project);
      await api.registerNarrationAudio(project.project_id, { source_path: narrationPath.trim() });
      setNarrationComplete(true);
      await api.registerScriptDocument(project.project_id, { source_path: scriptPath.trim() });
      setScriptComplete(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "프로젝트를 시작하지 못했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="project-onboarding-heading">
      <p className="section-kicker">새 작업</p>
      <h2 id="project-onboarding-heading">새 프로젝트 시작</h2>
      <p className="meta-copy">현재 PC에서 API 서버가 접근할 수 있는 파일의 로컬 경로를 입력하세요.</p>
      <form onSubmit={(event) => void handleSubmit(event)}>
        <label>
          프로젝트 이름
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>
          나레이션 로컬 경로
          <input value={narrationPath} onChange={(event) => setNarrationPath(event.target.value)} />
        </label>
        <label>
          스크립트 로컬 경로
          <input value={scriptPath} onChange={(event) => setScriptPath(event.target.value)} />
        </label>
        <button className="action-button primary" disabled={isSubmitting} type="submit">
          {isSubmitting ? "프로젝트 준비 중" : "프로젝트 만들고 소스 등록"}
        </button>
      </form>
      {narrationComplete ? <p>나레이션 등록 완료</p> : null}
      {scriptComplete ? <p>스크립트 등록 완료</p> : null}
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
    </section>
  );
}
