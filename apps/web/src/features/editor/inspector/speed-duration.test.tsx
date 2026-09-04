import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

import { rippleDisplayDurationSec } from "./rippleDuration"

const inspector = readFileSync(resolve(process.cwd(), "src/features/editor/inspector/InspectorControls.tsx"), "utf8")

/** **한 번 틀린 자리다(2026-09-04 코드리뷰가 잡음).**
 *
 *  owner 지시("속도는 캡컷이랑 동일하게")를 받고 인스펙터 `속도` 칸 아래에
 *  `장면 길이 N초`를 붙였는데 **틀린 숫자였다.** 그 칸은
 *  `media_controls.speed`이고, 엔진에서 그 값이 하는 일은 **원본을 얼마나
 *  먹는가**이지 장면 슬롯이 아니다 -- `composition_plan.py:838`이
 *  `source_out = source_in + (end - start) * speed`로 계산하고 `end - start`는
 *  그대로 둔다. 2배속을 걸면 같은 4초 자리에 원본 8초를 밀어 넣는 것이지
 *  장면이 2초가 되는 게 아니다.
 *
 *  더 나쁜 것은 **실기계 검증도 통과한 것처럼 보였다**는 점이다. 브라우저에서
 *  2.5초→1.3초가 바뀌는 걸 봤는데, 그건 내 공식이 다시 계산된 것이지 저장된
 *  장면이 짧아진 게 아니었다. 내 손으로 만든 숫자가 내 가정을 확인해 줬다.
 *
 *  장면 길이를 실제로 바꾸는 것은 `set_segment_ripple_playback_rate`이고
 *  화면에서는 `RightDock`의 `장면 길이` 단추 셋이다. 표시는 그쪽에만 둔다. */
describe("장면 길이 표시는 길이를 실제로 바꾸는 자리에만 둔다", () => {
  it("인스펙터 속도 칸은 장면 길이를 말하지 않는다", () => {
    // 이 칸은 `media_controls.speed`라 장면 슬롯을 안 바꾼다.
    expect(inspector).not.toMatch(/장면 길이 \$\{/)
    expect(inspector).not.toContain("speedAdjustedDurationSec")
  })
})

/** 리플 배속이 장면을 몇 초로 만드는지 계산한다.
 *
 *  **`endSec - startSec`를 그냥 나누면 안 된다.** 그 값은 이미 지금 배속이
 *  걸린 **표시 길이**(`원본 / 지금배속`)다. 원본으로 되돌린 뒤 새 배속으로
 *  나눠야 한다 -- 지금 배속이 1인 장면에서는 우연히 같은 값이 나와서
 *  처음엔 이 차이를 못 봤다. */
describe("리플 배속이 만드는 장면 길이", () => {
  it("지금 배속이 1이면 표시 길이를 그대로 나눈다", () => {
    expect(rippleDisplayDurationSec({ displayedSec: 5, currentRate: 1, nextRate: 2 })).toBeCloseTo(2.5)
  })

  it("이미 배속이 걸린 장면은 원본으로 되돌린 뒤 나눈다", () => {
    // 표시 2.5초 = 원본 5초를 2배속으로 본 것. 여기서 1배속으로 되돌리면 5초다.
    expect(rippleDisplayDurationSec({ displayedSec: 2.5, currentRate: 2, nextRate: 1 })).toBeCloseTo(5)
    // 2배속 -> 1.5배속이면 원본 5초 / 1.5.
    expect(rippleDisplayDurationSec({ displayedSec: 2.5, currentRate: 2, nextRate: 1.5 })).toBeCloseTo(3.333, 2)
  })

  it("말이 안 되는 값에는 답하지 않는다", () => {
    expect(rippleDisplayDurationSec({ displayedSec: 0, currentRate: 1, nextRate: 2 })).toBeNull()
    expect(rippleDisplayDurationSec({ displayedSec: 5, currentRate: 1, nextRate: 0 })).toBeNull()
  })
})
