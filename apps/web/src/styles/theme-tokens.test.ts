import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync } from "node:fs"
import { resolve } from "node:path"

const productShellCss = readFileSync(
  resolve(process.cwd(), "src/styles/product-shell.css"),
  "utf8",
)
const editorWorkbenchCss = readFileSync(
  resolve(process.cwd(), "src/styles/editor-workbench.css"),
  "utf8",
)

// Matches a literal color: 3/4/6/8-digit hex, or rgb()/rgba() with numeric
// channels. `var(--x)` and `color-mix(in srgb, var(--x) 4%, transparent)`
// do not match because they have no bare hex/rgb() token of their own.
const HARDCODED_COLOR = /#[0-9a-fA-F]{3,8}\b|rgba?\(\s*\d/g

describe("shell theme tokens", () => {
  it("has no hardcoded colors left in product-shell.css", () => {
    const matches = productShellCss.match(HARDCODED_COLOR) ?? []
    expect(matches).toEqual([])
  })

  it("drives the default button background from --primary", () => {
    const defaultButtonRule = productShellCss.match(
      /\[data-variant="default"\]\s*\{[^}]*\}/,
    )?.[0]
    expect(defaultButtonRule).toBeDefined()
    expect(defaultButtonRule).toContain("background:var(--primary)")
  })

  it("drives the default button text from --primary-foreground", () => {
    const defaultButtonRule = productShellCss.match(
      /\[data-variant="default"\]\s*\{[^}]*\}/,
    )?.[0]
    expect(defaultButtonRule).toContain("color:var(--primary-foreground)")
  })

  it("never wraps a color token in hsl() -- the tokens are complete colors", () => {
    // `--border` 같은 토큰은 `#EAEAEC` 같은 **완성색**이다. `hsl(var(--border))`는
    // `hsl(#EAEAEC)`가 되어 무효 선언이고, 브라우저는 그 속성을 통째로 버린다.
    // 이렇게 17곳(선언 13줄)이 조용히 죽어 있었다 -- 화면은 뜨지만 그 테두리·색만
    // 사라진다. 두 파일만 지키면 다음 파일에서 또 죽으니 css 전부를 훑는다.
    const sourceRoot = resolve(process.cwd(), "src")
    const cssFiles = (readdirSync(sourceRoot, { recursive: true }) as string[])
      .filter((file) => String(file).endsWith(".css"))
    expect(cssFiles.length).toBeGreaterThan(2)
    for (const file of cssFiles) {
      const css = readFileSync(resolve(sourceRoot, String(file)), "utf8")
      const matches = css.match(/hsl\(\s*var\(/g) ?? []
      expect(matches, `${file} wraps complete color tokens in hsl()`).toEqual([])
    }
  })

  it("has no hardcoded colors left in the preview shell of editor-workbench.css", () => {
    const previewShellRule = editorWorkbenchCss.match(
      /\.vb-preview-stage__media-shell\s*\{[^}]*\}/,
    )?.[0]
    expect(previewShellRule).toBeDefined()
    const matches = previewShellRule?.match(HARDCODED_COLOR) ?? []
    expect(matches).toEqual([])
    expect(previewShellRule).toContain("var(--vb-preview)")
  })
})

/** owner(2026-08-27): "위에 페이지 모두다 디자인 톤앤매너, 패키지디자인이 모두 다
 *  달라. 이것도 디자인을 통일해야지"
 *
 *  재 보니 색은 문제가 아니었다 -- `--vb-panel`과 `--card`는 **이미 같은 값**이다
 *  (`#FFFFFF`). 실제로 달라 보이게 만든 것은 **모서리**였다. 네 스타일시트에
 *  값이 **15가지**로 흩어져 있었다(0.25 ~ 1rem). 반지름 토큰은 이미 있었는데
 *  아무도 쓰지 않았다.
 *
 *  여기서 지키는 것은 **한 벌에서만 값을 꺼내 쓴다**이다. 승인된 색은 건드리지
 *  않는다(`docs/decisions/2026-08-05-dashboard-white-orange-direction.ko.md`).
 *  새 모서리 값을 쓰고 싶으면 척도를 늘리기 전에 먼저 물어라 -- 척도가 늘면
 *  다시 15가지가 된다. */
