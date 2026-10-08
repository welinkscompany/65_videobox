import { Button } from "../components/ui/button";

/** 라우터 기본 오류 화면. 영어 원문("Something went wrong")과 스택을 그대로 보여 주지
 *  않고, 다시 그리기와 목록으로 돌아가기만 준다. 라우터 밖에서도 그려질 수 있어
 *  링크는 router `Link`가 아니라 일반 `<a>`다. 오류 원문은 접어 둔 자세한 내용에만 둔다. */
export function RouteErrorFallback({ error, reset }: Readonly<{ error: unknown; reset: () => void }>) {
  const detail = error instanceof Error ? error.message : String(error ?? "");
  return (
    <main data-testid="route-error" role="alert">
      <h1>화면을 그리다 멈췄어요</h1>
      <p>다시 그려 볼게요. 그래도 안 되면 프로젝트 목록으로 돌아가 주세요.</p>
      <div>
        <Button type="button" onClick={reset}>다시 그리기</Button>
        <a href="/projects">프로젝트 목록으로</a>
      </div>
      {detail ? <details><summary>자세한 내용</summary><pre>{detail}</pre></details> : null}
    </main>
  );
}
