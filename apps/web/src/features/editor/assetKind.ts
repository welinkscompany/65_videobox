/** 얹은 자산이 사진인지 영상인지 가르는 자리 -- 타임라인 막대 이름과 인스펙터
 *  절 이름이 **같은 규칙**을 써야 한다. 두 벌로 나뉘면 막대는 "영상"이라 하는데
 *  인스펙터는 "이미지"라 하는 식으로 같은 클립을 다르게 부르게 된다.
 *
 *  `clipNames.ts`(타임라인)와 `inspector/inspectorRegistry.ts`가 둘 다 이 파일을
 *  가져다 쓴다. `clipNames.ts`가 `inspectorRegistry.ts`의 `SHAPE_OVERLAY_LABELS`를
 *  이미 가져다 쓰고 있어서, 이 규칙을 `clipNames.ts`에 그대로 두고
 *  `inspectorRegistry.ts`가 가져다 쓰면 두 파일이 서로를 부르는 순환
 *  import가 된다 -- 그래서 둘 다 이 자리에서 가져간다.
 */

const VIDEO_EXTENSIONS = new Set(["mp4", "mov", "m4v", "webm", "mkv", "avi"])

/** 얹은 자산이 사진이 아니라 영상인지. 확장자가 없거나 모르면 **사진으로 본다** --
 *  모르는 것을 영상이라 부르면 기존 편집본에 이미 찍힌 `그림`/`이미지` 문구가
 *  바뀐다. */
export function isVideoAssetUri(assetUri: string | null | undefined): boolean {
  if (!assetUri) return false
  const dot = assetUri.lastIndexOf(".")
  if (dot < 0) return false
  const extension = assetUri.slice(dot + 1).toLowerCase()
  return VIDEO_EXTENSIONS.has(extension)
}
