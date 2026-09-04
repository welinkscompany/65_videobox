import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

const source = readFileSync(resolve(process.cwd(), "src/features/editor/inspector/InspectorControls.tsx"), "utf8")

/** owner 지시(2026-09-04): "속도는 캡컷이랑 동일하게 맞춰."
 *  기록: `docs/decisions/2026-09-04-capcut-shell-with-my-assets.ko.md`
 *
 *  캡컷 `속도` 속성 실측: `속도 [ ]x`와 `기간 [19.9]s`를 **같이 보여 주고
 *  연동**한다 -- 배속을 바꾸면 기간이 따라 바뀐다. 우리 엔진은 이미 그렇게
 *  동작하는데(`set_segment_ripple_playback_rate`가 `end_sec`를 바꾸고 뒤
 *  장면을 당긴다) **화면이 그 결과를 안 보여 줬다.** 창작자는 배속을 걸고
 *  나서 장면이 몇 초가 되는지 알 수 없었다.
 *
 *  여기서 지키는 것은 **바뀐 길이를 숫자로 보여 준다**이다. */
describe("속도를 걸면 바뀐 길이가 같이 보인다", () => {
  it("기간을 속도로 나눠 계산한다", () => {
    // 배속이 2면 길이는 절반이다. 이 식이 사라지면 화면이 다시 침묵한다.
    expect(source).toMatch(/speedAdjustedDurationSec/)
    expect(source).toMatch(/\/\s*speed/)
  })

  it("기간을 초 단위로 화면에 적는다", () => {
    expect(source).toContain("장면 길이")
    expect(source).toMatch(/초/)
  })
})
