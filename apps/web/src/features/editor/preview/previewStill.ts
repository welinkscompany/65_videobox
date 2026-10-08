/** 재생기가 사라지기 전의 마지막 장면을 그림 한 장으로 잡아 둔다.
 *
 * 편집 뒤 새 미리보기가 만들어지는 동안(7.8초 영상도 44초) 재생기는 사라지고 빈
 * 상자만 남았다. 이 그림이 그 자리를 채운다. 데이터 주소(`data:`)라서 따로 풀어 줄
 * 객체 주소(`blob:`)가 없다 -- 그림을 버리면 끝이다.
 */
const MAX_STILL_WIDTH_PX = 960;

export function capturePreviewStill(video: HTMLVideoElement): string | null {
  try {
    const width = video.videoWidth;
    const height = video.videoHeight;
    if (!width || !height) return null;
    const scale = Math.min(1, MAX_STILL_WIDTH_PX / width);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const context = canvas.getContext("2d");
    if (!context) return null;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const url = canvas.toDataURL("image/jpeg", 0.7);
    return url.startsWith("data:image/jpeg") ? url : null;
  } catch {
    return null;
  }
}