describe("모서리는 한 벌에서만 나온다", () => {
  const RAW_RADIUS = /border-radius:\s*(?!0\b|999|9999)[0-9.]+rem/g;
  const sheets = {
    "product-shell.css": productShellCss,
    "editor-workbench.css": editorWorkbenchCss,
    "library.css": readFileSync(resolve(process.cwd(), "src/features/library/library.css"), "utf8"),
    "footage.css": readFileSync(resolve(process.cwd(), "src/features/footage/footage.css"), "utf8"),
  };

  for (const [name, css] of Object.entries(sheets)) {
    it(`${name}은 모서리를 토큰으로만 정한다`, () => {
      expect(css.match(RAW_RADIUS) ?? []).toEqual([]);
    });
  }

  it("척도는 셋뿐이다 — 늘리기 전에 먼저 묻는다", () => {
    const uiSystem = readFileSync(resolve(process.cwd(), "src/ui-system.css"), "utf8");
    for (const token of ["--vb-radius-sm", "--vb-radius-md", "--vb-radius-lg"]) {
      expect(uiSystem, `${token}가 정의돼 있어야 한다`).toContain(`${token}:`);
    }
    expect(uiSystem.match(/--vb-radius-[a-z]+:/g) ?? []).toHaveLength(3);
  });
});

/** owner(2026-08-27): "모든 페이지 톤앤매너, 디자인 패키지 셋팅 마치고"
 *
 *  재 보니 간격·글자 척도는 **이미 잘 정의돼 있었다**(`--vb-space-1..8`,
 *  `--vb-text-xs..2xl`). 문제는 **쓰는 곳이 갈렸다**는 것이다.
 *
 *  | 화면 | 간격 토큰 | 간격 날값 |
 *  |---|---|---|
 *  | 껍데기 | 92 | 0 |
 *  | 편집기 | 77 | 4 |
 *  | 내 라이브러리 | **0** | **46** |
 *  | 촬영본 정리 | **0** | **41** |
 *
 *  두 화면만 척도를 아예 안 썼다. 그래서 같은 제품인데 그 둘만 따로 논다.
 *  여기서 지키는 것은 **모든 화면이 같은 척도에서 값을 꺼낸다**이다. */
describe("간격과 글자는 한 척도에서만 나온다", () => {
  const RAW_SPACE = /(?:gap|padding|margin)[a-z-]*:\s*(?!0\b)[0-9.]+rem/g;
  const RAW_TYPE = /font-size:\s*[0-9.]+rem/g;
  const screens = {
    "product-shell.css": productShellCss,
    "editor-workbench.css": editorWorkbenchCss,
    "library.css": readFileSync(resolve(process.cwd(), "src/features/library/library.css"), "utf8"),
    "footage.css": readFileSync(resolve(process.cwd(), "src/features/footage/footage.css"), "utf8"),
  };

  for (const [name, css] of Object.entries(screens)) {
    it(`${name}은 간격을 척도에서 꺼낸다`, () => {
      expect(css.match(RAW_SPACE) ?? []).toEqual([]);
    });

    it(`${name}은 글자 크기를 척도에서 꺼낸다`, () => {
      expect(css.match(RAW_TYPE) ?? []).toEqual([]);
    });
  }
});

describe("대화상자 밖에서도 단추가 브라우저 기본 테두리로 새지 않는다", () => {
  // 2026-09-04 실측: Radix Dialog/Popover는 `document.body`의 직계 자식으로
  // 포털되어 `.vb-product-shell` 조상이 없다. `ghost`·`secondary`·
  // `destructive`·`link`는 그 조상에 건 border 리셋이 아예 없어서, "유진에게
  // 제목 추천받기" 목록을 열면 브라우저 기본 2px outset 테두리와 회색
  // 배경이 그대로 보였다. `:where(...)`로 특정도 0인 백스톱을 셸 밖에도
  // 두어 고쳤다 -- `.vb-editor-assets__tab` 같은 기존 테두리 스타일은
  // 특정도가 더 높아 그대로 이긴다(product-shell.css의 관련 주석 참고).
  const VARIANTS = ["default", "outline", "ghost", "secondary", "destructive", "link"] as const;

  it("여섯 변형 전부 :where() 백스톱이 border:0을 건다", () => {
    for (const variant of VARIANTS) {
      const pattern = new RegExp(
        `:where\\([^)]*\\[data-variant="${variant}"\\][^)]*\\)\\s*\\{[^}]*border:\\s*0`,
      );
      expect(productShellCss, `${variant} 변형에 :where() 백스톱이 없다`).toMatch(pattern);
    }
  });

  it("그 백스톱 규칙은 .vb-product-shell 조상을 요구하지 않는다", () => {
    // `:where(...)` 앞에 `.vb-product-shell`이 붙으면 포털 밖(대화상자 등)에는
    // 다시 안 닿는다 -- 이번에 고친 결함이 그대로 되돌아온다.
    const whereRules = productShellCss.match(/[^\n{}]*:where\([^)]*data-variant[^)]*\)[^{]*\{[^}]*\}/g) ?? [];
    expect(whereRules.length).toBeGreaterThan(0);
    for (const rule of whereRules) {
      expect(rule, `${rule} 앞에 .vb-product-shell 조상 스코프가 있다`).not.toMatch(/\.vb-product-shell\s+:where/);
    }
  });
});

