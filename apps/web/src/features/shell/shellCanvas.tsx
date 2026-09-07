import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

/** 지금 만들고 있는 화면의 크기. 띠는 이걸 **말하기만** 한다.
 *
 *  캡컷 위 툴바에는 화면 비율을 **고르는** 자리가 있다. 우리에겐 그 자리가 없다 --
 *  비율은 초안을 만들 때 한 번 정해지고(`AtomicDraftBundleCreateRequest.orientation`,
 *  기획 화면의 `숏폼(세로)으로 만들기` 체크), 그 뒤로 마스터 편집본의 비율을 바꾸는
 *  길은 서버에 아예 없다. 그래서 띠에 고르는 단추를 놓으면 **없는 기능의 자리를
 *  흉내 내는 것**이 된다 -- 익숙해서 쉬운 게 아니라 익숙해서 더 헷갈린다
 *  (`docs/decisions/2026-08-21-capcut-shell-layout.ko.md`).
 *
 *  대신 **사실만** 올린다. 지금 이 초안이 어떤 모양으로 나오는지는 owner가 늘
 *  알아야 하는 값이고, 그건 우리가 실제로 하는 일이다. */
export type ShellCanvas = Readonly<{ width: number; height: number }>;

const CanvasContext = createContext<ShellCanvas | null>(null);
const PublishContext = createContext<((canvas: ShellCanvas | null) => void) | null>(null);

export function ShellCanvasProvider({ children }: { children: ReactNode }) {
  const [canvas, setCanvas] = useState<ShellCanvas | null>(null);
  return (
    <PublishContext.Provider value={setCanvas}>
      <CanvasContext.Provider value={canvas}>{children}</CanvasContext.Provider>
    </PublishContext.Provider>
  );
}

export function useShellCanvas(): ShellCanvas | null {
  return useContext(CanvasContext);
}

/** 화면이 아는 비율을 띠에 알린다.
 *
 *  **떠날 때 지우는 것이 핵심이다.** 안 지우면 편집기를 나와 내 라이브러리로 가도
 *  아까 그 초안의 비율이 띠에 남아, 띠가 지금 화면과 무관한 사실을 말하게 된다.
 *
 *  제공자가 없으면(단위 테스트에서 화면만 따로 그릴 때) 조용히 아무것도 안 한다 --
 *  화면이 껍데기 없이도 그려져야 하는 것은 이 저장소의 기존 성질이다. */
export function usePublishShellCanvas(canvas: ShellCanvas | null | undefined): void {
  const publish = useContext(PublishContext);
  const width = canvas?.width ?? null;
  const height = canvas?.height ?? null;
  useEffect(() => {
    if (!publish) return;
    publish(width === null || height === null ? null : { width, height });
    return () => publish(null);
  }, [publish, width, height]);
}

function greatestCommonDivisor(a: number, b: number): number {
  return b === 0 ? a : greatestCommonDivisor(b, a % b);
}

/** `1920x1080` → `가로 16:9`. 값이 없거나 말이 안 되면 **아무것도 말하지 않는다.**
 *
 *  비율은 폭·높이에서 직접 줄여서 만든다. `가로면 16:9`라고 못박아 두면 그렇지 않은
 *  옛 초안에서 띠가 틀린 값을 자신 있게 적는다. */
export function shellCanvasLabel(canvas: ShellCanvas | null | undefined): string | null {
  if (!canvas) return null;
  const { width, height } = canvas;
  if (!Number.isFinite(width) || !Number.isFinite(height)) return null;
  if (!Number.isInteger(width) || !Number.isInteger(height)) return null;
  if (width <= 0 || height <= 0) return null;
  const divisor = greatestCommonDivisor(width, height);
  const shape = width > height ? "가로" : width < height ? "세로" : "정사각";
  return `${shape} ${width / divisor}:${height / divisor}`;
}
