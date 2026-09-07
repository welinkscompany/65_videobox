import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"

import * as apiModule from "../../api"
import { EditorAssetBrowser } from "../editor/assets/EditorAssetBrowser"

afterEach(() => { cleanup(); vi.restoreAllMocks() })

/** owner 지적(2026-09-04):
 *  > "캣컵은 드래그앤 드롭도 다 되는데, 우리는 그것도 아무것도 안되고"
 *
 *  확인해 보니 **자료 카드를 타임라인으로 끄는 것은 있었고**(`TimelineDock`),
 *  없던 것은 **탐색기에서 파일을 끌어다 놓는 것**이었다 -- `dataTransfer.files`를
 *  읽는 자리가 저장소 전체에 0곳이었다. owner가 캡컷에서 하던 동작이 그것이다.
 *
 *  올리는 절차(`ingestFilesIntoProject`)는 이미 있었다. 없던 것은 부르는
 *  자리뿐이라 새 기능이 아니라 배선이다. */
describe("탐색기에서 파일을 끌어다 놓으면 올라간다", () => {
  function dropFiles(target: Element, files: readonly File[]): void {
    fireEvent.drop(target, { dataTransfer: { files, types: ["Files"] } })
  }

  it("떨어뜨린 파일을 프로젝트로 가져온다", async () => {
    const ingest = vi.spyOn(apiModule.api, "ingestLibraryAssets").mockResolvedValue({
      items: [{ library_asset_id: "lib-1", state: "ready" }],
    } as never)
    const materialize = vi.spyOn(apiModule.api, "materializeLibraryAsset").mockResolvedValue({} as never)

    render(<EditorAssetBrowser cards={[]} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} projectId="project-a" />)

    const zone = document.querySelector(".vb-editor-assets")
    if (!zone) throw new Error("미디어 패널을 찾지 못했다")
    dropFiles(zone, [new File(["x"], "a.mp4", { type: "video/mp4" })])

    await waitFor(() => expect(ingest).toHaveBeenCalled())
    await waitFor(() => expect(materialize).toHaveBeenCalledWith("lib-1", "project-a"))
  })

  it("파일이 아닌 것을 끌면 아무 일도 하지 않는다", async () => {
    // 타임라인으로 자산 카드를 끄는 기존 동작(`carriesAsset`)과 부딪히면 안 된다.
    const ingest = vi.spyOn(apiModule.api, "ingestLibraryAssets").mockResolvedValue({ items: [] } as never)
    render(<EditorAssetBrowser cards={[]} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} projectId="project-a" />)

    const zone = document.querySelector(".vb-editor-assets")!
    fireEvent.drop(zone, { dataTransfer: { files: [], types: ["text/plain"] } })

    expect(ingest).not.toHaveBeenCalled()
  })
})

/** **두 번째 드롭이 영구 실패하던 문제(2026-09-04 코드리뷰가 잡음).**
 *
 *  처음 쓴 idempotency 키가 `drop-${projectId}-${files.length}`였다 -- 같은
 *  프로젝트에 **같은 개수**를 다시 떨어뜨리면 키가 똑같다. 서버는 같은 키에 다른
 *  바이트가 오면 거부한다(`tests/test_api_library_assets.py`의
 *  `test_retry_with_same_key_and_different_bytes_is_rejected`가 그 계약을 못박고
 *  있다). 그래서 `a.mp4` 하나를 올린 뒤 `b.mp4` 하나를 올리면 409가 나고,
 *  **다시 시도해도 키가 같아 영원히 실패한다.**
 *
 *  바로 옆 `AddMediaFiles`는 이 함정을 알고 `requestId` 카운터로 매번 다른 키를
 *  만든다 -- 드롭 경로만 그 규율이 빠졌다.
 *
 *  여기서 지키는 것은 **드롭마다 키가 달라진다**이다. */
describe("드롭마다 올리기 키가 달라진다", () => {
  it("같은 개수를 다시 떨어뜨려도 앞의 키를 재사용하지 않는다", async () => {
    const keys: string[] = []
    vi.spyOn(apiModule.api, "ingestLibraryAssets").mockImplementation((async (_files: unknown, _kind: unknown, key: string) => {
      keys.push(key)
      return { items: [{ library_asset_id: "lib-" + keys.length, state: "ready" }] }
    }) as never)
    vi.spyOn(apiModule.api, "materializeLibraryAsset").mockResolvedValue({} as never)

    render(<EditorAssetBrowser cards={[]} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} projectId="project-a" />)
    const zone = document.querySelector(".vb-editor-assets")!

    fireEvent.drop(zone, { dataTransfer: { files: [new File(["a"], "a.mp4")], types: ["Files"] } })
    await waitFor(() => expect(keys).toHaveLength(1))
    fireEvent.drop(zone, { dataTransfer: { files: [new File(["b"], "b.mp4")], types: ["Files"] } })
    await waitFor(() => expect(keys).toHaveLength(2))

    expect(keys[0]).not.toBe(keys[1])
  })
})

/** **되는 걸 알 수 있어야 한다(2026-09-04 갭검증이 잡음).**
 *
 *  드롭은 동작하는데 화면에 **시각 단서가 0개**였다 -- 점선도, 안내 문구도,
 *  끌어오는 중 강조도 없었다. owner 지적이 "드래그앤 드롭도 다 되는데 우리는
 *  아무것도 안된다"였던 만큼, **보이지 않으면 여전히 안 된다고 느낀다.**
 *  자료실 쪽(`AssetIngestDropzone`)에는 안내 문구가 있는데 편집기만 없었다.
 *
 *  여기서 지키는 것은 **끌어오면 받는다고 말한다**이다. */
describe("파일을 끌어오면 받는다고 보여 준다", () => {
  it("파일을 끌면 패널이 받을 자리임을 표시한다", () => {
    render(<EditorAssetBrowser cards={[]} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} projectId="project-a" />)
    const zone = document.querySelector(".vb-editor-assets")!

    expect(zone.getAttribute("data-dropping")).not.toBe("true")
    fireEvent.dragOver(zone, { dataTransfer: { files: [], types: ["Files"] } })
    expect(zone.getAttribute("data-dropping"), "끌어오는 중인데 표시가 없다").toBe("true")

    fireEvent.dragLeave(zone, { dataTransfer: { files: [], types: ["Files"] } })
    expect(zone.getAttribute("data-dropping")).not.toBe("true")
  })

  it("자산 카드를 끌 때는 표시하지 않는다", () => {
    // 타임라인으로 카드를 끄는 기존 동작과 섞이면 안 된다.
    render(<EditorAssetBrowser cards={[]} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} projectId="project-a" />)
    const zone = document.querySelector(".vb-editor-assets")!
    fireEvent.dragOver(zone, { dataTransfer: { files: [], types: ["application/x-videobox-asset"] } })
    expect(zone.getAttribute("data-dropping")).not.toBe("true")
  })
})
