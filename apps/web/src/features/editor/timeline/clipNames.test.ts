import { describe, expect, it } from "vitest"

import { clipContentLabel } from "./clipNames"

describe("타임라인 막대 이름", () => {
  it("자막 막대는 그 자막의 글자를 보여 준다", () => {
    // 예전에는 다섯 개가 전부 `자막 1`…`자막 5`였다. 어느 게 무슨 자막인지 알려면
    // 하나씩 눌러 봐야 했다.
    expect(clipContentLabel({ captionText: "요즘 영상 하나 만들려면 프로그램을 서너 개는 켜야 하죠" }))
      .toBe("요즘 영상 하나 만들려면 프로…")
  })

  it("짧은 자막은 자르지 않는다", () => {
    expect(clipContentLabel({ captionText: "여기를 보세요" })).toBe("여기를 보세요")
  })

  it("대본을 번호 목록으로 붙여 넣어도 번호만 남지 않는다", () => {
    // `sceneNames`가 같은 이유로 같은 일을 한다. 유진은 대본을 `1. …` 꼴로 쓴다.
    expect(clipContentLabel({ captionText: "1. 걷는 리듬이 하루를 정합니다" })).toBe("걷는 리듬이 하루를 정합니다")
  })

  it("도형은 화면이 쓰는 우리말 이름 그대로", () => {
    expect(clipContentLabel({ overlayType: "shape_overlay", overlayPayload: { shape: "icon_lightbulb" } })).toBe("전구")
    expect(clipContentLabel({ overlayType: "shape_overlay", overlayPayload: { shape: "icon_check" } })).toBe("체크")
  })

  it("설명 카드와 표는 얹은 글을 보여 준다", () => {
    expect(clipContentLabel({ overlayType: "explanation_card", overlayPayload: { title: "대본 한 장이면 됩니다" } }))
      .toBe("대본 한 장이면 됩니다")
    expect(clipContentLabel({ overlayType: "table_overlay", overlayPayload: { text: "자막에서 고칠 수 있는 것" } }))
      .toBe("자막에서 고칠 수 있는 것")
  })

  it("글이 없는 오버레이는 종류라도 말한다", () => {
    expect(clipContentLabel({ overlayType: "explanation_card", overlayPayload: {} })).toBe("설명 카드")
    expect(clipContentLabel({ overlayType: "table_overlay", overlayPayload: {} })).toBe("표")
    expect(clipContentLabel({ overlayType: "image_overlay", overlayPayload: {} })).toBe("그림")
  })

  it("모르는 것은 지어내지 않는다", () => {
    // 영상·음악 막대에는 이 자리에서 읽을 내용이 없다. 없는 이름을 만들어 붙이면
    // 화면이 아는 척을 하게 된다.
    expect(clipContentLabel({})).toBeNull()
    expect(clipContentLabel({ captionText: "   " })).toBeNull()
    expect(clipContentLabel({ overlayType: "무언가 새로운 것" })).toBeNull()
  })
})
