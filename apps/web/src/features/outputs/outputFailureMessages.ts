// `OutputsPage.tsx`(완성본·자막·CapCut 초안 카드)에 있던 표를 그대로 옮겨
// 왔다. `VariantOutputCard`(가로세로 변형본 카드)와 `VariantConflictPanel`도
// 같은 실패를 낸다 -- 서버가 코드를 보내고, 화면은 그걸 owner가 할 수 있는
// 일로 옮겨야 한다(task-3-brief.md). 표를 나눠 쓴다: 카드마다 새 표를
// 만들면 같은 코드가 화면마다 다른 문장으로 뜨는 사고가 난다.
//
// 백엔드가 실패 이유를 코드로 보내 준다. 옮길 문구가 없는 코드는 그대로
// 흘려보내지 않고 원래 쓰던 한 줄로 돌아간다 -- 화면에 영어를 띄우느니
// 덜 구체적인 편이 낫다.
const FINAL_RENDER_FAILURES: Record<string, string> = {
  final_output_requires_review_approval: "검토에서 아직 승인하지 않았어요. 검토를 마치면 완성본을 만들 수 있어요.",
  draft_bundle_gap_blocks_final_and_capcut_output: "장면이 비어 있는 구간이 있어요. 그 구간에 영상을 넣은 뒤 다시 만들어 주세요.",
  // 빈 편집판에서 바로 누른 경우다. 엔진은 문장으로 보낸다(`local_pipeline`의
  // 합성 단계) -- 코드가 아니어서 표에 없으면 "완성본을 만들지 못했어요"로
  // 뭉개졌고, 정작 할 일(영상 넣기)이 화면에서 사라졌다(2026-09-06 실측).
  "Timeline has no composable clips to render.": "아직 넣은 영상이 없어요. 편집 화면에서 영상이나 사진을 넣은 뒤 다시 만들어 주세요.",
  // 여기서부터는 가로세로 변형본(`VariantOutputCard`)을 만들 때만 나오는
  // 사유다 -- 완성본 경로와 같은 함수(`start_final_render_job` ->
  // `assert_timeline_output_allowed`)를 타므로 위 세 사유도 변형본에서
  // 그대로 나올 수 있고, 아래는 변형본 전용 실패다(local_pipeline.py의
  // `start_variant_renders`/`_materialize_variant_for_output`).
  stale_master_revision: "마스터 편집본이 그 사이에 바뀌었어요. 화면을 새로 고친 뒤 다시 만들어 주세요.",
  variant_session_mismatch: "이 변형이 지금 편집본과 연결돼 있지 않아요. 화면을 새로 고친 뒤 다시 시도해 주세요.",
  // 서버가 렌더를 맡을 일꾼을 못 띄웠을 때(routers/outputs.py) -- 만드는
  // 요청 자체는 받았지만 시작이 안 된 경우다.
  worker_start_failed: "출력을 시작하지 못했어요. 잠시 후 다시 시도해 주세요.",
  // 렌더는 시작됐지만 도중에 실패했을 때. 화면이 상태를 다시 물어 알아낸다
  // (`OutputsPage.tsx`의 변형 재확인 로직에서 이 코드를 붙인다).
  renderer_failed: "출력을 만드는 중에 오류가 났어요. 다시 만들어 주세요.",
  // 엔진이 **안전 문구로 바꿔** 보내는 사유 셋이다
  // (`packages/core-engine/src/videobox_core_engine/job_error_message.py`의
  // `safe_job_error_message`). 예외 문구에 호스트 파일 경로나 실행한 명령이
  // 섞여 나가는 것을 막느라 코드로 바꾸는데, 그 코드가 여기 없으면 화면은
  // "이 출력을 만들지 못했어요." 한 줄로 뭉갠다 -- 예전에 전부
  // `renderer_failed`로 찍히던 때보다 오히려 할 일이 사라졌다.
  // 그 함수가 만드는 코드는 이 셋이 전부이고, 나머지 예외는 문장 그대로 온다.
  asset_file_missing: "쓰던 파일을 찾지 못했어요. 그 파일이 자리에 있는지 확인한 뒤 다시 만들어 주세요.",
  asset_file_permission_denied: "쓰던 파일을 열 수 없었어요. 그 파일이 다른 프로그램에서 열려 있지 않은지 확인한 뒤 다시 만들어 주세요.",
  external_command_failed: "영상을 합치는 도중에 멈췄어요. 다시 만들어 주세요. 그래도 안 되면 쓰던 파일이 온전한지 확인해 주세요.",
};