describe("실행 취소·자르기 도구 여섯 개가 다닥다닥 붙지 않는다", () => {
  // 2026-09-04 실측: `.vb-timeline-edit-toolbar`(실행 취소·다시 실행·나누기·
  // 앞과 붙이기·빼기·다음 장면에도)에 CSS가 하나도 없어서 아이콘 단추 여섯
  // 개가 간격 0px로 붙어 있었다. 아이콘만 있는 단추라 글자 단추와 달리
  // 안쪽 여백이 시각적 틈을 만들어 주지 않는다 -- 어디까지가 한 단추인지
  // 구분이 안 됐다. 옆에 있는 확대·축소 묶음(`vb-editor-workbench__timeline-zoom`)과
  // 같은 무늬(`inline-flex` + 척도 간격)를 준다.
  it(".vb-timeline-edit-toolbar가 flex와 척도 간격을 건다", () => {
    const rule = editorWorkbenchCss.match(/\.vb-timeline-edit-toolbar\s*\{[^}]*\}/)?.[0];
    expect(rule, ".vb-timeline-edit-toolbar 규칙을 못 찾았다").toBeDefined();
    expect(rule).toMatch(/display:\s*(inline-)?flex/);
    expect(rule).toMatch(/gap:\s*var\(--vb-space-\d\)/);
  });
});

describe("완성본 아래 두 묶음이 다닥다닥 붙지 않는다", () => {
  // 2026-09-04 실측(`my-project`에 실제로 완성본을 구워 놓고 잼): 완성본이
  // 있어야만 나오는 두 묶음(`.vb-final-verdict`·`.vb-final-format`)에 CSS가
  // 하나도 없었다. 둘 다 그냥 `display:block`으로 떨어져 자식이 세로로 쌓이는데
  // 사이 간격이 **0px**이었다 -- 좋아요(y 2422, 높이 36)와 아쉬워요(y 2458)가
  // 정확히 맞닿아 있었다. 어제 고친 `.vb-timeline-edit-toolbar`와 같은 결함이다.
  it(".vb-final-verdict가 세로 묶음과 척도 간격을 건다", () => {
    const rule = productShellCss.match(/\.vb-final-verdict[^{}]*\{[^}]*\}/)?.[0]
    expect(rule, ".vb-final-verdict 규칙을 못 찾았다").toBeDefined()
    expect(rule).toMatch(/display:\s*(inline-)?flex|display:\s*grid/)
    expect(rule).toMatch(/gap:\s*var\(--vb-space-\d\)/)
  })

  it(".vb-final-format이 세로 묶음과 척도 간격을 건다", () => {
    const rule = productShellCss.match(/\.vb-final-format[^{}]*\{[^}]*\}/)?.[0]
    expect(rule, ".vb-final-format 규칙을 못 찾았다").toBeDefined()
    expect(rule).toMatch(/display:\s*(inline-)?flex|display:\s*grid/)
    expect(rule).toMatch(/gap:\s*var\(--vb-space-\d\)/)
  })

  // 같은 자리에서 잰 별개의 결함: 포맷 이름 입력칸이 제 칸을 **26px 넘어갔다**.
  // 이 빌드는 Tailwind Preflight를 안 쓰므로 `box-sizing`이 문서 전체에서
  // `content-box`였다 -- shadcn `Input`의 `w-full`(100% = 229.8px)에 좌우 안쪽
  // 여백 24px와 테두리 2px가 그대로 더해져 255.8px가 됐다(칸은 230px).
  // owner가 2026-09-04에 전역 `border-box` 도입을 선택했다. 그 규칙이 사라지면
  // 74곳의 `Input`/`Textarea`가 다시 제 칸을 넘치므로 여기서 지킨다.
  it("문서 전체가 border-box로 잰다", () => {
    const uiSystemCss = readFileSync(resolve(process.cwd(), "src/ui-system.css"), "utf8")
    const rule = uiSystemCss.match(/\*,\s*::before,\s*::after\s*\{[^}]*\}/)?.[0]
    expect(rule, "전역 box-sizing 규칙을 못 찾았다").toBeDefined()
    expect(rule).toMatch(/box-sizing:\s*border-box/)
  })
})

