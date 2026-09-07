/** 재료를 끌어다 놓기 위한 짐표.
 *
 * 2026-08-17에 세어 보니 `apps/web/src` 전체에 `onDrop`·`draggable`이 **하나도
 * 없었다.** 자산을 넣으려면 오른쪽 목록에서 장면을 먼저 고르고 `적용`을 눌러야 했다.
 * 캡컷은 끌어다 놓는다.
 *
 * **다른 곳에서 끌어온 것을 우리 것으로 착각하지 않게** 고유한 타입을 쓴다.
 * 브라우저 밖(파일 탐색기, 다른 탭)에서 온 드래그는 이 타입을 갖지 않는다.
 */
export const ASSET_DRAG_TYPE = "application/x-videobox-asset";

export function writeAssetDrag(transfer: DataTransfer, cardId: string): void {
  transfer.setData(ASSET_DRAG_TYPE, cardId);
  // 일부 브라우저는 dragover 동안 커스텀 타입만으로는 효과를 안 준다.
  transfer.effectAllowed = "copy";
}

/** 우리가 실은 짐이면 카드 id를, 아니면 `null`을 돌려준다. */
export function readAssetDrag(transfer: DataTransfer | null): string | null {
  if (!transfer) return null;
  const id = transfer.getData(ASSET_DRAG_TYPE);
  return id ? id : null;
}

/** dragover에서 우리가 받을 짐인지. 받지 않을 것에 커서를 바꾸면 거짓말이 된다. */
export function carriesAsset(transfer: DataTransfer | null): boolean {
  if (!transfer) return false;
  return Array.from(transfer.types ?? []).includes(ASSET_DRAG_TYPE);
}
