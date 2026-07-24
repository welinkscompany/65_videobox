import { useEffect, useRef, useState } from "react";

import { api, type Project } from "./api";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";

type ProjectOnboardingProps = {
  onProjectCreated: (project: Project) => void | Promise<void>;
  onIngestComplete?: () => void;
  existingProject?: Project;
};

type IngestStatus = "idle" | "loading" | "succeeded" | "failed";

function errorMessage(error: unknown, fallback: string) {
  void error;
  return fallback;
}

export function ProjectOnboarding({ onProjectCreated, onIngestComplete, existingProject }: ProjectOnboardingProps) {
  const [name, setName] = useState("");
  const [narrationPath, setNarrationPath] = useState("");
  const [scriptPath, setScriptPath] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [project, setProject] = useState<Project | null>(existingProject ?? null);
  const [narrationStatus, setNarrationStatus] = useState<IngestStatus>("idle");
  const [scriptStatus, setScriptStatus] = useState<IngestStatus>("idle");
  const [creationError, setCreationError] = useState<string | null>(null);
  const [narrationError, setNarrationError] = useState<string | null>(null);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const completionReported = useRef(false);

  useEffect(() => {
    if (!project || narrationStatus !== "succeeded" || scriptStatus !== "succeeded" || completionReported.current) {
      return;
    }
    completionReported.current = true;
    onIngestComplete?.();
  }, [narrationStatus, onIngestComplete, project, scriptStatus]);

  async function registerNarration(projectId: string) {
    setNarrationStatus("loading");
    setNarrationError(null);
    try {
      await api.registerNarrationAudio(projectId, { source_path: narrationPath.trim() });
      setNarrationStatus("succeeded");
      return true;
    } catch (caught) {
      setNarrationStatus("failed");
      setNarrationError(errorMessage(caught, "나레이션을 등록하지 못했습니다."));
      return false;
    }
  }

  async function registerScript(projectId: string) {
    setScriptStatus("loading");
    setScriptError(null);
    try {
      await api.registerScriptDocument(projectId, { source_path: scriptPath.trim() });
      setScriptStatus("succeeded");
      return true;
    } catch (caught) {
      setScriptStatus("failed");
      setScriptError(errorMessage(caught, "스크립트를 등록하지 못했습니다."));
      return false;
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim() || !narrationPath.trim() || !scriptPath.trim()) {
      setCreationError("프로젝트 이름, 나레이션 경로, 스크립트 경로를 모두 입력하세요.");
      return;
    }
    setIsSubmitting(true);
    setCreationError(null);
    setNarrationStatus("idle");
    setScriptStatus("idle");
    completionReported.current = false;
    try {
      if (project) {
        await Promise.all([registerNarration(project.project_id), registerScript(project.project_id)]);
        return;
      }
      const createdProject = await api.createProject({ name: name.trim() });
      setProject(createdProject);
      const [narrationRegistered, scriptRegistered] = await Promise.all([
        registerNarration(createdProject.project_id),
        registerScript(createdProject.project_id),
      ]);
      if (!narrationRegistered || !scriptRegistered) return;
      await onProjectCreated(createdProject);
    } catch (caught) {
      setCreationError(errorMessage(caught, "프로젝트를 시작하지 못했습니다."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="grid gap-4 rounded-xl border bg-card p-6 text-card-foreground shadow-sm" aria-labelledby="project-onboarding-heading">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">새 작업</p>
      <h2 id="project-onboarding-heading">영상 만들기 시작</h2>
      <p className="text-sm text-muted-foreground">이 컴퓨터에 저장한 나레이션과 대본 파일의 위치를 입력해 주세요.</p>
      <form className="grid gap-4" onSubmit={(event) => void handleSubmit(event)}>
        <label className="grid gap-2 text-sm">
          프로젝트 이름
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label className="grid gap-2 text-sm">
          나레이션 로컬 경로
          <Input value={narrationPath} onChange={(event) => setNarrationPath(event.target.value)} />
        </label>
        <label className="grid gap-2 text-sm">
          스크립트 로컬 경로
          <Input value={scriptPath} onChange={(event) => setScriptPath(event.target.value)} />
        </label>
        <Button disabled={isSubmitting} type="submit">
          {isSubmitting ? "프로젝트 준비 중" : project ? "소스 등록" : "프로젝트 만들고 소스 등록"}
        </Button>
      </form>
      {narrationStatus === "succeeded" ? <p>나레이션 등록 완료</p> : null}
      {narrationStatus === "failed" && project ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
          <p>{narrationError ?? "나레이션을 등록하지 못했습니다."}</p>
          <Button variant="outline" onClick={() => void registerNarration(project.project_id).then(async (ok) => {
            if (ok && scriptStatus === "succeeded") await onProjectCreated(project);
          }).catch(() => setCreationError("프로젝트를 시작하지 못했습니다."))} type="button">
            나레이션 다시 등록
          </Button>
        </div>
      ) : null}
      {scriptStatus === "succeeded" ? <p>스크립트 등록 완료</p> : null}
      {scriptStatus === "failed" && project ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
          <p>{scriptError ?? "스크립트를 등록하지 못했습니다."}</p>
          <Button variant="outline" onClick={() => void registerScript(project.project_id).then(async (ok) => {
            if (ok && narrationStatus === "succeeded") await onProjectCreated(project);
          }).catch(() => setCreationError("프로젝트를 시작하지 못했습니다."))} type="button">
            스크립트 다시 등록
          </Button>
        </div>
      ) : null}
      {creationError ? <p className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{creationError}</p> : null}
      {creationError && project && narrationStatus === "succeeded" && scriptStatus === "succeeded" ? (
        <Button variant="outline" type="button" onClick={() => void Promise.resolve(onProjectCreated(project)).catch(() => setCreationError("프로젝트를 시작하지 못했습니다."))}>
          계속하기
        </Button>
      ) : null}
    </section>
  );
}