describe("글자·단추 척도를 캡컷 실측값에 맞춘다", () => {
  // 2026-09-04, owner 승인(`decisions/2026-09-04-capcut-shell-with-my-assets.ko.md`).
  // 캡컷 편집기를 실제로 열어 재 보니 기준 12px에 본문 14px·설명 12px·띠 라벨
  // 10px이었고, 버튼은 **15개가 정확히 32px**이었다. 우리는 기준 16px에 버튼이
  // 28·29·32·36·52로 뒤섞여 있었다 -- owner가 "글자가 커서 버튼이 다 커지고
  // 어거지로 우겨넣게 된다"고 한 게 이 차이다.
  //
  // **`:root`의 font-size는 건드리지 않는다.** 척도가 rem이라 기준을 12px로
  // 내리면 `--vb-space-*`와 Tailwind `--spacing`까지 25% 줄어든다. 캡컷은 기준만
  // 12px이고 본문은 14px이라 그 방식이 아니다. 척도 자체를 캡컷 픽셀값에 맞춘다.
  const uiSystemCss = readFileSync(resolve(process.cwd(), "src/ui-system.css"), "utf8")
  const scale: ReadonlyArray<readonly [string, string]> = [
    ["--vb-text-xs", "0.625rem"],  // 10px — 세로 띠 라벨·배지
    ["--vb-text-sm", "0.75rem"],   // 12px — 설명·메타·격자 라벨
    ["--vb-text-md", "0.875rem"],  // 14px — 본문·항목 이름 (캡컷에서 제일 많음)
    ["--vb-text-lg", "1rem"],      // 16px — 패널 제목
    ["--vb-text-xl", "1.25rem"],   // 20px — 구역 제목
    ["--vb-text-2xl", "1.75rem"],  // 28px — 화면 제목
    ["--vb-text-3xl", "2.5rem"],   // 40px — 홍보 문구
  ]

  for (const [token, value] of scale) {
    it(`${token}가 ${value}다`, () => {
      // 정규식 대신 그대로 찾는다 — 값에 `.`이 있어 escape가 헷갈린다.
      expect(uiSystemCss).toContain(token + ": " + value + ";")
    })
  }

  it("기준 글자를 rem 척도째로 줄이지 않는다", () => {
    // `:root { font-size: 12px }`를 넣으면 여백까지 딸려 줄어든다.
    expect(uiSystemCss).not.toMatch(/:root\s*\{[^}]*font-size:\s*12px/)
  })

  it("화면 기본 글자가 본문 척도(14px)다", () => {
    const rule = productShellCss.match(/\.vb-product-shell\s*\{[^}]*\}/)?.[0]
    expect(rule, ".vb-product-shell 규칙을 못 찾았다").toBeDefined()
    expect(rule).toMatch(/font-size:\s*var\(--vb-text-md\)/)
  })

  it("단추 높이가 32px 하나로 통일된다", () => {
    // 캡컷은 15개가 정확히 32였다. shadcn `h-9`(36px)를 이겨야 하므로
    // `.vb-product-shell [data-slot=button]`(0,2,0)로 건다.
    const rule = productShellCss.match(/\.vb-product-shell \[data-slot=button\]\s*\{[^}]*height:\s*32px[^}]*\}/)
    expect(rule, "단추 높이 32px 규칙을 못 찾았다").not.toBeNull()
  })
})
