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
