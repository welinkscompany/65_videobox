import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { NativeSelect } from "../../../components/ui/native-select";
import type {
  RightDockMemory,
  RightDockMemoryCandidate,
} from "./rightDockTypes";

const categoryLabels: Record<
  RightDockMemoryCandidate["category"],
  string
> = {
  pacing: "편집 템포",
  caption: "자막",
  audio: "음악과 소리",
  tone: "영상 분위기",
  workflow: "작업 방식",
};

export function YujinMemoryPanel({
  memory,
}: {
  memory: RightDockMemory;
}) {
  return (
    <section
      aria-label="유진 기억"
      className="vb-editor-workbench__summary"
    >
      <h2>기억</h2>
      <p>내가 확인한 편집 취향만 저장합니다.</p>
      <div>
        <label>
          기억 종류
          <NativeSelect
            value={memory.candidateCategory}
            disabled={memory.createAction === "creating"}
            onChange={(event) => memory.onCandidateCategoryChange(
              event.target.value as RightDockMemoryCandidate["category"],
            )}
          >
            {Object.entries(categoryLabels).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </NativeSelect>
        </label>
        <label>
          기억 후보
          <Input
            value={memory.candidateDraft}
            maxLength={280}
            disabled={memory.createAction === "creating"}
            onChange={(event) => memory.onCandidateDraftChange(
              event.target.value,
            )}
          />
        </label>
        <Button
          type="button"
          disabled={
            memory.createAction === "creating"
            || !memory.canCreateCandidate
          }
          onClick={() => void memory.onCreateCandidate()}
        >
          {memory.createAction === "creating"
            ? "후보 만드는 중"
            : "기억 후보 만들기"}
        </Button>
        {memory.createError ? <p>{memory.createError}</p> : null}
      </div>
      {memory.loadError ? <p>{memory.loadError}</p> : null}
      {!memory.candidates.length ? (
        <p>현재 대화에는 확인할 기억이 없어요.</p>
      ) : memory.candidates.map((candidate) => (
        <article key={candidate.candidateId}>
          <p>{candidate.text}</p>
          <p>{categoryLabels[candidate.category]}</p>
          <MemoryCandidateStatus
            candidate={candidate}
            memory={memory}
          />
        </article>
      ))}
    </section>
  );
}

function MemoryCandidateStatus({
  candidate,
  memory,
}: {
  candidate: RightDockMemoryCandidate;
  memory: RightDockMemory;
}) {
  if (candidate.action === "approving") {
    return <p>승인 중</p>;
  }
  if (candidate.action === "rejecting") {
    return <p>거절 중</p>;
  }
  if (candidate.action === "saving") {
    return <p>저장 중</p>;
  }
  if (candidate.action === "deleting") {
    return <p>삭제 중</p>;
  }
  if (candidate.status === "pending") {
    return (
      <div>
        <Button
          type="button"
          onClick={() => void memory.onApproveAndStore(
            candidate.candidateId,
          )}
        >
          승인하고 저장
        </Button>
        <Button
          type="button"
          onClick={() => void memory.onReject(candidate.candidateId)}
        >
          거절
        </Button>
      </div>
    );
  }
  if (candidate.status === "rejected") {
    return <p>저장하지 않음</p>;
  }
  if (candidate.storageStatus === "deleted") {
    return <p>삭제됨</p>;
  }
  if (candidate.storageStatus === "claimed") {
    if (candidate.retryable) {
      return (
        <div>
          <p>저장 처리가 오래 걸리고 있어요. 다시 확인할 수 있어요.</p>
          <Button
            type="button"
            onClick={() => void memory.onStore(candidate.candidateId)}
          >
            저장 다시 시도
          </Button>
        </div>
      );
    }
    return <p>저장 처리 중</p>;
  }
  if (candidate.error === "delete") {
    return (
      <div>
        <p>기억을 삭제하지 못했어요. 다시 시도할 수 있어요.</p>
        <Button
          type="button"
          onClick={() => void memory.onDelete(candidate.candidateId)}
        >
          삭제 다시 시도
        </Button>
      </div>
    );
  }
  if (candidate.storageStatus === "stored") {
    return (
      <div>
        <p>저장됨</p>
        <Button
          type="button"
          onClick={() => void memory.onDelete(candidate.candidateId)}
        >
          기억 삭제
        </Button>
      </div>
    );
  }
  // 켜져 있지 않은 것은 실패가 아니다. `저장 다시 시도`를 내주면 owner는 눌러도
  // 안 되는 단추를 계속 누르게 된다.
  if (candidate.error === "not_configured") {
    return <p>기억 기능이 아직 켜져 있지 않아요. 편집과 대화는 그대로 쓸 수 있어요.</p>;
  }
  if (
    candidate.error === "save"
    || candidate.storageStatus === "failed_retryable"
    || candidate.storageStatus === "ambiguous"
    || candidate.storageStatus === "event_pending"
  ) {
    return (
      <div>
        <p>기억을 저장하지 못했어요. 편집과 대화는 계속할 수 있어요.</p>
        <Button
          type="button"
          onClick={() => void memory.onStore(candidate.candidateId)}
        >
          저장 다시 시도
        </Button>
      </div>
    );
  }
  return (
    <Button
      type="button"
      onClick={() => void memory.onStore(candidate.candidateId)}
    >
      저장하기
    </Button>
  );
}
