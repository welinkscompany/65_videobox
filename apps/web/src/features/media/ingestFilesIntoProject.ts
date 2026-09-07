import { api } from "../../api";

/** 파일 여러 개를 자료실에 넣고 이 프로젝트로 가져온다.
 *
 *  **`AddMediaFiles`에서 빼냈다(2026-09-04).** 같은 절차가 파일 고르기와
 *  끌어다 놓기 두 곳에서 필요해졌는데, 두 벌로 적으면 한쪽만 고쳐지는 날이
 *  온다(이 저장소가 지침을 두 벌 두었다가 어긋난 적이 있다).
 *
 *  결과를 숫자로 돌려주는 이유: 실패를 조용히 넘기지 않기 위해서다. 부르는
 *  쪽이 "몇 개가 들어갔는지" 그대로 말할 수 있어야 한다. */
export type IngestOutcome = Readonly<{ succeeded: number; failed: number }>;

export async function ingestFilesIntoProject(
  files: readonly File[],
  projectId: string,
  requestKey: string,
): Promise<IngestOutcome> {
  if (files.length === 0) return { succeeded: 0, failed: 0 };
  let succeeded = 0;
  let failed = 0;
  try {
    const batch = await api.ingestLibraryAssets([...files], "broll", requestKey);
    for (const item of batch.items) {
      // `duplicate`도 성공이다 -- 이미 자료실에 있는 파일을 다시 넣은 것뿐이고,
      // 창작자에게는 "들어갔다"가 맞는 말이다.
      if (!item.library_asset_id || (item.state !== "ready" && item.state !== "duplicate")) {
        failed += 1;
        continue;
      }
      try {
        await api.materializeLibraryAsset(item.library_asset_id, projectId);
        succeeded += 1;
      } catch {
        failed += 1;
      }
    }
  } catch {
    // 묶음 자체가 실패하면 전부 못 들어간 것이다.
    failed = files.length;
  }
  return { succeeded, failed };
}

/** 들어간 결과를 창작자의 말로 옮긴다. 두 부르는 자리가 같은 문구를 쓰게 한다. */
export function ingestOutcomeMessage({ succeeded, failed }: IngestOutcome): string {
  if (succeeded > 0 && failed === 0) return `${succeeded}개를 더했어요.`;
  if (succeeded > 0) return `${succeeded}개를 더했고 ${failed}개는 더하지 못했어요.`;
  return "파일을 더하지 못했어요. 다시 시도해 주세요.";
}