/** 무엇이 낡아서 막혔는지. 엔진은 `stale_output_asset: <사유>` 한 코드에 여러
 *  사유를 실어 보낸다(`output_source_verifier.py`) -- 정확히 일치하는 표로는
 *  이 무리를 통째로 놓친다. 사유는 앞에서부터 맞춰 본다. */
const STALE_OUTPUT_REASONS: ReadonlyArray<readonly [string, string]> = [
  ["subtitle", "편집을 고친 뒤 자막을 다시 만들지 않았어요. 자막을 먼저 만든 다음 완성본을 만들어 주세요."],
  ["review", "편집을 고친 뒤 검토를 다시 하지 않았어요. 검토를 마치면 완성본을 만들 수 있어요."],
  ["editing session", "편집본이 그 사이에 바뀌었어요. 화면을 새로 고친 뒤 다시 만들어 주세요."],
  ["timeline is not the active", "지금 편집본이 아닌 다른 편집본으로 만들려고 했어요. 화면을 새로 고쳐 주세요."],
  ["content SHA-256", "쓰던 파일이 바뀌었어요. 그 파일을 다시 넣은 뒤 만들어 주세요."],
  ["media revision", "쓰던 파일이 바뀌었어요. 그 파일을 다시 넣은 뒤 만들어 주세요."],
  ["missing or unavailable", "쓰던 파일을 찾지 못했어요. 그 파일이 자리에 있는지 확인해 주세요."],
  ["asset identity", "쓰던 파일이 다른 것으로 바뀌었어요. 그 파일을 다시 넣어 주세요."],
  ["variant", "가로세로 변형본이 그 사이에 바뀌었어요. 화면을 새로 고친 뒤 다시 만들어 주세요."],
];

function outputFailureMessage(reason: string | null | undefined, fallback: string) {
  const trimmed = reason?.trim();
  if (!trimmed) return fallback;
  const mapped = FINAL_RENDER_FAILURES[trimmed];
  if (mapped) return mapped;
  if (trimmed.startsWith("stale_output_asset")) {
    const detail = trimmed.slice("stale_output_asset".length).replace(/^:\s*/, "");
    // 사유는 문장이라 낱말이 가운데 오기도 한다("materialized source is
    // missing or unavailable") -- 앞머리 대신 포함으로 맞춘다. 목록은 위에서부터
    // 보므로 더 구체적인 것을 먼저 적는다.
    const known = STALE_OUTPUT_REASONS.find(([needle]) => detail.includes(needle));
    // 사유는 엔진이 늘리는 자리다. 모르는 사유라도 **무언가 낡았다**는 것은
    // 확실하니 그만큼은 말한다 -- 코드를 그대로 띄우지는 않는다.
    return known?.[1] ?? "만들려는 사이에 무언가 바뀌었어요. 화면을 새로 고친 뒤 다시 만들어 주세요.";
  }
  return fallback;
}

export function finalRenderFailureMessage(reason: string | null | undefined) {
  return outputFailureMessage(reason, "완성본을 만들지 못했어요.");
}

/** 자막과 CapCut 초안도 같은 실패를 낸다. 한 화면에서 어떤 칸은 이유를 말하고
 *  어떤 칸은 안 말하면 그게 더 헷갈린다 -- 기본 문구만 다르고 사유 표는 같이 쓴다. */
export function subtitleFailureMessage(reason: string | null | undefined) {
  return outputFailureMessage(reason, "자막을 만들지 못했어요.");
}

export function capcutDraftFailureMessage(reason: string | null | undefined) {
  return outputFailureMessage(reason, "CapCut 초안을 만들지 못했어요.");
}

/** 가로세로 변형본(`VariantOutputCard`)이 실패했을 때. 표에 없는 코드가 와도
 *  코드를 그대로 찍지 않고, 완성본/자막/CapCut 초안과 같은 방식(모르는
 *  코드는 일반화된 안내 문장)을 따른다 -- task-3-brief.md. */
export function variantRenderFailureMessage(reason: string | null | undefined) {
  return outputFailureMessage(reason, "이 출력을 만들지 못했어요.");
}
