// A tracked, deterministic 2-second H.264 MP4 generated locally with FFmpeg 8.1.1:
// ffmpeg -f lavfi -i "color=c=black:s=64x64:r=5:d=2" -c:v libx264 -g 1 -keyint_min 1 -sc_threshold 0 -pix_fmt yuv420p -movflags +faststart fixture.mp4
// Every frame is a keyframe so browser-native seek assertions are stable. The embedded fixture avoids a network dependency.
const base64 = "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";

export const validLocalMp4Fixture = Buffer.from(base64, "base64");

export async function fulfillLocalMp4WithRanges(route) {
  const range = await route.request().headerValue("range");
  if (!range) {
    await route.fulfill({ status: 200, contentType: "video/mp4", headers: { "Accept-Ranges": "bytes", "Content-Length": String(validLocalMp4Fixture.length) }, body: validLocalMp4Fixture });
    return;
  }
  const match = /^bytes=(\d+)-(\d*)$/.exec(range);
  if (!match) throw new Error(`unexpected local MP4 range: ${range}`);
  const start = Number(match[1]);
  const end = match[2] ? Math.min(Number(match[2]), validLocalMp4Fixture.length - 1) : validLocalMp4Fixture.length - 1;
  await route.fulfill({ status: 206, contentType: "video/mp4", headers: { "Accept-Ranges": "bytes", "Content-Range": `bytes ${start}-${end}/${validLocalMp4Fixture.length}`, "Content-Length": String(end - start + 1) }, body: validLocalMp4Fixture.subarray(start, end + 1) });
}
